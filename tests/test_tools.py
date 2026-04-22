"""
Comprehensive test suite for all assistant tools.

Tests each tool with:
- Valid inputs (success cases)
- Invalid inputs (error handling)
- Performance timing
- Graceful handling of missing dependencies
"""

import os
import sys
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.conftest import check_dependency, skip_if_missing

pytestmark = pytest.mark.side_effect


# ── Helper Functions ──────────────────────────────────────────────────────

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


# ── Core Tools Tests ──────────────────────────────────────────────────────

class TestAlarmTool:
    """Tests for set_alarm tool."""
    
    @pytest.mark.core
    def test_set_alarm_am(self):
        """Test setting alarm with AM time."""
        from src.tools.wrapped_tools import set_alarm
        
        result = run_tool_test(set_alarm, "7am", "Morning Alarm")
        assert result["success"], f"Alarm failed: {result['error']}"
        assert "alarm" in result["output"].lower()
    
    @pytest.mark.core
    def test_set_alarm_24hour(self):
        """Test setting alarm with 24-hour format."""
        from src.tools.wrapped_tools import set_alarm
        
        result = run_tool_test(set_alarm, "14:30", "Afternoon Alarm")
        assert result["success"], f"Alarm failed: {result['error']}"
    
    @pytest.mark.core
    def test_set_alarm_pm(self):
        """Test setting alarm with PM time."""
        from src.tools.wrapped_tools import set_alarm
        
        result = run_tool_test(set_alarm, "9pm", "Night Alarm")
        assert result["success"], f"Alarm failed: {result['error']}"


class TestCalendarTool:
    """Tests for create_calendar_event tool."""
    
    @pytest.mark.core
    def test_create_event_today(self):
        """Test creating event for today."""
        from src.tools.wrapped_tools import create_calendar_event
        
        result = run_tool_test(
            create_calendar_event,
            "Test Meeting",
            "today",
            "10:00",
            60
        )
        assert result["success"], f"Calendar event failed: {result['error']}"
        assert "event" in result["output"].lower()
    
    @pytest.mark.core
    def test_create_event_tomorrow(self):
        """Test creating event for tomorrow."""
        from src.tools.wrapped_tools import create_calendar_event
        
        result = run_tool_test(
            create_calendar_event,
            "Tomorrow Task",
            "tomorrow",
            "14:00"
        )
        assert result["success"], f"Calendar event failed: {result['error']}"
    
    @pytest.mark.core
    def test_create_event_no_time(self):
        """Test creating event without specific time."""
        from src.tools.wrapped_tools import create_calendar_event
        
        result = run_tool_test(
            create_calendar_event,
            "All Day Event",
            "today"
        )
        assert result["success"], f"Calendar event failed: {result['error']}"


class TestTaskTools:
    """Tests for add_task and get_tasks tools."""
    
    @pytest.mark.core
    def test_add_task(self):
        """Test adding a task."""
        from src.tools.wrapped_tools import add_task
        
        result = run_tool_test(add_task, "Test task for unit testing")
        assert result["success"], f"Add task failed: {result['error']}"
        assert "task" in result["output"].lower()
    
    @pytest.mark.core
    def test_add_empty_task(self):
        """Test adding empty task."""
        from src.tools.wrapped_tools import add_task
        
        result = run_tool_test(add_task, "   ")
        # Should handle gracefully
        assert result["output"] is not None
    
    @pytest.mark.core
    def test_get_tasks(self):
        """Test getting tasks list."""
        from src.tools.wrapped_tools import get_tasks
        
        result = run_tool_test(get_tasks)
        assert result["success"], f"Get tasks failed: {result['error']}"


class TestWebSearchTool:
    """Tests for web_search tool."""
    
    @pytest.mark.core
    @pytest.mark.requires_network
    def test_web_search_basic(self):
        """Test basic web search."""
        from src.tools.wrapped_tools import web_search
        
        result = run_tool_test(web_search, "python programming")
        assert result["success"], f"Web search failed: {result['error']}"
        assert "result" in result["output"].lower() or "python" in result["output"].lower()
    
    @pytest.mark.core
    @pytest.mark.requires_network
    def test_web_search_empty(self):
        """Test web search with empty query."""
        from src.tools.wrapped_tools import web_search
        
        result = run_tool_test(web_search, "")
        # Should handle gracefully
        assert result["output"] is not None


class TestSystemInfoTool:
    """Tests for get_system_info tool."""
    
    @pytest.mark.core
    def test_get_system_info(self):
        """Test getting system info."""
        from src.tools.wrapped_tools import get_system_info
        
        result = run_tool_test(get_system_info)
        assert result["success"], f"System info failed: {result['error']}"
        assert "time" in result["output"].lower()


class TestEmailSendTool:
    """Tests for send_email tool."""
    
    @pytest.mark.email
    def test_send_email_no_credentials(self):
        """Test email without credentials (should fail gracefully)."""
        from src.tools.wrapped_tools import send_email
        
        # Clear env temporarily
        original_addr = os.environ.get("GMAIL_ADDRESS")
        original_pass = os.environ.get("GMAIL_APP_PASSWORD")
        
        try:
            os.environ.pop("GMAIL_ADDRESS", None)
            os.environ.pop("GMAIL_APP_PASSWORD", None)
            
            result = run_tool_test(
                send_email,
                "Test Subject",
                "Test Body"
            )
            # Should fail gracefully with helpful message
            assert result["output"] is not None
        finally:
            if original_addr:
                os.environ["GMAIL_ADDRESS"] = original_addr
            if original_pass:
                os.environ["GMAIL_APP_PASSWORD"] = original_pass


class TestOpenAppTool:
    """Tests for open_app tool."""
    
    @pytest.mark.core
    def test_open_app_notepad(self):
        """Test opening notepad."""
        from src.tools.wrapped_tools import open_app
        
        result = run_tool_test(open_app, "notepad")
        # May succeed or fail depending on system
        assert result["output"] is not None
    
    @pytest.mark.core
    def test_open_app_invalid(self):
        """Test opening non-existent app."""
        from src.tools.wrapped_tools import open_app
        
        result = run_tool_test(open_app, "nonexistentapp12345")
        # Should handle gracefully
        assert result["output"] is not None




# ── Terminal Command Tests ────────────────────────────────────────────────

class TestRunCommandTool:
    """Tests for run_command tool."""
    

    @pytest.mark.file_ops
    def test_safe_command(self):
        """Test running a safe command."""
        from src.tools.wrapped_tools import run_command
        
        result = run_tool_test(run_command, "echo hello")
        assert result["success"], f"Command failed: {result['error']}"
    
    @pytest.mark.file_ops
    def test_git_status(self):
        """Test git status command."""
        from src.tools.wrapped_tools import run_command
        
        result = run_tool_test(run_command, "git --version")
        assert result["success"], f"Git command failed: {result['error']}"
    
    @pytest.mark.file_ops
    def test_blocked_command(self):
        """Test that dangerous commands are blocked."""
        from src.tools.wrapped_tools import run_command
        
        result = run_tool_test(run_command, "rm -rf /")
        assert "blocked" in result["output"].lower()
    
    @pytest.mark.file_ops
    def test_pip_list(self):
        """Test pip list command."""
        from src.tools.wrapped_tools import run_command
        
        result = run_tool_test(run_command, "pip list")
        assert result["success"], f"Pip list failed: {result['error']}"


# ── Research Tools Tests ──────────────────────────────────────────────────

# ── Habits Tools Tests ────────────────────────────────────────────────────

class TestHabitTools:
    """Tests for log_habit and get_habit_summary tools."""
    

    @pytest.mark.habits
    def test_log_habit(self, tmp_path):
        """Test logging a habit."""
        # Use temp database
        from src.managers.habit_manager import HabitManager
        
        db_path = str(tmp_path / "test_habits.db")
        mgr = HabitManager(db_path)
        
        # Test logging
        is_new = mgr.log("test_habit", "test notes")
        assert is_new, "Should be new habit entry"
        
        # Test duplicate
        is_new = mgr.log("test_habit")
        assert not is_new, "Should not be new (already logged today)"
    
    @pytest.mark.habits
    def test_get_habit_summary(self, tmp_path):
        """Test getting habit summary."""
        from src.managers.habit_manager import HabitManager
        
        db_path = str(tmp_path / "test_habits.db")
        mgr = HabitManager(db_path)
        
        # Log some habits
        mgr.log("exercise")
        mgr.log("reading")
        
        # Get summary
        summary = mgr.get_summary("today")
        assert summary["total_entries"] >= 2


# ── Email Reading Tests ───────────────────────────────────────────────────

class TestReadEmailsTool:
    """Tests for read_emails tool."""
    
    @pytest.mark.email
    @pytest.mark.requires_gmail
    def test_read_emails_unread(self):
        """Test reading unread emails."""
        pytest.skip("Requires Gmail credentials - run manually")
    
    @pytest.mark.email
    def test_read_emails_no_credentials(self):
        """Test reading emails without credentials."""
        from src.tools.wrapped_tools import read_emails
        
        # Clear credentials temporarily
        original_addr = os.environ.get("GMAIL_ADDRESS")
        original_pass = os.environ.get("GMAIL_APP_PASSWORD")
        
        try:
            os.environ.pop("GMAIL_ADDRESS", None)
            os.environ.pop("GMAIL_APP_PASSWORD", None)
            
            result = run_tool_test(read_emails, count=1)
            # Should fail gracefully
            assert "credential" in result["output"].lower() or "not" in result["output"].lower()
        finally:
            if original_addr:
                os.environ["GMAIL_ADDRESS"] = original_addr
            if original_pass:
                os.environ["GMAIL_APP_PASSWORD"] = original_pass


# ── Dependency Check Test ─────────────────────────────────────────────────

class TestDependencies:
    """Check which optional dependencies are installed."""
    
    def test_check_all_dependencies(self):
        """Report on all optional dependencies status."""
        dependencies = {
            "ddgs": "Web search (DuckDuckGo)",
            "AppOpener": "App launching",
            "requests": "HTTP requests"
        }
        
        results = []
        for module, feature in dependencies.items():
            installed = check_dependency(module)
            status = "✅ Installed" if installed else "❌ Missing"
            results.append(f"{status}: {module} ({feature})")
        
        # Print report
        print("\n" + "\n".join(results))
        
        # Always pass - this is informational
        assert True
