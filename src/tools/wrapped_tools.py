"""
LangGraph tools wrapping the existing managers.
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
    """Set a countdown timer for the given duration like '5 minutes' or '30 seconds'."""
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
    """Set an alarm for a specific time like '7am' or '14:30'."""
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
    """Create a calendar event with a title, date, time, and duration in minutes."""
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
    """Add a task to the to-do list."""
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
    """Get all tasks from the to-do list."""
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
    """Search the web for information using a search query."""
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
    """Get current status: time, timers, alarms, events, tasks."""
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
    """Send an email via Gmail."""
    try:
        svc = get_email_service()
        if svc.send_reminder(subject, body):
            return f"Email sent: '{subject}'"
        return "Failed to send email. Check Gmail credentials."
    except Exception as e:
        return f"Failed to send email: {e}"


@tool
def open_app(app_name: str) -> str:
    """Open a desktop application by name."""
    try:
        from AppOpener import open as app_open
        app_open(app_name)
        return f"Opened {app_name}."
    except Exception as e:
        return f"Couldn't open {app_name}: {e}"




@tool
def run_command(command: str) -> str:
    """Run a safe terminal command and return the output."""
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
            timeout=15,
            cwd=Config.BASE_DIR
        )
        output = result.stdout.strip()
        errors = result.stderr.strip()

        if result.returncode != 0 and errors:
            return f"Command failed:\n{errors[:1000]}"
        return output[:2000] if output else "Command ran successfully (no output)."

    except subprocess.TimeoutExpired:
        return "Command timed out (15s limit)."
    except Exception as e:
        return f"Failed to run command: {e}"


@tool
def search_stackoverflow(query: str) -> str:
    """Search Stack Overflow for coding answers."""
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
    """Search academic papers on arXiv."""
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
    """Read recent emails from Gmail inbox."""
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