# tools/tool_groups.py

from src.tools.wrapped_tools import (
    set_alarm, set_timer, add_task, get_tasks,
    create_calendar_event, get_system_info,
    open_app, run_command,
    web_search, search_arxiv, search_stackoverflow,
    send_email, read_emails
)

# Group tools by category
TOOL_GROUPS = {
    "productivity": [
        set_alarm, set_timer, add_task,
        get_tasks, create_calendar_event,
        get_system_info
    ],
    "system": [
        open_app, run_command
    ],
    "research": [
        web_search, search_arxiv, search_stackoverflow
    ],
    "communication": [
        send_email, read_emails
    ],
}

# Always sent regardless — general purpose
BASE_TOOLS = [web_search]

# Simple keyword router — runs locally, zero tokens
def get_tools_for_query(query: str) -> list:
    query_lower = query.lower()

    selected_groups = set()

    # Productivity keywords
    if any(w in query_lower for w in [
        "alarm", "timer", "remind", "task", "todo",
        "calendar", "event", "schedule", "status", "info"
    ]):
        selected_groups.add("productivity")

    # System keywords
    if any(w in query_lower for w in [
        "open", "terminal", "run", "command", "app", "launch"
    ]):
        selected_groups.add("system")

    # Research keywords
    if any(w in query_lower for w in [
        "search", "find", "arxiv", "paper", "stackoverflow",
        "look up", "google", "what is", "who is"
    ]):
        selected_groups.add("research")

    # Communication keywords
    if any(w in query_lower for w in [
        "email", "mail", "send", "message", "inbox"
    ]):
        selected_groups.add("communication")

    # If nothing matched — just use base tools + productivity as default
    if not selected_groups:
        selected_groups.add("productivity")

    # Combine selected groups
    tools = list(BASE_TOOLS)
    for group in selected_groups:
        tools.extend(TOOL_GROUPS[group])

    # Deduplicate
    seen = set()
    unique_tools = []
    for t in tools:
        if t.name not in seen:
            seen.add(t.name)
            unique_tools.append(t)

    return unique_tools