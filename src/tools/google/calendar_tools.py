"""
Google Calendar raw functions.
No @tool decorators — those live in wrapped_tools.py.
"""

from datetime import datetime, timezone
from src.tools.google.auth import get_calendar_service


def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    tz: str = "Asia/Kolkata",
) -> dict:
    """
    Creates a Google Calendar event.

    Args:
        title: Event title.
        start_time: ISO format "2025-03-15T10:00:00"
        end_time:   ISO format "2025-03-15T11:00:00"
        description: Optional event description.
        tz: Timezone string (default IST).

    Returns:
        {"success": True, "event_id": "...", "link": "..."}
    """
    try:
        service = get_calendar_service()
        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_time, "timeZone": tz},
            "end": {"dateTime": end_time, "timeZone": tz},
        }
        created = service.events().insert(calendarId="primary", body=event).execute()
        return {
            "success": True,
            "event_id": created.get("id", ""),
            "link": created.get("htmlLink", ""),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_upcoming_events(max_results: int = 10) -> list:
    """
    Returns the next N calendar events from now.

    Returns:
        list of {"title", "start", "end", "description", "id"}
    """
    try:
        service = get_calendar_service()
        now = datetime.now(timezone.utc).isoformat()
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = []
        for item in result.get("items", []):
            start = item["start"].get("dateTime", item["start"].get("date", ""))
            end = item["end"].get("dateTime", item["end"].get("date", ""))
            events.append(
                {
                    "id": item.get("id", ""),
                    "title": item.get("summary", "(no title)"),
                    "start": start,
                    "end": end,
                    "description": item.get("description", ""),
                }
            )
        return events
    except Exception as e:
        return []


def delete_calendar_event(event_id: str) -> dict:
    """
    Deletes a calendar event by ID.

    Returns:
        {"success": True/False}
    """
    try:
        service = get_calendar_service()
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
