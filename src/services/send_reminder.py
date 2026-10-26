"""
================================================================================
STANDALONE REMINDER SCRIPT
================================================================================

This script is launched by Windows Task Scheduler when an alarm fires.
It runs independently of the main Tsuzi application.

WHY STANDALONE?
===============
The main app might not be running when an alarm fires. This script:
- Is lightweight (fast startup)
- Has minimal dependencies
- Can run even if main app crashed
- Handles all cleanup itself

FLOW:
=====
1. Windows Task Scheduler fires at scheduled time
2. Runs this script with --alarm_id argument
3. Script reads alarm from SQLite database
4. Sends email notification via Gmail SMTP
5. Marks alarm as notified ONLY if at least one channel delivered;
   otherwise records the miss in logs/reminder_failures.log
6. Cleans up Windows Task Scheduler task
7. Cleans up .bat wrapper file
8. Exits

USAGE:
======
python send_reminder.py --alarm_id <UUID>

IMPORTANT:
==========
This script uses direct imports from same directory (not package imports)
because it runs as a standalone script, not as part of the package.

================================================================================
"""

import argparse
import logging
from logging.handlers import RotatingFileHandler
import sqlite3
import subprocess
import os
import sys
import re
from datetime import datetime

# =============================================================================
# PATH SETUP
# =============================================================================
# Both send_reminder.py and email_service.py live in src/services/
# Python auto-adds the script's directory to sys.path[0], so a direct
# import works without any package resolution.

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

try:
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    from src.utils.redaction import redact_string
except Exception:  # pragma: no cover - standalone fallback
    def redact_string(value: str, max_len: int) -> str:
        return str(value)[:max_len]

LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
FAILURE_LOG_PATH = os.path.join(LOG_DIR, "reminder_failures.log")

# Both reminder log files are bounded (ADR 0001): rotate at ~1 MB, keep 2
# backups, so a chatty reminder run can never fill the disk.
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 2

# stdout goes nowhere under Task Scheduler, so everything is also appended
# to logs/reminders.log by _setup_logging() below.
logger = logging.getLogger("send_reminder")

# Failure entries go ONLY to logs/reminder_failures.log (propagate off, so
# they do not duplicate into reminders.log) via a rotating handler that is
# attached lazily on first use.
_failure_logger = logging.getLogger("send_reminder.failures")
_failure_logger.propagate = False
_failure_logger.setLevel(logging.INFO)


def _safe_log_text(value, max_len: int = 1000) -> str:
    """Keep reminder logs single-line, bounded, and pattern-redacted."""
    text = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return redact_string(text, max_len)


def _setup_logging():
    """Attach rotating file + stream handlers so headless runs still leave a bounded trace."""
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [send_reminder] %(levelname)s %(message)s"
    )
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "reminders.log"),
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        pass  # logs dir unwritable; stream handler still captures output
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)


def _get_failure_logger() -> logging.Logger:
    """Lazily attach the rotating handler for logs/reminder_failures.log."""
    if not _failure_logger.handlers:
        handler = RotatingFileHandler(
            FAILURE_LOG_PATH,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        _failure_logger.addHandler(handler)
    return _failure_logger


def _log_failure(alarm_id: str, label: str, error: str):
    """Append one line to logs/reminder_failures.log so nothing is silently lost."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        safe_alarm_id = _safe_log_text(alarm_id, 200)
        safe_label = _safe_log_text(label, 500)
        safe_error = _safe_log_text(error, 1000)
        timestamp = datetime.now().isoformat(timespec="seconds")
        _get_failure_logger().error(
            "%s\talarm_id=%s\tlabel=%s\terror=%s",
            timestamp,
            safe_alarm_id,
            safe_label,
            safe_error,
        )
    except OSError:
        logger.error("Could not write failure log entry for alarm %s", _safe_log_text(alarm_id, 200))


def _load_config():
    """Return src.utils.config.Config, or None when it cannot be imported.

    Config normalizes env values in one place, but this script must keep
    working with plain os.environ reads if the import chain is unavailable
    (e.g. dotenv not installed in the standalone environment).
    """
    try:
        if PROJECT_ROOT not in sys.path:
            sys.path.insert(0, PROJECT_ROOT)
        from src.utils.config import Config
        return Config
    except Exception:
        return None


def _safe_alarm_id(alarm_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", alarm_id.strip())
    return safe_id or "unknown"


def main():
    """
    Main entry point for the reminder script.
    
    EXECUTION FLOW:
    ===============
    1. Parse command line arguments (alarm_id)
    2. Load environment variables from .env
    3. Read alarm details from SQLite database
    4. Send email notification
    5. Mark alarm as notified (only if at least one channel delivered)
    6. Clean up Windows Task Scheduler task
    7. Clean up .bat wrapper file
    """
    # Parse command line arguments
    _setup_logging()
    parser = argparse.ArgumentParser(description="Send alarm reminder email")
    parser.add_argument("--alarm_id", required=True, help="UUID of the alarm")
    args = parser.parse_args()

    # Load environment variables from .env at project root
    env_path = os.path.join(PROJECT_ROOT, ".env")
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        pass  # dotenv not installed; rely on system env vars

    # ==========================================================================
    # STEP 1: Read alarm from SQLite database
    # ==========================================================================
    # Direct SQLite access instead of importing AlarmManager
    # Keeps this script lightweight with minimal dependencies
    
    db_path = os.path.join(PROJECT_ROOT, "data", "alarms.db")
    if not os.path.exists(db_path):
        logger.error("Database not found: %s", _safe_log_text(db_path))
        _log_failure(args.alarm_id, "unknown", f"database not found: {db_path}")
        sys.exit(1)

    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM alarms WHERE id = ?", (args.alarm_id,)
        ).fetchone()
    except sqlite3.Error as e:
        logger.error("Failed to read alarm %s from database: %s", _safe_log_text(args.alarm_id, 200), _safe_log_text(e))
        _log_failure(args.alarm_id, "unknown", f"database read failed: {e}")
        if conn is not None:
            conn.close()
        sys.exit(1)

    if not row:
        logger.error("Alarm %s not found", _safe_log_text(args.alarm_id, 200))
        conn.close()
        sys.exit(1)

    alarm = dict(row)

    # Check if already notified (prevent double notification)
    if alarm.get("notified"):
        logger.info("Alarm %s already notified, skipping", _safe_log_text(args.alarm_id, 200))
        conn.close()
        sys.exit(0)

    # ==========================================================================
    # STEP 2: Send email notification
    # ==========================================================================
    # Prefer Config (normalized env values); fall back to raw os.environ if
    # src.utils.config is not importable in the standalone environment.
    Config = _load_config()
    sender = (
        getattr(Config, "GMAIL_ADDRESS", None)
        or os.environ.get("GMAIL_ADDRESS", "")
    )
    password = (
        getattr(Config, "GMAIL_APP_PASSWORD", None)
        or os.environ.get("GMAIL_APP_PASSWORD", "")
    )
    recipient = (
        getattr(Config, "REMINDER_EMAIL", None)
        or os.environ.get("REMINDER_EMAIL", sender)
    )

    label = alarm.get("label", "Alarm")
    delivered = False
    delivery_errors = []

    if sender and password:
        # Direct import from same directory (no package resolution needed)
        from email_service import EmailService

        email_svc = EmailService(sender, password, recipient)
        subject = f"Reminder: {label}"
        body = (
            f"Your alarm '{label}' "
            f"scheduled for {alarm.get('time', 'unknown')} has fired.\n\n"
            f"Alarm ID: {args.alarm_id}"
        )

        if email_svc.send_reminder(subject, body):
            delivered = True
            logger.info("Email sent for alarm %s", _safe_log_text(args.alarm_id, 200))
        else:
            delivery_errors.append("email send failed")
            logger.error("Failed to send email for alarm %s", _safe_log_text(args.alarm_id, 200))
    else:
        delivery_errors.append("email not configured")
        logger.warning("Gmail credentials not configured, skipping email")

    # ==========================================================================
    # STEP 2B: Send Telegram notification (non-fatal if it fails)
    # ==========================================================================
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat_id_raw = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()

    if tg_token and tg_chat_id_raw:
        try:
            import asyncio
            from telegram import Bot

            tg_chat_id = int(tg_chat_id_raw) if tg_chat_id_raw.lstrip("-").isdigit() else tg_chat_id_raw
            tg_text = (
                f"🔔 Reminder: {label}\n"
                f"Time: {alarm.get('time', 'unknown')}\n"
                f"Alarm ID: {args.alarm_id}"
            )

            async def _send_telegram_message():
                bot = Bot(token=tg_token)
                try:
                    # timeout=15 so a hung API call can't wedge the
                    # Task Scheduler process indefinitely
                    await bot.send_message(
                        chat_id=tg_chat_id, text=tg_text, timeout=15
                    )
                finally:
                    await bot.close()

            asyncio.run(_send_telegram_message())
            delivered = True
            logger.info("Telegram message sent for alarm %s", _safe_log_text(args.alarm_id, 200))
        except Exception as e:
            delivery_errors.append(f"telegram send failed: {e}")
            logger.error("Telegram send failed for alarm %s: %s", _safe_log_text(args.alarm_id, 200), _safe_log_text(e))
    else:
        delivery_errors.append("telegram not configured")
        logger.warning("Telegram credentials not configured, skipping Telegram")

    # ==========================================================================
    # STEP 3: Mark alarm as notified in database
    # ==========================================================================
    # ONLY when at least one delivery channel succeeded. Marking notified on
    # total delivery failure would permanently destroy the reminder on a
    # single transient SMTP outage; instead the miss is recorded in
    # logs/reminder_failures.log and notified stays 0.
    if delivered:
        try:
            # Atomic guard: "AND notified = 0" + rowcount check prevents a
            # concurrent run from double-marking (double-send guard).
            cur = conn.execute(
                "UPDATE alarms SET notified = 1 WHERE id = ? AND notified = 0",
                (args.alarm_id,),
            )
            conn.commit()
            if cur.rowcount == 0:
                logger.info(
                    "Alarm %s already marked notified by another run", args.alarm_id
                )
        except sqlite3.Error as e:
            logger.error(
                "Failed to mark alarm %s notified: %s",
                _safe_log_text(args.alarm_id, 200),
                _safe_log_text(e),
            )
            _log_failure(args.alarm_id, label, f"delivered but mark-notified failed: {e}")
    else:
        error_summary = "; ".join(delivery_errors)
        logger.error(
            "No delivery channel succeeded for alarm %s (%s); leaving notified = 0",
            args.alarm_id,
            error_summary,
        )
        _log_failure(args.alarm_id, label, error_summary)

    # ==========================================================================
    # STEP 4: Clean up Windows Task Scheduler task
    # ==========================================================================
    # Remove the scheduled task that triggered this script. The task was
    # registered as one-shot, so cleanup runs in both the delivered and
    # failed-delivery paths (the failure log preserves the record).
    task_name = alarm.get("scheduled_task_name", "")
    if task_name:
        try:
            subprocess.run(
                ["schtasks", "/delete", "/tn", task_name, "/f"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            logger.info("Cleaned up scheduled task '%s'", _safe_log_text(task_name, 300))
        except Exception as e:
            logger.error("Failed to clean up task: %s", _safe_log_text(e))

    # ==========================================================================
    # STEP 5: Clean up .bat wrapper file
    # ==========================================================================
    bat_paths = [
        os.path.join(PROJECT_ROOT, "data", f"reminder_{_safe_alarm_id(args.alarm_id)}.bat"),
        os.path.join(PROJECT_ROOT, "data", f"reminder_{args.alarm_id[:8]}.bat"),
    ]
    for bat_path in dict.fromkeys(bat_paths):
        try:
            if os.path.exists(bat_path):
                os.remove(bat_path)
                logger.info("Cleaned up batch file '%s'", _safe_log_text(bat_path, 300))
        except OSError:
            pass  # File might be locked, ignore

    conn.close()


if __name__ == "__main__":
    main()
