"""
Tests for trace privacy and bounded retention (R10 / ADR 0001).

Covers:
- src/utils/redaction.py: key-marker redaction, secret value patterns,
  truncation, primitive preservation
- src/graph/agent.py: JSONL trace redaction at the write choke point and
  trace file pruning
- src/utils/config.py: DEBUG_MODE default flip (subprocess probe so the
  import-time env read is tested for real)
- src/tools/pc_automation/screenshot.py: screenshot retention cap
- src/services/send_reminder.py: rotating handlers for both log files

Deterministic: no network, no desktop automation, no real credentials —
every secret below is an obviously fake value ("hunter2", "sk-fake...").
src.graph.agent is imported with real langgraph/langchain packages (fetched
by the test runner) while the Windows/desktop-only libraries it transitively
imports are stubbed, following tests/test_registry_smoke.py.
"""

import json
import logging
import os
import subprocess
import sys
import time
import types
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


# ── Redaction unit tests ──────────────────────────────────────────────────

class TestRedactString:
    def test_bearer_token_scrubbed(self):
        from src.utils.redaction import redact_string

        out = redact_string("auth ok: Bearer abc123.def456ghi", 2000)
        assert "abc123.def456ghi" not in out
        assert "[REDACTED]" in out
        assert "auth ok:" in out

    def test_sk_style_key_scrubbed(self):
        from src.utils.redaction import redact_string

        out = redact_string("here is your key sk-fake1234567890abcd ok", 2000)
        assert "sk-fake1234567890abcd" not in out
        assert "[REDACTED]" in out

    @pytest.mark.parametrize("value", [
        "GMAIL_APP_PASSWORD=hunter2",
        "NVIDIA_API_KEY=nvapi-example-secret",
        "github_pat_123456789012345678901234567890",
        # Assembled at runtime so the fake value is not stored as a literal.
        "xox" + "b-1234567890-abcdefghijklmnop",
    ])
    def test_common_environment_and_provider_secrets_scrubbed(self, value):
        from src.utils.redaction import redact_string

        assert value.split("=", 1)[-1] not in redact_string(value, 2000)

    def test_sensitive_key_value_assignment_scrubbed_keeps_key(self):
        from src.utils.redaction import redact_string

        out = redact_string('set my "password": "hunter2" please', 2000)
        assert "hunter2" not in out
        assert "[REDACTED]" in out
        assert "password" in out  # key text kept so the record stays explainable

    def test_serialized_personal_fields_are_scrubbed(self):
        from src.utils.redaction import redact_string

        redacted = redact_string("{'body': 'private text', 'to': 'person@example.com'}", 1000)
        assert "private text" not in redacted
        assert "person@example.com" not in redacted

    def test_normal_text_not_mangled(self):
        from src.utils.redaction import redact_string

        text = "open chrome and search for github repositories"
        assert redact_string(text, 2000) == text

    def test_long_string_truncated_with_explicit_marker(self):
        from src.utils.redaction import redact_string

        long_text = "abcdefghij" * 500  # 5000 chars
        out = redact_string(long_text, 2000)
        assert out.startswith("abcdefghij")  # head preserved
        assert "…[truncated 3000 chars]" in out
        assert "abcdefghij" * 500 not in out


class TestRedactValue:
    def test_sensitive_dict_keys_redacted_at_nesting_depth(self):
        from src.utils.redaction import redact_value

        obj = {
            "retries": 3,
            "config": {
                "password": "hunter2",
                "nested": [{"api_key": "sk-fake1234567890", "note": "ok"}],
            },
        }
        out = redact_value(obj, 2000)
        assert out["retries"] == 3
        assert out["config"]["password"] == "[REDACTED]"
        assert out["config"]["nested"][0]["api_key"] == "[REDACTED]"
        assert out["config"]["nested"][0]["note"] == "ok"

    def test_non_sensitive_keys_untouched(self):
        from src.utils.redaction import redact_value

        obj = {"app_name": "chrome", "count": 2, "enabled": True, "note": None}
        assert redact_value(obj, 2000) == obj

    def test_primitives_preserved(self):
        from src.utils.redaction import redact_value

        assert redact_value(42, 10) == 42
        assert redact_value(3.14, 10) == 3.14
        assert redact_value(True, 10) is True
        assert redact_value(None, 10) is None

    def test_tuple_recursed_and_type_preserved(self):
        from src.utils.redaction import redact_value

        out = redact_value(("Bearer abc123.def456", 7), 2000)
        assert isinstance(out, tuple)
        assert "abc123.def456" not in out[0]
        assert out[1] == 7


# ── Config default flip (import-time env read → subprocess probe) ────────

def _run_config_probe(extra_env: dict) -> str:
    """Import Config in a fresh subprocess with a controlled environment.

    load_dotenv is neutralized first so a developer's local .env cannot
    influence the outcome; only the subprocess env decides.
    """
    code = (
        "import dotenv\n"
        "dotenv.load_dotenv = lambda *a, **k: None\n"
        f"import sys; sys.path.insert(0, {str(PROJECT_ROOT)!r})\n"
        "from src.utils.config import Config\n"
        "print(Config.DEBUG_MODE, Config.TRACE_RETENTION_DAYS,\n"
        "      Config.SCREENSHOT_MAX_FILES)\n"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("DEBUG_MODE", "TRACE_RETENTION_DAYS", "SCREENSHOT_MAX_FILES")
    }
    env.update(extra_env)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(PROJECT_ROOT),
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_debug_mode_defaults_false_when_env_unset():
    assert _run_config_probe({}) == "False 14 50"


def test_debug_mode_true_when_env_set_true():
    assert _run_config_probe({"DEBUG_MODE": "true"}) == "True 14 50"


# ── Agent trace redaction + pruning ───────────────────────────────────────

def _stub_module(monkeypatch, name, **attrs):
    """Insert a lightweight fake module into sys.modules."""
    module = types.ModuleType(name)
    for attr, value in attrs.items():
        setattr(module, attr, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _install_offline_stubs(monkeypatch):
    """
    Stub the desktop-only and Google libraries that wrapped_tools imports
    at module level (same pattern as tests/test_registry_smoke.py).
    langgraph / langchain-core / langchain-ollama are real, fetched by the
    test runner.
    """
    _stub_module(monkeypatch, "pyautogui")
    _stub_module(monkeypatch, "psutil")
    _stub_module(monkeypatch, "pywinauto", Desktop=type("Desktop", (), {}))

    google = _stub_module(monkeypatch, "google")
    google_auth = _stub_module(monkeypatch, "google.auth")
    google_auth.exceptions = _stub_module(
        monkeypatch,
        "google.auth.exceptions",
        RefreshError=type("RefreshError", (Exception,), {}),
    )
    google_auth.transport = _stub_module(monkeypatch, "google.auth.transport")
    google_auth.transport.requests = _stub_module(
        monkeypatch,
        "google.auth.transport.requests",
        Request=type("Request", (), {}),
    )
    google.auth = google_auth

    google_oauth2 = _stub_module(monkeypatch, "google.oauth2")
    google_oauth2.credentials = _stub_module(
        monkeypatch,
        "google.oauth2.credentials",
        Credentials=type("Credentials", (), {}),
    )
    google.oauth2 = google_oauth2

    google_auth_oauthlib = _stub_module(monkeypatch, "google_auth_oauthlib")
    google_auth_oauthlib.flow = _stub_module(
        monkeypatch,
        "google_auth_oauthlib.flow",
        InstalledAppFlow=type("InstalledAppFlow", (), {}),
    )

    googleapiclient = _stub_module(monkeypatch, "googleapiclient")
    googleapiclient.discovery = _stub_module(
        monkeypatch,
        "googleapiclient.discovery",
        build=lambda *args, **kwargs: None,
    )


@pytest.fixture
def agent_module(monkeypatch):
    """Import src.graph.agent once with offline stubs installed."""
    _install_offline_stubs(monkeypatch)
    import src.graph.agent as agent

    return agent


def test_write_trace_record_redacts_secrets_and_keeps_diagnostics(
    agent_module, monkeypatch, tmp_path
):
    from src.utils.config import Config

    monkeypatch.setattr(Config, "DEBUG_LOG_DIR", str(tmp_path))

    long_payload = "x" * 5000
    poisoned = {
        "timestamp": "2026-10-26T12:00:00",
        "source": "terminal_text",
        "thread_id": "session_test",
        "query": 'login with {"password": "hunter2"} now',
        "tool_calls": [
            {
                "name": "send_email",
                "args": {"to": "master@example.test", "password": "hunter2"},
            },
            {
                "name": "web_search",
                "args": {"query": "GET /admin Authorization: Bearer abc123.def456xyz"},
            },
        ],
        "tool_results": [{"name": "web_search", "result": long_payload}],
        "final_response": "Done. Your key was sk-fake1234567890abcd",
        "duration_s": 1.234,
        "error": None,
    }

    agent_module._write_trace_record(poisoned)

    trace_files = list(tmp_path.glob("agent_trace_*.jsonl"))
    assert len(trace_files) == 1
    raw = trace_files[0].read_text(encoding="utf-8")
    record = json.loads(raw.splitlines()[0])

    # Secrets gone
    assert "hunter2" not in raw
    assert "Bearer abc123" not in raw
    assert "sk-fake1234567890abcd" not in raw
    assert long_payload not in raw
    assert "[REDACTED]" in raw

    # Diagnostics survive
    assert record["timestamp"] == "2026-10-26T12:00:00"
    assert record["source"] == "terminal_text"
    assert record["thread_id"] == "session_test"
    assert record["duration_s"] == 1.234
    assert record["error"] is None
    assert record["tool_calls"][0]["name"] == "send_email"
    assert record["tool_calls"][0]["args"]["to"] == "[REDACTED]"
    assert record["tool_calls"][0]["args"]["password"] == "[REDACTED]"
    assert record["tool_calls"][1]["name"] == "web_search"
    assert record["tool_results"][0]["name"] == "web_search"
    assert record["tool_results"][0]["result"].startswith("xxx")  # head kept
    assert "[truncated" in record["tool_results"][0]["result"]


def test_write_trace_record_prunes_old_trace_files(
    agent_module, monkeypatch, tmp_path
):
    from src.utils.config import Config

    monkeypatch.setattr(Config, "DEBUG_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(Config, "TRACE_RETENTION_DAYS", 14)

    old_dated = tmp_path / "agent_trace_20200101.jsonl"
    old_dated.write_text("{}\n", encoding="utf-8")

    unparseable_name = tmp_path / "agent_trace_not-a-date.jsonl"
    unparseable_name.write_text("{}\n", encoding="utf-8")
    ancient = time.time() - 60 * 60 * 24 * 365  # one year ago
    os.utime(unparseable_name, (ancient, ancient))  # mtime fallback path

    future_dated = tmp_path / "agent_trace_20991231.jsonl"
    future_dated.write_text("{}\n", encoding="utf-8")

    non_trace_file = tmp_path / "other.jsonl"
    non_trace_file.write_text("{}\n", encoding="utf-8")

    agent_module._write_trace_record({"timestamp": "t", "query": "hello"})

    assert not old_dated.exists()  # pruned by filename date
    assert not unparseable_name.exists()  # pruned by mtime fallback
    assert future_dated.exists()  # inside retention window
    assert non_trace_file.exists()  # not a trace file, untouched
    assert len(list(tmp_path.glob("agent_trace_*.jsonl"))) == 2  # future + today


def test_write_trace_record_rotates_active_file(agent_module, monkeypatch, tmp_path):
    from src.utils.config import Config

    monkeypatch.setattr(Config, "DEBUG_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(Config, "TRACE_MAX_BYTES", 100)
    monkeypatch.setattr(Config, "TRACE_BACKUP_COUNT", 2)

    for _ in range(4):
        agent_module._write_trace_record({"query": "x" * 80})

    base_files = list(tmp_path.glob("agent_trace_*.jsonl"))
    assert any(".1.jsonl" in path.name for path in base_files)
    assert len(base_files) <= 3


# ── Screenshot retention ──────────────────────────────────────────────────

def test_enforce_screenshot_retention_deletes_oldest_beyond_cap(
    monkeypatch, tmp_path
):
    monkeypatch.setitem(sys.modules, "pyautogui", types.SimpleNamespace())

    from src.tools.pc_automation import screenshot as screenshot_module
    from src.utils.config import Config

    monkeypatch.setattr(screenshot_module, "SCREENSHOT_DIR", str(tmp_path))
    monkeypatch.setattr(Config, "SCREENSHOT_MAX_FILES", 5)

    for i in range(10):
        path = tmp_path / f"screenshot_{i:02d}.png"
        path.write_bytes(b"png")
        os.utime(path, (1000 + i, 1000 + i))  # staggered mtimes, i is oldest

    screenshot_module.enforce_screenshot_retention()

    remaining = sorted(path.name for path in tmp_path.glob("*.png"))
    assert remaining == [f"screenshot_{i:02d}.png" for i in range(5, 10)]


def test_screenshot_filename_must_be_png_basename(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pyautogui", types.SimpleNamespace())
    from src.tools.pc_automation import screenshot as screenshot_module

    monkeypatch.setattr(screenshot_module, "SCREENSHOT_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        screenshot_module._validated_filename("../outside.png")
    with pytest.raises(ValueError):
        screenshot_module._validated_filename("capture.jpg")


# ── Reminder log rotation ─────────────────────────────────────────────────

class TestReminderLogRotation:
    def test_setup_logging_uses_rotating_file_handler(self, tmp_path, monkeypatch):
        import src.services.send_reminder as send_reminder

        monkeypatch.setattr(send_reminder, "LOG_DIR", str(tmp_path))
        send_reminder.logger.handlers.clear()
        try:
            send_reminder._setup_logging()

            file_handlers = [
                handler
                for handler in send_reminder.logger.handlers
                if isinstance(handler, logging.FileHandler)
            ]
            assert len(file_handlers) == 1
            assert isinstance(file_handlers[0], RotatingFileHandler)
            assert file_handlers[0].maxBytes == 1_000_000
            assert file_handlers[0].backupCount == 2
        finally:
            for handler in send_reminder.logger.handlers:
                handler.close()
            send_reminder.logger.handlers.clear()

    def test_log_failure_keeps_line_format_through_rotating_handler(
        self, tmp_path, monkeypatch
    ):
        import src.services.send_reminder as send_reminder

        monkeypatch.setattr(
            send_reminder, "FAILURE_LOG_PATH", str(tmp_path / "reminder_failures.log")
        )
        for handler in send_reminder._failure_logger.handlers:
            handler.close()
        send_reminder._failure_logger.handlers.clear()
        try:
            send_reminder._log_failure(
                "alarm-123", "bad\nlabel", "smtp down\nfor token=secret-value"
            )

            content = (tmp_path / "reminder_failures.log").read_text(encoding="utf-8")
            assert content.count("\n") == 1  # exactly one record line
            assert "alarm_id=alarm-123" in content
            assert "label=bad label" in content  # newline flattened
            assert "error=smtp down for token=[REDACTED]" in content
            assert content.count("\n") == 1  # error newline cannot forge a record
            assert isinstance(
                send_reminder._failure_logger.handlers[0], RotatingFileHandler
            )
            assert send_reminder._failure_logger.propagate is False
        finally:
            for handler in send_reminder._failure_logger.handlers:
                handler.close()
            send_reminder._failure_logger.handlers.clear()
