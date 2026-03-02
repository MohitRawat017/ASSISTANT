"""
LangGraph tools wrapping the existing managers.

IMPORTANT: The docstrings below are used for BOTH:
1. The LLM — to decide which tool to call and how to fill args
2. The embedding retriever — to match user queries to relevant tools

So keep docstrings specific, action-oriented, and rich with trigger
phrases. Vague docstrings = wrong tools getting selected.
"""

import os
import re
from datetime import datetime, timedelta
from langchain_core.tools import tool
from src.utils.config import Config


# Manager instances (lazy-loaded)
timer_mgr = None
alarm_mgr = None
task_mgr = None
calendar_mgr = None
email_svc = None


def get_timer_manager():
    global timer_mgr
    if timer_mgr is None:
        from src.managers.timer_manager import TimerManager
        timer_mgr = TimerManager()
    return timer_mgr


def get_alarm_manager():
    global alarm_mgr
    if alarm_mgr is None:
        from src.managers.alarm_manager import AlarmManager
        alarm_mgr = AlarmManager()
    return alarm_mgr


def get_task_manager():
    global task_mgr
    if task_mgr is None:
        from src.managers.task_manager import TaskManager
        task_mgr = TaskManager()
    return task_mgr


def get_calendar_manager():
    global calendar_mgr
    if calendar_mgr is None:
        from src.managers.calendar_manager import CalendarManager
        calendar_mgr = CalendarManager()
    return calendar_mgr


def get_email_service():
    global email_svc
    if email_svc is None:
        from src.services.email_service import EmailService
        sender = os.environ.get("GMAIL_ADDRESS", "")
        password = os.environ.get("GMAIL_APP_PASSWORD", "")
        recipient = os.environ.get("REMINDER_EMAIL", sender)
        email_svc = EmailService(sender, password, recipient)
    return email_svc


# Helpers
def parse_duration(duration_str: str) -> int:
    """Parse '10 minutes', '1 hour', etc. to seconds."""
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
    
    if total == 0:
        nums = re.findall(r'\d+', duration_str)
        if nums:
            total = int(nums[0]) * 60
    return total


def normalize_time(time_str: str) -> str:
    """Normalize time to HH:MM format."""
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


def parse_date(date_str: str) -> str:
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


# Tools
@tool
def set_timer(duration: str, label: str = "Timer") -> str:
    """Set a countdown timer for a specified duration. Use for timing activities, cooking, study sessions, or any timed event. Accepts durations like '5 minutes', '1 hour 30 minutes', or '90 seconds'. Optionally label the timer."""
    try:
        mgr = get_timer_manager()
        seconds = parse_duration(duration)
        if seconds <= 0:
            return f"Couldn't understand duration: '{duration}'. Try '5 minutes' or '30 seconds'."
        mgr.add_timer(label, seconds)
        return f"Timer '{label}' set for {duration}."
    except Exception as e:
        return f"Failed to set timer: {e}"


@tool
def set_alarm(time: str, label: str = "Alarm") -> str:
    """Set a clock alarm to ring at a specific time of day. Use for wake-up alarms, meeting reminders, or scheduled notifications. Accepts times like '7am', '14:30', or '6:30 pm'. Optionally label the alarm."""
    try:
        mgr = get_alarm_manager()
        normalized = normalize_time(time)
        alarm_id = mgr.add_alarm(normalized, label)
        
        if alarm_id:
            try:
                from src.scheduler_windows import WindowsScheduler
                task_name = WindowsScheduler.register_alarm(alarm_id, normalized, label)
                if task_name:
                    mgr.set_scheduled_task(alarm_id, task_name)
            except:
                pass
            return f"Alarm set for {normalized}" + (f" ({label})" if label != "Alarm" else "") + "."
        return "Failed to set alarm."
    except Exception as e:
        return f"Failed to set alarm: {e}"


@tool
def create_calendar_event(title: str, date: str = "today", time: str = "09:00", duration: int = 60) -> str:
    """Create a new event on the calendar with a title, date, time, and duration. Use when the user wants to schedule a meeting, appointment, class, deadline, or any time-bound event. Accepts dates like 'today', 'tomorrow', 'next Monday', or 'YYYY-MM-DD'."""
    try:
        mgr = get_calendar_manager()
        event_date = parse_date(date)
        normalized_time = normalize_time(time) if time else "09:00"
        start_dt = f"{event_date} {normalized_time}:00"
        
        try:
            start = datetime.strptime(start_dt, "%Y-%m-%d %H:%M:%S")
            end = start + timedelta(minutes=duration if isinstance(duration, int) else 60)
            end_dt = end.strftime("%Y-%m-%d %H:%M:%S")
        except:
            end_dt = start_dt
        
        event = mgr.add_event(title, start_dt, end_dt)
        if event:
            return f"Created event '{title}' on {date}" + (f" at {time}" if time else "") + "."
        return "Failed to create event."
    except Exception as e:
        return f"Failed to create event: {e}"


@tool
def add_task(text: str) -> str:
    """Add a new task or to-do item to the task list. Use when the user wants to remember, track, or schedule something they need to do. Accepts any task description text like 'buy groceries' or 'finish homework'."""
    try:
        mgr = get_task_manager()
        if not text.strip():
            return "No task text provided."
        task = mgr.add_task(text.strip())
        if task:
            return f"Added task: {text}"
        return "Failed to add task."
    except Exception as e:
        return f"Failed to add task: {e}"


@tool
def get_tasks() -> str:
    """Retrieve and display all tasks from the to-do list, showing both pending and completed items. Use when the user asks what they need to do, checks their task list, or reviews their progress."""
    try:
        mgr = get_task_manager()
        tasks = mgr.get_tasks()
        
        if not tasks:
            return "Your task list is empty."
        
        lines = []
        pending = [t for t in tasks if not t.get("completed")]
        done = [t for t in tasks if t.get("completed")]
        
        if pending:
            lines.append(f"Pending ({len(pending)}):")
            for t in pending:
                lines.append(f"  - {t['text']}")
        if done:
            lines.append(f"Completed ({len(done)}):")
            for t in done:
                lines.append(f"  ✓ {t['text']}")
        
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to get tasks: {e}"


@tool
def web_search(query: str) -> str:
    """Search the internet using DuckDuckGo for real-time information, news, facts, or answers. Use for general knowledge questions like 'what is', 'who is', 'where is', geography, history, current events, definitions, or any factual lookup. Also use for weather queries ('weather in Delhi', 'temperature today'), finding latest information ('latest news', 'recent research'), searching for models or technologies ('latest AI models', 'new image models'), or when no other specific tool matches. This is a general-purpose search tool. Returns top results with titles and snippets."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        
        if results:
            lines = [f"Results for '{query}':"]
            for i, r in enumerate(results[:3], 1):
                lines.append(f"{i}. {r.get('title', '')}")
                body = r.get("body", "")[:200]
                if body:
                    lines.append(f"   {body}")
            return "\n".join(lines)
        return f"No results for '{query}'."
    except Exception as e:
        return f"Search failed: {e}"


@tool
def get_system_info() -> str:
    """Get a comprehensive system status overview including the current date and time, active timers and their remaining time, scheduled alarms, today's calendar events, and pending tasks. Use when the user asks 'what time is it', 'what day is it', 'what's my schedule', 'what's going on', or wants a full status summary."""
    try:
        parts = []
        now = datetime.now()
        parts.append(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Timers
        try:
            timers = get_timer_manager().get_active_timers()
            if timers:
                parts.append("Timers: " + ", ".join(f"{t['label']} ({t['remaining']})" for t in timers))
            else:
                parts.append("No active timers.")
        except:
            pass
        
        # Alarms
        try:
            alarms = get_alarm_manager().get_alarms()
            if alarms:
                parts.append("Alarms: " + ", ".join(f"{a['label']} at {a['time']}" for a in alarms[:5]))
            else:
                parts.append("No alarms.")
        except:
            pass
        
        # Calendar
        try:
            events = get_calendar_manager().get_events(now.strftime("%Y-%m-%d"))
            if events:
                parts.append("Today: " + ", ".join(f"{e['title']} at {e['start_time']}" for e in events[:5]))
            else:
                parts.append("No events today.")
        except:
            pass
        
        # Tasks
        try:
            tasks = get_task_manager().get_tasks()
            pending = [t for t in tasks if not t.get("completed")]
            if pending:
                parts.append(f"Tasks ({len(pending)}): " + ", ".join(t['text'] for t in pending[:5]))
            else:
                parts.append("No pending tasks.")
        except:
            pass
        
        return "\n".join(parts)
    except Exception as e:
        return f"Failed to get info: {e}"


@tool
def send_email(subject: str, body: str) -> str:
    """Send an email through Gmail with a subject and body. Use when the user wants to email someone, send a message, compose a mail, or forward information. Requires Gmail credentials configured in .env."""
    try:
        svc = get_email_service()
        if svc.send_reminder(subject, body):
            return f"Email sent: '{subject}'"
        return "Failed to send email. Check Gmail credentials."
    except Exception as e:
        return f"Failed to send email: {e}"


@tool
def open_app(app_name: str) -> str:
    """Launch and open a desktop application or program by name. Use when the user wants to start, launch, or open an app, application, program, or software. Examples: 'open Chrome', 'start Spotify', 'launch Discord', 'run Notepad', 'open browser', 'start VS Code', 'launch Firefox'. Works with any installed desktop application on Windows."""
    try:
        from AppOpener import open as app_open
        app_open(app_name)
        return f"Opened {app_name}."
    except Exception as e:
        return f"Couldn't open {app_name}: {e}"




@tool
def run_command(command: str) -> str:
    """Execute a safe terminal or shell command on the system and return the output. Use for system operations like checking disk space, listing files, getting IP address, checking current directory, running scripts, or executing shell commands. Examples: 'pwd' for current directory, 'dir' to list files, 'ipconfig' for network info, 'python script.py' to run Python. Dangerous commands (rm, del, format, shutdown) are blocked for safety."""
    import subprocess

    # Block dangerous commands
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
            timeout=10,  # Reduced from 15s to prevent long waits
            cwd=Config.BASE_DIR
        )
        output = result.stdout.strip()
        errors = result.stderr.strip()

        if result.returncode != 0 and errors:
            return f"Command failed:\n{errors[:500]}"  # Capped at 500 chars
        
        # Cap output at 500 chars to prevent LLM confusion/looping
        if output:
            return output[:500] if len(output) > 500 else output
        return "Command ran successfully (no output)."

    except subprocess.TimeoutExpired:
        return "Command timed out (10s limit)."
    except Exception as e:
        return f"Failed to run command: {str(e)[:200]}"


@tool
def search_stackoverflow(query: str) -> str:
    """Search Stack Overflow for programming questions, coding solutions, and technical answers. Use when the user asks 'how to' do something in code, needs debugging help, code examples, error message fixes, or software development questions like 'how to reverse a list in python'. Returns relevant Q&A excerpts."""
    import requests

    try:
        resp = requests.get(
            "https://api.stackexchange.com/2.3/search/excerpts",
            params={"order": "desc", "sort": "relevance", "q": query, "site": "stackoverflow", "pagesize": 3},
            timeout=10
        )
        data = resp.json()
        items = data.get("items", [])

        if not items:
            return f"No Stack Overflow results for '{query}'."

        lines = [f"Stack Overflow results for '{query}':"]
        for i, item in enumerate(items, 1):
            title = item.get("title", "").replace("&#39;", "'").replace("&quot;", '"')
            excerpt = item.get("excerpt", "")[:200].replace("<span class=\"highlight\">", "").replace("</span>", "")
            lines.append(f"{i}. {title}")
            if excerpt:
                lines.append(f"   {excerpt}")

        return "\n".join(lines)
    except Exception as e:
        return f"Stack Overflow search failed: {e}"


@tool
def search_arxiv(query: str, max_results: int = 3) -> str:
    """Search arXiv for academic research papers, preprints, and scientific publications. Use when the user asks about research papers, scientific studies, ML papers, academic literature, or wants to find papers on a topic. Examples: 'research paper on transformers', 'latest papers on OpenCV', 'find ML papers about attention', 'arXiv search for neural networks'. Returns paper titles, authors, dates, and summaries."""
    import arxiv

    try:
        search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance)
        results = list(search.results())

        if not results:
            return f"No arXiv papers found for '{query}'."

        lines = [f"arXiv results for '{query}':"]
        for i, paper in enumerate(results, 1):
            lines.append(f"{i}. {paper.title}")
            lines.append(f"   Authors: {', '.join(a.name for a in paper.authors[:3])}")
            lines.append(f"   Published: {paper.published.strftime('%Y-%m-%d')}")
            lines.append(f"   URL: {paper.entry_id}")
            summary = paper.summary[:150].replace("\n", " ")
            lines.append(f"   {summary}...")

        return "\n".join(lines)
    except Exception as e:
        return f"arXiv search failed: {e}"






@tool
def read_emails(count: int = 5, filter_type: str = "unread") -> str:
    """Read and display recent emails from the Gmail inbox. Can filter by unread, today's messages, or all mail. Use when the user wants to check their inbox, see new messages, or review recent correspondence."""
    import imaplib
    import email
    from email.header import decode_header

    address = os.environ.get("GMAIL_ADDRESS", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not address or not password:
        return "Gmail credentials not configured in .env."

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(address, password)
        mail.select("inbox")

        # Pick search criteria
        if filter_type == "unread":
            criteria = "UNSEEN"
        elif filter_type == "today":
            from datetime import date
            today = date.today().strftime("%d-%b-%Y")
            criteria = f'SINCE {today}'
        else:
            criteria = "ALL"

        status, msg_ids = mail.search(None, criteria)
        ids = msg_ids[0].split()

        if not ids:
            return f"No {filter_type} emails found."

        # Get the most recent ones
        recent_ids = ids[-count:]
        recent_ids.reverse()

        lines = [f"Recent {filter_type} emails ({len(recent_ids)}):"]
        for mid in recent_ids:
            status, msg_data = mail.fetch(mid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            # Decode subject
            subject_raw = msg["Subject"] or "(no subject)"
            decoded = decode_header(subject_raw)
            subject = decoded[0][0]
            if isinstance(subject, bytes):
                subject = subject.decode(decoded[0][1] or "utf-8", errors="replace")

            sender = msg["From"] or "unknown"
            date_str = msg["Date"] or ""

            lines.append(f"  From: {sender}")
            lines.append(f"  Subject: {subject}")
            lines.append(f"  Date: {date_str}")
            lines.append("")

        mail.logout()
        return "\n".join(lines)

    except Exception as e:
        return f"Failed to read emails: {e}"


# ── Tool Registry ───────────────────────────────────────────────────────

ALL_TOOLS = [
    # Productivity
    set_timer,
    set_alarm,
    create_calendar_event,
    add_task,
    get_tasks,
    get_system_info,
    # System
    open_app,
    run_command,
    # Research
    web_search,
    search_stackoverflow,
    search_arxiv,
    # Communication
    send_email,
    read_emails,
]