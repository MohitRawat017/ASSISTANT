"""Google OAuth2 credential management for the Google tool services.

Credential lifecycle (get_credentials):
  1. LOAD: read the previously saved token.json from disk.
  2. SILENT REFRESH: if the saved token is expired but has a refresh_token,
     refresh it in the background. This is attempted regardless of
     allow_interactive so agent tool calls keep working after the ~1h
     access-token expiry; the rotated token is persisted atomically.
  3. REAUTH: if the token cannot be loaded or silently refreshed, raise the
     typed ReauthRequired error and keep the saved token file on disk. Only a
     caller that explicitly passes allow_interactive=True may fall back to the
     blocking browser OAuth flow.
"""

import os

from google.auth.exceptions import RefreshError
try:
    from google.auth.exceptions import TransportError
except ImportError:  # lightweight import stubs and older google-auth releases
    TransportError = OSError
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


class ReauthRequired(RuntimeError):
    """A saved Google token exists but cannot be used or silently refreshed.

    Raised when the saved token is expired/invalid with no refresh token, or
    when a silent refresh attempt fails (e.g. the refresh token was revoked,
    or Google could not be reached). The saved token file is deliberately kept
    on disk; recovery requires an explicit browser re-authorization.
    """


def _start_oauth_flow() -> Credentials:
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    return flow.run_local_server(port=0)


def _auth_unavailable(reason: str) -> RuntimeError:
    return RuntimeError(
        f"{reason} Run an interactive Google auth flow to regenerate "
        f"{os.path.relpath(TOKEN_PATH, Config.BASE_DIR)}."
    )


def _interactive_credentials(token_rel: str, credentials_rel: str) -> Credentials:
    """Start browser auth only when its client-secret file is available."""
    if not os.path.exists(CREDENTIALS_PATH):
        raise ReauthRequired(
            f"{credentials_rel} is missing. Restore it, then run "
            f"python -m src.tools.google.auth to create {token_rel}."
        )
    return _start_oauth_flow()


def get_credentials(allow_interactive: bool = True) -> Credentials:
    """
    Load, silently refresh, or (interactively) re-create OAuth2 credentials.

    POLICY:
    =======
    - A saved token with a refresh_token is ALWAYS refreshed silently once
      expired -- even when allow_interactive=False (startup / tool calls).
    - allow_interactive gates ONLY the browser OAuth flow; a browser flow is
      never launched in non-interactive mode.
    - token.json is never deleted by this function: a failed refresh keeps the
      file on disk so a transient failure cannot destroy the refresh token.
    - Failures surface as the typed ReauthRequired error, or as the legacy
      "credentials not set up" RuntimeError when no token exists at all.

    Args:
        allow_interactive: When False, never open the browser OAuth flow. This is
            used during app startup and agent tool calls so missing/stale
            credentials degrade cleanly into a typed error.

    Returns:
        Valid Credentials object ready for API calls

    Raises:
        ReauthRequired: a saved token exists but is expired/invalid and could
            not be silently refreshed; a browser re-authorization is required.
        RuntimeError: no saved token exists (and no browser flow may run), or
            the saved token file could not be read.
    """
    token_rel = os.path.relpath(TOKEN_PATH, Config.BASE_DIR)
    credentials_rel = os.path.relpath(CREDENTIALS_PATH, Config.BASE_DIR)

    creds = None

    # Try to load existing tokens
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception as e:
            if not allow_interactive:
                raise _auth_unavailable(
                    "Saved Google token could not be read."
                ) from e
            creds = _interactive_credentials(token_rel, credentials_rel)

    # If no valid credentials, need to get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Silent refresh: always attempted, interactive or not, so tool
            # calls survive the ~1h access-token expiry.
            try:
                creds.refresh(Request())
            except (RefreshError, TransportError, OSError, ValueError) as e:
                # Never delete token.json here: the saved refresh token may
                # still be recoverable (e.g. a transient network error), and
                # wiping it would force a full browser re-consent.
                if allow_interactive and os.path.exists(CREDENTIALS_PATH):
                    # Explicitly interactive caller: fall back to a full
                    # browser re-consent. The flow's result is saved atomically
                    # below, overwriting the stale token only on success.
                    creds = _interactive_credentials(token_rel, credentials_rel)
                else:
                    if os.path.exists(CREDENTIALS_PATH):
                        recovery = (
                            f"Re-authorize by deleting {token_rel} and running "
                            "the app interactively."
                        )
                    else:
                        recovery = (
                            f"{credentials_rel} is missing, so browser "
                            "re-authorization is unavailable; restore it, then "
                            f"delete {token_rel} and re-authorize interactively."
                        )
                    raise ReauthRequired(
                        "The saved Google token could not be refreshed (it may "
                        "have been revoked or expired, or Google could not be "
                        f"reached). {token_rel} was kept. {recovery}"
                    ) from e
        elif creds is not None:
            # A saved token exists but cannot be silently refreshed (expired
            # or otherwise unusable, with no refresh token).
            if not allow_interactive:
                raise ReauthRequired(
                    "The saved Google token is expired or otherwise unusable "
                    "and cannot be silently refreshed. Re-authorize by "
                    f"deleting {token_rel} and running the app interactively."
                )
            creds = _interactive_credentials(token_rel, credentials_rel)
        else:
            # No token.json on disk: Google credentials were never set up.
            if not allow_interactive:
                raise _auth_unavailable(
                    "Google credentials are missing or require browser sign-in."
                )
            # Start OAuth flow - opens browser
            creds = _interactive_credentials(token_rel, credentials_rel)

        # Save the new/refreshed tokens atomically: write a temp file next to
        # the target, then swap it in, so a crash mid-write cannot corrupt
        # token.json
        tmp_path = TOKEN_PATH + ".tmp"
        with open(tmp_path, "w") as token:
            token.write(creds.to_json())
        os.replace(tmp_path, TOKEN_PATH)

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
    # Non-interactive: an expired token during an agent tool call is refreshed
    # silently; if that fails a typed ReauthRequired error is raised and no
    # blocking browser OAuth flow is ever launched.
    return build("calendar", "v3", credentials=get_credentials(allow_interactive=False))


def get_tasks_service():
    """
    Get authenticated Google Tasks API client.
    
    Returns:
        googleapiclient Resource object for Tasks API v1
        
    USAGE:
        service = get_tasks_service()
        tasks = service.tasks().list(tasklist='@default').execute()
    """
    # Non-interactive: see get_calendar_service().
    return build("tasks", "v1", credentials=get_credentials(allow_interactive=False))


def get_gmail_service():
    """
    Get authenticated Gmail API client.
    
    Returns:
        googleapiclient Resource object for Gmail API v1
        
    USAGE:
        service = get_gmail_service()
        messages = service.users().messages().list(userId='me').execute()
    """
    # Non-interactive: see get_calendar_service().
    return build("gmail", "v1", credentials=get_credentials(allow_interactive=False))


if __name__ == "__main__":
    try:
        get_credentials(allow_interactive=True)
    except Exception as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Google credentials saved to {os.path.relpath(TOKEN_PATH, Config.BASE_DIR)}")
