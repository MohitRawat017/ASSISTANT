import pyautogui

# Safety settings — set once at import
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.02  # Reduced from 0.1 for faster typing


def mouse_click(x: int, y: int, button: str = "left", clicks: int = 1) -> dict:
    """
    Click at screen coordinates.
    button: "left", "right", "middle"
    clicks: 1 for single, 2 for double click
    Returns: {"success": True, "x": x, "y": y}
    """
    pyautogui.click(x, y, button=button, clicks=clicks)
    return {"success": True, "x": x, "y": y}


def mouse_move(x: int, y: int, duration: float = 0.3) -> dict:
    """
    Move mouse to coordinates smoothly.
    duration: seconds to take for movement (0 = instant)
    """
    pyautogui.moveTo(x, y, duration=duration)
    return {"success": True, "x": x, "y": y}


def type_text(text: str, interval: float = 0.05) -> dict:
    """
    Type text at current cursor position.
    interval: seconds between each keypress (0.05 = natural typing speed)
    Returns: {"success": True, "typed": text}
    """
    pyautogui.write(text, interval=interval)
    return {"success": True, "typed": text}


def press_key(key: str) -> dict:
    """
    Press a single key.
    key: any pyautogui key name — "enter", "tab", "escape", "backspace",
         "ctrl", "alt", "delete", "f1"-"f12", "up", "down", "left", "right"
    Returns: {"success": True, "key": key}
    """
    pyautogui.press(key)
    return {"success": True, "key": key}


def hotkey(*keys: str) -> dict:
    """
    Press a keyboard shortcut combination.
    Example: hotkey("ctrl", "c") for copy
    Example: hotkey("ctrl", "alt", "t") for terminal
    Common shortcuts:
      "ctrl", "c"       → copy
      "ctrl", "v"       → paste
      "ctrl", "z"       → undo
      "ctrl", "s"       → save
      "ctrl", "w"       → close tab
      "alt", "f4"       → close window
      "win", "d"        → show desktop
      "win", "l"        → lock screen (use system_controls.lock_screen() instead)
    """
    pyautogui.hotkey(*keys)
    return {"success": True, "keys": list(keys)}


def scroll(direction: str, amount: int = 3, x: int = None, y: int = None) -> dict:
    """
    Scroll up or down.
    direction: "up" or "down"
    amount: number of scroll clicks (3 = one screen roughly)
    x, y: coordinates to scroll at (None = current mouse position)
    """
    clicks = amount if direction == "up" else -amount
    if x is not None and y is not None:
        pyautogui.scroll(clicks, x=x, y=y)
    else:
        pyautogui.scroll(clicks)
    return {"success": True, "direction": direction, "amount": amount}


def get_screen_size() -> dict:
    """Returns current screen resolution."""
    width, height = pyautogui.size()
    return {"width": width, "height": height}


def get_mouse_position() -> dict:
    """Returns current mouse position."""
    x, y = pyautogui.position()
    return {"x": x, "y": y}
