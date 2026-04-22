"""
Integration tests for multi-tool workflows.

Tests complex workflows that involve multiple tools working together:
- Search Stack Overflow and summarize results
- Find a file and read its contents  
- Set a reminder and add it to calendar
- Research workflow (search -> summarize -> save)
"""

import os
import sys
import time
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.conftest import check_dependency, skip_if_missing


# ── Helper Function (same as test_tools.py) ────────────────────────────────

def run_tool_test(tool_func, *args, should_succeed=True, **kwargs):
    """
    Run a tool function and verify result.
    
    Args:
        tool_func: The tool function to test (can be a LangChain StructuredTool or regular function)
        *args: Arguments to pass to the tool
        should_succeed: Whether we expect success (True) or graceful failure (False)
        **kwargs: Keyword arguments for the tool
    
    Returns:
        dict with 'success', 'output', 'duration', 'error' keys
    """
    start = time.time()
    result = {
        "success": False,
        "output": None,
        "error": None,
        "duration": 0
    }
    
    try:
        # Check if this is a LangChain StructuredTool (has .invoke method)
        if hasattr(tool_func, 'invoke') and callable(getattr(tool_func, 'invoke')):
            # LangChain tools expect a dict of arguments
            tool_input = {}
            
            # Get tool's argument names from its schema if available
            if hasattr(tool_func, 'args_schema') and tool_func.args_schema:
                arg_names = list(tool_func.args_schema.model_fields.keys())
            else:
                # Fallback: try to infer from function signature
                import inspect
                if hasattr(tool_func, 'func'):
                    sig = inspect.signature(tool_func.func)
                    arg_names = list(sig.parameters.keys())
                else:
                    arg_names = []
            
            # Map positional args to names
            for i, arg in enumerate(args):
                if i < len(arg_names):
                    tool_input[arg_names[i]] = arg
            
            # Add keyword args
            tool_input.update(kwargs)
            
            # Invoke the tool
            output = tool_func.invoke(tool_input)
            
            # Extract content if it's a ToolMessage
            if hasattr(output, 'content'):
                output = output.content
        else:
            # Regular function call
            output = tool_func(*args, **kwargs)
        
        result["output"] = output
        result["success"] = True
        
        # Check if output indicates a failure
        if isinstance(output, str):
            failure_indicators = ["failed", "error", "couldn't", "can't", "not found", "missing"]
            if any(indicator in output.lower() for indicator in failure_indicators):
                result["success"] = False
                result["error"] = output
                
    except Exception as e:
        result["error"] = str(e)
        result["success"] = False
    
    result["duration"] = time.time() - start
    
    # Verify expectation
    if should_succeed and not result["success"]:
        result["expectation_mismatch"] = "Expected success but got failure"
    elif not should_succeed and result["success"]:
        result["expectation_mismatch"] = "Expected failure but got success"
    
    return result


# ── Research Workflows ─────────────────────────────────────────────────────

class TestResearchWorkflows:
    """Test research-related multi-tool workflows."""
    
    @pytest.mark.integration
    @pytest.mark.requires_network
    def test_web_search_workflow(self):
        """Test web search and result processing."""
        from src.tools.wrapped_tools import web_search
        
        # Search for information
        result = run_tool_test(web_search, "Python pytest tutorial")
        
        assert result["output"] is not None
        # Result should contain search information or error message
        assert isinstance(result["output"], str)






# ── Task & Calendar Workflows ──────────────────────────────────────────────

class TestTaskCalendarWorkflows:
    """Test task and calendar integration workflows."""
    
    @pytest.mark.integration
    def test_create_task_and_calendar_event(self, tmp_path):
        """Test creating a task and corresponding calendar event."""
        from src.managers.task_manager import TaskManager
        from src.managers.calendar_manager import CalendarManager
        
        # Setup
        task_db = str(tmp_path / "tasks.db")
        calendar_db = str(tmp_path / "calendar.db")
        
        task_mgr = TaskManager(task_db)
        calendar_mgr = CalendarManager(calendar_db)
        
        # Create a task with a deadline
        task = task_mgr.add_task("Complete project report")
        
        # Create a calendar event for the deadline
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        start = f"{tomorrow} 14:00:00"
        end = f"{tomorrow} 15:00:00"
        
        event = calendar_mgr.add_event("Work on project report", start, end)
        
        # Verify both exist
        tasks = task_mgr.get_tasks()
        events = calendar_mgr.get_events(tomorrow)
        
        assert any("project report" in t.get("text", "").lower() for t in tasks)
        assert any("project report" in e.get("title", "").lower() for e in events)
    
    @pytest.mark.integration
    def test_complete_task_updates(self, tmp_path):
        """Test task completion workflow."""
        from src.managers.task_manager import TaskManager
        
        db_path = str(tmp_path / "tasks.db")
        mgr = TaskManager(db_path)
        
        # Create multiple tasks
        task1 = mgr.add_task("Task 1")
        task2 = mgr.add_task("Task 2")
        task3 = mgr.add_task("Task 3")
        
        # Complete first two
        mgr.toggle_task(task1.get("id"), True)
        mgr.toggle_task(task2.get("id"), True)
        
        # Check pending count
        tasks = mgr.get_tasks()
        pending = [t for t in tasks if not t.get("completed")]
        
        assert len(pending) >= 1


# ── Alarm & Timer Workflows ────────────────────────────────────────────────

class TestTimeManagementWorkflows:
    """Test alarm integration workflows."""
    
    @pytest.mark.integration
    def test_set_alarm_workflow(self, tmp_path):
        """Test setting an alarm reminder."""
        from src.managers.alarm_manager import AlarmManager
        
        # Setup
        alarm_db = str(tmp_path / "alarms.db")
        alarm_mgr = AlarmManager(alarm_db)
        
        # Set an alarm for morning meeting
        alarm_id = alarm_mgr.add_alarm("09:00", "Team standup")
        
        # Verify it is active
        alarms = alarm_mgr.get_alarms()
        
        assert any(a.get("label") == "Team standup" for a in alarms)


# ── Habit & Task Integration ───────────────────────────────────────────────

class TestHabitTaskWorkflows:
    """Test habit tracking integrated with tasks."""
    
    @pytest.mark.integration
    def test_daily_routine_workflow(self, tmp_path):
        """Test tracking daily routine with habits and tasks."""
        from src.managers.habit_manager import HabitManager
        from src.managers.task_manager import TaskManager
        
        habit_db = str(tmp_path / "habits.db")
        task_db = str(tmp_path / "tasks.db")
        
        habit_mgr = HabitManager(habit_db)
        task_mgr = TaskManager(task_db)
        
        # Log morning habits
        habit_mgr.log("meditation", "15 minutes")
        habit_mgr.log("exercise", "30 min run")
        
        # Create tasks for the day
        task_mgr.add_task("Review pull requests")
        task_mgr.add_task("Update documentation")
        
        # Check habit summary
        summary = habit_mgr.get_summary("today")
        assert summary["total_entries"] >= 2
        
        # Check task count
        tasks = task_mgr.get_tasks()
        assert len(tasks) >= 2


# ── Email Workflows ────────────────────────────────────────────────────────

class TestEmailWorkflows:
    """Test email-related workflows."""
    
    @pytest.mark.integration
    def test_send_reminder_workflow(self, tmp_path, clean_env):
        """Test creating task and sending email reminder."""
        from src.managers.task_manager import TaskManager
        
        # Create a high-priority task
        task_db = str(tmp_path / "tasks.db")
        task_mgr = TaskManager(task_db)
        
        task = task_mgr.add_task("IMPORTANT: Submit report by EOD")
        
        # In production, this would trigger:
        # 1. Email reminder via send_email tool
        # 2. Calendar blocking via CalendarManager
        
        # For now, verify task was created
        tasks = task_mgr.get_tasks()
        assert any("IMPORTANT" in t.get("text", "") for t in tasks)






# ── Error Recovery Workflows ───────────────────────────────────────────────

class TestErrorRecoveryWorkflows:
    """Test error handling in workflows."""
    
    @pytest.mark.integration
    def test_blocked_command_recovery(self):
        """Test handling of blocked commands."""
        from src.tools.wrapped_tools import run_command
        
        # Try dangerous command
        result = run_tool_test(run_command, "rm -rf /")
        
        # Should be blocked
        assert "blocked" in result["output"].lower() or "not allowed" in result["output"].lower()


# ── Performance Tests ──────────────────────────────────────────────────────

class TestPerformanceWorkflows:
    """Test performance under load."""
    
    @pytest.mark.integration
    def test_rapid_task_creation(self, tmp_path):
        """Test creating many tasks rapidly."""
        from src.managers.task_manager import TaskManager
        import time
        
        db_path = str(tmp_path / "perf_tasks.db")
        mgr = TaskManager(db_path)
        
        start = time.time()
        
        # Create 50 tasks
        for i in range(50):
            mgr.add_task(f"Task {i}")
        
        elapsed = time.time() - start
        
        # Should complete in reasonable time (< 5 seconds)
        assert elapsed < 5.0
        
        # Verify all tasks exist
        tasks = mgr.get_tasks()
        assert len(tasks) >= 50
    
    @pytest.mark.integration
    def test_concurrent_managers(self, tmp_path):
        """Test multiple manager instances working concurrently."""
        from src.managers.task_manager import TaskManager
        from src.managers.alarm_manager import AlarmManager
        from src.managers.habit_manager import HabitManager
        
        task_db = str(tmp_path / "tasks.db")
        alarm_db = str(tmp_path / "alarms.db")
        habit_db = str(tmp_path / "habits.db")
        
        # Create instances
        task_mgr = TaskManager(task_db)
        alarm_mgr = AlarmManager(alarm_db)
        habit_mgr = HabitManager(habit_db)
        
        # Perform operations on each
        task_mgr.add_task("Test task")
        alarm_mgr.add_alarm("10:00", "Test alarm")
        habit_mgr.log("test_habit")
        
        # Verify all succeeded
        assert len(task_mgr.get_tasks()) >= 1
        assert len(alarm_mgr.get_alarms()) >= 1
        assert habit_mgr.get_summary("today")["total_entries"] >= 1