"""Standalone alarm delivery worker with durable claim/transition semantics."""

from __future__ import annotations

import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import re
from datetime import datetime
from typing import Any, Callable

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from src.utils.redaction import redact_string
    from src.utils.reliability import ToolResult, failure_result, success_result, stable_operation_id
    from src.managers.alarm_manager import AlarmManager
    from src.scheduler_windows import WindowsScheduler
except Exception:  # pragma: no cover - direct standalone fallback
    def redact_string(value: str, max_len: int) -> str:
        return str(value)[:max_len]

LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
FAILURE_LOG_PATH = os.path.join(LOG_DIR, "reminder_failures.log")
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 2
logger = logging.getLogger("send_reminder")
_failure_logger = logging.getLogger("send_reminder.failures")
_failure_logger.propagate = False
_failure_logger.setLevel(logging.INFO)


def _safe_log_text(value, max_len: int = 1000) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return redact_string(text, max_len)


def _setup_logging():
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [send_reminder] %(levelname)s %(message)s")
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler = RotatingFileHandler(os.path.join(LOG_DIR, "reminders.log"), maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    except OSError:
        pass
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)


def _get_failure_logger() -> logging.Logger:
    if not _failure_logger.handlers:
        handler = RotatingFileHandler(FAILURE_LOG_PATH, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        _failure_logger.addHandler(handler)
    return _failure_logger


def _log_failure(alarm_id: str, label: str, error: str):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        _get_failure_logger().error(
            "%s\talarm_id=%s\tlabel=%s\terror=%s",
            datetime.now().isoformat(timespec="seconds"), _safe_log_text(alarm_id, 200),
            _safe_log_text(label, 500), _safe_log_text(error, 1000),
        )
    except OSError:
        logger.error("Could not write failure log entry for alarm %s", _safe_log_text(alarm_id, 200))


def _load_config():
    try:
        from src.utils.config import Config
        return Config
    except Exception:
        return None


def _safe_alarm_id(alarm_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(alarm_id).strip())
    return safe_id or "unknown"


def _result_ok(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value.get("ok", value.get("success", False)))
    return bool(getattr(value, "ok", value))


def _normalize_delivery(value: Any, *, provider: str, operation_id: str) -> ToolResult:
    if isinstance(value, ToolResult):
        return value
    if isinstance(value, dict) and {"ok", "success"} & set(value):
        ok = bool(value.get("ok", value.get("success")))
        if ok:
            extras = {k: v for k, v in value.items() if k not in {"ok", "success", "code", "retryable", "unknown_outcome", "hint", "operation_id", "provider", "attempts", "error"}}
            return ToolResult(True, operation_id=value.get("operation_id", operation_id), provider=value.get("provider", provider), attempts=int(value.get("attempts", 1)), **extras)
        return ToolResult(False, code=value.get("code", "delivery_failed"), retryable=bool(value.get("retryable", False)), unknown_outcome=bool(value.get("unknown_outcome", False)), hint=value.get("hint", "Try again later."), error=value.get("error"), provider=value.get("provider", provider), operation_id=value.get("operation_id", operation_id), attempts=int(value.get("attempts", 1)))
    if value:
        return success_result(provider=provider, operation_id=operation_id)
    return ToolResult(False, code="delivery_failed", hint="The channel rejected the reminder; retry later.", error="channel returned false", provider=provider, operation_id=operation_id)


def _invoke_delivery(sender: Callable[[], Any], *, provider: str, operation_id: str) -> ToolResult:
    try:
        return _normalize_delivery(sender(), provider=provider, operation_id=operation_id)
    except Exception as exc:
        # A delivery exception after invocation does not prove that the
        # provider did not accept the message.
        return ToolResult(False, code="unknown_outcome", unknown_outcome=True,
                          hint="The provider may have accepted the reminder; inspect it before retrying.",
                          error=str(exc), provider=provider, operation_id=operation_id)


def _default_email_sender(alarm: dict[str, Any], alarm_id: str) -> Callable[[], Any] | None:
    Config = _load_config()
    sender = getattr(Config, "GMAIL_ADDRESS", None) or os.environ.get("GMAIL_ADDRESS", "") if Config else os.environ.get("GMAIL_ADDRESS", "")
    password = getattr(Config, "GMAIL_APP_PASSWORD", None) or os.environ.get("GMAIL_APP_PASSWORD", "") if Config else os.environ.get("GMAIL_APP_PASSWORD", "")
    recipient = (getattr(Config, "REMINDER_EMAIL", None) or os.environ.get("REMINDER_EMAIL", sender)) if Config else os.environ.get("REMINDER_EMAIL", sender)
    if not sender or not password:
        return None
    def send():
        try:
            from .email_service import EmailService
        except ImportError:
            from email_service import EmailService
        label = alarm.get("label", "Alarm")
        return EmailService(sender, password, recipient).send_reminder(
            f"Reminder: {label}", f"Your alarm '{label}' scheduled for {alarm.get('time', 'unknown')} has fired.\n\nAlarm ID: {alarm_id}"
        )
    return send


def _default_telegram_sender(alarm: dict[str, Any], alarm_id: str) -> Callable[[], Any] | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id_raw = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
    if not token or not chat_id_raw:
        return None
    def send():
        from telegram import Bot
        chat_id = int(chat_id_raw) if chat_id_raw.lstrip("-").isdigit() else chat_id_raw
        label = alarm.get("label", "Alarm")
        async def deliver():
            bot = Bot(token=token)
            try:
                await bot.send_message(chat_id=chat_id, text=f"🔔 Reminder: {label}\nTime: {alarm.get('time', 'unknown')}\nAlarm ID: {alarm_id}", timeout=15)
            finally:
                await bot.close()
        asyncio.run(deliver())
        return True
    return send


def _cleanup_alarm(manager: AlarmManager, alarm: dict[str, Any], scheduler=WindowsScheduler) -> ToolResult:
    task_name = alarm.get("scheduled_task_name") or ""
    if task_name:
        try:
            raw = scheduler.unregister_task_result(task_name) if hasattr(scheduler, "unregister_task_result") else scheduler.unregister_task(task_name)
            if isinstance(raw, ToolResult):
                result = raw
            elif isinstance(raw, dict):
                result = ToolResult(
                    _result_ok(raw),
                    code="ok" if _result_ok(raw) else raw.get("code", "cleanup_failed"),
                    unknown_outcome=bool(raw.get("unknown_outcome", False)),
                    hint=raw.get("hint", "Retry cleanup from reconciliation."),
                    error=raw.get("error"),
                    provider=raw.get("provider", "windows_scheduler"),
                    operation_id=raw.get("operation_id", stable_operation_id("alarm", "cleanup", alarm["id"])),
                )
            else:
                result = success_result(provider="windows_scheduler", operation_id=stable_operation_id("alarm", "cleanup", alarm["id"])) if raw else ToolResult(False, code="cleanup_failed", hint="Retry cleanup from reconciliation.", provider="windows_scheduler", operation_id=stable_operation_id("alarm", "cleanup", alarm["id"]))
        except Exception as exc:
            result = failure_result(exc, provider="windows_scheduler", operation_id=stable_operation_id("alarm", "cleanup", alarm["id"]), dispatched=True)
        if _result_ok(result):
            manager.mark_cleanup_done(alarm["id"])
        else:
            manager.mark_cleanup_failed(alarm["id"], result.get("error") or result.hint, hint=result.hint, unknown=result.unknown_outcome)
        return result
    # No registered task means there is nothing to remove.  Do not invent a
    # task name; the stored name is the sole authority for cleanup.
    manager.mark_cleanup_done(alarm["id"])
    return success_result(provider="windows_scheduler", operation_id=stable_operation_id("alarm", "cleanup", alarm["id"]))


def process_alarm(
    alarm_id: str,
    *,
    db_path: str | None = None,
    email_sender: Callable[[], Any] | None = None,
    telegram_sender: Callable[[], Any] | None = None,
    scheduler=WindowsScheduler,
    now: datetime | str | None = None,
    lease_seconds: int = 300,
) -> dict[str, Any]:
    """Claim and deliver one alarm; never sends without a successful claim."""
    manager = AlarmManager(db_path)
    alarm = manager.claim_for_delivery(alarm_id, now=now, lease_seconds=lease_seconds)
    if not alarm:
        current = manager.get_alarm_by_id(alarm_id)
        return {"ok": True, "state": (current or {}).get("lifecycle", "not_found"), "sent": False, "hint": "Alarm is disabled, cancelled, delivered, unknown, or already claimed."}
    claim = alarm.get("delivery_claim")
    attempt_id = claim or stable_operation_id("alarm", "delivery", alarm_id)
    channels = [("email", email_sender if email_sender is not None else _default_email_sender(alarm, alarm_id)), ("telegram", telegram_sender if telegram_sender is not None else _default_telegram_sender(alarm, alarm_id))]
    outcomes = []
    for channel, sender in channels:
        if sender is None:
            result = ToolResult(False, code="not_configured", hint=f"{channel} is not configured.", error=f"{channel} not configured", provider=channel, operation_id=stable_operation_id(channel, "deliver", alarm_id))
        else:
            result = _invoke_delivery(sender, provider=channel, operation_id=stable_operation_id(channel, "deliver", alarm_id))
        manager.record_channel_outcome(alarm_id, channel, result, attempt_id=attempt_id, now=now)
        outcomes.append((channel, result))

    successes = [result for _, result in outcomes if result.ok]
    unknowns = [result for _, result in outcomes if result.unknown_outcome]
    errors = "; ".join(f"{channel}: {result.get('error') or result.hint}" for channel, result in outcomes if not result.ok)
    if successes:
        if not manager.mark_delivery_success(alarm_id, claim=claim):
            return {"ok": False, "state": "delivery_unknown", "sent": True, "operation_id": attempt_id, "hint": "Delivery succeeded but durable state could not be recorded; inspect the provider and database."}
        current = manager.get_alarm_by_id(alarm_id) or alarm
        cleanup = _cleanup_alarm(manager, current, scheduler)
        return {"ok": True, "state": "delivered", "sent": True, "cleanup_state": "done" if cleanup.ok else "failed", "operation_id": attempt_id, "hint": cleanup.hint if not cleanup.ok else ""}
    if unknowns:
        if not manager.mark_delivery_unknown(alarm_id, errors or "delivery outcome unknown", claim=claim):
            return {"ok": False, "state": "delivery_unknown", "sent": False, "operation_id": attempt_id, "hint": "Delivery outcome and durable state are unresolved; inspect the provider before retrying."}
        current = manager.get_alarm_by_id(alarm_id) or alarm
        cleanup = _cleanup_alarm(manager, current, scheduler)
        return {"ok": False, "state": "delivery_unknown", "sent": False, "cleanup_state": "done" if cleanup.ok else "failed", "operation_id": attempt_id, "hint": "Provider outcome is unknown; inspect it before retrying."}
    if not manager.mark_delivery_failure(alarm_id, errors or "all delivery channels failed", claim=claim):
        return {"ok": False, "state": "delivery_unknown", "sent": False, "operation_id": attempt_id, "hint": "Delivery failed but durable state could not be recorded; reconciliation is required."}
    _log_failure(alarm_id, alarm.get("label", "Alarm"), errors or "all delivery channels failed")
    return {"ok": False, "state": "failed", "sent": False, "operation_id": attempt_id, "hint": "All channels definitely failed; the alarm was retained for retry/reconciliation."}


def main():
    _setup_logging()
    parser = argparse.ArgumentParser(description="Send alarm reminder")
    parser.add_argument("--alarm_id", required=True, help="UUID of the alarm")
    args = parser.parse_args()
    result = process_alarm(args.alarm_id)
    logger.info("Alarm %s finished with state=%s", _safe_log_text(args.alarm_id, 200), _safe_log_text(result.get("state")))
    if result.get("state") == "not_found":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
