"""
Function Executor - Executes Gemma-routed functions with actual backend calls.
"""

from datetime import datetime, timedelta
from typing import Dict, Any
import re


class FunctionExecutor:
    """Central executor for all Gemma-routed functions."""

    def __init__(self):
        self.task_manager = None
        self.alarm_manager = None
        self.timer_manager = None
        self.calendar_manager = None
        self.weather_manager = None
        self.news_manager = None

        self._init_managers()

    def _init_managers(self):
        """Lazy-load each manager independently so one failure doesn't block others."""
        try:
            from src.managers.task_manager import TaskManager
            self.task_manager = TaskManager()
        except Exception as e:
            print(f"[FunctionExecutor] TaskManager init failed: {e}")

        try:
            from src.managers.alarm_manager import AlarmManager
            self.alarm_manager = AlarmManager()
        except Exception as e:
            print(f"[FunctionExecutor] AlarmManager init failed: {e}")

        try:
            from src.managers.timer_manager import TimerManager
            self.timer_manager = TimerManager()
        except Exception as e:
            print(f"[FunctionExecutor] TimerManager init failed: {e}")

        try:
            from src.managers.calendar_manager import CalendarManager
            self.calendar_manager = CalendarManager()
        except Exception as e:
            print(f"[FunctionExecutor] CalendarManager init failed: {e}")

        try:
            from src.managers.weather_manager import WeatherManager
            self.weather_manager = WeatherManager()
        except Exception as e:
            print(f"[FunctionExecutor] WeatherManager init failed: {e}")

        try:
            from src.managers.news_manager import NewsManager
            self.news_manager = NewsManager()
        except Exception as e:
            print(f"[FunctionExecutor] NewsManager init failed: {e}")

    def execute(self, func_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a routed function call.

        Returns:
            {"success": bool, "message": str, "data": Any}
        """
        try:
            dispatch = {
                "set_timer": self._set_timer,
                "set_alarm": self._set_alarm,
                "create_calendar_event": self._create_calendar_event,
                "add_task": self._add_task,
                "web_search": self._web_search,
                "get_system_info": lambda p: self._get_system_info(),
            }

            handler = dispatch.get(func_name)
            if handler:
                return handler(params)
            return {"success": False, "message": f"Unknown function: {func_name}", "data": None}

        except Exception as e:
            return {"success": False, "message": f"Error: {str(e)}", "data": None}

    # ── Timer ──────────────────────────────────────────────────────────

    def _set_timer(self, params: Dict) -> Dict:
        """Set a countdown timer (in-memory, not persisted)."""
        duration_str = params.get("duration", "")
        label = params.get("label", "Timer")

        if not self.timer_manager:
            return {"success": False, "message": "Timer manager not available", "data": None}

        seconds = self._parse_duration(duration_str)
        if seconds <= 0:
            return {"success": False, "message": f"Invalid duration: {duration_str}", "data": None}

        self.timer_manager.add_timer(label, seconds)

        return {
            "success": True,
            "message": f"Timer '{label}' set for {duration_str}",
            "data": {"label": label, "duration": duration_str, "seconds": seconds}
        }

    def _parse_duration(self, duration_str: str) -> int:
        """Parse '10 minutes', '1 hour 30 minutes', '30s' etc. to seconds."""
        duration_str = duration_str.lower().strip()
        total = 0

        patterns = [
            (r'(\d+)\s*h(?:our)?s?', 3600),
            (r'(\d+)\s*m(?:in(?:ute)?s?)?', 60),
            (r'(\d+)\s*s(?:ec(?:ond)?s?)?', 1),
        ]
        for pattern, multiplier in patterns:
            match = re.search(pattern, duration_str)
            if match:
                total += int(match.group(1)) * multiplier

        # Bare number -> assume minutes
        if total == 0:
            nums = re.findall(r'\d+', duration_str)
            if nums:
                total = int(nums[0]) * 60

        return total

    # ── Alarm ──────────────────────────────────────────────────────────

    def _set_alarm(self, params: Dict) -> Dict:
        """Set an alarm (persisted in SQLite) and register a Windows Scheduled Task."""
        time_str = params.get("time", "")
        label = params.get("label", "Alarm")

        if not self.alarm_manager:
            return {"success": False, "message": "Alarm manager not available", "data": None}

        normalized = self._normalize_time(time_str)
        alarm_id = self.alarm_manager.add_alarm(normalized, label)

        if alarm_id:
            # Register a Windows Scheduled Task so the reminder fires
            # even if the assistant is closed.
            try:
                from src.scheduler_windows import WindowsScheduler
                task_name = WindowsScheduler.register_alarm(alarm_id, normalized, label)
                if task_name:
                    self.alarm_manager.set_scheduled_task(alarm_id, task_name)
            except Exception as e:
                print(f"[FunctionExecutor] Scheduler registration failed: {e}")

            return {
                "success": True,
                "message": f"Alarm set for {normalized}" + (f" ({label})" if label != "Alarm" else ""),
                "data": {"id": alarm_id, "time": normalized, "label": label}
            }
        return {"success": False, "message": "Failed to set alarm", "data": None}

    def _normalize_time(self, time_str: str) -> str:
        """Normalize time string to HH:MM format."""
        time_str = time_str.lower().strip()
        match = re.match(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', time_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2)) if match.group(2) else 0
            period = match.group(3)
            if period == 'pm' and hour < 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0
            return f"{hour:02d}:{minute:02d}"
        return time_str

    # ── Calendar ───────────────────────────────────────────────────────

    def _create_calendar_event(self, params: Dict) -> Dict:
        """Create a calendar event (persisted in SQLite)."""
        title = params.get("title", "Event")
        date = params.get("date", "today")
        time_str = params.get("time", "09:00")
        duration = params.get("duration", 60)

        if not self.calendar_manager:
            return {"success": False, "message": "Calendar manager not available", "data": None}

        event_date = self._parse_date(date)
        normalized_time = self._normalize_time(time_str) if time_str else "09:00"
        start_dt = f"{event_date} {normalized_time}:00"

        try:
            start = datetime.strptime(start_dt, "%Y-%m-%d %H:%M:%S")
            end = start + timedelta(minutes=duration if isinstance(duration, int) else 60)
            end_dt = end.strftime("%Y-%m-%d %H:%M:%S")
        except:
            end_dt = start_dt

        event = self.calendar_manager.add_event(title, start_dt, end_dt)
        if event:
            return {
                "success": True,
                "message": f"Created event '{title}' on {date}" + (f" at {time_str}" if time_str else ""),
                "data": event
            }
        return {"success": False, "message": "Failed to create event", "data": None}

    def _parse_date(self, date_str: str) -> str:
        """Parse date string to YYYY-MM-DD."""
        date_str = date_str.lower().strip()
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            pass

        today = datetime.now()
        if date_str in ("today", ""):
            return today.strftime("%Y-%m-%d")
        if date_str == "tomorrow":
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")

        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for i, day in enumerate(days):
            if day in date_str:
                ahead = i - today.weekday()
                if ahead <= 0:
                    ahead += 7
                if "next" in date_str:
                    ahead += 7
                return (today + timedelta(days=ahead)).strftime("%Y-%m-%d")

        return today.strftime("%Y-%m-%d")

    # ── Tasks ──────────────────────────────────────────────────────────

    def _add_task(self, params: Dict) -> Dict:
        """Add a task (persisted in SQLite)."""
        text = params.get("text", "")
        if not text:
            return {"success": False, "message": "No task text provided", "data": None}
        if not self.task_manager:
            return {"success": False, "message": "Task manager not available", "data": None}

        task = self.task_manager.add_task(text)
        if task:
            return {"success": True, "message": f"Added task: {text}", "data": task}
        return {"success": False, "message": "Failed to add task", "data": None}

    # ── Web Search ─────────────────────────────────────────────────────

    def _web_search(self, params: Dict) -> Dict:
        """Search the web via DuckDuckGo."""
        query = params.get("query", "")
        if not query:
            return {"success": False, "message": "No search query provided", "data": None}

        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))

            if results:
                formatted = [
                    {"title": r.get("title", ""), "body": r.get("body", "")[:200], "url": r.get("href", "")}
                    for r in results[:3]
                ]
                return {
                    "success": True,
                    "message": f"Found {len(results)} results for '{query}'",
                    "data": {"query": query, "results": formatted}
                }
            return {"success": True, "message": f"No results found for '{query}'", "data": None}

        except Exception as e:
            return {"success": False, "message": f"Search failed: {e}", "data": None}

    # ── System Info (aggregates everything) ────────────────────────────

    def _get_system_info(self) -> Dict:
        """Pull status from every manager into a single snapshot."""
        info = {
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timers": [],
            "alarms": [],
            "calendar_today": [],
            "tasks": [],
            "weather": None,
            "news": []
        }

        # Timers (in-memory)
        if self.timer_manager:
            info["timers"] = self.timer_manager.get_active_timers()

        # Alarms (SQLite)
        if self.alarm_manager:
            try:
                alarms = self.alarm_manager.get_alarms()
                info["alarms"] = [{"time": a["time"], "label": a["label"]} for a in alarms]
            except:
                pass

        # Calendar (SQLite)
        if self.calendar_manager:
            try:
                today = datetime.now().strftime("%Y-%m-%d")
                events = self.calendar_manager.get_events(today)
                info["calendar_today"] = [{"title": e["title"], "time": e["start_time"]} for e in events]
            except:
                pass

        # Tasks (SQLite)
        if self.task_manager:
            try:
                tasks = self.task_manager.get_tasks()
                info["tasks"] = [{"text": t["text"], "completed": t["completed"]} for t in tasks]
            except:
                pass

        # Weather (API)
        if self.weather_manager:
            try:
                weather = self.weather_manager.get_weather()
                if weather and "temp" in weather:
                    info["weather"] = {
                        "temp": weather.get("temp"),
                        "code": weather.get("code"),
                        "high": weather.get("high"),
                        "low": weather.get("low")
                    }
            except:
                pass

        # News (API + optional AI)
        if self.news_manager:
            try:
                items = self.news_manager.get_briefing(use_ai=False)
                info["news"] = [
                    {"title": n.get("title", ""), "category": n.get("category", "News"), "url": n.get("url", "")}
                    for n in items[:5]
                ]
            except:
                pass

        return {"success": True, "message": "System info retrieved", "data": info}


# Global instance
executor = FunctionExecutor()
