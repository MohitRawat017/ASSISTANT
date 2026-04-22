import sqlite3
import uuid
import os
from src.utils.config import Config

# Data directory for SQLite database
DATA_DIR = os.path.join(Config.BASE_DIR, "data")


class AlarmManager:

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
