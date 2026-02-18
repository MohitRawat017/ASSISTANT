"""
Timer Manager - In-memory countdown timers (not persisted to disk).

Unlike alarms (which persist in SQLite and survive restarts),
timers are ephemeral countdowns that only live while the app is running.
When a timer expires, an email notification is sent via EmailService.
"""

from dataclasses import dataclass
from typing import Dict, List
import os
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

    def format_duration(self) -> str:
        """Format the original duration for display."""
        mins, secs = divmod(self.duration_seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"{hours}h {mins}m"
        elif mins:
            return f"{mins}m"
        return f"{secs}s"


class TimerManager:
    """Manages in-memory countdown timers."""

    def __init__(self):
        self.active_timers: Dict[str, ActiveTimer] = {}
        self._lock = threading.Lock()

    def add_timer(self, label: str, duration_seconds: int) -> ActiveTimer:
        """Create and store a new timer, and schedule an email on expiry."""
        timer = ActiveTimer(
            label=label,
            duration_seconds=duration_seconds,
            start_time=time.time()
        )
        with self._lock:
            self.active_timers[label] = timer

        # Fire email notification when timer expires
        t = threading.Thread(
            target=self._wait_and_notify,
            args=(label, duration_seconds),
            daemon=True,
        )
        t.start()

        return timer

    def _wait_and_notify(self, label: str, duration_seconds: int):
        """Sleep until the timer expires, then send an email."""
        time.sleep(duration_seconds)

        # Check the timer wasn't cancelled while we slept
        with self._lock:
            timer = self.active_timers.get(label)
            if timer is None:
                return  # cancelled

        sender = os.environ.get("GMAIL_ADDRESS", "")
        password = os.environ.get("GMAIL_APP_PASSWORD", "")
        recipient = os.environ.get("REMINDER_EMAIL", sender)

        if not sender or not password:
            print(f"[TimerManager] Timer '{label}' expired but Gmail credentials not configured")
            return

        try:
            from src.services.email_service import EmailService

            svc = EmailService(sender, password, recipient)
            subject = f"Timer Expired: {label}"
            body = (
                f"Your timer '{label}' ({timer.format_duration()}) has expired.\n\n"
                f"Time now: {time.strftime('%H:%M:%S')}"
            )
            if svc.send_reminder(subject, body):
                print(f"[TimerManager] Email sent for expired timer '{label}'")
            else:
                print(f"[TimerManager] Failed to send email for timer '{label}'")
        except Exception as e:
            print(f"[TimerManager] Error sending timer email: {e}")

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
