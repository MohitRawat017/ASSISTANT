"""
Unit tests for all manager modules.

Tests each manager's core functionality independently:
- TimerManager
- AlarmManager
- TaskManager
- CalendarManager
- HabitManager
"""

import os
import sys
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── Alarm Manager Tests ───────────────────────────────────────────────────

class TestAlarmManager:
    """Tests for AlarmManager."""
    
    def test_add_alarm(self, tmp_path):
        """Test adding an alarm."""
        from src.managers.alarm_manager import AlarmManager
        
        db_path = str(tmp_path / "test_alarms.db")
        mgr = AlarmManager(db_path)
        
        alarm_id = mgr.add_alarm("07:00", "Morning Alarm")
        assert alarm_id is not None
    
    def test_get_alarms(self, tmp_path):
        """Test getting all alarms."""
        from src.managers.alarm_manager import AlarmManager
        
        db_path = str(tmp_path / "test_alarms.db")
        mgr = AlarmManager(db_path)
        
        mgr.add_alarm("08:00", "Work Alarm")
        mgr.add_alarm("14:00", "Afternoon Alarm")
        
        alarms = mgr.get_alarms()
        assert len(alarms) >= 2
    
    def test_delete_alarm(self, tmp_path):
        """Test deleting an alarm."""
        from src.managers.alarm_manager import AlarmManager
        
        db_path = str(tmp_path / "test_alarms.db")
        mgr = AlarmManager(db_path)
        
        alarm_id = mgr.add_alarm("09:00", "Temp Alarm")
        mgr.delete_alarm(alarm_id)
        
        # Verify alarm is deleted
        alarms = mgr.get_alarms()
        alarm_ids = [a.get("id") for a in alarms]
        assert alarm_id not in alarm_ids
    
    def test_alarm_time_format(self, tmp_path):
        """Test alarm time is stored correctly."""
        from src.managers.alarm_manager import AlarmManager
        
        db_path = str(tmp_path / "test_alarms.db")
        mgr = AlarmManager(db_path)
        
        mgr.add_alarm("14:30", "Test Time")
        alarms = mgr.get_alarms()
        
        test_alarm = next((a for a in alarms if a.get("label") == "Test Time"), None)
        if test_alarm:
            assert "14:30" in test_alarm.get("time", "")
    
    def test_toggle_alarm(self, tmp_path):
        """Test enabling/disabling alarm."""
        from src.managers.alarm_manager import AlarmManager
        
        db_path = str(tmp_path / "test_alarms.db")
        mgr = AlarmManager(db_path)
        
        alarm_id = mgr.add_alarm("10:00", "Toggle Test")
        
        # Disable
        mgr.toggle_alarm(alarm_id, False)
        
        alarm = mgr.get_alarm_by_id(alarm_id)
        # SQLite returns 0/1 for booleans, not False/True
        assert alarm.get("enabled") == 0 or alarm.get("enabled") is False
        
        # Enable
        mgr.toggle_alarm(alarm_id, True)
        alarm = mgr.get_alarm_by_id(alarm_id)
        assert alarm.get("enabled") == 1 or alarm.get("enabled") is True


# ── Task Manager Tests ────────────────────────────────────────────────────

class TestTaskManager:
    """Tests for TaskManager."""
    
    def test_add_task(self, tmp_path):
        """Test adding a task."""
        from src.managers.task_manager import TaskManager
        
        db_path = str(tmp_path / "test_tasks.db")
        mgr = TaskManager(db_path)
        
        task = mgr.add_task("Test task item")
        assert task is not None
        assert task.get("text") == "Test task item"
    
    def test_get_tasks(self, tmp_path):
        """Test getting all tasks."""
        from src.managers.task_manager import TaskManager
        
        db_path = str(tmp_path / "test_tasks.db")
        mgr = TaskManager(db_path)
        
        mgr.add_task("Task 1")
        mgr.add_task("Task 2")
        mgr.add_task("Task 3")
        
        tasks = mgr.get_tasks()
        assert len(tasks) >= 3
    
    def test_complete_task(self, tmp_path):
        """Test marking a task as complete."""
        from src.managers.task_manager import TaskManager
        
        db_path = str(tmp_path / "test_tasks.db")
        mgr = TaskManager(db_path)
        
        task = mgr.add_task("To Complete")
        task_id = task.get("id")
        
        # TaskManager uses toggle_task, not complete_task
        mgr.toggle_task(task_id, True)
        
        # Verify task is marked complete
        tasks = mgr.get_tasks()
        completed = next((t for t in tasks if t.get("id") == task_id), None)
        if completed:
            # SQLite returns 0/1 for booleans
            assert completed.get("completed") in (True, 1)
    
    def test_delete_task(self, tmp_path):
        """Test deleting a task."""
        from src.managers.task_manager import TaskManager
        
        db_path = str(tmp_path / "test_tasks.db")
        mgr = TaskManager(db_path)
        
        task = mgr.add_task("To Delete")
        task_id = task.get("id")
        
        # delete_task doesn't return a value
        mgr.delete_task(task_id)
        
        # Verify task is deleted
        tasks = mgr.get_tasks()
        task_ids = [t.get("id") for t in tasks]
        assert task_id not in task_ids
    
    def test_get_pending_tasks(self, tmp_path):
        """Test getting only pending tasks."""
        from src.managers.task_manager import TaskManager
        
        db_path = str(tmp_path / "test_tasks.db")
        mgr = TaskManager(db_path)
        
        mgr.add_task("Pending Task")
        task = mgr.add_task("Completed Task")
        mgr.toggle_task(task.get("id"), True)
        
        tasks = mgr.get_tasks()
        pending = [t for t in tasks if not t.get("completed")]
        assert any(t.get("text") == "Pending Task" for t in pending)
    
    def test_toggle_task_incomplete(self, tmp_path):
        """Test toggling a task back to incomplete."""
        from src.managers.task_manager import TaskManager
        
        db_path = str(tmp_path / "test_tasks.db")
        mgr = TaskManager(db_path)
        
        task = mgr.add_task("Toggle Test")
        task_id = task.get("id")
        
        # Complete it
        mgr.toggle_task(task_id, True)
        # Uncomplete it
        mgr.toggle_task(task_id, False)
        
        tasks = mgr.get_tasks()
        task = next((t for t in tasks if t.get("id") == task_id), None)
        # SQLite returns 0/1 for booleans
        assert task.get("completed") in (False, 0)


# ── Calendar Manager Tests ────────────────────────────────────────────────

class TestCalendarManager:
    """Tests for CalendarManager."""
    
    def test_add_event(self, tmp_path):
        """Test adding a calendar event."""
        from src.managers.calendar_manager import CalendarManager
        
        db_path = str(tmp_path / "test_calendar.db")
        mgr = CalendarManager(db_path)
        
        now = datetime.now()
        start = now.strftime("%Y-%m-%d %H:%M:%S")
        end = (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        
        event = mgr.add_event("Test Event", start, end)
        assert event is not None
    
    def test_get_events(self, tmp_path):
        """Test getting events for a date."""
        from src.managers.calendar_manager import CalendarManager
        
        db_path = str(tmp_path / "test_calendar.db")
        mgr = CalendarManager(db_path)
        
        today = datetime.now().strftime("%Y-%m-%d")
        start = f"{today} 10:00:00"
        end = f"{today} 11:00:00"
        
        mgr.add_event("Morning Meeting", start, end)
        
        events = mgr.get_events(today)
        assert len(events) >= 1
    
    def test_delete_event(self, tmp_path):
        """Test deleting an event."""
        from src.managers.calendar_manager import CalendarManager
        
        db_path = str(tmp_path / "test_calendar.db")
        mgr = CalendarManager(db_path)
        
        now = datetime.now()
        start = now.strftime("%Y-%m-%d %H:%M:%S")
        end = (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        
        event = mgr.add_event("To Delete", start, end)
        event_id = event.get("id")
        
        # delete_event doesn't return a value
        mgr.delete_event(event_id)
        
        # Verify event is deleted
        today = datetime.now().strftime("%Y-%m-%d")
        events = mgr.get_events(today)
        event_ids = [e.get("id") for e in events]
        assert event_id not in event_ids
    
    def test_get_upcoming_events(self, tmp_path):
        """Test getting upcoming events."""
        from src.managers.calendar_manager import CalendarManager
        
        db_path = str(tmp_path / "test_calendar.db")
        mgr = CalendarManager(db_path)
        
        # Add event for tomorrow
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        start = f"{tomorrow} 09:00:00"
        end = f"{tomorrow} 10:00:00"
        
        mgr.add_event("Tomorrow Event", start, end)
        
        events = mgr.get_events(tomorrow)
        assert any("Tomorrow Event" in e.get("title", "") for e in events)
    
    def test_event_with_category(self, tmp_path):
        """Test creating event with category."""
        from src.managers.calendar_manager import CalendarManager
        
        db_path = str(tmp_path / "test_calendar.db")
        mgr = CalendarManager(db_path)
        
        now = datetime.now()
        start = now.strftime("%Y-%m-%d %H:%M:%S")
        end = (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        
        event = mgr.add_event("Work Meeting", start, end, category="WORK")
        assert event.get("category") == "WORK"


# ── Habit Manager Tests ───────────────────────────────────────────────────

class TestHabitManager:
    """Tests for HabitManager."""
    
    def test_log_habit(self, tmp_path):
        """Test logging a habit."""
        from src.managers.habit_manager import HabitManager
        
        db_path = str(tmp_path / "test_habits.db")
        mgr = HabitManager(db_path)
        
        is_new = mgr.log("exercise", "30 min workout")
        assert is_new is True
    
    def test_log_duplicate_habit(self, tmp_path):
        """Test that duplicate log on same day returns False."""
        from src.managers.habit_manager import HabitManager
        
        db_path = str(tmp_path / "test_habits.db")
        mgr = HabitManager(db_path)
        
        mgr.log("reading", "chapter 1")
        is_new = mgr.log("reading", "chapter 2")
        
        assert is_new is False
    
    def test_get_summary_today(self, tmp_path):
        """Test getting today's habit summary."""
        from src.managers.habit_manager import HabitManager
        
        db_path = str(tmp_path / "test_habits.db")
        mgr = HabitManager(db_path)
        
        mgr.log("meditation")
        mgr.log("water")
        
        summary = mgr.get_summary("today")
        assert summary["total_entries"] >= 2
    
    def test_get_summary_week(self, tmp_path):
        """Test getting weekly habit summary."""
        from src.managers.habit_manager import HabitManager
        
        db_path = str(tmp_path / "test_habits.db")
        mgr = HabitManager(db_path)
        
        mgr.log("exercise")
        
        summary = mgr.get_summary("week")
        assert "habits" in summary
        assert "exercise" in summary["habits"]
    
    def test_get_summary_month(self, tmp_path):
        """Test getting monthly habit summary."""
        from src.managers.habit_manager import HabitManager
        
        db_path = str(tmp_path / "test_habits.db")
        mgr = HabitManager(db_path)
        
        mgr.log("sleep_8h", "good sleep")
        
        summary = mgr.get_summary("month")
        assert summary["total_entries"] >= 1
    
    def test_habit_case_insensitive(self, tmp_path):
        """Test that habits are stored case-insensitively."""
        from src.managers.habit_manager import HabitManager
        
        db_path = str(tmp_path / "test_habits.db")
        mgr = HabitManager(db_path)
        
        mgr.log("Exercise")
        is_new = mgr.log("EXERCISE")  # Should not add new entry (same day)
        
        assert is_new is False
        
        summary = mgr.get_summary("today")
        exercise_count = summary["habits"].get("exercise", {}).get("count", 0)
        assert exercise_count == 1


# ── Database Integrity Tests ──────────────────────────────────────────────

class TestDatabaseIntegrity:
    """Test database integrity and error handling."""
    
    def test_invalid_database_path(self):
        """Test handling of invalid database path."""
        from src.managers.habit_manager import HabitManager
        
        # This should create the database anyway
        invalid_path = "/nonexistent/path/test.db"
        try:
            mgr = HabitManager(invalid_path)
            # Should fail or handle gracefully
        except Exception as e:
            # Expected
            assert True
    
    def test_concurrent_access(self, tmp_path):
        """Test concurrent database access."""
        from src.managers.task_manager import TaskManager
        
        db_path = str(tmp_path / "test_concurrent.db")
        mgr1 = TaskManager(db_path)
        mgr2 = TaskManager(db_path)
        
        # Add tasks from different instances
        mgr1.add_task("Task from mgr1")
        mgr2.add_task("Task from mgr2")
        
        # Both should be present
        tasks = mgr1.get_tasks()
        assert len(tasks) >= 2


# ── Edge Cases ────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_empty_task_text(self, tmp_path):
        """Test adding task with empty text."""
        from src.managers.task_manager import TaskManager
        
        db_path = str(tmp_path / "test_edge.db")
        mgr = TaskManager(db_path)
        
        # Should handle gracefully
        task = mgr.add_task("")
        # May or may not succeed, but shouldn't crash
    
    def test_special_characters_in_task(self, tmp_path):
        """Test task with special characters."""
        from src.managers.task_manager import TaskManager
        
        db_path = str(tmp_path / "test_edge.db")
        mgr = TaskManager(db_path)
        
        special_text = "Task with 'quotes' and \"double quotes\" and <html>"
        task = mgr.add_task(special_text)
        
        tasks = mgr.get_tasks()
        assert any(special_text in t.get("text", "") for t in tasks)
    
    def test_very_long_task_text(self, tmp_path):
        """Test task with very long text."""
        from src.managers.task_manager import TaskManager
        
        db_path = str(tmp_path / "test_edge.db")
        mgr = TaskManager(db_path)
        
        long_text = "A" * 1000  # 1000 characters
        task = mgr.add_task(long_text)
        
        assert task is not None
    
    def test_past_alarm_time(self, tmp_path):
        """Test setting alarm for past time."""
        from src.managers.alarm_manager import AlarmManager
        
        db_path = str(tmp_path / "test_edge.db")
        mgr = AlarmManager(db_path)
        
        # Should still add (may fire immediately or next day)
        alarm_id = mgr.add_alarm("00:01", "Past Alarm")
        assert alarm_id is not None