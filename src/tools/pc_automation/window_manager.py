import psutil
from pywinauto import Desktop


def get_open_windows() -> list:
    """
    Returns list of all visible open windows.
    Returns: [{"title": str, "pid": int, "process": str}, ...]
    """
    windows = []
    desktop = Desktop(backend="uia")
    for window in desktop.windows():
        try:
            title = window.window_text()
            if title and title.strip():  # skip blank title windows
                pid = window.process_id()
                proc = psutil.Process(pid)
                windows.append({
                    "title": title,
                    "pid": pid,
                    "process": proc.name()
                })
        except Exception:
            continue
    return windows


def focus_window(title_keyword: str) -> dict:
    """
    Brings a window to the foreground by partial title match.
    title_keyword: partial window title, case insensitive
    Returns: {"success": True/False, "window": title}
    """
    desktop = Desktop(backend="uia")
    for window in desktop.windows():
        try:
            title = window.window_text()
            if title_keyword.lower() in title.lower():
                window.set_focus()
                return {"success": True, "window": title}
        except Exception:
            continue
    return {"success": False, "error": f"No window found matching '{title_keyword}'"}


def close_window(title_keyword: str) -> dict:
    """
    Closes a window by partial title match.
    Returns: {"success": True/False}
    """
    desktop = Desktop(backend="uia")
    for window in desktop.windows():
        try:
            title = window.window_text()
            if title_keyword.lower() in title.lower():
                window.close()
                return {"success": True, "closed": title}
        except Exception:
            continue
    return {"success": False, "error": f"No window found matching '{title_keyword}'"}


def minimize_window(title_keyword: str) -> dict:
    """Minimizes a window by partial title match."""
    desktop = Desktop(backend="uia")
    for window in desktop.windows():
        try:
            title = window.window_text()
            if title_keyword.lower() in title.lower():
                window.minimize()
                return {"success": True, "minimized": title}
        except Exception:
            continue
    return {"success": False, "error": f"No window found matching '{title_keyword}'"}


def maximize_window(title_keyword: str) -> dict:
    """Maximizes a window by partial title match."""
    desktop = Desktop(backend="uia")
    for window in desktop.windows():
        try:
            title = window.window_text()
            if title_keyword.lower() in title.lower():
                window.maximize()
                return {"success": True, "maximized": title}
        except Exception:
            continue
    return {"success": False, "error": f"No window found matching '{title_keyword}'"}


def minimize_all_windows() -> dict:
    """Minimizes all windows — shows desktop."""
    import pyautogui
    pyautogui.hotkey("win", "d")
    return {"success": True}
