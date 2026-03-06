import subprocess
import psutil
import os

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


def open_application(app_name: str) -> dict:
    """
    Opens an application by name.
    Tries: known app map → AppOpener → direct subprocess
    Returns: {"success": True/False, "app": app_name}
    """
    name_lower = app_name.lower().strip()

    # Try known map first
    if name_lower in APP_MAP:
        executable = APP_MAP[name_lower]
        try:
            if executable.startswith("ms-"):
                # Windows URI scheme (settings, etc.)
                os.startfile(executable)
            else:
                subprocess.Popen(executable)
            return {"success": True, "app": app_name, "method": "app_map"}
        except Exception:
            pass  # Fall through to AppOpener

    # Try AppOpener (handles installed apps by display name)
    try:
        import appopener
        appopener.open(app_name)
        return {"success": True, "app": app_name, "method": "appopener"}
    except Exception:
        pass

    # Last resort — direct subprocess
    try:
        subprocess.Popen(app_name)
        return {"success": True, "app": app_name, "method": "subprocess"}
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
            if exe_name in proc.info["name"].lower():
                return {"running": True, "app": app_name}
        except psutil.NoSuchProcess:
            continue
    return {"running": False, "app": app_name}
