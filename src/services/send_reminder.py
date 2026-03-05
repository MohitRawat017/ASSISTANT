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
5. Marks alarm as notified in database
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
KEY CONCEPTS FOR INTERVIEW:
================================================================================

Q: Why not just run the main app in the background?
A: A full Python app with models loaded:
   - Takes seconds to start
   - Uses significant RAM
   - Could fail to start
   This script starts instantly and uses minimal resources.

================================================================================
"""

import argparse
import sqlite3
import subprocess
import os
import sys

# =============================================================================
# PATH SETUP
# =============================================================================
# Both send_reminder.py and email_service.py live in src/services/
# Python auto-adds the script's directory to sys.path[0], so a direct
# import works without any package resolution.

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))


def main():
    """
    Main entry point for the reminder script.
    
    EXECUTION FLOW:
    ===============
    1. Parse command line arguments (alarm_id)
    2. Load environment variables from .env
    3. Read alarm details from SQLite database
    4. Send email notification
    5. Mark alarm as notified
    6. Clean up Windows Task Scheduler task
    7. Clean up .bat wrapper file
    """
    # Parse command line arguments
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

    # Check if already notified (prevent double notification)
    if alarm.get("notified"):
        print(f"[send_reminder] Alarm {args.alarm_id} already notified, skipping")
        conn.close()
        sys.exit(0)

    # ==========================================================================
    # STEP 2: Send email notification
    # ==========================================================================
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

    # ==========================================================================
    # STEP 3: Mark alarm as notified in database
    # ==========================================================================
    conn.execute("UPDATE alarms SET notified = 1 WHERE id = ?", (args.alarm_id,))
    conn.commit()

    # ==========================================================================
    # STEP 4: Clean up Windows Task Scheduler task
    # ==========================================================================
    # Remove the scheduled task that triggered this script
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

    # ==========================================================================
    # STEP 5: Clean up .bat wrapper file
    # ==========================================================================
    bat_path = os.path.join(PROJECT_ROOT, "data", f"reminder_{args.alarm_id[:8]}.bat")
    try:
        if os.path.exists(bat_path):
            os.remove(bat_path)
            print(f"[send_reminder] Cleaned up batch file '{bat_path}'")
    except OSError:
        pass  # File might be locked, ignore

    conn.close()


if __name__ == "__main__":
    main()


# =============================================================================
# INTERVIEW QUESTIONS FOR THIS FILE
# =============================================================================
"""
Q1: Why import email_service directly instead of from src.services?
A: When running as a standalone script (not as a module), Python adds the
   script's directory to sys.path[0]. Direct imports work naturally.
   Package-style imports (from src.services) would fail because Python
   doesn't know about the package structure when running standalone.

Q2: Why not use AlarmManager class instead of direct SQLite?
A: AlarmManager imports other modules, which might:
   - Import heavy dependencies
   - Fail if dependencies missing
   - Slow down startup
   
   Direct SQLite keeps this script lightweight and fast.

Q3: What happens if Gmail credentials are missing?
A: The script continues without error:
   - Logs "skipping email"
   - Still marks alarm as notified
   - Still cleans up tasks and files
   
   This ensures cleanup happens even if email fails.

Q4: Why check if already notified?
A: Edge cases where alarm might fire twice:
   - Task Scheduler runs task twice (rare bug)
   - Manual run of .bat file for testing
   - Database restored from backup
   
   Checking prevents double notification.

Q5: How would you add Telegram notification?
A: Add Telegram API call alongside email:
   
   from telegram import Bot
   bot = Bot(token=os.environ.get("TELEGRAM_BOT_TOKEN"))
   bot.send_message(
       chat_id=os.environ.get("TELEGRAM_ALLOWED_USER_ID"),
       text=f"🔔 {alarm.get('label', 'Alarm')}"
   )

Q6: Why use argparse instead of sys.argv directly?
A: argparse provides:
   - Automatic help (--help)
   - Required argument validation
   - Type conversion
   - Clean error messages
   
   More robust than manual argv parsing.

Q7: What if the script crashes mid-execution?
A: Each step is independent:
   - If email fails, still marks notified and cleans up
   - If cleanup fails, alarm is still marked notified
   - Database updates are atomic (commit after update)
   
   Next run will skip (notified=1) rather than error.

Q8: How would you add push notification (Pushover, etc.)?
A: Add HTTP request to push service:
   
   import requests
   requests.post(
       "https://api.pushover.net/1/messages.json",
       data={
           "token": PUSHOVER_TOKEN,
           "user": PUSHOVER_USER,
           "message": f"Alarm: {alarm['label']}"
       }
   )

Q9: Why clean up .bat file?
A: .bat files accumulate over time if not cleaned:
   - Disk space waste
   - Security risk (contains paths)
   - Clutter in data directory
   
   Cleanup ensures one .bat per active alarm.

Q10: How would you make this cross-platform (Linux/Mac)?
A: Replace Windows-specific parts:
   1. Task Scheduler → cron jobs (Linux) / launchd (Mac)
   2. schtasks commands → crontab commands
   3. .bat files → shell scripts
   
   Or use a cross-platform scheduler like APScheduler.
"""