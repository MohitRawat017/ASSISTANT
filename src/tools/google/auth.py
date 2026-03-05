"""
================================================================================
GOOGLE OAUTH2 AUTHENTICATION MODULE
================================================================================

Handles Google API authentication using OAuth2. All Google tool modules
(calendar, tasks, gmail) import from here to get authenticated API clients.

OAUTH2 FLOW EXPLAINED:
=====================
1. First Run:
   - Opens browser to Google login page
   - User grants permissions (calendar, tasks, gmail)
   - Google returns authorization code
   - Code exchanged for access token + refresh token
   - Tokens saved to token.json

2. Subsequent Runs:
   - Load tokens from token.json
   - If access token expired, use refresh token to get new one
   - No user interaction needed

3. Token Refresh:
   - Access tokens expire after ~1 hour
   - Refresh tokens are long-lived (until revoked)
   - Automatic refresh happens transparently

SCOPES:
=======
SCOPES define what permissions the app requests:
- calendar: Create/read calendar events
- tasks: Manage Google Tasks
- gmail.modify: Read and send emails

SECURITY:
=========
- credentials.json: OAuth client config (from Google Cloud Console)
- token.json: User's access/refresh tokens (generated on first run)
- NEVER commit these files to version control!

REQUIRED PACKAGES:
=================
pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2

================================================================================
KEY CONCEPTS FOR INTERVIEW:
================================================================================

Q: What's the difference between access token and refresh token?
A: Access token: Short-lived (~1 hour), used for API calls
   Refresh token: Long-lived, used to get new access tokens
   This is more secure than permanent tokens.

Q: Why OAuth2 instead of just API keys?
A: OAuth2 provides:
   - User consent (user must approve access)
   - Scoped access (only requested permissions)
   - Revocable (user can revoke anytime)
   - Secure (no password sharing)

================================================================================
"""

import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from src.utils.config import Config

# =============================================================================
# OAUTH2 SCOPES
# =============================================================================
# Scopes define what permissions we request from the user
# The user sees these during the consent screen

SCOPES = [
    "https://www.googleapis.com/auth/calendar",   # Full calendar access
    "https://www.googleapis.com/auth/tasks",      # Full tasks access
    "https://www.googleapis.com/auth/gmail.modify",  # Read/send emails
]

# =============================================================================
# FILE PATHS
# =============================================================================
# credentials.json: Download from Google Cloud Console (OAuth client)
# token.json: Generated on first run, stores user's tokens

CREDENTIALS_PATH = os.path.join(Config.BASE_DIR, "src", "credentials", "credentials.json")
TOKEN_PATH = os.path.join(Config.BASE_DIR, "src", "credentials", "token.json")


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
            creds.refresh(Request())
        else:
            # Start OAuth flow - opens browser
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

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


# =============================================================================
# INTERVIEW QUESTIONS FOR THIS FILE
# =============================================================================
"""
Q1: What is the OAuth2 flow and why is it used?
A: OAuth2 allows third-party apps to access user data without sharing
   passwords. The flow:
   1. App requests authorization (redirects to Google)
   2. User grants permission
   3. Google gives authorization code to app
   4. App exchanges code for access token
   5. App uses token to access APIs
   
   Benefits: Secure, revocable, scoped access.

Q2: Why store tokens in token.json instead of re-authenticating each time?
A: 1. User experience: No need to login every session
   2. API limits: Fewer auth calls
   3. Offline access: App can work without user present
   4. Speed: Instant startup vs waiting for OAuth flow

Q3: What happens when the access token expires?
A: Access tokens expire after ~1 hour. When this happens:
   - API calls return 401 Unauthorized
   - google-auth library catches this
   - Uses refresh_token to get new access_token
   - Retries the API call
   All this happens automatically in the background.

Q4: What is the difference between credentials.json and token.json?
A: credentials.json: OAuth client configuration from Google Cloud Console
   - Client ID and secret
   - Redirect URIs
   - Created once in Google Cloud Console
   
   token.json: User-specific tokens generated by OAuth flow
   - Access token
   - Refresh token
   - Created on first run, refreshed as needed

Q5: What are scopes and why do they matter?
A: Scopes define what permissions the app requests:
   - calendar: Can read/write calendar
   - tasks: Can manage tasks
   - gmail.modify: Can read and send email
   
   The user sees these on the consent screen. Principle of least
   privilege: request only what you need.

Q6: How would you handle revoked access?
A: If user revokes access in their Google account:
   1. Refresh fails with error
   2. Delete token.json
   3. Re-run OAuth flow to get new tokens
   
   Add error handling:
   try:
       creds.refresh(Request())
   except google.auth.exceptions.RefreshError:
       os.remove(TOKEN_PATH)
       creds = get_credentials()  # Re-auth

Q7: Why use run_local_server() instead of run_console()?
A: run_local_server():
   - Opens browser automatically
   - Receives callback on localhost
   - Works with modern Google security requirements
   
   run_console():
   - Prints URL, user must click
   - User pastes code back
   - Less user-friendly but works in headless environments

Q8: How would you add support for multiple Google accounts?
A: 1. Store tokens per account: token_{account_id}.json
   2. Add account parameter to get_credentials(account_id)
   3. Track which account to use per operation
   4. Handle account switching in the UI

Q9: What security considerations are important?
A: 1. Never commit credentials.json or token.json to git
   2. Use environment variables for sensitive paths
   3. Restrict API key usage in Google Cloud Console
   4. Use minimal scopes needed
   5. Implement token encryption at rest if needed

Q10: How does googleapiclient.discovery.build work?
A: build() creates a service object that:
   1. Downloads API discovery document
   2. Creates methods matching API endpoints
   3. Handles authentication headers
   4. Returns a Resource object with methods like .events(), .tasks()
   
   This is simpler than manually constructing HTTP requests.
"""