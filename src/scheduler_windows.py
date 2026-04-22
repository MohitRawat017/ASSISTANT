import subprocess
import sys
import os
from datetime import datetime, timedelta


class WindowsScheduler:
    # Prefix for all tasks (makes them easy to identify)
    TASK_PREFIX = "TsuziReminder_"

    @staticmethod
    def register_alarm(alarm_id: str, fire_time: str, label: str = "Alarm") -> str:
        # Generate unique task name
        task_name = f"{WindowsScheduler.TASK_PREFIX}{alarm_id[:8]}"

        # Find paths
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(base_dir, "src", "services", "send_reminder.py")
        python_exe = sys.executable

        # Determine next occurrence of fire_time
        now = datetime.now()
        hour, minute = map(int, fire_time.split(":"))
        alarm_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If time already passed today, schedule for tomorrow
        if alarm_dt <= now:
            alarm_dt += timedelta(days=1)

        # Format for schtasks
        schedule_date = alarm_dt.strftime("%m/%d/%Y")
        schedule_time = fire_time

        # Create .bat wrapper
        bat_dir = os.path.join(base_dir, "data")
        os.makedirs(bat_dir, exist_ok=True)
        bat_path = os.path.join(bat_dir, f"reminder_{alarm_id[:8]}.bat")

        with open(bat_path, "w") as f:
            # @ prefix suppresses echo, quotes handle spaces in paths
            f.write(f'@"{python_exe}" "{script_path}" --alarm_id {alarm_id}\n')

        try:
            # Create scheduled task using Windows schtasks command
            result = subprocess.run(
                [
                    "schtasks", "/create",
                    "/tn", task_name,           # Task name
                    "/tr", f'"{bat_path}"',     # Program to run (.bat), quoted for spaces in path
                    "/sc", "once",              # Schedule: one time
                    "/st", schedule_time,       # Start time (HH:MM)
                    "/sd", schedule_date,       # Start date (MM/DD/YYYY)
                    "/f",                       # Force: overwrite if exists
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
                # Clean up .bat file on failure
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
