import os
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from src.utils.config import Config


SCOPES = [
    "https://www.googleapis.com/auth/calendar",   # Full calendar access
    "https://www.googleapis.com/auth/tasks",      # Full tasks access
    "https://www.googleapis.com/auth/gmail.modify",  # Read/send emails
]


CREDENTIALS_PATH = os.path.join(Config.BASE_DIR, "src", "credentials", "credentials.json")
TOKEN_PATH = os.path.join(Config.BASE_DIR, "src", "credentials", "token.json")


def _start_oauth_flow() -> Credentials:
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    return flow.run_local_server(port=0)


def get_credentials() -> Credentials:
    """
    Load or refresh OAuth2 credentials.
    
    FLOW:
    =====
    1. Check if token.json exists (previously saved credentials)
    2. If exists and valid → use it
    3. If expired but has refresh_token → refresh automatically
    4. If no valid credentials → start OAuth flow
    
    OAUTH FLOW (First Run):
    =======================
    1. InstalledAppFlow opens local server on random port
    2. Opens browser to Google consent screen
    3. User logs in and grants permissions
    4. Google redirects to localhost with auth code
    5. Flow exchanges code for tokens
    6. Tokens saved to token.json
    
    Returns:
        Valid Credentials object ready for API calls
        
    Raises:
        Exception if credentials.json not found or auth fails
    """
    creds = None

    # Try to load existing tokens
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    # If no valid credentials, need to get new ones
    if not creds or not creds.valid:
        # Try to refresh expired token
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                # The saved refresh token is no longer usable (revoked/expired).
                # Remove it and ask Google for a fresh token pair.
                if os.path.exists(TOKEN_PATH):
                    os.remove(TOKEN_PATH)
                creds = _start_oauth_flow()
        else:
            # Start OAuth flow - opens browser
            creds = _start_oauth_flow()

        # Save the new/refreshed tokens
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return creds


def get_calendar_service():
    """
    Get authenticated Google Calendar API client.
    
    Returns:
        googleapiclient Resource object for Calendar API v3
        
    USAGE:
        service = get_calendar_service()
        events = service.events().list(calendarId='primary').execute()
    """
    return build("calendar", "v3", credentials=get_credentials())


def get_tasks_service():
    """
    Get authenticated Google Tasks API client.
    
    Returns:
        googleapiclient Resource object for Tasks API v1
        
    USAGE:
        service = get_tasks_service()
        tasks = service.tasks().list(tasklist='@default').execute()
    """
    return build("tasks", "v1", credentials=get_credentials())


def get_gmail_service():
    """
    Get authenticated Gmail API client.
    
    Returns:
        googleapiclient Resource object for Gmail API v1
        
    USAGE:
        service = get_gmail_service()
        messages = service.users().messages().list(userId='me').execute()
    """
    return build("gmail", "v1", credentials=get_credentials())
