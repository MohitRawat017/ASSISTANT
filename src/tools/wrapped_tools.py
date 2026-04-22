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


# =============================================================================
# SYSTEM CONTROL TOOLS
# =============================================================================

@tool
def open_app(app_name: str) -> str:
    """
    Launch a desktop application by name.
    If already running, focuses the existing window instead of opening a new instance.

    USE when the user says:
    - "open [app]", "launch [app]", "start [app]", "run [app]"
    - Examples: "open Chrome", "start Spotify", "launch Discord",
      "open VS Code", "run Notepad", "start Steam"

    DO NOT use for:
    - Shell commands or direct terminal execution
    - Opening arbitrary files by path

    IMPORTANT: After opening an app, wait at least 0.5 seconds before
    typing or clicking inside it to ensure the window is fully loaded.

    Args:
        app_name: Name of the application to launch
        
    Returns:
        Confirmation message or error
    """
    result = open_application(app_name)
    
    if result.get("success"):
        if result.get("focused"):
            return f"{app_name} was already open, focused it for you, master."
        return f"Opened {app_name}, master."
    
    # Provide suggestions for failed attempts
    from src.tools.pc_automation.app_launcher import APP_MAP
    app_name_lower = app_name.lower().strip()
    suggestions = []
    for alias in APP_MAP:
        if app_name_lower in alias or alias in app_name_lower:
            suggestions.append(alias)
    
    error_msg = result.get("error", f"Couldn't open '{app_name}'.")
    if suggestions:
        error_msg += f" Did you mean: {', '.join(suggestions[:3])}?"
    
    return error_msg


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
    - Task-only requests (use get_tasks)

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
    - Calendar events (use get_upcoming_events)
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


# =============================================================================
# PC AUTOMATION TOOLS — Phase 4
# =============================================================================

from src.tools.pc_automation.screenshot import take_screenshot, take_region_screenshot
from src.tools.pc_automation.mouse_keyboard import (
    mouse_click, mouse_move, type_text, press_key, hotkey, scroll, get_screen_size
)
from src.tools.pc_automation.window_manager import (
    get_open_windows, focus_window,
    minimize_window, maximize_window, minimize_all_windows
)
from src.tools.pc_automation.system_controls import (
    set_volume, get_volume, mute_volume, unmute_volume,
    set_brightness, get_brightness, lock_screen, get_pc_stats
)
from src.tools.pc_automation.app_launcher import (
    open_application, close_application, is_app_running
)


@tool
def take_screenshot_tool() -> str:
    """
    Take a screenshot of the current screen and save it.
    Use when user asks to capture screen or take a screenshot.
    Returns the file path of the saved screenshot.
    """
    path = take_screenshot()
    return f"Screenshot saved to: {path}"


@tool
async def screenshot_to_telegram() -> str:
    """
    Take a screenshot and send it to the user on Telegram.
    Use when user says 'send me a screenshot', 'show me my screen on Telegram', etc.
    Returns confirmation that screenshot was sent.
    """
    path = take_screenshot()

    from src.interfaces.telegram_bot import get_app
    app = get_app()
    if app:
        # Read file bytes with context manager to avoid handle leak
        with open(path, "rb") as f:
            photo_bytes = f.read()
        await app.bot.send_photo(
            chat_id=Config.TELEGRAM_ALLOWED_USER_ID,
            photo=photo_bytes,
            caption="Here's your screen, master."
        )
        return "Screenshot sent to Telegram."
    return f"Screenshot saved locally: {path} (Telegram not available)"


@tool
def close_app(app_name: str) -> str:
    """
    Close an application on the PC by name.
    
    Use this to CLOSE, QUIT, or TERMINATE a running application.
    Do NOT use list_open_windows for closing — use this tool instead.
    
    Use when user says 'close X', 'quit X', 'kill X', 'stop X'.
    Returns confirmation or error.
    """
    result = close_application(app_name)
    if result["success"]:
        return f"Closed {app_name}, master."
    return f"Could not close {app_name}: {result.get('error', 'not found')}"


def _legacy_list_open_windows() -> str:
    """
    List all currently open windows on the PC.
    Use when user asks 'what apps are open', 'what windows do I have open',
    'what's running', 'list my open programs', etc.
    Returns a list of open window titles and their processes.
    """
    windows = get_open_windows()
    if not windows:
        return "No open windows found."
    seen = set()
    result = []
    for w in windows:
        if w["title"] not in seen:
            seen.add(w["title"])
            result.append(f"• {w['title']} ({w['process']})")
    return "\n".join(result[:20])  # cap at 20 to avoid huge responses


@tool
def list_open_windows() -> str:
    """
    List all currently open windows on the PC.
    Handles timeout/error entries from get_open_windows() gracefully.
    """
    windows = get_open_windows()
    if not windows:
        return "No open windows found."

    seen = set()
    result = []
    scan_errors = []

    for w in windows:
        if not isinstance(w, dict):
            continue
        if w.get("error"):
            scan_errors.append(w["error"])
            continue

        title = w.get("title")
        process = w.get("process", "unknown")
        if not title:
            continue

        if title not in seen:
            seen.add(title)
            result.append(f"- {title} ({process})")

    if not result:
        if scan_errors:
            unique_errors = list(dict.fromkeys(scan_errors))
            return "No open windows found.\nWindow scan status: " + ", ".join(unique_errors)
        return "No open windows found."

    output = result[:20]
    if scan_errors:
        unique_errors = list(dict.fromkeys(scan_errors))
        output.append("Window scan status: " + ", ".join(unique_errors))

    return "\n".join(output)


@tool
def focus_app(window_title: str) -> str:
    """
    Bring a window to the foreground and focus it.
    Use when user says 'switch to X', 'bring up X', 'focus X', 'go to X'.
    window_title: partial window title is fine, case insensitive.
    Returns confirmation or error.
    """
    result = focus_window(window_title)
    return f"Focused {result.get('window', window_title)}." if result["success"] else result.get("error")


@tool
def control_volume(action: str, level: int = None) -> str:
    """
    Control system volume.
    action: "set" (requires level), "get", "mute", "unmute"
    level: 0-100, only used when action="set"
    Examples:
      control_volume("set", 50) → sets to 50%
      control_volume("mute")    → mutes
      control_volume("get")     → returns current level
    Returns confirmation with volume level.
    """
    if action == "set" and level is not None:
        set_volume(level)
        return f"Volume set to {level}%, master."
    elif action == "get":
        result = get_volume()
        return f"Current volume: {result['volume']}%"
    elif action == "mute":
        mute_volume()
        return "Volume muted, master."
    elif action == "unmute":
        unmute_volume()
        return "Volume unmuted, master."
    return "Invalid volume action. Use: set, get, mute, unmute"


@tool
def control_brightness(action: str, level: int = None) -> str:
    """
    Control display brightness.
    action: "set" (requires level), "get"
    level: 0-100, only used when action="set"
    Note: Only works on laptop displays or external monitors with DDC/CI support.
    Returns confirmation with brightness level.
    """
    if action == "set" and level is not None:
        result = set_brightness(level)
        if result["success"]:
            return f"Brightness set to {level}%, master."
        return f"Could not set brightness: {result.get('error')}"
    elif action == "get":
        result = get_brightness()
        if result["success"]:
            return f"Current brightness: {result['brightness']}%"
        return f"Could not get brightness: {result.get('error')}"
    return "Invalid brightness action. Use: set, get"


@tool
def lock_screen_tool() -> str:
    """
    Lock the Windows screen immediately.
    Use when user says 'lock my screen', 'lock the computer', 'lock PC'.
    Returns confirmation.
    """
    lock_screen()
    return "Screen locked, master."


@tool
def get_pc_status() -> str:
    """
    Get current PC system stats: CPU usage, memory, and disk space.
    Use when user asks about PC performance, system status, resource usage,
    'how is my PC doing', 'check CPU', 'how much RAM is free', etc.
    Returns formatted system information.
    """
    info = get_pc_stats()
    return (
        f"CPU: {info['cpu_percent']}%\n"
        f"Memory: {info['memory_percent']}% used ({info['memory_available_gb']}GB free)\n"
        f"Disk: {info['disk_free_gb']}GB free"
    )


@tool
def click_at(x: int, y: int, button: str = "left") -> str:
    """
    Click the mouse at specific screen coordinates.
    Use when user specifies exact coordinates to click.
    x, y: screen coordinates (top-left is 0,0)
    button: "left", "right", or "middle"
    Returns confirmation.
    """
    mouse_click(x, y, button=button)
    return f"Clicked at ({x}, {y}) with {button} button."


@tool
def type_text_tool(text: str) -> str:
    """
    Type text at the current cursor position.
    Use when user wants to type something in the currently focused app.
    The app must already be focused and have a text input active.
    Returns confirmation.
    """
    type_text(text)
    return f"Typed: {text}"


@tool
def press_keyboard_key(key: str) -> str:
    """
    Press a keyboard key.
    Single keys: "enter", "tab", "escape", "backspace", "space",
                 "up", "down", "left", "right", "delete", "home", "end",
                 "f1" through "f12"
    For shortcuts use hotkey_tool instead.
    Returns confirmation.
    """
    press_key(key)
    return f"Pressed {key}."


@tool
def hotkey_tool(keys: str) -> str:
    """
    Press a keyboard shortcut combination.
    keys: comma-separated key names, e.g. "ctrl,c" or "ctrl,alt,t" or "win,d"
    Common shortcuts:
      "ctrl,c"         → copy
      "ctrl,v"         → paste
      "ctrl,z"         → undo
      "ctrl,s"         → save
      "ctrl,w"         → close tab
      "alt,f4"         → close window
      "win,d"          → show desktop
      "ctrl,shift,esc" → task manager
    Returns confirmation.
    """
    key_list = [k.strip() for k in keys.split(",")]
    hotkey(*key_list)
    return f"Pressed hotkey: {' + '.join(key_list)}"


@tool
def minimize_all() -> str:
    """
    Minimize all windows and show the desktop.
    Use when user says 'show desktop', 'minimize everything', 'clear screen',
    'hide all windows'.
    Returns confirmation.
    """
    minimize_all_windows()
    return "All windows minimized, master."


# =============================================================================
# PHASE 5 — SCREEN VISION TOOLS
# =============================================================================
# These tools give the agent the ability to locate and interact with UI elements
# on screen using natural-language descriptions instead of hardcoded coordinates.
#
# How it works:
#   1. Tool is called with a description like "search bar" or "close button"
#   2. find_element() in screen_vision.py takes a screenshot
#   3. VISION_MODEL (via Config) locates the element and returns a bbox
#   4. Bbox is scaled to real screen coordinates and returned
#   5. pyautogui performs the click at those coordinates
#
# Vision import is optional - tools must fail gracefully if unavailable.
try:
    from src.vision.screen_vision import find_element, describe_screen, read_screen_text
    _VISION_IMPORT_ERROR = None
except ImportError:
    find_element = None
    describe_screen = None
    read_screen_text = None
    _VISION_IMPORT_ERROR = True


def _vision_module_available() -> bool:
    return _VISION_IMPORT_ERROR is None


@tool
def find_and_click(description: str, button: str = "left") -> str:
    """
    Find a UI element on screen by description and click it.
    Use this INSTEAD of click_at() when you don't know the coordinates.
    Use this when user says 'click X', 'press X button', 'tap X'.

    description: what to find, e.g. "search bar", "close button", "submit button",
                 "minimize button", "the X button", "send button in Gmail"
    button: "left" (default), "right", or "middle"

    Automatically takes screenshot, locates element, clicks center of it.
    Returns confirmation with coordinates used, or error if not found.

    IMPORTANT: After calling this tool, wait for result before taking further action.
    Do NOT assume the click succeeded — check the return value.
    """
    if not _vision_module_available():
        return "Vision module not available"

    # Resolve element coordinates via the vision model
    result = find_element(description)

    if not result["found"]:
        return f"Could not find '{description}' on screen: {result.get('error', 'unknown error')}"

    x, y = result["x"], result["y"]
    # Use the existing pc_automation mouse_click — already imported at module level
    mouse_click(x, y, button=button)
    return f"Found '{description}' and clicked at ({x}, {y}), master."


@tool
def find_and_double_click(description: str) -> str:
    """
    Find a UI element on screen by description and double-click it.
    Use when user says 'double click X', 'open X by double clicking'.

    description: what to find, e.g. "Chrome icon on desktop", "folder"
    Returns confirmation or error.
    """
    if not _vision_module_available():
        return "Vision module not available"

    result = find_element(description)

    if not result["found"]:
        return f"Could not find '{description}' on screen: {result.get('error', 'unknown error')}"

    x, y = result["x"], result["y"]
    # pyautogui.doubleClick is not wrapped in pc_automation, so import locally
    import pyautogui as _pag
    _pag.doubleClick(x, y)
    return f"Found '{description}' and double-clicked at ({x}, {y}), master."


@tool
def find_and_right_click(description: str) -> str:
    """
    Find a UI element on screen and right-click it to open context menu.
    Use when user says 'right click X', 'open context menu for X'.

    description: what to right-click
    Returns confirmation or error.
    """
    if not _vision_module_available():
        return "Vision module not available"

    result = find_element(description)

    if not result["found"]:
        return f"Could not find '{description}' on screen: {result.get('error', 'unknown error')}"

    x, y = result["x"], result["y"]
    # Use pc_automation's mouse_click with button="right"
    mouse_click(x, y, button="right")
    return f"Found '{description}' and right-clicked at ({x}, {y}), master."


@tool
def find_and_type(description: str, text: str) -> str:
    """
    Find a text input field on screen, click it, then type text into it.
    Use when user says 'type X in the search bar', 'enter X in the input field'.
    Combines find_and_click + type_text in one step.

    description: the input field to find, e.g. "search bar", "address bar",
                 "notepad text area", "username field"
    text: what to type
    Returns confirmation or error.
    """
    import time

    if not _vision_module_available():
        return "Vision module not available"

    # Step 1: Locate and click the target field
    result = find_element(description)
    if not result["found"]:
        return f"Could not find '{description}' on screen: {result.get('error', 'unknown error')}"

    x, y = result["x"], result["y"]
    # Click to give the field focus using the existing pc_automation wrapper
    mouse_click(x, y)

    # Brief delay so the field receives keyboard focus before we start typing
    time.sleep(0.3)

    # Step 2: Type using the existing type_text wrapper from pc_automation
    type_text(text)
    return f"Clicked '{description}' at ({x}, {y}) and typed: {text}"


@tool
def what_is_on_screen() -> str:
    """
    Describes what is currently visible on the screen.
    Use when user asks 'what's on my screen', 'what do you see',
    'what app is open', 'describe my screen', 'what's happening on screen'.
    Takes a screenshot and uses vision AI to describe it.
    Returns detailed description of screen contents.
    """
    if not _vision_module_available():
        return "Vision module not available"

    # describe_screen() handles the screenshot + model call internally
    return describe_screen()


@tool
def read_text_on_screen(area: str = None) -> str:
    """
    Reads and extracts text currently visible on screen.
    Use when user asks 'read the error message', 'what does it say',
    'read the text on screen', 'what's written there'.

    area: optional — specific area to focus on, e.g. "error dialog",
          "title bar", "notification", "selected text"
          If None, reads all text on screen.
    Returns extracted text from screen.
    """
    if not _vision_module_available():
        return "Vision module not available"

    # Pass area directly; read_screen_text handles None (full screen) gracefully
    return read_screen_text(area)


ALL_TOOLS = [
    # Productivity
    set_alarm,
    create_calendar_event,
    get_upcoming_events,
    add_task,
    get_tasks,
    complete_task,
    # System
    open_app,
    # Research
    web_search,
    # Communication
    send_email,
    read_emails,
    search_emails,
    # Memory
    save_memory,
    get_user_context,
    # PC Automation — App control
    close_app,
    list_open_windows,
    focus_app,
    minimize_all,
    # PC Automation — System controls
    control_volume,
    control_brightness,
    lock_screen_tool,
    get_pc_status,
    # PC Automation — Screenshots
    take_screenshot_tool,
    screenshot_to_telegram,
    # PC Automation — Input
    click_at,
    type_text_tool,
    press_keyboard_key,
    hotkey_tool,
    # Phase 5 — Screen Vision (vision-guided mouse automation)
    find_and_click,
    find_and_double_click,
    find_and_right_click,
    find_and_type,
    what_is_on_screen,
    read_text_on_screen,
]
