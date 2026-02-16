"""
Standalone reminder script launched by Windows Task Scheduler.

Flow:
    1. Windows fires this script at the alarm's scheduled time.
    2. Reads the alarm row directly from SQLite (avoids heavy imports).
    3. Sends an email notification via EmailService.
    4. Marks the alarm as notified in the database.
    5. Cleans up the Windows Scheduled Task and .bat wrapper.
    6. Exits.

Usage:
    python send_reminder.py --alarm_id <UUID>
"""

import argparse
import sqlite3
import subprocess
import os
import sys

# Both send_reminder.py and email_service.py live in src/services/.
# Python auto-adds the script's directory to sys.path[0], so a direct
# import works without any package resolution.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))


def main():
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

    # ── Read alarm from SQLite (no heavy imports) ──
    db_path = os.path.join(PROJECT_ROOT, "data", "alarms.db")
    if not os.path.exists(db_path):
        print(f"[send_reminder] Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM alarms WHERE id = ?", (args.alarm_id,)
    ).fetchone()

    if not row:
        print(f"[send_reminder] Alarm {args.alarm_id} not found")
        conn.close()
        sys.exit(1)

    alarm = dict(row)

    if alarm.get("notified"):
        print(f"[send_reminder] Alarm {args.alarm_id} already notified, skipping")
        conn.close()
        sys.exit(0)

    # ── Send email ──
    sender = os.environ.get("GMAIL_ADDRESS", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    recipient = os.environ.get("REMINDER_EMAIL", sender)

    if sender and password:
        # Direct import from same directory (no package resolution needed)
        from email_service import EmailService

        email_svc = EmailService(sender, password, recipient)
        subject = f"Reminder: {alarm.get('label', 'Alarm')}"
        body = (
            f"Your alarm '{alarm.get('label', 'Alarm')}' "
            f"scheduled for {alarm.get('time', 'unknown')} has fired.\n\n"
            f"Alarm ID: {args.alarm_id}"
        )

        if email_svc.send_reminder(subject, body):
            print(f"[send_reminder] Email sent for alarm {args.alarm_id}")
        else:
            print(f"[send_reminder] Failed to send email for alarm {args.alarm_id}")
    else:
        print("[send_reminder] Gmail credentials not configured, skipping email")

    # ── Mark as notified ──
    conn.execute("UPDATE alarms SET notified = 1 WHERE id = ?", (args.alarm_id,))
    conn.commit()

    # ── Clean up the Windows Scheduled Task ──
    task_name = alarm.get("scheduled_task_name", "")
    if task_name:
        try:
            subprocess.run(
                ["schtasks", "/delete", "/tn", task_name, "/f"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            print(f"[send_reminder] Cleaned up scheduled task '{task_name}'")
        except Exception as e:
            print(f"[send_reminder] Failed to clean up task: {e}")

    # ── Clean up the .bat wrapper file ──
    bat_path = os.path.join(PROJECT_ROOT, "data", f"reminder_{args.alarm_id[:8]}.bat")
    try:
        if os.path.exists(bat_path):
            os.remove(bat_path)
            print(f"[send_reminder] Cleaned up batch file '{bat_path}'")
    except OSError:
        pass

    conn.close()


if __name__ == "__main__":
    main()
