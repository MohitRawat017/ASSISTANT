"""
Habit Manager - Tracks daily habits in SQLite.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from src.utils.config import Config

DATA_DIR = os.path.join(Config.BASE_DIR, "data")


class HabitManager:
    """Tracks daily habits in SQLite.

    Table: habits
        - id          INTEGER PRIMARY KEY AUTOINCREMENT
        - habit       TEXT NOT NULL
        - notes       TEXT
        - logged_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        - date        TEXT NOT NULL  (YYYY-MM-DD)
    """

    def __init__(self, db_path=None):
        self.db_path = db_path or os.path.join(DATA_DIR, "habits.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS habits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit TEXT NOT NULL,
                    notes TEXT,
                    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    date TEXT NOT NULL
                )
            """)
            conn.commit()

    def log(self, habit, notes=None):
        """Log a habit for today. Returns True if new, False if already logged."""
        today = datetime.now().strftime("%Y-%m-%d")

        with sqlite3.connect(self.db_path) as conn:
            # Check if already logged today
            exists = conn.execute(
                "SELECT id FROM habits WHERE habit = ? AND date = ?",
                (habit.lower(), today)
            ).fetchone()

            if exists:
                return False

            conn.execute(
                "INSERT INTO habits (habit, notes, date) VALUES (?, ?, ?)",
                (habit.lower(), notes, today)
            )
            conn.commit()
            return True

    def get_summary(self, period="week"):
        """Get habit summary for a given period."""
        now = datetime.now()

        if period == "today":
            start = now.strftime("%Y-%m-%d")
        elif period == "month":
            start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        else:  # week
            start = (now - timedelta(days=7)).strftime("%Y-%m-%d")

        end = now.strftime("%Y-%m-%d")

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT habit, date, notes FROM habits WHERE date >= ? AND date <= ? ORDER BY date DESC",
                (start, end)
            ).fetchall()

        if not rows:
            return {"period": period, "habits": {}, "total_entries": 0}

        # Group by habit name
        habits = {}
        for row in rows:
            name = row["habit"]
            if name not in habits:
                habits[name] = {"count": 0, "dates": []}
            habits[name]["count"] += 1
            habits[name]["dates"].append(row["date"])

        return {
            "period": period,
            "habits": habits,
            "total_entries": len(rows)
        }
