import sqlite3
import uuid
import os
from typing import List, Dict, Optional
from src.utils.config import Config

DATA_DIR = os.path.join(Config.BASE_DIR, "data")


class AlarmManager:
    """Manages alarms using a local SQLite database.

    Database: data/alarms.db
    Table: alarms
        - id                  TEXT PRIMARY KEY   (UUID)
        - time                TEXT NOT NULL      (HH:MM format, e.g. "07:00")
        - label               TEXT               (optional description)
        - enabled             BOOLEAN DEFAULT 1  (1 = active, 0 = disabled)
        - notified            BOOLEAN DEFAULT 0  (1 = reminder sent)
        - scheduled_task_name TEXT               (Windows Task Scheduler task name)
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(DATA_DIR, "alarms.db")
        self._init_db()

    def _init_db(self):
        """Create the data directory and alarms table if they don't exist."""
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
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection):
        """Add new columns to existing databases that lack them."""
        cursor = conn.execute("PRAGMA table_info(alarms)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        if "notified" not in existing_cols:
            conn.execute("ALTER TABLE alarms ADD COLUMN notified BOOLEAN DEFAULT 0")
        if "scheduled_task_name" not in existing_cols:
            conn.execute("ALTER TABLE alarms ADD COLUMN scheduled_task_name TEXT")
        conn.commit()

    def add_alarm(self, time: str, label: str = "Alarm") -> Optional[str]:
        """Add a new alarm. Returns the alarm ID or None on failure."""
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

    def get_alarms(self) -> List[Dict]:
        """Retrieve all alarms ordered by time."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM alarms ORDER BY time ASC").fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            print(f"[AlarmManager] Error loading alarms: {e}")
            return []

    def get_alarm_by_id(self, alarm_id: str) -> Optional[Dict]:
        """Retrieve a single alarm by ID."""
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
        """Delete an alarm by ID."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM alarms WHERE id = ?", (alarm_id,))
                conn.commit()
        except Exception as e:
            print(f"[AlarmManager] Error deleting alarm: {e}")

    def toggle_alarm(self, alarm_id: str, enabled: bool):
        """Enable or disable an alarm."""
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
        """Mark an alarm as notified (reminder sent)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE alarms SET notified = 1 WHERE id = ?",
                    (alarm_id,)
                )
                conn.commit()
        except Exception as e:
            print(f"[AlarmManager] Error marking alarm notified: {e}")

    def set_scheduled_task(self, alarm_id: str, task_name: str):
        """Store the Windows Scheduled Task name for an alarm."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE alarms SET scheduled_task_name = ? WHERE id = ?",
                    (task_name, alarm_id)
                )
                conn.commit()
        except Exception as e:
            print(f"[AlarmManager] Error setting scheduled task: {e}")
