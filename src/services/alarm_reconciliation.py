"""Safe, no-send startup reconciliation for alarm lifecycle rows."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.managers.alarm_manager import AlarmManager
from src.scheduler_windows import WindowsScheduler
from src.utils.reliability import ToolResult

logger = logging.getLogger(__name__)


def reconcile_startup(
    *, db_path: str | None = None, now: datetime | str | None = None,
    scheduler=WindowsScheduler,
) -> dict[str, Any]:
    """Inspect and make safe bookkeeping transitions without delivering.

    A stale delivery lease is treated as ``delivery_unknown`` rather than
    requeued: the previous worker may have reached a provider.  Overdue rows
    are marked for visibility only; another process can explicitly decide how
    to recover them.
    """
    manager = AlarmManager(db_path)
    summary = {
        "ok": True, "sent": False, "stale_claims": 0, "overdue": 0,
        "schedule_attention": 0, "missing_tasks": 0, "cleanup_pending": 0,
        "errors": [],
    }
    try:
        summary["stale_claims"] = manager.mark_stale_claims_unknown(now=now)
        current = manager._now(now)
        for alarm in manager.get_alarms():
            if alarm.get("lifecycle") in {"cancelled", "disabled", "delivered", "delivery_unknown"}:
                if alarm.get("cleanup_state") not in {None, "done"}:
                    summary["cleanup_pending"] += 1
                continue
            target = alarm.get("target_at")
            if target:
                try:
                    if manager._now(target) < current and alarm.get("delivery_state") in {"pending", "failed", "overdue"}:
                        if manager._update(alarm["id"], {"lifecycle": "overdue", "status": "overdue", "delivery_state": "overdue", "last_hint": "Alarm is overdue; reconciliation reported it without sending."}, where="AND (delivery_claim IS NULL OR delivery_claim = '') AND enabled = 1"):
                            summary["overdue"] += 1
                except (TypeError, ValueError):
                    summary["errors"].append(f"invalid target_at for {alarm['id']}")
            if alarm.get("schedule_state") in {"failed", "unknown", "pending"}:
                summary["schedule_attention"] += 1
            if alarm.get("cleanup_state") not in {None, "done"}:
                summary["cleanup_pending"] += 1

            task_name = alarm.get("scheduled_task_name")
            query = getattr(scheduler, "query_task", None)
            if task_name and callable(query):
                present = query(task_name)
                if present is False and alarm.get("schedule_state") == "scheduled":
                    manager.set_schedule_state(alarm["id"], "unknown", hint="Stored scheduled task is missing; inspect before re-registering.", error="task not found")
                    summary["missing_tasks"] += 1
    except Exception as exc:  # startup reconciliation is explicitly non-fatal
        logger.exception("Alarm reconciliation failed")
        summary["ok"] = False
        summary["errors"].append(str(exc))
    return summary


def retry_cleanup(alarm_id: str, *, db_path: str | None = None, scheduler=WindowsScheduler) -> dict[str, Any]:
    """Retry only scheduler cleanup; never redeliver an alarm."""
    manager = AlarmManager(db_path)
    row = manager.get_alarm_by_id(alarm_id)
    if not row:
        return {"ok": False, "state": "not_found"}
    task_name = row.get("scheduled_task_name")
    if not task_name:
        manager.mark_cleanup_done(alarm_id)
        return {"ok": True, "state": "done"}
    try:
        result = scheduler.unregister_task_result(task_name) if hasattr(scheduler, "unregister_task_result") else scheduler.unregister_task(task_name)
        ok = result.ok if isinstance(result, ToolResult) else bool(result)
        if ok:
            manager.mark_cleanup_done(alarm_id)
            return {"ok": True, "state": "done"}
        manager.mark_cleanup_failed(alarm_id, result.get("error", "cleanup failed") if isinstance(result, dict) else "cleanup failed", hint=getattr(result, "hint", "Retry cleanup."), unknown=bool(getattr(result, "unknown_outcome", False)))
        return {"ok": False, "state": "unknown" if getattr(result, "unknown_outcome", False) else "failed"}
    except Exception as exc:
        manager.mark_cleanup_failed(alarm_id, str(exc), unknown=True)
        return {"ok": False, "state": "unknown"}


# Descriptive alias for callers/tests.
reconcile_alarms = reconcile_startup
