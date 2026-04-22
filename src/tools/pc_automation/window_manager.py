import psutil
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pywinauto import Desktop

SCAN_TIMEOUT_SECONDS = 5.0


def _scan_open_windows(windows: list, stop_event: threading.Event) -> None:
    """Collect visible windows into a shared list."""
    try:
        # win32 backend is significantly faster/more stable for broad window scans.
        desktop = Desktop(backend="win32")
        for window in desktop.windows():
            if stop_event.is_set():
                break
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
    except Exception as e:
        windows.append({"error": f"scan failed: {e}"})


def get_open_windows() -> list:
    """
    Returns list of all visible open windows.
    Returns: [{"title": str, "pid": int, "process": str}, ...]
    """
    windows = []
    stop_event = threading.Event()
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_scan_open_windows, windows, stop_event)

    try:
        future.result(timeout=SCAN_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        stop_event.set()
        windows.append({"error": "scan timed out"})
    except Exception as e:
        windows.append({"error": f"scan failed: {e}"})
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

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
