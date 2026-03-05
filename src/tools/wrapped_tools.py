import os
import re
from datetime import datetime, timedelta
from langchain_core.tools import tool
from src.utils.config import Config

alarm_mgr = None
memory_store = None


def get_alarm_manager():
    """
    Get or create the AlarmManager singleton.
    """
    global alarm_mgr
    if alarm_mgr is None:
        from src.managers.alarm_manager import AlarmManager
        alarm_mgr = AlarmManager()
    return alarm_mgr


def get_memory_store():
    global memory_store
    if memory_store is None:
        from src.memory import LongTermMemory
        memory_store = LongTermMemory()
    return memory_store


def parse_duration(duration_str: str) -> int:
    """
    Parse a human-readable duration string into seconds.
    
    EXAMPLES:
    - "10 minutes" → 600
    - "1 hour" → 3600
    - "90 seconds" → 90
    - "5" → 300 (defaults to minutes if no unit)
    
    Args:
        duration_str: Human-readable duration string
        
    Returns:
        Duration in seconds
    """
    duration_str = duration_str.lower().strip()
    total = 0

    # Regex patterns for different time units
    # Each pattern captures a number followed by optional unit
    patterns = [
        (r'(\d+)\s*h(?:our)?s?', 3600),      # hours
        (r'(\d+)\s*m(?:in(?:ute)?s?)?', 60), # minutes
        (r'(\d+)\s*s(?:ec(?:ond)?s?)?', 1),  # seconds
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, duration_str)
        if match:
            total += int(match.group(1)) * multiplier

    # If no units found, assume minutes
    if total == 0:
        nums = re.findall(r'\d+', duration_str)
        if nums:
            total = int(nums[0]) * 60
    return total


def normalize_time(time_str: str) -> str:
    """
    Normalize a time string to 24-hour HH:MM format.
    
    EXAMPLES:
    - "7am" → "07:00"
    - "2:30pm" → "14:30"
    - "14:30" → "14:30" (already normalized)
    - "12am" → "00:00" (midnight)
    - "12pm" → "12:00" (noon)
    
    Args:
        time_str: Time in various formats
        
    Returns:
        Time in HH:MM (24-hour format)
    """
    time_str = time_str.lower().strip()
    # Match: hour, optional minutes, optional am/pm
    match = re.match(r'(\d{1,2}):?(\d{2})?\s*(am|pm)?', time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        period = match.group(3)
        
        # Convert 12-hour to 24-hour
        if period == 'pm' and hour < 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0  # 12am = midnight
            
        return f"{hour:02d}:{minute:02d}"
    return time_str


def parse_date(date_str: str) -> str:
    """
    Parse a date string into YYYY-MM-DD format.
    
    EXAMPLES:
    - "today" → today's date
    - "tomorrow" → tomorrow's date
    - "next monday" → next Monday's date
    - "2025-03-15" → "2025-03-15" (already normalized)
    
    Args:
        date_str: Date in various formats
        
    Returns:
        Date in YYYY-MM-DD format
    """
    date_str = date_str.lower().strip()
    
    # Try ISO format first
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        pass

    today = datetime.now()
    
    # Relative dates
    if date_str in ("today", ""):
        return today.strftime("%Y-%m-%d")
    if date_str == "tomorrow":
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    # Day names (e.g., "monday", "next friday")
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day in enumerate(days):
        if day in date_str:
            ahead = i - today.weekday()
            if ahead <= 0:
                ahead += 7  # Move to next week
            if "next" in date_str:
                ahead += 7  # Skip a week
            return (today + timedelta(days=ahead)).strftime("%Y-%m-%d")

    return today.strftime("%Y-%m-%d")


# PRODUCTIVITY TOOLS

@tool
def set_alarm(time: str, label: str = "Alarm") -> str:
    """
    Set a clock alarm to ring at a specific time of day.

    USE when the user says:
    - "wake me up at 7am", "set an alarm for 8:30", "remind me at 6pm"
    - "alert me at noon", "alarm for 9", "set a reminder for 10pm"

    DO NOT use for:
    - Adding tasks or calendar events — use add_task or create_calendar_event

    Args:
        time: Time of day in any format ("7am", "14:30", "6:30 pm")
        label: Optional alarm label (default: "Alarm")
        
    Returns:
        Confirmation message or error
    """
    try:
        mgr = get_alarm_manager()
        normalized = normalize_time(time)
        
        # Add alarm to SQLite database
        alarm_id = mgr.add_alarm(normalized, label)

        if alarm_id:
            # Register with Windows Task Scheduler for reliable delivery
            # This ensures alarm fires even if the app is closed
            try:
                from src.scheduler_windows import WindowsScheduler
                task_name = WindowsScheduler.register_alarm(alarm_id, normalized, label)
                if task_name:
                    mgr.set_scheduled_task(alarm_id, task_name)
            except:
                pass  # Windows scheduler is optional
                
            return f"Alarm set for {normalized}" + (f" ({label})" if label != "Alarm" else "") + "."
        return "Failed to set alarm."
    except Exception as e:
        return f"Failed to set alarm: {e}"


@tool
def web_search(query: str) -> str:
    """
    Search the internet for real-time information.

    USE when the user asks for:
    - Current/recent information: "latest news about X", "what happened with X", Datese
    - Weather: "weather in [city]", "temperature in [place] today"
    - Specific facts you don't know with certainty: stats, prices, scores
    - External content: "find articles about X", "look up X"

    DO NOT use for:
    - Casual conversation or greetings ("hello", "how are you")
    - Questions you can answer from your own knowledge (history, definitions)
    - Tasks that have dedicated tools (alarms, calendar, email, apps)
    - When the user hasn't asked you to search for anything

    Args:
        query: Search query string
        
    Returns:
        Top 3 search results with titles and snippets
    """
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            # Get top 5 results, return top 3
            results = list(ddgs.text(query, max_results=5))

        if results:
            lines = [f"Results for '{query}':"]
            for i, r in enumerate(results[:3], 1):
                lines.append(f"{i}. {r.get('title', '')}")
                body = r.get("body", "")[:200]  # Truncate long snippets
                if body:
                    lines.append(f"   {body}")
            return "\n".join(lines)
        return f"No results for '{query}'."
    except Exception as e:
        return f"Search failed: {e}"


@tool
def get_system_info() -> str:
    """
    Get a full status overview: current date/time, scheduled alarms, today's
    calendar events, and pending tasks.

    USE when the user asks:
    - "what time is it?", "what's the date?", "what day is today?"
    - "what's my schedule?", "what's on today?", "give me a status update"
    - "what do I have going on?", "what's happening today?"

    DO NOT use for:
    - Only adding things (use add_task / set_alarm / create_calendar_event)
    - Only reading tasks (use get_tasks if no schedule context is needed)

    Returns:
        Multi-line string with time, alarms, calendar events, and tasks
    """
    try:
        parts = []
        now = datetime.now()
        parts.append(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")

        # Get alarms from local SQLite
        try:
            alarms = get_alarm_manager().get_alarms()
            if alarms:
                parts.append("Alarms: " + ", ".join(f"{a['label']} at {a['time']}" for a in alarms[:5]))
            else:
                parts.append("No alarms.")
        except:
            pass

        # Get Google Calendar events for today
        try:
            from src.tools.google.calendar_tools import get_upcoming_events as _get_upcoming_events
            events = _get_upcoming_events(max_results=5)
            today_str = now.strftime("%Y-%m-%d")
            today_events = [e for e in events if e["start"].startswith(today_str)]
            if today_events:
                parts.append("Today: " + ", ".join(f"{e['title']} at {e['start']}" for e in today_events))
            else:
                parts.append("No events today.")
        except:
            parts.append("Calendar unavailable.")

        # Get Google Tasks
        try:
            from src.tools.google.tasks_tools import get_google_tasks as _get_google_tasks
            tasks = _get_google_tasks()
            if tasks:
                parts.append(f"Tasks ({len(tasks)}): " + ", ".join(t['title'] for t in tasks[:5]))
            else:
                parts.append("No pending tasks.")
        except:
            parts.append("Tasks unavailable.")

        return "\n".join(parts)
    except Exception as e:
        return f"Failed to get info: {e}"


# =============================================================================
# SYSTEM CONTROL TOOLS
# =============================================================================

@tool
def open_app(app_name: str) -> str:
    """
    Launch a desktop application by name.

    USE when the user says:
    - "open [app]", "launch [app]", "start [app]", "run [app]"
    - Examples: "open Chrome", "start Spotify", "launch Discord",
      "open VS Code", "run Notepad", "start Steam"

    DO NOT use for:
    - Shell commands (use run_command)
    - Opening files (use run_command with the file path)

    Args:
        app_name: Name of the application to launch
        
    Returns:
        Confirmation message or error
    """
    import subprocess
    
    # Common app name aliases - maps user input to actual Windows app names
    APP_ALIASES = {
        "spotify": "Spotify",
        "camera": "Windows Camera",
        "chrome": "Google Chrome",
        "firefox": "Firefox",
        "edge": "Microsoft Edge",
        "vscode": "Visual Studio Code",
        "vs code": "Visual Studio Code",
        "code": "Visual Studio Code",
        "notepad": "Notepad",
        "calculator": "Calculator",
        "calc": "Calculator",
        "discord": "Discord",
        "steam": "Steam",
        "vlc": "VLC",
        "word": "Microsoft Word",
        "excel": "Microsoft Excel",
        "powerpoint": "Microsoft PowerPoint",
        "outlook": "Microsoft Outlook",
        "teams": "Microsoft Teams",
        "zoom": "Zoom",
        "slack": "Slack",
        "terminal": "Windows Terminal",
        "cmd": "Command Prompt",
        "command prompt": "Command Prompt",
        "powershell": "Windows PowerShell",
        "settings": "Settings",
        "control panel": "Control Panel",
        "file explorer": "File Explorer",
        "explorer": "File Explorer",
        "photos": "Microsoft Photos",
        "paint": "Paint",
        "store": "Microsoft Store",
        "music": "Windows Media Player",
        "media player": "Windows Media Player",
    }
    
    # Normalize app name and check aliases
    app_name_lower = app_name.lower().strip()
    resolved_name = APP_ALIASES.get(app_name_lower, app_name)
    
    # Method 1: Try AppOpener (best for Windows apps)
    try:
        from AppOpener import open as app_open, close as app_close
        result = app_open(resolved_name, match_closest=True, output=True)
        # AppOpener returns a tuple (success_bool, output_str) when output=True
        if result and result[0]:
            return f"Opened {resolved_name}."
        # If AppOpener failed but didn't raise exception, try fallback
    except ImportError:
        pass  # AppOpener not installed, use fallback
    except Exception:
        pass  # AppOpener failed, use fallback
    
    # Method 2: Try Windows 'start' command with subprocess.run for better error capture
    try:
        result = subprocess.run(
            f'start "" "{resolved_name}"',
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        # start command returns 0 even if app not found, so we can't rely on returncode
        # But at least we tried - return success
        return f"Opened {resolved_name}."
    except subprocess.TimeoutExpired:
        return f"Timeout while trying to open {resolved_name}."
    except Exception as e:
        pass  # Try next method
    
    # Method 3: Try common installation paths for known apps
    common_paths = {
        "spotify": [
            os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Spotify\Spotify.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
        ],
        "chrome": [
            os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ],
        "firefox": [
            os.path.expandvars(r"%PROGRAMFILES%\Mozilla Firefox\firefox.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Mozilla Firefox\firefox.exe"),
        ],
        "discord": [
            os.path.expandvars(r"%LOCALAPPDATA%\Discord\app-*\Discord.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Discord.exe"),
        ],
        "visual studio code": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\Microsoft VS Code\Code.exe"),
        ],
    }
    
    # Check if we have known paths for this app
    for app_key, paths in common_paths.items():
        if app_key in app_name_lower:
            for path in paths:
                # Handle wildcards (e.g., app-*)
                if "*" in path:
                    import glob
                    matches = glob.glob(path)
                    if matches:
                        path = matches[0]
                    else:
                        continue
                
                if os.path.exists(path):
                    try:
                        subprocess.Popen([path], shell=False)
                        return f"Opened {resolved_name}."
                    except Exception:
                        continue
    
    # Method 4: Try using 'where' command to find executable
    try:
        where_result = subprocess.run(
            f'where {resolved_name}',
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        if where_result.returncode == 0 and where_result.stdout.strip():
            exe_path = where_result.stdout.strip().split('\n')[0]
            subprocess.Popen([exe_path], shell=False)
            return f"Opened {resolved_name}."
    except Exception:
        pass
    
    # All methods failed
    suggestions = []
    for alias in APP_ALIASES:
        if app_name_lower in alias or alias in app_name_lower:
            suggestions.append(APP_ALIASES[alias])
    
    error_msg = f"Couldn't find or open '{app_name}'."
    if suggestions:
        error_msg += f" Did you mean: {', '.join(suggestions[:3])}?"
    else:
        error_msg += " Try specifying the full app name or installing AppOpener: pip install AppOpener"
    
    return error_msg


@tool
def run_command(command: str) -> str:
    """
    Execute a shell/terminal command and return its output.

    USE when the user asks to:
    - Run a specific terminal command: "run 'dir'", "execute 'ipconfig'"
    - Check system info via CLI: "what's my IP?", "check disk space"
    - Run a Python script: "run my_script.py"

    DO NOT use for:
    - Opening apps (use open_app)
    - Anything the user didn't explicitly ask to run
    - Destructive commands are blocked (rm, del, format, shutdown, etc.)

    Args:
        command: Shell command to execute
        
    Returns:
        Command output (up to 500 chars) or error message
    """
    import subprocess

    # SAFETY: Block potentially destructive commands
    # This prevents accidental data loss or system damage
    blocked = ["rm ", "del ", "format", "rmdir", "shutdown", "restart",
               "reg delete", "taskkill", "> nul", "mkfs", "dd if="]
    cmd_lower = command.lower()
    for b in blocked:
        if b in cmd_lower:
            return f"Blocked: '{command}' looks destructive. Won't run it."

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,  # Prevent hanging on long commands
            cwd=Config.BASE_DIR
        )
        output = result.stdout.strip()
        errors = result.stderr.strip()

        if result.returncode != 0 and errors:
            return f"Command failed:\n{errors[:500]}"

        if output:
            return output[:500] if len(output) > 500 else output
        return "Command ran successfully (no output)."

    except subprocess.TimeoutExpired:
        return "Command timed out (10s limit)."
    except Exception as e:
        return f"Failed to run command: {str(e)[:200]}"


# =============================================================================
# MEMORY TOOLS
# =============================================================================

@tool
def save_memory(content: str, category: str = "other") -> str:
    """
    Save an important fact about the user for future reference.

    USE when the user:
    - Shares a preference: "I prefer dark mode", "I like my coffee black"
    - Shares personal details: "my name is X", "I live in Y"
    - Mentions their schedule: "I wake up at 7am", "my meeting is at 3pm"
    - Says "remember that" or "don't forget this"
    - Mentions current projects or interests

    The saved fact persists across sessions and restarts.
    Automatically updates if a similar fact already exists.

    DO NOT ask for permission — just save it quietly.

    Args:
        content: The fact to remember (e.g., "User's name is Mohit")
        category: Type of fact - "name", "location", "preference", 
                  "schedule", "project", "other"
        
    Returns:
        Confirmation message
    """
    try:
        store = get_memory_store()
        memory_id = store.save(content, category)
        if memory_id:
            return f"Remembered: {content}"
        return "Failed to save memory."
    except Exception as e:
        return f"Failed to save memory: {e}"


@tool
def get_user_context(query: str = "") -> str:
    """
    Look up stored memories about the user.

    USE when you need to:
    - Recall specific information: "what's the user's name?"
    - Check preferences: "do they prefer Celsius or Fahrenheit?"
    - Find related facts: search for "location" or "preference"

    DO NOT use for:
    - General conversation (just respond naturally)
    - When the user hasn't asked about their stored information

    Args:
        query: Optional search term to filter memories (empty = all memories)
        
    Returns:
        Formatted list of stored facts about the user
    """
    try:
        store = get_memory_store()
        if query:
            memories = store.search(query)
            if not memories:
                return f"No memories found matching '{query}'."
            lines = [f"Memories matching '{query}':"]
            for m in memories:
                lines.append(f"- {m['content']}")
            return "\n".join(lines)
        else:
            context = store.get_context_string()
            return context if context else "No memories stored yet."
    except Exception as e:
        return f"Failed to retrieve memories: {e}"


from src.tools.google.calendar_tools import (
    create_calendar_event as _create_calendar_event,
    get_upcoming_events as _get_upcoming_events,
    delete_calendar_event as _delete_calendar_event,
)
from src.tools.google.tasks_tools import (
    add_google_task as _add_google_task,
    get_google_tasks as _get_google_tasks,
    complete_google_task as _complete_google_task,
    delete_google_task as _delete_google_task,
)
from src.tools.google.gmail_tools import (
    send_gmail as _send_gmail,
    read_unread_emails as _read_unread_emails,
    search_emails as _search_emails,
    mark_as_read as _mark_as_read,
)


@tool
def create_calendar_event(title: str, start_time: str, end_time: str, description: str = "") -> str:
    """
    Create a Google Calendar event.

    USE when the user says:
    - "schedule a meeting", "book an appointment", "add an event"
    - "put [X] on the calendar", "plan a call at [time]"
    - "I have a class on Friday", "add a deadline for tomorrow"

    DO NOT use for:
    - Simple to-dos without a specific time (use add_task)
    - Setting alarms (use set_alarm)
    - Reading the calendar (use get_upcoming_events)

    Args:
        title: Name of the event.
        start_time: ISO format "2025-03-15T10:00:00" (IST assumed)
        end_time: ISO format "2025-03-15T11:00:00" (IST assumed)
        description: Optional event description.

    Returns:
        Confirmation with Google Calendar link or error
    """
    result = _create_calendar_event(title, start_time, end_time, description)
    if result["success"]:
        return f"Event '{title}' created. Link: {result['link']}"
    return f"Failed to create event: {result.get('error', 'unknown error')}"


@tool
def get_upcoming_events(max_results: int = 5) -> str:
    """
    Get upcoming Google Calendar events.

    USE when the user says:
    - "what's on my calendar?", "show my schedule", "any upcoming meetings?"
    - "what do I have this week?", "what's next on my calendar?"

    DO NOT use for:
    - Creating events (use create_calendar_event)
    - Full status overview (use get_system_info)

    Args:
        max_results: Number of events to return (default 5).

    Returns:
        List of upcoming events with start times
    """
    events = _get_upcoming_events(max_results)
    if not events:
        return "No upcoming events found."
    return "\n".join([f"• {e['title']} at {e['start']}" for e in events])


@tool
def add_task(title: str, notes: str = "", due: str = None) -> str:
    """
    Add a new task or to-do item to Google Tasks.

    USE when the user says:
    - "add a task", "note this down", "don't forget to [X]", "remember to [X]"
    - "put [X] on my list", "add to my to-do", "track [X]"
    - "remind me to [X]" (without a specific time)

    DO NOT use for:
    - Events with a specific time (use create_calendar_event)
    - Reading tasks (use get_tasks)

    Args:
        title: Task title / description.
        notes: Optional additional notes.
        due: Optional due date "YYYY-MM-DD" (e.g. "2025-03-15")
        
    Returns:
        Confirmation message
    """
    # Convert date to ISO format expected by Google Tasks API
    if due and len(due) == 10:
        due = due + "T00:00:00.000Z"
    result = _add_google_task(title, notes, due)
    return f"Task '{title}' added." if result["success"] else f"Failed to add task: {result.get('error', '')}"


@tool
def get_tasks() -> str:
    """
    Get all pending tasks from Google Tasks.

    USE when the user says:
    - "what are my tasks?", "show my to-do list", "what do I have to do?"
    - "what's pending?", "check my tasks", "any tasks?", "what's on my list?"

    DO NOT use for:
    - Calendar events (use get_upcoming_events or get_system_info)
    - Adding new tasks (use add_task)

    Returns:
        Formatted list of pending tasks with IDs
    """
    tasks = _get_google_tasks()
    if not tasks:
        return "No pending tasks."
    return "\n".join(
        [f"• [{t['id']}] {t['title']}" + (f" (due: {t['due'][:10]})" if t.get("due") else "")
         for t in tasks]
    )


@tool
def complete_task(task_id: str) -> str:
    """
    Mark a Google Task as completed.

    USE when the user says:
    - "mark [task] as done", "complete task", "I finished [X]", "task done"
    - task_id is shown in get_tasks() output in brackets like [abc123]

    Requires task_id — call get_tasks() first to find it if needed.
    
    Args:
        task_id: Google Task ID (from get_tasks output)
        
    Returns:
        Confirmation or error message
    """
    result = _complete_google_task(task_id)
    return "Task marked as complete." if result["success"] else f"Failed: {result.get('error', '')}"


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """
    Send an email via Gmail.

    USE when the user explicitly says:
    - "send an email", "email [someone] about X", "compose a mail"
    - "mail this to [address]", "send a message via email"

    DO NOT use for:
    - Reading emails (use read_emails)
    - Casual messaging — this sends a real email via Gmail

    Args:
        to: Recipient email address (e.g. "someone@gmail.com")
        subject: Email subject line.
        body: Email body text.

    Returns:
        Confirmation or error message
    """
    result = _send_gmail(to, subject, body)
    return "Email sent successfully." if result["success"] else f"Failed to send email: {result.get('error', '')}"


@tool
def read_emails(max_results: int = 5) -> str:
    """
    Read unread emails from the Gmail inbox.

    USE when the user says:
    - "check my email", "any new emails?", "what's in my inbox?"
    - "show unread messages", "read my emails", "any mail today?"

    DO NOT use for:
    - Sending emails (use send_email)
    - Searching specific emails (use search_emails)

    Args:
        max_results: Number of unread emails to fetch (default 5).

    Returns:
        Sender, subject, and preview for each unread email
    """
    emails = _read_unread_emails(max_results)
    if not emails:
        return "No unread emails."
    lines = []
    for e in emails:
        lines.append(f"From: {e['from']}\nSubject: {e['subject']}\nPreview: {e['snippet']}\n")
    return "\n".join(lines)


@tool
def search_emails(query: str) -> str:
    """
    Search Gmail with a query string.

    USE when the user asks to:
    - "find emails from [name]", "search for emails about [topic]"
    - "any emails with subject [X]?", "emails after [date]"

    Supports Gmail search syntax:
    - "from:name", "subject:meeting", "after:2025/3/1", plain keywords

    DO NOT use for:
    - Reading all unread emails (use read_emails)
    - Sending emails (use send_email)
    
    Args:
        query: Gmail search query
        
    Returns:
        List of matching emails with subject and sender
    """
    emails = _search_emails(query)
    if not emails:
        return "No emails found matching that query."
    return "\n".join([f"• {e['subject']} — from {e['from']}" for e in emails])


ALL_TOOLS = [
    # Productivity
    set_alarm,
    create_calendar_event,
    get_upcoming_events,
    add_task,
    get_tasks,
    complete_task,
    get_system_info,
    # System
    open_app,
    run_command,
    # Research
    web_search,
    # Communication
    send_email,
    read_emails,
    search_emails,
    # Memory
    save_memory,
    get_user_context,
]
