"""Deterministic unit tests for src/tools/google/auth.py.

No network and no browser: the auth module's ``Credentials``, ``Request`` and
``_start_oauth_flow`` names are replaced with in-process fakes, and
``CREDENTIALS_PATH``/``TOKEN_PATH`` are pointed at pytest ``tmp_path`` files.
The tests exercise the token lifecycle end to end:
load -> silent refresh (always attempted) -> typed ReauthRequired error /
interactive browser flow.

Run with:
  uv run --no-project --with pytest --with python-dotenv --with google-auth \
    --with google-auth-oauthlib --with google-api-python-client \
    python -m pytest tests/test_google_auth.py -q --no-test-report
"""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

# These tests run against the real google-auth packages (with faked
# Credentials/Request objects inside). Skip cleanly at collection time when
# they are not installed instead of erroring the whole-suite collect.
pytest.importorskip(
    "google.auth",
    reason="requires google-auth / google-auth-oauthlib (not installed)",
)
pytest.importorskip("google_auth_oauthlib.flow", reason="requires google-auth-oauthlib")
pytest.importorskip("googleapiclient.discovery", reason="requires google-api-python-client")

from google.auth.exceptions import RefreshError

from src.tools.google import auth as google_auth


# Fake token values. Tests assert these never leak into error messages.
FAKE_ACCESS_TOKEN = "fake-access-token-DO-NOT-LEAK-9f2c1a"
FAKE_REFRESH_TOKEN = "fake-refresh-token-DO-NOT-LEAK-7b4e2d"
FAKE_FLOW_ACCESS_TOKEN = "fake-browser-access-token-DO-NOT-LEAK-5c3f0b"
FAKE_FLOW_REFRESH_TOKEN = "fake-browser-refresh-token-DO-NOT-LEAK-8d1a4e"


class FakeRequest:
    """Stand-in for google.auth.transport.requests.Request."""


class FakeCredentials:
    """Stand-in for google.oauth2.credentials.Credentials.

    Mirrors the real semantics get_credentials relies on:
    - expired: True only when an expiry exists and has passed
    - valid: needs a non-None token and to not be expired
    - from_authorized_user_file: loads token/refresh_token/expiry from JSON
    - refresh: rotates the access token, or raises a preset RefreshError
    - to_json: serializes back to the token-file shape
    """

    def __init__(self, token=None, refresh_token=None, expiry=None, scopes=None,
                 refresh_error=None):
        self.token = token
        self.refresh_token = refresh_token
        self.expiry = expiry
        self.scopes = scopes
        self.refresh_error = refresh_error
        self.refresh_calls = 0
        self.refresh_requests = []

    @property
    def expired(self):
        return self.expiry is not None and self.expiry <= datetime.now(timezone.utc)

    @property
    def valid(self):
        return self.token is not None and not self.expired

    @classmethod
    def from_authorized_user_file(cls, filename, scopes):
        with open(filename, "r", encoding="utf-8") as f:
            info = json.load(f)
        expiry = None
        if info.get("expiry"):
            expiry = datetime.fromisoformat(info["expiry"])
        refresh_error = None
        if info.get("raise_on_refresh"):
            # Test hook: make refresh() raise, simulating Google rejecting it.
            refresh_error = RefreshError(info["raise_on_refresh"])
        return cls(
            token=info.get("token"),
            refresh_token=info.get("refresh_token"),
            expiry=expiry,
            scopes=info.get("scopes") or list(scopes),
            refresh_error=refresh_error,
        )

    def refresh(self, request):
        self.refresh_calls += 1
        self.refresh_requests.append(request)
        if self.refresh_error is not None:
            raise self.refresh_error
        # Simulate Google rotating the access token with a fresh ~1h expiry.
        self.token = (self.token or "") + "-refreshed"
        self.expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    def to_json(self):
        return json.dumps(
            {
                "token": self.token,
                "refresh_token": self.refresh_token,
                "expiry": self.expiry.isoformat() if self.expiry else None,
                "scopes": list(self.scopes) if self.scopes else None,
            }
        )


def write_token_file(path, *, token=FAKE_ACCESS_TOKEN,
                     refresh_token=FAKE_REFRESH_TOKEN, hours=None,
                     raise_on_refresh=None):
    """Write a token.json-style file; hours < 0 => expired, hours > 0 => valid."""
    expiry = (
        datetime.now(timezone.utc) + timedelta(hours=hours)
        if hours is not None
        else None
    )
    info = {
        "token": token,
        "refresh_token": refresh_token,
        "expiry": expiry.isoformat() if expiry else None,
        "scopes": list(google_auth.SCOPES),
    }
    if raise_on_refresh is not None:
        info["raise_on_refresh"] = raise_on_refresh
    path.write_text(json.dumps(info), encoding="utf-8")
    return info


@pytest.fixture
def auth_env(monkeypatch, tmp_path):
    """Patch the auth module to operate on tmp_path files with fake auth pieces."""
    token_path = tmp_path / "token.json"
    credentials_path = tmp_path / "credentials.json"

    monkeypatch.setattr(google_auth, "TOKEN_PATH", str(token_path))
    monkeypatch.setattr(google_auth, "CREDENTIALS_PATH", str(credentials_path))
    monkeypatch.setattr(google_auth, "Credentials", FakeCredentials)
    monkeypatch.setattr(google_auth, "Request", FakeRequest)

    flow_calls = []

    def fake_oauth_flow():
        # Recorder: never a real browser.
        flow_calls.append(str(token_path))
        return FakeCredentials(
            token=FAKE_FLOW_ACCESS_TOKEN,
            refresh_token=FAKE_FLOW_REFRESH_TOKEN,
            expiry=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes=list(google_auth.SCOPES),
        )

    monkeypatch.setattr(google_auth, "_start_oauth_flow", fake_oauth_flow)

    class Env:
        pass

    env = Env()
    env.tmp_path = tmp_path
    env.token_path = token_path
    env.credentials_path = credentials_path
    env.flow_calls = flow_calls
    return env


def test_valid_credentials_returned_without_refresh(auth_env):
    """a) Valid, non-expired creds are returned as-is; nothing else happens."""
    write_token_file(auth_env.token_path, hours=1)
    before = auth_env.token_path.read_text(encoding="utf-8")

    creds = google_auth.get_credentials(allow_interactive=False)

    assert creds.token == FAKE_ACCESS_TOKEN
    assert creds.valid
    assert creds.refresh_calls == 0
    assert auth_env.flow_calls == []
    assert auth_env.token_path.read_text(encoding="utf-8") == before


def test_expired_token_silently_refreshed_non_interactive(auth_env):
    """b) Expired + refresh_token: silent refresh even when non-interactive."""
    write_token_file(auth_env.token_path, hours=-1)

    creds = google_auth.get_credentials(allow_interactive=False)

    assert creds.refresh_calls == 1
    assert isinstance(creds.refresh_requests[0], FakeRequest)
    assert creds.token == FAKE_ACCESS_TOKEN + "-refreshed"
    assert creds.expired is False
    assert auth_env.flow_calls == []

    # Refreshed token persisted atomically to token.json (no .tmp leftover).
    data = json.loads(auth_env.token_path.read_text(encoding="utf-8"))
    assert data["token"] == FAKE_ACCESS_TOKEN + "-refreshed"
    assert data["refresh_token"] == FAKE_REFRESH_TOKEN
    assert data["expiry"] is not None
    assert not os.path.exists(str(auth_env.token_path) + ".tmp")


def test_expired_without_refresh_token_raises_reauth_non_interactive(auth_env):
    """c) Expired, no refresh_token, non-interactive: typed ReauthRequired."""
    write_token_file(auth_env.token_path, hours=-1, refresh_token=None)

    with pytest.raises(google_auth.ReauthRequired) as excinfo:
        google_auth.get_credentials(allow_interactive=False)

    message = str(excinfo.value)
    assert "re-authoriz" in message.lower()  # actionable: says how to recover
    assert "token.json" in message
    assert auth_env.flow_calls == []      # no browser flow attempted
    assert auth_env.token_path.exists()   # token file not deleted
    # Privacy: the planted fake secrets must not leak into the error text.
    assert FAKE_ACCESS_TOKEN not in message
    assert FAKE_REFRESH_TOKEN not in message


def test_expired_without_refresh_token_runs_flow_interactively(auth_env):
    """d) Expired, no refresh_token, interactive: browser flow saves a new token."""
    write_token_file(auth_env.token_path, hours=-1, refresh_token=None)
    auth_env.credentials_path.write_text(json.dumps({"installed": {}}), encoding="utf-8")

    creds = google_auth.get_credentials(allow_interactive=True)

    assert len(auth_env.flow_calls) == 1  # fake flow recorded exactly one attempt
    assert creds.token == FAKE_FLOW_ACCESS_TOKEN
    data = json.loads(auth_env.token_path.read_text(encoding="utf-8"))
    assert data["token"] == FAKE_FLOW_ACCESS_TOKEN
    assert data["refresh_token"] == FAKE_FLOW_REFRESH_TOKEN
    assert not os.path.exists(str(auth_env.token_path) + ".tmp")


def test_interactive_reauth_without_client_secret_is_actionable(auth_env):
    write_token_file(auth_env.token_path, hours=-1, refresh_token=None)

    with pytest.raises(google_auth.ReauthRequired, match="credentials.json"):
        google_auth.get_credentials(allow_interactive=True)


def test_failed_refresh_raises_reauth_and_keeps_token_file(auth_env):
    """e) Refresh fails, non-interactive: ReauthRequired; token.json NOT deleted."""
    write_token_file(auth_env.token_path, hours=-1, raise_on_refresh="invalid_grant")
    auth_env.credentials_path.write_text(json.dumps({"installed": {}}), encoding="utf-8")
    before = auth_env.token_path.read_text(encoding="utf-8")

    with pytest.raises(google_auth.ReauthRequired) as excinfo:
        google_auth.get_credentials(allow_interactive=False)

    message = str(excinfo.value)
    assert "token.json" in message
    assert "refresh" in message.lower()
    assert FAKE_ACCESS_TOKEN not in message
    assert FAKE_REFRESH_TOKEN not in message
    # token.json is untouched on disk (kept, not deleted).
    assert auth_env.token_path.read_text(encoding="utf-8") == before
    assert auth_env.flow_calls == []
    assert not os.path.exists(str(auth_env.token_path) + ".tmp")


def test_failed_refresh_falls_back_to_browser_flow_interactively(auth_env):
    """Extra) Refresh fails, interactive + credentials.json present: browser
    re-auth fallback runs and its result overwrites token.json (which was
    never deleted first)."""
    write_token_file(auth_env.token_path, hours=-1, raise_on_refresh="invalid_grant")
    auth_env.credentials_path.write_text(json.dumps({"installed": {}}), encoding="utf-8")

    creds = google_auth.get_credentials(allow_interactive=True)

    assert len(auth_env.flow_calls) == 1
    assert creds.token == FAKE_FLOW_ACCESS_TOKEN
    data = json.loads(auth_env.token_path.read_text(encoding="utf-8"))
    assert data["token"] == FAKE_FLOW_ACCESS_TOKEN


@pytest.mark.parametrize("allow_interactive", [False, True])
def test_failed_refresh_without_credentials_json_mentions_it(auth_env, allow_interactive):
    """f) Refresh fails and credentials.json is missing: ReauthRequired whose
    message mentions credentials.json; token.json kept; no flow attempt."""
    write_token_file(auth_env.token_path, hours=-1, raise_on_refresh="invalid_grant")
    assert not auth_env.credentials_path.exists()

    with pytest.raises(google_auth.ReauthRequired) as excinfo:
        google_auth.get_credentials(allow_interactive=allow_interactive)

    message = str(excinfo.value)
    assert "credentials.json" in message
    assert "token.json" in message
    assert auth_env.token_path.exists()  # token file kept
    assert auth_env.flow_calls == []     # flow cannot run without credentials.json
    assert FAKE_ACCESS_TOKEN not in message
    assert FAKE_REFRESH_TOKEN not in message


def test_missing_token_file_non_interactive_preserves_setup_error(auth_env):
    """g) No token.json at all, non-interactive: legacy "credentials not set
    up" RuntimeError is preserved (not ReauthRequired)."""
    with pytest.raises(RuntimeError) as excinfo:
        google_auth.get_credentials(allow_interactive=False)

    assert not isinstance(excinfo.value, google_auth.ReauthRequired)
    message = str(excinfo.value)
    assert "Google credentials are missing" in message
    assert "token.json" in message  # points at what to regenerate
    assert auth_env.flow_calls == []


def test_unreadable_token_file_non_interactive_preserves_error(auth_env):
    """Extra) Corrupt token.json, non-interactive: legacy read-failure
    RuntimeError is preserved, and the file content (incl. the fake token)
    must not leak into the message."""
    auth_env.token_path.write_text("this is not json " + FAKE_ACCESS_TOKEN,
                                   encoding="utf-8")

    with pytest.raises(RuntimeError) as excinfo:
        google_auth.get_credentials(allow_interactive=False)

    assert not isinstance(excinfo.value, google_auth.ReauthRequired)
    message = str(excinfo.value)
    assert "could not be read" in message
    assert FAKE_ACCESS_TOKEN not in message
    assert auth_env.flow_calls == []
