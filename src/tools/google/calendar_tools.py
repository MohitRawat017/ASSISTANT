"""
https://developers.google.com/calendar/api/v3/reference
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
    """
    try:
        # Validate ISO 8601 times before touching the API; a ValueError
        # falls through to the failure return below
        datetime.fromisoformat(start_time)
        datetime.fromisoformat(end_time)

        service = get_calendar_service()

        # Build event object for API
        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_time, "timeZone": tz},
            "end": {"dateTime": end_time, "timeZone": tz},
        }
        
        # Insert into primary calendar
        created = service.events().insert(
            calendarId="primary",  # User's main calendar
            body=event
        ).execute()
        
        return {
            "success": True,
            "event_id": created.get("id", ""),
            "link": created.get("htmlLink", ""),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_upcoming_events(max_results: int = 10) -> dict:
    """
    Returns the next N calendar events from now.

    Returns:
        {"success": True, "events": [...]} on success
        {"success": False, "error": "..."} on failure
    """
    try:
        service = get_calendar_service()
        
        # Current time in UTC for filtering
        now = datetime.now(timezone.utc).isoformat()
        
        # Fetch events
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,          # Only future events
                maxResults=max_results,
                singleEvents=True,    # Expand recurring events
                orderBy="startTime",  # Sort by start time
            )
            .execute()
        )
        
        # Extract relevant fields from API response
        events = []
        for item in result.get("items", []):
            # Cancelled events lack start/end; skip them
            if item.get("status") == "cancelled":
                continue

            # Handle both dateTime (timed events) and date (all-day events)
            start_obj = item.get("start", {})
            end_obj = item.get("end", {})
            start = start_obj.get("dateTime", start_obj.get("date", ""))
            end = end_obj.get("dateTime", end_obj.get("date", ""))

            events.append(
                {
                    "id": item.get("id", ""),
                    "title": item.get("summary", "(no title)"),
                    "start": start,
                    "end": end,
                    "description": item.get("description", ""),
                }
            )
        return {"success": True, "events": events}
    except Exception as e:
        # HttpError.reason is the short API message; str(e) dumps the whole blob
        reason = getattr(e, "reason", None) or str(e)
        return {"success": False, "error": str(reason)[:200]}


def delete_calendar_event(event_id: str) -> dict:
    """
    Deletes a calendar event by ID.
    """
    try:
        service = get_calendar_service()
        service.events().delete(
            calendarId="primary",
            eventId=event_id
        ).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
