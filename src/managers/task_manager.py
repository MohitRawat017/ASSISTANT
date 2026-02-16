import sqlite3
import uuid
import os
from typing import List, Dict, Optional
from src.utils.config import Config

DATA_DIR = os.path.join(Config.BASE_DIR, "data")


class TaskManager:
    """Manages tasks using a local SQLite database.

    Database: data/tasks.db
    Table: tasks
        - id          TEXT PRIMARY KEY   (UUID)
        - text        TEXT NOT NULL      (task description)
        - completed   BOOLEAN DEFAULT 0  (0 = pending, 1 = done)
        - created_at  TIMESTAMP          (auto-set on insert)
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(DATA_DIR, "tasks.db")
        self._init_db()

    def _init_db(self):
        """Create the data directory and tasks table if they don't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    completed BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def get_tasks(self) -> List[Dict]:
        """Retrieve all tasks ordered by creation time."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM tasks ORDER BY created_at ASC").fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            print(f"[TaskManager] Error loading tasks: {e}")
            return []

    def add_task(self, text: str) -> Optional[Dict]:
        """Add a new task. Returns the task dict or None on failure."""
        task_id = str(uuid.uuid4())
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO tasks (id, text, completed) VALUES (?, ?, ?)",
                    (task_id, text, False)
                )
                conn.commit()
                return {"id": task_id, "text": text, "completed": False}
        except Exception as e:
            print(f"[TaskManager] Error adding task: {e}")
            return None

    def delete_task(self, task_id: str):
        """Delete a task by ID."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                conn.commit()
        except Exception as e:
            print(f"[TaskManager] Error deleting task: {e}")

    def toggle_task(self, task_id: str, completed: bool):
        """Update task completion status."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE tasks SET completed = ? WHERE id = ?",
                    (completed, task_id)
                )
                conn.commit()
        except Exception as e:
            print(f"[TaskManager] Error toggling task: {e}")
