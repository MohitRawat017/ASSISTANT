"""
Deterministic smoke tests for the manager package and the tool registry.

Proves the import graph stays healthy on machines without the
Windows/desktop-only dependencies: pyautogui, pywinauto and psutil are
stubbed in sys.modules before wrapped_tools is imported (it only uses
them inside function bodies), while langchain-core is real so the @tool
decorators genuinely run and build the registry.
"""

import sys
import types

import pytest


def _stub_module(monkeypatch, name, **attrs):
    """Insert a lightweight fake module into sys.modules."""
    module = types.ModuleType(name)
    for attr, value in attrs.items():
        setattr(module, attr, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _install_offline_stubs(monkeypatch):
    """
    Stub every library that wrapped_tools imports at module level but
    only uses inside function bodies (these tests never call them).

    Covers exactly the transitive module-level imports of:
    - src/tools/pc_automation/*: pyautogui, psutil, pywinauto
    - src/tools/google/auth.py: google.*, google_auth_oauthlib, googleapiclient
    """
    # PC automation (Windows desktop only)
    _stub_module(monkeypatch, "pyautogui")
    _stub_module(monkeypatch, "psutil")
    _stub_module(monkeypatch, "pywinauto", Desktop=type("Desktop", (), {}))

    # Google API client stack
    google = _stub_module(monkeypatch, "google")
    google_auth = _stub_module(monkeypatch, "google.auth")
    google_auth.exceptions = _stub_module(
        monkeypatch,
        "google.auth.exceptions",
        RefreshError=type("RefreshError", (Exception,), {}),
    )
    google_auth.transport = _stub_module(monkeypatch, "google.auth.transport")
    google_auth.transport.requests = _stub_module(
        monkeypatch,
        "google.auth.transport.requests",
        Request=type("Request", (), {}),
    )
    google.auth = google_auth

    google_oauth2 = _stub_module(monkeypatch, "google.oauth2")
    google_oauth2.credentials = _stub_module(
        monkeypatch,
        "google.oauth2.credentials",
        Credentials=type("Credentials", (), {}),
    )
    google.oauth2 = google_oauth2

    google_auth_oauthlib = _stub_module(monkeypatch, "google_auth_oauthlib")
    google_auth_oauthlib.flow = _stub_module(
        monkeypatch,
        "google_auth_oauthlib.flow",
        InstalledAppFlow=type("InstalledAppFlow", (), {}),
    )

    googleapiclient = _stub_module(monkeypatch, "googleapiclient")
    googleapiclient.discovery = _stub_module(
        monkeypatch,
        "googleapiclient.discovery",
        build=lambda *args, **kwargs: None,
    )


# ── Manager package ───────────────────────────────────────────────────────

@pytest.mark.safe_smoke
def test_managers_package_exports_alarm_manager():
    from src import managers

    assert managers.AlarmManager is not None
    assert managers.__all__ == ["AlarmManager"]


@pytest.mark.safe_smoke
def test_alarm_manager_importable_from_submodule():
    from src.managers.alarm_manager import AlarmManager

    assert AlarmManager is not None


@pytest.mark.safe_smoke
def test_alarm_manager_constructs_against_temp_db(tmp_path):
    from src.managers.alarm_manager import AlarmManager

    db_path = str(tmp_path / "smoke_alarms.db")
    mgr = AlarmManager(db_path)

    assert mgr.db_path == db_path
    assert mgr.get_alarms() == []


# ── Tool registry ─────────────────────────────────────────────────────────

@pytest.mark.safe_smoke
def test_tool_registry_loads(monkeypatch):
    _install_offline_stubs(monkeypatch)

    from src.tools.wrapped_tools import ALL_TOOLS

    assert len(ALL_TOOLS) > 0


@pytest.mark.safe_smoke
def test_tool_registry_contains_core_tools(monkeypatch):
    _install_offline_stubs(monkeypatch)

    from src.tools.wrapped_tools import ALL_TOOLS

    names = {t.name for t in ALL_TOOLS}
    for expected in (
        "set_alarm",
        "save_memory",
        "send_email",
        "find_and_click",
        "take_screenshot_tool",
    ):
        assert expected in names
