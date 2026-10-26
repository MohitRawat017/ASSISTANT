"""Deterministic Wave 2 reliability-contract tests."""

import types

import pytest

from src.utils.reliability import (
    ToolResult,
    classify_exception,
    execute_google_read,
    execute_google_write,
    execute_with_retry,
)


class _FakeRequest:
    def __init__(self, value=None, error=None, calls=None):
        self.value = value
        self.error = error
        self.calls = calls if calls is not None else []

    def execute(self, *, num_retries):
        self.calls.append(num_retries)
        if self.error:
            raise self.error
        return self.value or {}


class _FakeGmailMessages:
    def __init__(self, request):
        self.request = request

    def send(self, **kwargs):
        self.kwargs = kwargs
        return self.request


class _FakeGmailUsers:
    def __init__(self, messages):
        self._messages = messages

    def messages(self):
        return self._messages


class _FakeGmailService:
    def __init__(self, request):
        self.messages_api = _FakeGmailMessages(request)
        self.users_api = _FakeGmailUsers(self.messages_api)

    def users(self):
        return self.users_api


class _FakeCalendarEvents:
    def __init__(self, request):
        self.request = request

    def insert(self, **kwargs):
        self.kwargs = kwargs
        return self.request


class _FakeCalendarService:
    def __init__(self, request):
        self.events_api = _FakeCalendarEvents(request)

    def events(self):
        return self.events_api


class _FakeTasksCollection:
    def __init__(self, request):
        self.request = request

    def insert(self, **kwargs):
        self.kwargs = kwargs
        return self.request


class _FakeTasksService:
    def __init__(self, request):
        self.tasks_api = _FakeTasksCollection(request)

    def tasks(self):
        return self.tasks_api


@pytest.mark.safe_smoke
def test_result_envelope_invariants_and_legacy_fields():
    result = ToolResult(True, operation_id="op-1", provider="test", attempts=1, value=3)
    assert result.ok is True
    assert result["success"] is True
    assert result.code == "ok"
    assert result.unknown_outcome is False
    assert result.retryable is False
    assert result.value == 3

    with pytest.raises(ValueError):
        ToolResult(False, code="unknown_outcome", unknown_outcome=True, retryable=True)


@pytest.mark.safe_smoke
def test_retry_limit_backoff_and_one_operation_id():
    calls = []
    sleeps = []

    def operation():
        calls.append(True)
        raise TimeoutError("temporary")

    result = execute_with_retry(
        operation,
        provider="test",
        operation_id="stable-op",
        max_retries=2,
        safe_to_retry=True,
        sleeper=sleeps.append,
        backoff_base=0.1,
    )

    assert result.code == "timeout"
    assert result.attempts == 3
    assert len(calls) == 3
    assert sleeps == [0.1, 0.2]
    assert result.operation_id == "stable-op"


@pytest.mark.safe_smoke
def test_side_effect_is_not_retried_and_dispatched_transient_is_unknown():
    calls = []

    def operation():
        calls.append(True)
        raise ConnectionError("connection dropped")

    result = execute_with_retry(
        operation, provider="test", max_retries=5, safe_to_retry=False
    )
    assert len(calls) == 1
    assert result.unknown_outcome is True
    assert result.retryable is False

    classified = classify_exception(TimeoutError("late response"), dispatched=True)
    assert classified["code"] == "unknown_outcome"
    assert classified["unknown_outcome"] is True
    assert classified["retryable"] is False

    class ServerFailure(Exception):
        status = 503

    server = classify_exception(ServerFailure("provider response"), dispatched=True)
    assert server["code"] == "unknown_outcome"
    assert server["unknown_outcome"] is True


@pytest.mark.safe_smoke
def test_status_and_timeout_codes_before_dispatch_are_retryable_only_when_safe():
    class TooManyRequests(Exception):
        status_code = 429

    rate_limited = classify_exception(TooManyRequests("busy"))
    assert rate_limited == {
        "code": "provider_transient",
        "retryable": True,
        "unknown_outcome": False,
        "hint": "The provider is temporarily unavailable; try again later.",
    }
    timeout = classify_exception(TimeoutError("deadline"))
    assert timeout["code"] == "timeout"
    assert timeout["retryable"] is True


@pytest.mark.safe_smoke
def test_google_read_retries_transient_request_without_raw_error():
    attempts = []
    sleeps = []

    class Request:
        def execute(self, *, num_retries):
            attempts.append(num_retries)
            if len(attempts) == 1:
                raise TimeoutError("secret-token should not be returned")
            return {"items": [1]}

    result = execute_google_read(
        lambda: Request(), max_retries=1, sleeper=sleeps.append
    )
    assert result.ok is True
    assert result.value == {"items": [1]}
    assert attempts == [0, 0]
    assert len(sleeps) == 1


@pytest.mark.safe_smoke
def test_google_write_is_exactly_once_and_unknown_after_dispatch():
    calls = []

    class Request:
        def execute(self, *, num_retries):
            calls.append(num_retries)
            raise TimeoutError("provider response lost")

    result = execute_google_write(
        lambda: Request(), provider="calendar", operation_id="write-1"
    )
    assert calls == [0]
    assert result.success is False
    assert result.code == "unknown_outcome"
    assert result.unknown_outcome is True
    assert result.retryable is False
    assert result.operation_id == "write-1"


@pytest.mark.safe_smoke
def test_ollama_vision_timeout_is_configured(monkeypatch):
    calls = {}

    class Client:
        def __init__(self, **kwargs):
            calls["client"] = kwargs

        def chat(self, **kwargs):
            return {"message": {"content": "ok"}}

    monkeypatch.setitem(__import__("sys").modules, "ollama", types.SimpleNamespace(Client=Client))
    from src.utils.config import Config
    from src.vision.screen_vision import _chat_with_ollama_vision

    monkeypatch.setattr(Config, "VISION_TIMEOUT", 7.5)
    monkeypatch.setattr(Config, "VISION_MAX_RETRIES", 0)
    monkeypatch.setattr(Config, "VISION_MODEL_HOST", "http://vision.test")
    assert _chat_with_ollama_vision([{"role": "user", "content": "x"}]) == "ok"
    assert calls["client"]["timeout"] == 7.5


@pytest.mark.safe_smoke
def test_nvidia_vision_timeout_is_forwarded_when_supported(monkeypatch):
    calls = {}

    class HumanMessage:
        def __init__(self, content):
            self.content = content

    class ChatNVIDIA:
        def __init__(self, **kwargs):
            calls["client"] = kwargs

        def invoke(self, messages):
            return types.SimpleNamespace(content="ok")

    import sys
    core = types.ModuleType("langchain_core")
    messages = types.ModuleType("langchain_core.messages")
    messages.HumanMessage = HumanMessage
    nvidia = types.ModuleType("langchain_nvidia_ai_endpoints")
    nvidia.ChatNVIDIA = ChatNVIDIA
    monkeypatch.setitem(sys.modules, "langchain_core", core)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", messages)
    monkeypatch.setitem(sys.modules, "langchain_nvidia_ai_endpoints", nvidia)

    from src.utils.config import Config
    from src.vision.screen_vision import _chat_with_nvidia_vision

    monkeypatch.setattr(Config, "NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setattr(Config, "VISION_TIMEOUT", 8.0)
    monkeypatch.setattr(Config, "VISION_MAX_RETRIES", 0)
    _chat_with_nvidia_vision([{"role": "user", "content": "x"}])
    assert calls["client"]["timeout"] == 8.0


@pytest.mark.safe_smoke
def test_gmail_send_adapter_uses_exactly_once_write_boundary(monkeypatch):
    from src.tools.google import gmail_tools

    calls = []
    service = _FakeGmailService(_FakeRequest({"id": "gmail-1"}, calls=calls))
    monkeypatch.setattr(gmail_tools, "get_gmail_service", lambda: service)

    result = gmail_tools.send_gmail("user@example.test", "Subject", "Body")

    assert result.ok is True
    assert result["message_id"] == "gmail-1"
    assert calls == [0]
    assert service.messages_api.kwargs["userId"] == "me"


@pytest.mark.safe_smoke
def test_calendar_create_adapter_marks_post_dispatch_timeout_unknown(monkeypatch):
    from src.tools.google import calendar_tools

    calls = []
    service = _FakeCalendarService(
        _FakeRequest(error=TimeoutError("provider response lost"), calls=calls)
    )
    monkeypatch.setattr(calendar_tools, "get_calendar_service", lambda: service)

    result = calendar_tools.create_calendar_event(
        "Meeting", "2026-10-27T10:00:00", "2026-10-27T11:00:00"
    )

    assert result.unknown_outcome is True
    assert result.retryable is False
    assert result.operation_id
    assert calls == [0]


@pytest.mark.safe_smoke
def test_tasks_add_adapter_returns_task_id_without_retry(monkeypatch):
    from src.tools.google import tasks_tools

    calls = []
    service = _FakeTasksService(_FakeRequest({"id": "task-1"}, calls=calls))
    monkeypatch.setattr(tasks_tools, "get_tasks_service", lambda: service)

    result = tasks_tools.add_google_task("Buy milk", notes="2 litres")

    assert result.ok is True
    assert result["task_id"] == "task-1"
    assert calls == [0]
    assert service.tasks_api.kwargs["body"] == {"title": "Buy milk", "notes": "2 litres"}
