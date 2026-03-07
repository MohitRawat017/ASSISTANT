import subprocess
import psutil
import os
from pywinauto import Desktop

# Common app name → executable mappings for Windows 11
# This is the single source of truth for app name resolution
APP_MAP = {
    # Browsers
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    # Text/Code editors
    "notepad": "notepad.exe",
    "vscode": "Code.exe",
    "vs code": "Code.exe",
    "visual studio code": "Code.exe",
    "code": "Code.exe",
    # System apps
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "task manager": "Taskmgr.exe",
    "settings": "ms-settings:",
    "control panel": "control.exe",
    "snipping tool": "SnippingTool.exe",
    # Media
    "spotify": "Spotify.exe",
    "vlc": "vlc.exe",
    "camera": "Windows Camera",
    "photos": "Microsoft Photos",
    "music": "Windows Media Player",
    "media player": "Windows Media Player",
    "store": "Microsoft Store",
    # Communication
    "discord": "Discord.exe",
    "teams": "Teams.exe",
    "zoom": "Zoom.exe",
    "slack": "Slack.exe",
    "outlook": "OUTLOOK.EXE",
    # Microsoft Office
    "word": "WINWORD.EXE",
    "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE",
    # Games
    "steam": "Steam.exe",
}


def _focus_app_by_process(executable: str) -> bool:
    """
    Focus a running application by its executable name.
    Returns True if successfully focused, False otherwise.
    """
    exe_name = executable.lower().replace(".exe", "")
    desktop = Desktop(backend="uia")
    
    for window in desktop.windows():
        try:
            pid = window.process_id()
            proc = psutil.Process(pid)
            proc_name = proc.name().lower()
            
            # Match process name
            if exe_name in proc_name or proc_name.startswith(exe_name):
                window.set_focus()
                return True
        except Exception:
            continue
    return False


def open_application(app_name: str) -> dict:
    """
    Opens an application by name.
    If already running, focuses the existing window instead of opening new instance.
    Tries: known app map → AppOpener → direct subprocess
    Returns: {"success": True/False, "app": app_name, "focused": bool}
    """
    name_lower = app_name.lower().strip()

    # Determine the executable name
    executable = APP_MAP.get(name_lower, app_name)
    
    # Check if already running - focus instead of opening new instance
    running_check = is_app_running(app_name)
    if running_check.get("running", False):
        # App is running - try to focus its window
        if _focus_app_by_process(executable):
            return {"success": True, "app": app_name, "focused": True, "method": "focus"}
        # Couldn't focus by process, try by app name in window title
        desktop = Desktop(backend="uia")
        for window in desktop.windows():
            try:
                title = window.window_text()
                if name_lower in title.lower():
                    window.set_focus()
                    return {"success": True, "app": app_name, "focused": True, "method": "focus_title"}
            except Exception:
                continue

    # App not running or couldn't focus - open new instance
    # Try known map first
    if name_lower in APP_MAP:
        executable = APP_MAP[name_lower]
        try:
            if executable.startswith("ms-"):
                # Windows URI scheme (settings, etc.)
                os.startfile(executable)
            else:
                subprocess.Popen(executable)
            return {"success": True, "app": app_name, "method": "app_map", "focused": False}
        except Exception:
            pass  # Fall through to AppOpener

    # Try AppOpener (handles installed apps by display name)
    try:
        import AppOpener
        AppOpener.open(app_name)
        return {"success": True, "app": app_name, "method": "appopener", "focused": False}
    except Exception:
        pass

    # Last resort — direct subprocess
    try:
        subprocess.Popen(app_name)
        return {"success": True, "app": app_name, "method": "subprocess", "focused": False}
    except Exception as e:
        return {"success": False, "error": f"Could not open '{app_name}': {str(e)}"}


def close_application(app_name: str) -> dict:
    """
    Closes an application by process name or display name.
    Returns: {"success": True, "killed": count}
    """
    name_lower = app_name.lower().strip()
    executable = APP_MAP.get(name_lower, app_name)
    exe_name = executable.lower().replace(".exe", "")

    killed = 0
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            proc_name_raw = proc.info.get("name")
            if proc_name_raw is None:
                continue
            proc_name = proc_name_raw.lower().replace(".exe", "")
            if exe_name in proc_name or proc_name in exe_name:
                proc.terminate()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if killed > 0:
        return {"success": True, "killed": killed, "app": app_name}
    return {"success": False, "error": f"No process found for '{app_name}'"}


def is_app_running(app_name: str) -> dict:
    """Check if an application is currently running."""
    name_lower = app_name.lower().strip()
    executable = APP_MAP.get(name_lower, app_name)
    exe_name = executable.lower().replace(".exe", "")

    for proc in psutil.process_iter(["name"]):
        try:
            proc_name_raw = proc.info.get("name")
            if proc_name_raw is None:
                continue
            if exe_name in proc_name_raw.lower():
                return {"running": True, "app": app_name}
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"running": False, "app": app_name}
