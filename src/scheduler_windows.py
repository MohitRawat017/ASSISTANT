"""
Windows Task Scheduler integration for alarm reminders.

Registers one-time scheduled tasks that run send_reminder.py
at the alarm's fire time, even if the assistant is not running.

Uses a .bat wrapper file to avoid quoting issues when paths contain spaces.
"""

import subprocess
import sys
import os
from datetime import datetime, timedelta


class WindowsScheduler:
    """Register and manage Windows Scheduled Tasks for alarm reminders."""

    TASK_PREFIX = "TsuziReminder_"

    @staticmethod
    def register_alarm(alarm_id: str, fire_time: str, label: str = "Alarm") -> str:
        """Register a Windows Scheduled Task for an alarm.

        Args:
            alarm_id:  UUID of the alarm in the database.
            fire_time: Time in HH:MM (24-hour) format.
            label:     Human-readable alarm label (unused by scheduler, kept for logging).

        Returns:
            The task name on success, or an empty string on failure.
        """
        task_name = f"{WindowsScheduler.TASK_PREFIX}{alarm_id[:8]}"

        # Resolve paths
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(base_dir, "src", "services", "send_reminder.py")
        python_exe = sys.executable

        # Determine the next occurrence of fire_time
        now = datetime.now()
        hour, minute = map(int, fire_time.split(":"))
        alarm_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if alarm_dt <= now:
            alarm_dt += timedelta(days=1)

        schedule_date = alarm_dt.strftime("%m/%d/%Y")
        schedule_time = fire_time

        # Create a .bat wrapper so schtasks doesn't mangle quoted paths
        bat_dir = os.path.join(base_dir, "data")
        os.makedirs(bat_dir, exist_ok=True)
        bat_path = os.path.join(bat_dir, f"reminder_{alarm_id[:8]}.bat")

        with open(bat_path, "w") as f:
            f.write(f'@"{python_exe}" "{script_path}" --alarm_id {alarm_id}\n')

        try:
            result = subprocess.run(
                [
                    "schtasks", "/create",
                    "/tn", task_name,
                    "/tr", f'"{bat_path}"',
                    "/sc", "once",
                    "/st", schedule_time,
                    "/sd", schedule_date,
                    "/f",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode == 0:
                print(f"[Scheduler] Registered task '{task_name}' for {schedule_date} {schedule_time}")
                return task_name
            else:
                print(f"[Scheduler] Failed to create task: {result.stderr.strip()}")
                # Clean up the .bat file on failure
                try:
                    os.remove(bat_path)
                except OSError:
                    pass
                return ""
        except Exception as e:
            print(f"[Scheduler] Error creating task: {e}")
            return ""

    @staticmethod
    def unregister_task(task_name: str) -> bool:
        """Remove a Windows Scheduled Task by name."""
        try:
            result = subprocess.run(
                ["schtasks", "/delete", "/tn", task_name, "/f"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                print(f"[Scheduler] Removed task '{task_name}'")
            return result.returncode == 0
        except Exception as e:
            print(f"[Scheduler] Error removing task: {e}")
            return False
