import os
import pyautogui
from datetime import datetime
from src.utils.config import Config

SCREENSHOT_DIR = os.path.join(Config.BASE_DIR, "data", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def take_screenshot(filename: str = None) -> str:
    """
    Captures full screen screenshot.
    Returns: absolute file path to saved screenshot
    """
    if not filename:
        filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

    path = os.path.join(SCREENSHOT_DIR, filename)
    screenshot = pyautogui.screenshot()
    screenshot.save(path)
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
    return path
