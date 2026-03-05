"""
================================================================================
ALARM MANAGER
================================================================================

Manages alarm storage and retrieval using SQLite. This is the data layer for
alarms - it doesn't handle the actual triggering (that's Windows Task Scheduler).

RESPONSIBILITIES:
=================
1. Store alarm data (time, label, enabled status)
2. Track which alarms have fired (notified flag)
3. Store Windows Task Scheduler task names for cleanup
4. Provide CRUD operations for alarms

WHY SQLITE?
===========
- Simple, no external dependencies
- Persistent across restarts
- Fast for small datasets
- Easy to query and filter

DATABASE SCHEMA:
================
alarms table:
- id: UUID primary key
- time: Time in HH:MM format (24-hour)
- label: User-defined alarm name
- enabled: Whether alarm is active
- notified: Whether alarm has fired
- scheduled_task_name: Windows Task Scheduler task name

================================================================================
KEY CONCEPTS FOR INTERVIEW:
================================================================================

Q: Why separate alarm storage from alarm triggering?
A: Separation of concerns:
   - AlarmManager: Data storage, CRUD operations
   - WindowsScheduler: Actual alarm triggering
   This makes the system testable and portable.

================================================================================
"""

import sqlite3
import uuid
import os
from src.utils.config import Config

# Data directory for SQLite database
DATA_DIR = os.path.join(Config.BASE_DIR, "data")


class AlarmManager:
    """
    Manages alarms in SQLite database.
    
    USAGE:
    ======
    mgr = AlarmManager()
    
    # Add alarm
    alarm_id = mgr.add_alarm("07:00", "Wake up")
    
    # Get all alarms
    alarms = mgr.get_alarms()
    
    # Mark as notified
    mgr.mark_notified(alarm_id)
    """
    
    def __init__(self, db_path: str = None):
        """
        Initialize the alarm manager.
        
        Args:
            db_path: Path to SQLite database file. If None, uses default.
        """
        self.db_path = db_path or os.path.join(DATA_DIR, "alarms.db")
        self.init_db()
    
    def init_db(self):
        """
        Create alarms table if it doesn't exist.
        
        Called on every instantiation - safe to call multiple times
        because of "IF NOT EXISTS".
        """
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alarms (
                    id TEXT PRIMARY KEY,
                    time TEXT NOT NULL,
                    label TEXT,
                    enabled BOOLEAN DEFAULT 1,
                    notified BOOLEAN DEFAULT 0,
                    scheduled_task_name TEXT
                )
            """)
            conn.commit()
            
            # Run migrations for existing databases
            self.migrate(conn)
    
    def migrate(self, conn: sqlite3.Connection):
        """
        Add missing columns for older databases.
        
        DATABASE MIGRATION:
        ===================
        As features are added, new columns may be needed.
        This method adds columns that might not exist in older
        database versions.
        
        Args:
            conn: Active SQLite connection
        """
        # Get existing columns
        cursor = conn.execute("PRAGMA table_info(alarms)")
        existing = {row[1] for row in cursor.fetchall()}
        
        # Add 'notified' column if missing
        if "notified" not in existing:
            conn.execute("ALTER TABLE alarms ADD COLUMN notified BOOLEAN DEFAULT 0")
        
        # Add 'scheduled_task_name' column if missing
        if "scheduled_task_name" not in existing:
            conn.execute("ALTER TABLE alarms ADD COLUMN scheduled_task_name TEXT")
            
        conn.commit()
    
    def add_alarm(self, time: str, label: str = "Alarm") -> str:
        """
        Add a new alarm.
        
        Args:
            time: Time in HH:MM format (24-hour)
            label: Optional alarm label
            
        Returns:
            Alarm ID (UUID string) on success, None on failure
        """
        alarm_id = str(uuid.uuid4())
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO alarms (id, time, label) VALUES (?, ?, ?)",
                    (alarm_id, time, label)
                )
                conn.commit()
                return alarm_id
        except Exception as e:
            print(f"[AlarmManager] Error adding alarm: {e}")
            return None
    
    def get_alarms(self) -> list:
        """
        Get all alarms ordered by time.
        
        Returns:
            List of alarm dicts with all fields
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM alarms ORDER BY time ASC").fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            print(f"[AlarmManager] Error loading alarms: {e}")
            return []
    
    def get_alarm_by_id(self, alarm_id: str) -> dict:
        """
        Get a single alarm by ID.
        
        Args:
            alarm_id: UUID of the alarm
            
        Returns:
            Alarm dict or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM alarms WHERE id = ?", (alarm_id,)
                ).fetchone()
                return dict(row) if row else None
        except Exception as e:
            print(f"[AlarmManager] Error fetching alarm: {e}")
            return None
    
    def delete_alarm(self, alarm_id: str):
        """
        Delete an alarm by ID.
        
        Args:
            alarm_id: UUID of the alarm to delete
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM alarms WHERE id = ?", (alarm_id,))
                conn.commit()
        except Exception as e:
            print(f"[AlarmManager] Error deleting alarm: {e}")
    
    def toggle_alarm(self, alarm_id: str, enabled: bool):
        """
        Enable or disable an alarm.
        
        Args:
            alarm_id: UUID of the alarm
            enabled: True to enable, False to disable
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE alarms SET enabled = ? WHERE id = ?",
                    (enabled, alarm_id)
                )
                conn.commit()
        except Exception as e:
            print(f"[AlarmManager] Error toggling alarm: {e}")
    
    def mark_notified(self, alarm_id: str):
        """
        Mark alarm as having fired.
        
        This prevents the same alarm from being processed multiple times.
        Called by send_reminder.py after sending the notification.
        
        Args:
            alarm_id: UUID of the alarm
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE alarms SET notified = 1 WHERE id = ?",
                    (alarm_id,)
                )
                conn.commit()
        except Exception as e:
            print(f"[AlarmManager] Error marking notified: {e}")
    
    def set_scheduled_task(self, alarm_id: str, task_name: str):
        """
        Store Windows Scheduled Task name for cleanup.
        
        When the alarm fires, send_reminder.py uses this to
        delete the Windows Task Scheduler entry.
        
        Args:
            alarm_id: UUID of the alarm
            task_name: Windows Task Scheduler task name
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE alarms SET scheduled_task_name = ? WHERE id = ?",
                    (task_name, alarm_id)
                )
                conn.commit()
        except Exception as e:
            print(f"[AlarmManager] Error setting scheduled task: {e}")


# =============================================================================
# INTERVIEW QUESTIONS FOR THIS FILE
# =============================================================================
"""
Q1: Why use UUID instead of auto-increment for alarm IDs?
A: UUIDs are:
   - Globally unique: No conflicts even across different devices
   - Non-sequential: Can't guess other alarm IDs
   - Independent: Not tied to SQLite implementation
   
   Auto-increment would work, but UUIDs are more portable.

Q2: What is the 'notified' flag for?
A: When a Windows Task Scheduler alarm fires:
   1. send_reminder.py reads the alarm from database
   2. Sends notification
   3. Sets notified=1
   This prevents double-notification if something goes wrong.

Q3: Why store scheduled_task_name?
A: Windows Task Scheduler tasks persist even after our app closes.
   When an alarm fires, we need to:
   1. Delete the Windows Task
   2. Delete the .bat file
   
   Storing the task name allows send_reminder.py to find and delete it.

Q4: How would you add recurring alarms?
A: Add a 'recur' column:
   - "once": One-time alarm (current behavior)
   - "daily": Repeat every day
   - "weekdays": Mon-Fri only
   - "weekly": Same day each week
   
   When alarm fires, if recurring, create new Windows Task for next occurrence.

Q5: What's the difference between 'enabled' and 'notified'?
A: enabled: User can disable without deleting (like snooze)
   notified: System flag - alarm has fired
   An alarm can be enabled but already notified, or disabled but not notified.

Q6: Why store time as string (HH:MM) instead of datetime?
A: Alarms are time-of-day, not specific dates. The Windows Task Scheduler
   handles the date calculation. This keeps the data model simple.

Q7: How would you add alarm sound customization?
A: Add a 'sound' column:
   - Default: system beep
   - Custom: path to audio file
   
   send_reminder.py would play the specified sound.

Q8: What happens if the database file is corrupted?
A: SQLite is ACID compliant, so corruption is rare. If it happens:
   - sqlite3.connect() might raise exception
   - Methods return empty lists/None
   - App continues running but alarms don't work
   
   Recovery: Delete alarms.db, it will be recreated.

Q9: Why use sqlite3.Row for row_factory?
A: sqlite3.Row returns dict-like objects instead of tuples:
   - Access by column name: row['time'] instead of row[1]
   - More readable code
   - Easier to convert to dict with dict(row)

Q10: How would you add alarm categories (wake, reminder, meeting)?
A: Add a 'category' column:
   ALTER TABLE alarms ADD COLUMN category TEXT DEFAULT 'general'
   
   Then filter: SELECT * FROM alarms WHERE category = 'wake'
   
   This would allow different handling per category.
"""