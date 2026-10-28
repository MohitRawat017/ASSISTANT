"""
https://developers.google.com/calendar/api/v3/reference
"""

from datetime import datetime, timezone
from src.tools.google.auth import get_calendar_service
from src.utils.config import Config
from src.utils.reliability import execute_google_read, execute_google_write, failure_result, stable_operation_id


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
    operation_id = stable_operation_id("calendar", "create")
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
        result = execute_google_write(
            lambda: service.events().insert(calendarId="primary", body=event),
            provider="calendar",
            operation_id=operation_id,
        )
        if result.ok:
            created = result.pop("value", {})
            result["event_id"] = created.get("id", "")
            result["link"] = created.get("htmlLink", "")
        return result
    except Exception as e:
        return failure_result(e, provider="calendar", operation_id=operation_id)


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
        result = execute_google_read(
            lambda: service.events().list(
                calendarId="primary",
                timeMin=now,          # Only future events
                maxResults=max_results,
                singleEvents=True,    # Expand recurring events
                orderBy="startTime",  # Sort by start time
            ),
            operation_id=stable_operation_id("calendar", "upcoming", str(max_results)),
            max_retries=Config.GOOGLE_MAX_RETRIES,
        )
        if not result.ok:
            return result
        payload = result.pop("value", {})
        # Extract relevant fields from API response
        events = []
        for item in payload.get("items", []):
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
        result["events"] = events
        return result
    except Exception as e:
        return failure_result(e, provider="calendar", operation_id=stable_operation_id("calendar", "upcoming"))


def delete_calendar_event(event_id: str) -> dict:
    """
    Deletes a calendar event by ID.
    """
    operation_id = stable_operation_id("calendar", "delete")
    try:
        service = get_calendar_service()
        return execute_google_write(
            lambda: service.events().delete(calendarId="primary", eventId=event_id),
            provider="calendar",
            operation_id=operation_id,
        )
    except Exception as e:
        return failure_result(e, provider="calendar", operation_id=operation_id)
