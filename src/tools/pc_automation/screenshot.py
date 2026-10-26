import os
import pyautogui
from datetime import datetime
from src.utils.config import Config

SCREENSHOT_DIR = os.path.join(Config.BASE_DIR, "data", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def enforce_screenshot_retention() -> None:
    """
    Keeps data/screenshots bounded: after a save, deletes the oldest *.png
    files beyond Config.SCREENSHOT_MAX_FILES. Best-effort — a retention
    failure must never break the screenshot that was just taken.
    """
    try:
        png_paths = [
            os.path.join(SCREENSHOT_DIR, name)
            for name in os.listdir(SCREENSHOT_DIR)
            if name.lower().endswith(".png")
        ]
        png_paths.sort(key=os.path.getmtime, reverse=True)  # newest first
        keep_count = max(1, int(Config.SCREENSHOT_MAX_FILES))
        for old_path in png_paths[keep_count:]:
            os.remove(old_path)
    except OSError:
        pass  # retention is housekeeping; the saved screenshot is unaffected


def _validated_filename(filename: str) -> str:
    """Return a safe PNG basename confined to the screenshot directory."""
    if filename is None:
        return f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    filename = os.fspath(filename)
    if (
        not filename
        or os.path.basename(filename) != filename
        or "\\" in filename
        or not filename.lower().endswith(".png")
    ):
        raise ValueError("Screenshot filename must be a .png basename")
    return filename


def take_screenshot(filename: str = None) -> str:
    """
    Captures full screen screenshot.
    Returns: absolute file path to saved screenshot
    """
    path = os.path.join(SCREENSHOT_DIR, _validated_filename(filename))
    screenshot = pyautogui.screenshot()
    screenshot.save(path)
    enforce_screenshot_retention()
    return path


def take_region_screenshot(x: int, y: int, width: int, height: int) -> str:
    """
    Captures a specific screen region.
    Returns: absolute file path to saved screenshot
    """
    filename = f"region_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = os.path.join(SCREENSHOT_DIR, filename)
    screenshot = pyautogui.screenshot(region=(x, y, width, height))
    screenshot.save(path)
    enforce_screenshot_retention()
    return path
