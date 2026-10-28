"""Deterministic Wave 2 R3 alarm lifecycle coverage."""

import sqlite3
import threading
import os
from datetime import datetime, timedelta

import pytest

from src.managers.alarm_manager import AlarmManager
from src.services.alarm_reconciliation import reconcile_startup
from src.services.send_reminder import process_alarm
from src.utils.reliability import ToolResult


@pytest.mark.safe_smoke
def test_migration_preserves_legacy_alarm_and_adds_lifecycle(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE alarms (id TEXT PRIMARY KEY, time TEXT NOT NULL, label TEXT, enabled BOOLEAN DEFAULT 1, notified BOOLEAN DEFAULT 1, scheduled_task_name TEXT)")
        conn.execute("INSERT INTO alarms VALUES ('old-1', '08:00', 'Old', 1, 1, 'TsuziReminder_old-1')")
    alarm = AlarmManager(str(path)).get_alarm_by_id("old-1")
    assert alarm["notified"] == 1
    assert alarm["lifecycle"] == "delivered"
    assert alarm["schedule_state"] == "scheduled"
    assert alarm["target_at"]
    assert alarm["operation_id"]


@pytest.mark.safe_smoke
def test_migration_preserves_cancelled_state(tmp_path):
    path = tmp_path / "cancelled.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE alarms (id TEXT PRIMARY KEY, time TEXT NOT NULL, label TEXT, enabled BOOLEAN DEFAULT 0, notified BOOLEAN DEFAULT 0, scheduled_task_name TEXT)")
        conn.execute("INSERT INTO alarms VALUES ('cancelled-1', '08:00', 'Cancelled', 0, 0, NULL)")
    manager = AlarmManager(str(path))
    manager._update("cancelled-1", {"lifecycle": "cancelled", "status": "cancelled"})
    migrated = AlarmManager(str(path)).get_alarm_by_id("cancelled-1")
    assert migrated["lifecycle"] == "cancelled"


@pytest.mark.safe_smoke
def test_migration_preserves_legacy_disabled_projection(tmp_path):
    path = tmp_path / "disabled.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE alarms (id TEXT PRIMARY KEY, time TEXT NOT NULL, label TEXT, enabled BOOLEAN DEFAULT 1, notified BOOLEAN DEFAULT 0, scheduled_task_name TEXT)")
        conn.execute("INSERT INTO alarms VALUES ('disabled-1', '08:00', 'Disabled', 0, 0, NULL)")
    row = AlarmManager(str(path)).get_alarm_by_id("disabled-1")
    assert row["lifecycle"] == "disabled"
    assert row["status"] == "disabled"


@pytest.mark.safe_smoke
def test_claim_is_atomic_under_concurrency(tmp_path):
    manager = AlarmManager(str(tmp_path / "alarms.db"))
    alarm_id = manager.add_alarm("08:00", target_at=datetime(2026, 1, 1, 7))
    claims = []

    def claim():
        claims.append(manager.claim_for_delivery(alarm_id, now=datetime(2026, 1, 1, 8)))

    workers = [threading.Thread(target=claim) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert sum(item is not None for item in claims) == 1


@pytest.mark.safe_smoke
def test_total_definite_delivery_failure_is_retained(tmp_path):
    path = str(tmp_path / "alarms.db")
    manager = AlarmManager(path)
    alarm_id = manager.add_alarm("08:00", target_at=datetime(2026, 1, 1, 7))
    result = process_alarm(alarm_id, db_path=path, email_sender=lambda: False, telegram_sender=lambda: False, now=datetime(2026, 1, 1, 8))
    row = manager.get_alarm_by_id(alarm_id)
    assert result["state"] == "failed"
    assert row["delivery_state"] == "failed"
    assert row["notified"] == 0
    assert row["cleanup_state"] == "pending"
    assert manager.delivery_attempts(alarm_id)


@pytest.mark.safe_smoke
def test_ambiguous_delivery_is_not_resent(tmp_path):
    path = str(tmp_path / "alarms.db")
    manager = AlarmManager(path)
    alarm_id = manager.add_alarm("08:00")
    calls = []
    ambiguous = lambda: (calls.append(1) or ToolResult(False, code="unknown_outcome", unknown_outcome=True, hint="inspect"))
    first = process_alarm(alarm_id, db_path=path, email_sender=ambiguous, telegram_sender=lambda: False)
    second = process_alarm(alarm_id, db_path=path, email_sender=ambiguous, telegram_sender=lambda: False)
    assert first["state"] == "delivery_unknown"
    assert second["sent"] is False
    assert len(calls) == 1


@pytest.mark.safe_smoke
def test_disabled_and_cancelled_alarms_skip_delivery(tmp_path):
    path = str(tmp_path / "alarms.db")
    manager = AlarmManager(path)
    disabled = manager.add_alarm("08:00")
    cancelled = manager.add_alarm("08:00")
    manager.toggle_alarm(disabled, False)
    manager.cancel_alarm(cancelled)
    sender = lambda: pytest.fail("disabled/cancelled alarm was delivered")
    assert process_alarm(disabled, db_path=path, email_sender=sender, telegram_sender=sender)["sent"] is False
    assert process_alarm(cancelled, db_path=path, email_sender=sender, telegram_sender=sender)["sent"] is False


@pytest.mark.safe_smoke
def test_cleanup_failure_is_independently_reconcilable(tmp_path):
    path = str(tmp_path / "alarms.db")
    manager = AlarmManager(path)
    alarm_id = manager.add_alarm("08:00")
    manager.set_scheduled_task(alarm_id, "stored-task")

    class Scheduler:
        @staticmethod
        def unregister_task_result(_name):
            return ToolResult(False, code="cleanup_failed", hint="retry cleanup", operation_id="cleanup-1")

    result = process_alarm(alarm_id, db_path=path, email_sender=lambda: True, telegram_sender=lambda: False, scheduler=Scheduler)
    assert result["state"] == "delivered"
    assert manager.get_alarm_by_id(alarm_id)["cleanup_state"] == "failed"


@pytest.mark.safe_smoke
def test_cleanup_retry_does_not_redeliver(tmp_path):
    from src.services.alarm_reconciliation import retry_cleanup

    path = str(tmp_path / "alarms.db")
    manager = AlarmManager(path)
    alarm_id = manager.add_alarm("08:00")
    manager.set_scheduled_task(alarm_id, "stored-task")
    calls = []

    class Scheduler:
        @staticmethod
        def unregister_task_result(name):
            calls.append(name)
            return ToolResult(True, provider="windows_scheduler", operation_id="cleanup-2")

    result = retry_cleanup(alarm_id, db_path=path, scheduler=Scheduler)
    assert result == {"ok": True, "state": "done"}
    assert calls == ["stored-task"]
    assert manager.get_alarm_by_id(alarm_id)["cleanup_state"] == "done"


@pytest.mark.safe_smoke
def test_reconciliation_reports_without_sending(tmp_path):
    path = str(tmp_path / "alarms.db")
    manager = AlarmManager(path)
    alarm_id = manager.add_alarm("08:00", target_at=datetime(2026, 1, 1, 7))
    summary = reconcile_startup(db_path=path, now=datetime(2026, 1, 1, 8), scheduler=type("NoQuery", (), {})())
    assert summary["sent"] is False
    assert summary["overdue"] == 1
    assert manager.get_alarm_by_id(alarm_id)["delivery_state"] == "overdue"


@pytest.mark.safe_smoke
def test_scheduler_nonzero_and_timeout_are_not_success(monkeypatch):
    from src.scheduler_windows import WindowsScheduler
    import subprocess
    from types import SimpleNamespace

    monkeypatch.setattr(WindowsScheduler, "runner", lambda *a, **k: SimpleNamespace(returncode=1, stderr="rejected"))
    failed = WindowsScheduler.register_alarm_result("r3-fail", "08:00")
    assert failed.ok is False and failed.unknown_outcome is False
    monkeypatch.setattr(WindowsScheduler, "runner", lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("schtasks", 15)))
    unknown = WindowsScheduler.register_alarm_result("r3-timeout", "08:00")
    assert unknown.ok is False and unknown.unknown_outcome is True
    assert unknown.task_name == WindowsScheduler.task_name_for_alarm("r3-timeout")
    try:
        os.remove(os.path.join("data", "reminder_r3-timeout.bat"))
    except OSError:
        pass


@pytest.mark.safe_smoke
def test_unregister_already_absent_task_is_a_valid_success(monkeypatch):
    from src.scheduler_windows import WindowsScheduler
    from types import SimpleNamespace

    def runner(command, **kwargs):
        return SimpleNamespace(returncode=1, stderr="ERROR: task not found")

    monkeypatch.setattr(WindowsScheduler, "runner", staticmethod(runner))
    result = WindowsScheduler.unregister_task_result("TsuziReminder_already-absent")

    assert result.ok is True
    assert result.code == "ok"
    assert result.get("already_absent") is True


@pytest.mark.safe_smoke
def test_unregister_query_timeout_is_unknown(monkeypatch):
    from src.scheduler_windows import WindowsScheduler
    import subprocess
    from types import SimpleNamespace

    def runner(command, **kwargs):
        if "/query" in command:
            raise subprocess.TimeoutExpired("schtasks", 15)
        return SimpleNamespace(returncode=1, stderr="delete failed")

    monkeypatch.setattr(WindowsScheduler, "runner", staticmethod(runner))
    result = WindowsScheduler.unregister_task_result("TsuziReminder_query-timeout")

    assert result.ok is False
    assert result.unknown_outcome is True


@pytest.mark.safe_smoke
def test_set_alarm_empty_scheduler_registration_is_not_success(monkeypatch, tmp_path):
    from tests.test_registry_smoke import _install_offline_stubs
    _install_offline_stubs(monkeypatch)
    import src.tools.wrapped_tools as wrapped
    from src.scheduler_windows import WindowsScheduler

    manager = AlarmManager(str(tmp_path / "alarms.db"))
    monkeypatch.setattr(wrapped, "alarm_mgr", manager)
    monkeypatch.setattr(WindowsScheduler, "register_alarm_result", lambda *args, **kwargs: ToolResult(False, code="schedule_failed", hint="scheduler rejected", operation_id="schedule-1", provider="windows_scheduler"))
    response = wrapped.set_alarm.invoke({"time": "08:00", "label": "R3"})
    assert "scheduling failed" in response
    row = manager.get_alarms()[0]
    assert row["schedule_state"] == "failed"
    assert "Alarm set for" not in response


@pytest.mark.safe_smoke
def test_set_alarm_success_stores_task_name(monkeypatch, tmp_path):
    from tests.test_registry_smoke import _install_offline_stubs
    _install_offline_stubs(monkeypatch)
    import src.tools.wrapped_tools as wrapped
    from src.scheduler_windows import WindowsScheduler

    manager = AlarmManager(str(tmp_path / "alarms.db"))
    monkeypatch.setattr(wrapped, "alarm_mgr", manager)
    monkeypatch.setattr(WindowsScheduler, "register_alarm_result", lambda *args, **kwargs: ToolResult(True, provider="windows_scheduler", operation_id="schedule-ok", task_name="stored-task"))
    response = wrapped.set_alarm.invoke({"time": "08:00", "label": "R3"})
    assert "Alarm set for 08:00" in response
    assert manager.get_alarms()[0]["scheduled_task_name"] == "stored-task"


@pytest.mark.safe_smoke
def test_stale_claim_becomes_unknown_without_delivery(tmp_path):
    path = str(tmp_path / "alarms.db")
    manager = AlarmManager(path)
    alarm_id = manager.add_alarm("08:00")
    claimed = manager.claim_for_delivery(alarm_id, now=datetime(2026, 1, 1, 8), lease_seconds=1)
    assert claimed
    summary = reconcile_startup(db_path=path, now=datetime(2026, 1, 1, 8, 1), scheduler=type("NoQuery", (), {})())
    assert summary["stale_claims"] == 1
    assert manager.get_alarm_by_id(alarm_id)["lifecycle"] == "delivery_unknown"


@pytest.mark.safe_smoke
def test_lifecycle_tools_are_registered(monkeypatch):
    # Importing the registry is deterministic; no tool is invoked here.
    from tests.test_registry_smoke import _install_offline_stubs
    _install_offline_stubs(monkeypatch)
    from src.tools.wrapped_tools import ALL_TOOLS
    names = {tool.name for tool in ALL_TOOLS}
    assert {"set_alarm", "list_alarms", "delete_alarm", "enable_alarm", "disable_alarm", "alarm_status", "reconcile_alarms"} <= names
