"""
Timer Manager - In-memory countdown timers (not persisted to disk).

Unlike alarms (which persist in SQLite and survive restarts),
timers are ephemeral countdowns that only live while the app is running.
"""

from dataclasses import dataclass
from typing import Dict, List
import threading
import time


@dataclass
class ActiveTimer:
    """Represents a single countdown timer."""
    label: str
    duration_seconds: int
    start_time: float

    @property
    def remaining_seconds(self) -> int:
        elapsed = time.time() - self.start_time
        return max(0, int(self.duration_seconds - elapsed))

    @property
    def is_expired(self) -> bool:
        return self.remaining_seconds <= 0

    def format_remaining(self) -> str:
        secs = self.remaining_seconds
        mins, secs = divmod(secs, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"{hours}h {mins}m {secs}s"
        elif mins:
            return f"{mins}m {secs}s"
        return f"{secs}s"


class TimerManager:
    """Manages in-memory countdown timers."""

    def __init__(self):
        self.active_timers: Dict[str, ActiveTimer] = {}
        self._lock = threading.Lock()

    def add_timer(self, label: str, duration_seconds: int) -> ActiveTimer:
        """Create and store a new timer."""
        timer = ActiveTimer(
            label=label,
            duration_seconds=duration_seconds,
            start_time=time.time()
        )
        with self._lock:
            self.active_timers[label] = timer
        return timer

    def get_active_timers(self) -> List[Dict]:
        """Return all non-expired timers, cleaning up expired ones."""
        with self._lock:
            expired = [k for k, t in self.active_timers.items() if t.is_expired]
            for k in expired:
                del self.active_timers[k]

            return [
                {"label": t.label, "remaining": t.format_remaining()}
                for t in self.active_timers.values()
            ]

    def cancel_timer(self, label: str) -> bool:
        """Cancel a timer by label. Returns True if found."""
        with self._lock:
            if label in self.active_timers:
                del self.active_timers[label]
                return True
            return False
