# Phase 5 — Screen Vision (Vision-Guided Mouse Automation)
> Platform: Windows 11, RTX 4060 8GB VRAM
> Model: configurable via `VISION_MODEL` (default: qwen3.5:9b)
> Goal: Find any UI element on screen by description and click it — no hardcoded coordinates
> Read entire file before writing any code

---

## What You're Building

```
"click the search bar in Chrome"
    ↓
take_screenshot()
    ↓
VISION_MODEL sees screenshot + "where is the Chrome search bar?"
    ↓
returns bbox_2d: [452, 18, 1460, 52]  ← normalized 0-1000 range
    ↓
scale to real pixels: x=956, y=35  ← center of bounding box
    ↓
mouse_click(956, 35)
    ↓
done
```

More examples of what becomes possible:
```
"click the X button on notepad"       → closes without knowing coordinates
"click send in Gmail"                 → finds send button and clicks
"click the minimize button"           → minimizes current window
"double click the desktop icon for Chrome" → finds and double-clicks icon
"right click the taskbar"             → context menu without coordinates
"tell me what's on my screen"         → full screen description
"read the error message on screen"    → extracts text from screenshot
"is Spotify playing?"                 → reads screen state to answer
```

---

## Architecture — Two Models Working Together

Qwen3.5:9b (text LLM, already running) — decides WHAT to do, calls tools
VISION_MODEL (vision-capable model via Config) — finds WHERE things are on screen

These are two model roles that may be served by one or more Ollama models.
Qwen3.5 calls a tool → tool internally calls VISION_MODEL → returns coordinates → Qwen3.5 acts on them.
The text LLM never sees the screenshot directly. Only the vision module does.

Runtime recommendation:
- Keep `VISION_NUM_GPU=0` by default (CPU-only vision, safest for VRAM contention).
- If you want faster vision and have headroom, increase `VISION_NUM_GPU`.
- Vision calls are typically infrequent, so CPU-only is often acceptable.

---

## CRITICAL: Coordinate Scaling

This is the most important technical detail in this entire phase.
Get this wrong and every click lands in the wrong place.

The vision model returns bounding box coordinates in NORMALIZED 0-1000 range.
These are NOT pixel coordinates. They must be converted.

Official formula from Qwen cookbook:
```python
# Model returns: bbox_2d = [x1, y1, x2, y2] in 0-1000 range
# You need: actual pixel coordinates on your screen

screen_width, screen_height = pyautogui.size()  # e.g. 1920, 1080

# Convert bbox corners to pixels
pixel_x1 = int(bbox[0] / 1000 * screen_width)
pixel_y1 = int(bbox[1] / 1000 * screen_height)
pixel_x2 = int(bbox[2] / 1000 * screen_width)
pixel_y2 = int(bbox[3] / 1000 * screen_height)

# Click the CENTER of the bounding box
click_x = (pixel_x1 + pixel_x2) // 2
click_y = (pixel_y1 + pixel_y2) // 2
```

Known issue with some Ollama vision setups:
There is a reported Y-axis offset bug where the Y coordinate is slightly off
when Ollama internally resizes the image before passing to the model.
The fix is to resize the screenshot to a known size before sending it,
then scale coordinates relative to that known size instead of original screen size.
Implementation is shown in Step 2 below.

---

## New Library

```bash
uv pip install ollama  # if not already installed — for direct Ollama API calls
```

No other new dependencies needed.
All mouse/keyboard actions already exist from Phase 4.

---

## Folder Structure — New Files Only

```
src/
├── vision/
│   ├── __init__.py
│   └── screen_vision.py      # all vision logic lives here
├── tools/
│   └── wrapped_tools.py      # add new @tool wrappers at bottom (DO NOT touch existing tools)
```

---

## Step 1 — Install and Verify Vision Model

Run this in terminal before writing any code:
```bash
ollama pull qwen3.5:9b
```

Verify it works:
```bash
ollama run qwen3.5:9b "describe this image" --image path/to/any/test.png
```

If that model is too slow on CPU (>10 seconds), pull a smaller vision-capable model instead.
```bash
ollama pull qwen3.5:4b
```

Add to config.py:
```python
VISION_MODEL = os.getenv("VISION_MODEL", "qwen3.5:9b")
VISION_MODEL_HOST = os.getenv("VISION_MODEL_HOST", "http://localhost:11434")
VISION_NUM_GPU = int(os.getenv("VISION_NUM_GPU", "0"))
```

---

## Step 2 — Create `src/vision/screen_vision.py`

```python
# src/vision/screen_vision.py
# Vision module — uses configurable VISION_MODEL to find UI elements on screen
# Called by tools, never directly by the agent

import re
import json
import base64
import pyautogui
from PIL import Image
import io
import ollama
from src.utils.config import Config

# Resize screenshot to this before sending to vision model
# Fixes the Ollama Y-axis offset bug by using consistent known dimensions
VISION_WIDTH = 1280
VISION_HEIGHT = 720


def _screenshot_to_base64(resize: bool = True) -> tuple[str, int, int]:
    """
    Takes a screenshot and returns it as base64.
    Also returns the dimensions used (for coordinate scaling).

    Returns: (base64_string, width_used, height_used)
    """
    screenshot = pyautogui.screenshot()
    orig_w, orig_h = screenshot.size

    if resize:
        # Resize to fixed known dimensions to fix Ollama coordinate offset bug
        screenshot = screenshot.resize((VISION_WIDTH, VISION_HEIGHT), Image.LANCZOS)
        w, h = VISION_WIDTH, VISION_HEIGHT
    else:
        w, h = orig_w, orig_h

    buffer = io.BytesIO()
    screenshot.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return b64, w, h


def _parse_bbox(text: str) -> list | None:
    """
    Parses bounding box from model response.
    Handles multiple formats the model might return:
      {"bbox_2d": [x1, y1, x2, y2]}
      [x1, y1, x2, y2]
      <box>(x1,y1),(x2,y2)</box>
    Returns: [x1, y1, x2, y2] in 0-1000 range, or None if not found
    """
    # Try JSON bbox_2d format
    json_match = re.search(r'"bbox_2d"\s*:\s*\[([^\]]+)\]', text)
    if json_match:
        try:
            coords = [float(x.strip()) for x in json_match.group(1).split(",")]
            if len(coords) == 4:
                return coords
        except ValueError:
            pass

    # Try plain list format [x1, y1, x2, y2]
    list_match = re.search(r'\[(\d+\.?\d*)\s*,\s*(\d+\.?\d*)\s*,\s*(\d+\.?\d*)\s*,\s*(\d+\.?\d*)\]', text)
    if list_match:
        return [float(x) for x in list_match.groups()]

    # Try <box> format (older Qwen format)
    box_match = re.search(r'<box>\s*\((\d+),(\d+)\)\s*,\s*\((\d+),(\d+)\)\s*</box>', text)
    if box_match:
        return [float(x) for x in box_match.groups()]

    return None


def _bbox_to_screen_coords(bbox: list, img_w: int, img_h: int) -> tuple[int, int]:
    """
    Converts normalized 0-1000 bbox to actual screen pixel coordinates.
    Returns: (click_x, click_y) — center of the bounding box on actual screen

    img_w, img_h: dimensions of the image that was sent to the model
    (may differ from actual screen resolution if image was resized)
    """
    screen_w, screen_h = pyautogui.size()

    # Step 1: convert 0-1000 to image pixel coords
    img_x1 = bbox[0] / 1000 * img_w
    img_y1 = bbox[1] / 1000 * img_h
    img_x2 = bbox[2] / 1000 * img_w
    img_y2 = bbox[3] / 1000 * img_h

    # Step 2: if image was resized, scale back to screen resolution
    scale_x = screen_w / img_w
    scale_y = screen_h / img_h

    screen_x1 = img_x1 * scale_x
    screen_y1 = img_y1 * scale_y
    screen_x2 = img_x2 * scale_x
    screen_y2 = img_y2 * scale_y

    # Step 3: return center of bounding box
    click_x = int((screen_x1 + screen_x2) / 2)
    click_y = int((screen_y1 + screen_y2) / 2)

    return click_x, click_y


def find_element(description: str) -> dict:
    """
    Finds a UI element on screen by natural language description.
    Takes a screenshot, asks VISION_MODEL where the element is.

    description: what to look for, e.g. "search bar", "close button", "send button"

    Returns:
        {"found": True, "x": int, "y": int, "raw_bbox": list}
        {"found": False, "error": str}
    """
    try:
        # Take and encode screenshot
        b64_image, img_w, img_h = _screenshot_to_base64(resize=True)

        # Build prompt — explicit JSON format request dramatically improves accuracy
        prompt = (
            f"Look at this screenshot. Find the '{description}'. "
            f"Return ONLY a JSON object with the bounding box in this exact format: "
            f'{"{"}"bbox_2d": [x1, y1, x2, y2]{"}"} '
            f"where coordinates are in 0-1000 normalized range. "
            f"If you cannot find it, return: "
            f'{"{"}"bbox_2d": null{"}"}'
        )

        # Call VISION_MODEL via Ollama
        response = ollama.chat(
            model=Config.VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64_image],
                }
            ],
        )

        response_text = response["message"]["content"]

        # Check for null response (element not found)
        if '"bbox_2d": null' in response_text or "null" in response_text.lower():
            return {"found": False, "error": f"Could not find '{description}' on screen"}

        # Parse bounding box
        bbox = _parse_bbox(response_text)
        if not bbox:
            return {
                "found": False,
                "error": f"Vision model responded but could not parse coordinates. Response: {response_text[:200]}"
            }

        # Convert to screen coordinates
        click_x, click_y = _bbox_to_screen_coords(bbox, img_w, img_h)

        # Safety check — ensure coordinates are within screen bounds
        screen_w, screen_h = pyautogui.size()
        click_x = max(0, min(click_x, screen_w - 1))
        click_y = max(0, min(click_y, screen_h - 1))

        return {
            "found": True,
            "x": click_x,
            "y": click_y,
            "raw_bbox": bbox
        }

    except Exception as e:
        return {"found": False, "error": f"Vision error: {str(e)}"}


def describe_screen() -> str:
    """
    Takes a screenshot and asks VISION_MODEL to describe what's on screen.
    Returns: natural language description of current screen state
    """
    try:
        b64_image, _, _ = _screenshot_to_base64(resize=True)

        response = ollama.chat(
            model=Config.VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Describe what's currently on this screen in detail. "
                        "Include: what application is open, what content is visible, "
                        "any text you can read, and the overall state of the screen."
                    ),
                    "images": [b64_image],
                }
            ],
        )

        return response["message"]["content"]

    except Exception as e:
        return f"Could not analyze screen: {str(e)}"


def read_screen_text(region_description: str = None) -> str:
    """
    Extracts text visible on screen using vision model (OCR-like).
    region_description: optional — focus on a specific area, e.g. "error message", "title bar"
    Returns: text found on screen
    """
    try:
        b64_image, _, _ = _screenshot_to_base64(resize=True)

        if region_description:
            prompt = f"Read and extract all text from the '{region_description}' area of this screenshot. Return only the text, nothing else."
        else:
            prompt = "Read and extract all visible text from this screenshot. Return only the text content, organized by location."

        response = ollama.chat(
            model=Config.VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64_image],
                }
            ],
        )

        return response["message"]["content"]

    except Exception as e:
        return f"Could not read screen text: {str(e)}"
```

---

## Step 3 — Add @tool Wrappers to `wrapped_tools.py`

Add ONLY these tools at the bottom of wrapped_tools.py.
Do NOT modify any existing tools.

```python
# ── Screen Vision Tools (Phase 5) ──────────────────────────────────
# Add at the very bottom of wrapped_tools.py

from src.vision.screen_vision import find_element, describe_screen, read_screen_text

@tool
def find_and_click(description: str, button: str = "left") -> str:
    """
    Find a UI element on screen by description and click it.
    Use this INSTEAD of click_at() when you don't know the coordinates.
    Use this when user says 'click X', 'press X button', 'tap X'.

    description: what to find, e.g. "search bar", "close button", "submit button",
                 "minimize button", "the X button", "send button in Gmail"
    button: "left" (default), "right", or "middle"

    Automatically takes screenshot, locates element, clicks center of it.
    Returns confirmation with coordinates used, or error if not found.

    IMPORTANT: After calling this tool, wait for result before taking further action.
    Do NOT assume the click succeeded — check the return value.
    """
    import pyautogui
    result = find_element(description)

    if not result["found"]:
        return f"Could not find '{description}' on screen: {result.get('error', 'unknown error')}"

    x, y = result["x"], result["y"]
    pyautogui.click(x, y, button=button)
    return f"Found '{description}' and clicked at ({x}, {y}), master."


@tool
def find_and_double_click(description: str) -> str:
    """
    Find a UI element on screen by description and double-click it.
    Use when user says 'double click X', 'open X by double clicking'.

    description: what to find, e.g. "Chrome icon on desktop", "folder"
    Returns confirmation or error.
    """
    import pyautogui
    result = find_element(description)

    if not result["found"]:
        return f"Could not find '{description}' on screen: {result.get('error', 'unknown error')}"

    x, y = result["x"], result["y"]
    pyautogui.doubleClick(x, y)
    return f"Found '{description}' and double-clicked at ({x}, {y}), master."


@tool
def find_and_right_click(description: str) -> str:
    """
    Find a UI element on screen and right-click it to open context menu.
    Use when user says 'right click X', 'open context menu for X'.

    description: what to right-click
    Returns confirmation or error.
    """
    import pyautogui
    result = find_element(description)

    if not result["found"]:
        return f"Could not find '{description}' on screen: {result.get('error', 'unknown error')}"

    x, y = result["x"], result["y"]
    pyautogui.rightClick(x, y)
    return f"Found '{description}' and right-clicked at ({x}, {y}), master."


@tool
def find_and_type(description: str, text: str) -> str:
    """
    Find a text input field on screen, click it, then type text into it.
    Use when user says 'type X in the search bar', 'enter X in the input field'.
    Combines find_and_click + type_text in one step.

    description: the input field to find, e.g. "search bar", "address bar",
                 "notepad text area", "username field"
    text: what to type
    Returns confirmation or error.
    """
    import pyautogui
    import time

    # Find and click the field
    result = find_element(description)
    if not result["found"]:
        return f"Could not find '{description}' on screen: {result.get('error', 'unknown error')}"

    x, y = result["x"], result["y"]
    pyautogui.click(x, y)
    time.sleep(0.3)  # wait for focus

    # Type the text
    pyautogui.write(text, interval=0.02)
    return f"Clicked '{description}' at ({x}, {y}) and typed: {text}"


@tool
def what_is_on_screen() -> str:
    """
    Describes what is currently visible on the screen.
    Use when user asks 'what's on my screen', 'what do you see',
    'what app is open', 'describe my screen', 'what's happening on screen'.
    Takes a screenshot and uses vision AI to describe it.
    Returns detailed description of screen contents.
    """
    return describe_screen()


@tool
def read_text_on_screen(area: str = None) -> str:
    """
    Reads and extracts text currently visible on screen.
    Use when user asks 'read the error message', 'what does it say',
    'read the text on screen', 'what's written there'.

    area: optional — specific area to focus on, e.g. "error dialog",
          "title bar", "notification", "selected text"
          If None, reads all text on screen.
    Returns extracted text from screen.
    """
    return read_screen_text(area)
```

---

## Step 4 — Update `ALL_TOOLS` in `wrapped_tools.py`

Add new vision tools to ALL_TOOLS list:

```python
ALL_TOOLS = [
    # ... all existing tools unchanged ...

    # Phase 5 — Screen Vision
    find_and_click,
    find_and_double_click,
    find_and_right_click,
    find_and_type,
    what_is_on_screen,
    read_text_on_screen,
]
```

---

## Step 5 — Update System Prompt in `agent.py`

Add this paragraph to the existing system prompt.
Do NOT replace the existing system prompt — append to it.

```
You have vision capabilities. When the user asks you to click, press, or interact
with something on screen without giving coordinates, always use find_and_click()
or the appropriate vision tool instead of asking for coordinates.
For typing into a specific field, use find_and_type() which handles clicking
the field first. Only use click_at() when the user explicitly provides coordinates.
Vision tools take 2-4 seconds — inform the user if they seem to be waiting.
```

---

## Step 6 — Update `tool_registry.py` (if it exists in your codebase)

If tool_registry.py exists, add vision tools to the system category:

```python
"vision": [
    "find_and_click",
    "find_and_double_click",
    "find_and_right_click",
    "find_and_type",
    "what_is_on_screen",
    "read_text_on_screen",
],
```

If tool_registry.py does not exist (using embedding retriever), skip this step entirely.
The embedding retriever will pick up vision tools automatically from their docstrings.

---

## Requirements.txt Additions

```
ollama>=0.3.0      # if not already present
Pillow>=10.0.0     # for image resizing — likely already installed
```

---

## Testing Protocol — Run In This Order

### Test 0 — Vision model sanity check (before running assistant)
```python
# Run this standalone script to verify VISION_MODEL works:
# save as test_vision.py and run: uv run python test_vision.py

from src.vision.screen_vision import find_element, describe_screen

# Open notepad manually first
result = find_element("notepad title bar")
print(result)
# Expected: {"found": True, "x": ~960, "y": ~15, "raw_bbox": [...]}

desc = describe_screen()
print(desc[:200])
# Expected: a description mentioning Notepad
```

### Test 1 — Basic element finding
```
Open Notepad manually
Say: "click the title bar of notepad"
Pass: Mouse moves and clicks the notepad title bar
```

### Test 2 — Click interactive element
```
Open Chrome
Say: "click the address bar in Chrome"
Pass: Chrome address bar gets focused (cursor appears in it)
```

### Test 3 — Find and type combined
```
Open Chrome
Say: "type google.com in the address bar"
Pass: Vision finds address bar, clicks it, types google.com
```

### Test 4 — Screen description
```
Open any app
Say: "what's on my screen right now?"
Pass: Accurate description of what's visible returned
```

### Test 5 — Read text from screen
```
Open any webpage with visible text
Say: "read me the title of the page on screen"
Pass: Correct title text returned
```

### Test 6 — Multi-step vision automation
```
Say: "open Chrome and search for weather in Delhi"
Pass:
  1. Chrome opens (Phase 4 tool)
  2. Vision finds address bar
  3. Types search query
  4. Presses Enter
```

### Test 7 — Telegram voice + vision
```
Send voice message: "click the search bar in Chrome"
Pass: Works identically to text command
```

### Test 8 — Error handling
```
Say: "click the purple elephant button"
Pass: Returns clean "could not find" message, no crash, no wrong click
```

---

## Common Issues and Fixes

**VISION_MODEL returns coordinates outside 0-1000 range**
Some responses return actual pixel coordinates instead of normalized.
Fix: add a detection check in _bbox_to_screen_coords():
```python
# If values are clearly > 1000, treat as actual pixel coords not normalized
if max(bbox) > 1001:
    # Already pixel coords — just find center
    click_x = int((bbox[0] + bbox[2]) / 2)
    click_y = int((bbox[1] + bbox[3]) / 2)
    return click_x, click_y
```

**Y-axis is consistently offset (clicks too high or too low)**
This is the known Ollama resize bug.
Fix: adjust VISION_HEIGHT in screen_vision.py — try 800 instead of 720.
Or: send screenshot at original resolution (resize=False) and use screen dimensions directly.
Test both and use whichever gives accurate Y clicks.

**Vision calls take too long (>10 seconds)**
You're running 7b on CPU while 9b is on GPU.
Options:
  1. Switch to a smaller vision-capable model (faster, slightly less accurate)
  2. When vision is needed, ollama can automatically swap models if VRAM allows
  3. Offload qwen3.5 to CPU while vision runs on GPU (swap models manually)

**find_element returns "found: False" for obvious elements**
The description needs to match what the model can see.
Instead of "the X" try "the close button" or "the red X button in top right corner".
More descriptive = more accurate finding.
Prompt the model with location hints when possible.

**Model returns text description instead of JSON bbox**
The prompt format matters enormously for multimodal models.
If the model keeps describing instead of returning JSON, update the prompt to:
"You MUST respond with ONLY the JSON object. No explanation. No other text."
Add this line to the prompt in find_element().

**VRAM OOM error**
Both models trying to use GPU simultaneously.
Fix: set OLLAMA_NUM_GPU=0 for the vision model specifically via environment variable,
or run vision model in a separate Ollama instance on a different port.
Simplest fix: in Config, set VISION_MODEL_HOST to a separate Ollama instance
with GPU disabled: OLLAMA_CUDA_VISIBLE_DEVICES="" ollama serve --port 11435

---
