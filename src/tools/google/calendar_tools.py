"""
================================================================================
GOOGLE CALENDAR API TOOLS
================================================================================

Raw functions for Google Calendar operations. These functions are wrapped
by @tool decorators in wrapped_tools.py for use by the LangGraph agent.

WHY SEPARATE RAW FUNCTIONS?
===========================
1. Testability: Can test API calls independently
2. Reusability: Can be called from other code, not just agent
3. Separation of concerns: API logic vs tool documentation
4. Error handling: Consistent error format for all operations

API DOCUMENTATION:
==================
https://developers.google.com/calendar/api/v3/reference

COMMON PATTERNS:
================
- All functions return dict with "success" key
- Error messages in "error" key for debugging
- ISO 8601 datetime format for all times

================================================================================
KEY CONCEPTS FOR INTERVIEW:
================================================================================

Q: Why use the primary calendar?
A: Primary calendar is the user's main calendar. It always exists and
   is the default view in Google Calendar. Other calendars could be
   shared calendars or secondary calendars.

================================================================================
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
    
    TIMEZONE HANDLING:
    ==================
    All times are in the specified timezone (default: IST/Asia/Kolkata).
    The API accepts local time + timezone, converts to UTC internally.
    
    Args:
        title: Event title/summary
        start_time: ISO format "2025-03-15T10:00:00" (local time)
        end_time: ISO format "2025-03-15T11:00:00" (local time)
        description: Optional event description
        tz: Timezone string (default: IST)
        
    Returns:
        {"success": True, "event_id": "...", "link": "..."} on success
        {"success": False, "error": "..."} on failure
    """
    try:
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


def get_upcoming_events(max_results: int = 10) -> list:
    """
    Returns the next N calendar events from now.
    
    TIME FILTERING:
    ===============
    Uses timeMin parameter to get only future events.
    Events are ordered by start time (singleEvents=True, orderBy='startTime').
    
    Args:
        max_results: Maximum number of events to return
        
    Returns:
        List of event dicts with: id, title, start, end, description
        Empty list on error
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
            # Handle both dateTime (timed events) and date (all-day events)
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
    
    WARNING:
    ========
    This is permanent - cannot be undone. Consider implementing
    soft delete or confirmation for production use.
    
    Args:
        event_id: Google Calendar event ID
        
    Returns:
        {"success": True} on success
        {"success": False, "error": "..."} on failure
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


# =============================================================================
# INTERVIEW QUESTIONS FOR THIS FILE
# =============================================================================
"""
Q1: How does the Calendar API handle timezones?
A: You can specify timezone in two ways:
   1. Pass timeZone in start/end objects (what we do)
   2. Pass UTC time with 'Z' suffix: "2025-03-15T04:30:00Z"
   
   Best practice: Always specify timezone explicitly.

Q2: What's the difference between singleEvents=True and False?
A: singleEvents=True: Expands recurring events into individual instances
   singleEvents=False: Returns the recurring event template
   
   Example: A weekly meeting appears as:
   - True: 7 separate events for next 7 weeks
   - False: 1 recurring event definition
   
   We use True because users want to see upcoming instances.

Q3: How would you handle all-day events?
A: All-day events use "date" instead of "dateTime":
   - Timed: {"dateTime": "2025-03-15T10:00:00"}
   - All-day: {"date": "2025-03-15"}
   
   The code handles both by checking which field exists.

Q4: What is the calendarId?
A: "primary" = user's main calendar
   Other IDs can be:
   - Email addresses (shared calendars)
   - IDs from calendarList.list()
   
   We use "primary" for simplicity.

Q5: How would you add attendees to an event?
A: Add "attendees" field to event object:
   event = {
       "summary": "Meeting",
       "start": {...},
       "end": {...},
       "attendees": [
           {"email": "person1@gmail.com"},
           {"email": "person2@gmail.com"}
       ]
   }
   
   Google sends invitations automatically.

Q6: What are common errors with Calendar API?
A: - 401: Auth token expired/invalid
   - 403: Permission denied (scope not granted)
   - 404: Event not found
   - 400: Invalid request (bad datetime format)
   
   All are caught by our try/except and returned as errors.

Q7: How would you implement event search?
A: Use the 'q' parameter:
   service.events().list(
       calendarId="primary",
       q="meeting",  # Search term
       ...
   )
   
   Searches title and description.

Q8: What's the rate limit for Calendar API?
A: - 1,000,000 requests/day per user
   - ~100 requests/100 seconds per user
   
   For personal use, unlikely to hit limits.
   Implement exponential backoff for production.

Q9: How would you handle recurring events?
A: To CREATE recurring event, add "recurrence" field:
   event = {
       "summary": "Weekly standup",
       "start": {"dateTime": "2025-03-15T10:00:00", "timeZone": "Asia/Kolkata"},
       "end": {"dateTime": "2025-03-15T10:30:00", "timeZone": "Asia/Kolkata"},
       "recurrence": ["RRULE:FREQ=WEEKLY;COUNT=10"]
   }
   
   RRULE is RFC 5545 standard.

Q10: Why return dict instead of raising exceptions?
A: The tool wrapper needs to return a string to the LLM.
    By returning dict with success/error, the wrapper can:
    1. Check success flag
    2. Format appropriate message for user
    3. Log errors for debugging
"""