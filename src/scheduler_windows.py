"""
================================================================================
WINDOWS TASK SCHEDULER INTEGRATION
================================================================================

This module integrates with Windows Task Scheduler to create reliable alarm
triggers that work even when the Python app is closed.

WHY WINDOWS TASK SCHEDULER?
===========================
Problems with in-process alarms:
- App must be running at alarm time
- App crash = missed alarm
- Computer sleep = missed alarm

Windows Task Scheduler benefits:
- Runs independently of Python app
- Can wake computer from sleep
- Survives app restarts/crashes
- Built into Windows (no extra software)

HOW IT WORKS:
=============
1. User sets alarm via set_alarm tool
2. AlarmManager stores alarm in SQLite
3. This module creates Windows Task Scheduler task
4. Task runs send_reminder.py at alarm time
5. send_reminder.py sends notification
6. Task and .bat file are cleaned up

ALARM FLOW:
===========
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ set_alarm() │ ──► │ AlarmManager    │ ──► │ Windows Task    │
│ (tool)      │     │ (SQLite)         │     │ Scheduler       │
└─────────────┘     └──────────────────┘     └─────────────────┘
                                                      │
                                                      ▼ (at alarm time)
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Telegram    │ ◄── │ EmailService    │ ◄── │ send_reminder.py│
│ Notification│     │ (SMTP)           │     │ (standalone)    │
└─────────────┘     └──────────────────┘     └─────────────────┘

================================================================================
KEY CONCEPTS FOR INTERVIEW:
================================================================================

Q: Why use .bat files instead of direct Python command?
A: Windows Task Scheduler has quirks with path quoting. .bat files:
   - Avoid complex quoting issues
   - Easy to debug (can run manually)
   - Simple one-line command

================================================================================
"""

import subprocess
import sys
import os
from datetime import datetime, timedelta


class WindowsScheduler:
    """
    Register and manage Windows Scheduled Tasks for alarm reminders.
    
    USAGE:
    ======
    # Register an alarm
    task_name = WindowsScheduler.register_alarm(
        alarm_id="abc123",
        fire_time="07:00",
        label="Wake up"
    )
    
    # Later, when alarm fires, clean up
    WindowsScheduler.unregister_task(task_name)
    """
    
    # Prefix for all tasks (makes them easy to identify)
    TASK_PREFIX = "TsuziReminder_"

    @staticmethod
    def register_alarm(alarm_id: str, fire_time: str, label: str = "Alarm") -> str:
        """
        Register a Windows Scheduled Task for an alarm.
        
        PROCESS:
        ========
        1. Calculate next occurrence of fire_time
        2. Create .bat wrapper script
        3. Register task with schtasks command
        4. Return task name for later cleanup
        
        WHY .BAT WRAPPER?
        ================
        Windows Task Scheduler has issues with:
        - Quoted paths (spaces in "Program Files")
        - Multiple arguments
        - Environment variables
        
        A .bat file avoids all these issues with a simple one-liner.
        
        Args:
            alarm_id: UUID of the alarm (from AlarmManager)
            fire_time: Time in HH:MM (24-hour) format
            label: Alarm label (for logging)
            
        Returns:
            Task name on success, empty string on failure
        """
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
                    "/tr", bat_path,            # Program to run (.bat)
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
        """
        Remove a Windows Scheduled Task by name.
        
        Called by send_reminder.py after alarm fires to clean up.
        
        Args:
            task_name: Name of the task to remove
            
        Returns:
            True on success, False on failure
        """
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


# =============================================================================
# INTERVIEW QUESTIONS FOR THIS FILE
# =============================================================================
"""
Q1: Why use Windows Task Scheduler instead of a background thread?
A: Background threads require the app to be running. Task Scheduler:
   - Works even when app is closed
   - Can wake computer from sleep
   - Persists across reboots
   - More reliable for critical alarms

Q2: What is the schtasks command?
A: Windows built-in command for Task Scheduler operations:
   - schtasks /create: Create new task
   - schtasks /delete: Delete task
   - schtasks /query: List tasks
   - schtasks /run: Run task immediately
   
   Available on all Windows versions.

Q3: Why use /sc once instead of /sc daily?
A: /sc once = one-time task (self-deleting after run)
   /sc daily = recurring task (needs manual cleanup)
   
   One-time is simpler for alarms - we create a new task each time.

Q4: What happens if the computer is off at alarm time?
A: Task Scheduler has options:
   - Start only if logged on: Miss if not logged in
   - Run whether logged in or not: Runs as scheduled
   
   We use default settings. For reliability, could add:
   /rl HIGHEST (run with highest privileges)

Q5: How would you add "wake from sleep" support?
A: In Task Scheduler GUI, this is "Wake the computer to run this task".
   Via schtasks, it requires creating an XML definition:
   
   <Settings>
     <WakeToRun>true</WakeToRun>
   </Settings>
   
   Then use schtasks /create /xml task.xml

Q6: What's the /f flag for?
A: /f = Force. Overwrites existing task with same name.
   Useful during development when testing same alarm multiple times.
   Without it, create fails if task already exists.

Q7: Why use alarm_id[:8] instead of full UUID?
A: Full UUID (36 chars) + prefix could exceed Windows task name limit.
   First 8 chars of UUID are unique enough for our purposes.
   Task name limit is typically 238 characters.

Q8: How would you handle timezone changes?
A: Windows Task Scheduler stores times in local time.
   If user changes timezone, tasks adjust automatically.
   For daylight saving time, use:
   /ri 1 /st HH:MM /du 0000:01 (repeat every minute for 1 minute)
   
   This ensures alarm fires even during DST transition hour.

Q9: What if the user doesn't have admin rights?
A: schtasks /create requires admin for some settings.
   User-level tasks can be created without admin:
   - Remove /rl HIGHEST
   - Use /tr with accessible paths
   
   Our implementation should work for standard users.

Q10: How would you implement a snooze feature?
A: When user snoozes:
   1. Delete current task
   2. Create new task for X minutes later
   3. Update AlarmManager if needed
   
   snooze(alarm_id, minutes):
       WindowsScheduler.unregister_task(current_task)
       new_time = now + timedelta(minutes=minutes)
       WindowsScheduler.register_alarm(alarm_id, new_time.strftime("%H:%M"))
"""