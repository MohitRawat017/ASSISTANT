"""
Shared Google OAuth2 authentication module.
All Google tool modules (calendar, tasks, gmail) import from here.

Required packages (add to requirements.txt):
    google-api-python-client
    google-auth
    google-auth-oauthlib
    google-auth-httplib2
"""

import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from src.utils.config import Config

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/gmail.modify",
]

CREDENTIALS_PATH = os.path.join(Config.BASE_DIR, "src", "credentials", "credentials.json")
TOKEN_PATH = os.path.join(Config.BASE_DIR, "src", "credentials", "token.json")


def get_credentials() -> Credentials:
    """
    Load or refresh OAuth2 credentials.
    First run: opens browser for Google login.
    Subsequent runs: uses saved token.json silently.
    """
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return creds


def get_calendar_service():
    """Returns authenticated Google Calendar API client."""
    return build("calendar", "v3", credentials=get_credentials())


def get_tasks_service():
    """Returns authenticated Google Tasks API client."""
    return build("tasks", "v1", credentials=get_credentials())


def get_gmail_service():
    """Returns authenticated Gmail API client."""
    return build("gmail", "v1", credentials=get_credentials())
