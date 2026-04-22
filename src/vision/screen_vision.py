import re
import base64
import io

from src.utils.config import Config


VISION_WIDTH = 1280
VISION_HEIGHT = 720


def _resolve_vision_provider() -> str:
    provider = Config.VISION_PROVIDER
    if provider not in {"auto", "nvidia", "ollama"}:
        raise RuntimeError(
            "Unsupported VISION_PROVIDER. Use 'auto', 'nvidia', or 'ollama'."
        )
    if provider == "auto":
        return "nvidia" if Config.NVIDIA_API_KEY else "ollama"
    if provider == "nvidia" and not Config.NVIDIA_API_KEY:
        raise RuntimeError(
            "NVIDIA vision provider selected but NVIDIA_API_KEY is not configured."
        )
    return provider


def _normalize_model_text(response: object) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _chat_with_ollama_vision(messages: list[dict], options: dict | None = None) -> str:
    import ollama

    client = ollama.Client(host=Config.VISION_MODEL_HOST)
    response = client.chat(
        model=Config.VISION_MODEL,
        messages=messages,
        options=options or {"num_gpu": Config.VISION_NUM_GPU},
    )
    return response["message"]["content"]


def _to_nvidia_human_message(message: dict):
    from langchain_core.messages import HumanMessage

    content = []
    text = message.get("content", "")
    if text:
        content.append({"type": "text", "text": text})

    for image_b64 in message.get("images", []) or []:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_b64}"},
            }
        )

    return HumanMessage(content=content)


def _chat_with_nvidia_vision(messages: list[dict]) -> str:
    if not Config.NVIDIA_API_KEY:
        raise RuntimeError(
            "NVIDIA vision provider selected but NVIDIA_API_KEY is not configured."
        )

    from langchain_nvidia_ai_endpoints import ChatNVIDIA

    client = ChatNVIDIA(
        model=Config.VISION_MODEL,
        api_key=Config.NVIDIA_API_KEY,
        temperature=Config.VISION_TEMPERATURE,
        top_p=Config.VISION_TOP_P,
        max_completion_tokens=Config.VISION_MAX_COMPLETION_TOKENS,
    )
    response = client.invoke([_to_nvidia_human_message(message) for message in messages])
    return _normalize_model_text(response)


def _chat_with_vision_model(messages: list[dict], options: dict | None = None) -> str:
    provider = _resolve_vision_provider()
    if provider == "nvidia":
        return _chat_with_nvidia_vision(messages)
    return _chat_with_ollama_vision(messages, options)


def _screenshot_to_base64(resize: bool = True) -> tuple[str, int, int]:
    """
    Capture the current screen and return it as a base64-encoded PNG string.

    Args:
        resize: If True, downscale to VISION_WIDTH × VISION_HEIGHT before
                encoding.  This fixes the Ollama coordinate offset bug and
                also reduces the payload sent to the model.

    Returns:
        (base64_string, width_used, height_used)
        width/height are the dimensions of the image that was actually encoded
        (not the original screen resolution) — needed for coordinate scaling.
    """
    import pyautogui
    from PIL import Image

    screenshot = pyautogui.screenshot()

    if resize:
        # Resize to fixed known size so coordinate math is deterministic
        # Pillow >= 9.1 uses Image.Resampling.LANCZOS (the plan requires >= 10.0.0)
        screenshot = screenshot.resize((VISION_WIDTH, VISION_HEIGHT), Image.Resampling.LANCZOS)
        w, h = VISION_WIDTH, VISION_HEIGHT
    else:
        # Use original screen resolution — accurate but may trigger Ollama bug
        w, h = screenshot.size

    buffer = io.BytesIO() # save the image to an in-memory buffer instead of disk
    screenshot.save(buffer, format="PNG") 
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8") # encode the image bytes to base64 string
    return b64, w, h



def _parse_bbox(text: str) -> list | None:
    """
    Extract a [x1, y1, x2, y2] bounding box from the model's response text.

    Vision-capable models can return coordinates in several formats depending on how
    they were prompted.
    was prompted.  We try each format in order of reliability:

      1. JSON: {"bbox_2d": [x1, y1, x2, y2]}   ← most reliable, we ask for this
      2. Plain list: [x1, y1, x2, y2]            ← fallback if model drops key
      3. <box> tag: <box>(x1,y1),(x2,y2)</box>   ← older Qwen format

    Returns:
        List of 4 floats in 0-1000 range, or None if no bbox found.
    """
    # ── Format 1: JSON {"bbox_2d": [...]} ──
    json_match = re.search(r'"bbox_2d"\s*:\s*\[([^\]]+)\]', text)
    if json_match:
        try:
            coords = [float(x.strip()) for x in json_match.group(1).split(",")]
            if len(coords) == 4:
                return coords
        except ValueError:
            pass  # malformed — fall through to next format

    # ── Format 2: bare list [x1, y1, x2, y2] ──
    list_match = re.search(
        r'\[(\d+\.?\d*)\s*,\s*(\d+\.?\d*)\s*,\s*(\d+\.?\d*)\s*,\s*(\d+\.?\d*)\]',
        text
    )
    if list_match:
        return [float(x) for x in list_match.groups()]

    # ── Format 3: <box>(x1,y1),(x2,y2)</box> ──
    box_match = re.search(
        r'<box>\s*\((\d+),(\d+)\)\s*,\s*\((\d+),(\d+)\)\s*</box>',
        text
    )
    if box_match:
        return [float(x) for x in box_match.groups()]

    return None  # couldn't find any bounding box


def _bbox_to_screen_coords(bbox: list, img_w: int, img_h: int) -> tuple[int, int]:
    """
    Convert a normalized 0-1000 bounding box to actual screen pixel coordinates.

    Two-stage conversion:
      Stage 1 — 0-1000 range → image pixel coords   (normalised → absolute within image)
      Stage 2 — image pixels → screen pixels         (scale back if image was resized)

    This two-stage approach is necessary because we pre-resize the screenshot
    before sending it, so "image pixel" ≠ "screen pixel".

    Args:
        bbox:  [x1, y1, x2, y2] in 0-1000 normalised range from the model
        img_w: width of the image that was passed to the model (VISION_WIDTH)
        img_h: height of the image that was passed to the model (VISION_HEIGHT)

    Returns:
        (click_x, click_y) — centre of the bounding box in screen pixel coords
    """
    import pyautogui

    screen_w, screen_h = pyautogui.size() # get actual screen resolution for final scaling
    scale_x = screen_w / img_w
    scale_y = screen_h / img_h

    # Handle edge case: some model versions return raw pixel coords (> 1000)
    # instead of normalised coords.  Detect and convert directly.
    if max(bbox) > 1001:
        # Already in pixel coords relative to some resolution — just find centre
        click_x = int(((bbox[0] + bbox[2]) / 2) * scale_x)
        click_y = int(((bbox[1] + bbox[3]) / 2) * scale_y)
        return click_x, click_y

    # Stage 1: map 0-1000 to image pixel space
    img_x1 = bbox[0] / 1000 * img_w
    img_y1 = bbox[1] / 1000 * img_h
    img_x2 = bbox[2] / 1000 * img_w
    img_y2 = bbox[3] / 1000 * img_h

    # Stage 2: scale image pixels back to actual screen resolution
    # (necessary because we resized the screenshot before sending it)
    screen_x1 = img_x1 * scale_x
    screen_y1 = img_y1 * scale_y
    screen_x2 = img_x2 * scale_x
    screen_y2 = img_y2 * scale_y

    # Return centre of the bounding box
    click_x = int((screen_x1 + screen_x2) / 2)
    click_y = int((screen_y1 + screen_y2) / 2)

    return click_x, click_y


# ─── Public API ──────────────────────────────────────────────────────────────

def find_element(description: str) -> dict:
    """
    Locate a UI element on the current screen by natural-language description.

    Workflow:
      1. Take and resize screenshot
      2. Send to Config.VISION_MODEL with a tightly-formatted prompt asking for JSON bbox
      3. Parse the response for [x1, y1, x2, y2]
      4. Scale from 0-1000 normalised → actual screen pixels
      5. Return centre coordinates safe for pyautogui.click()

    The prompt explicitly requests ONLY JSON output.  This dramatically
    improves reliability compared to open-ended prompts.

    Args:
        description: Natural language description of the element to find,
                     e.g. "search bar", "close button", "send button in Gmail"

    Returns:
        On success: {"found": True, "x": int, "y": int, "raw_bbox": list}
        On failure: {"found": False, "error": str}
    """
    try:
        # Capture screen and get the image dimensions we actually used
        b64_image, img_w, img_h = _screenshot_to_base64(resize=True)

        # Highly explicit prompt improves reliability for vision model responses.
        # The "ONLY" and "No explanation" instructions suppress prose responses.
        prompt = (
            f"Look at this screenshot carefully. "
            f"Find the UI element described as: '{description}'. "
            f"You MUST respond with ONLY a JSON object in this exact format: "
            f'{{"bbox_2d": [x1, y1, x2, y2]}} '
            f"where x1, y1, x2, y2 are coordinates in the 0-1000 normalized range "
            f"(0=left/top, 1000=right/bottom of the screen). "
            f"No explanation. No other text. "
            f"If the element is not visible, respond with: "
            f'{{"bbox_2d": null}}'
        )

        # Call configured vision model and normalize provider-specific responses.
        response_text = _chat_with_vision_model(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64_image],
                }
            ],
            options={
                "num_gpu": Config.VISION_NUM_GPU,
            },
        )

        # If the model explicitly says null, the element isn't visible
        if '"bbox_2d": null' in response_text or (
            "null" in response_text.lower() and "bbox" in response_text.lower()
        ):
            return {"found": False, "error": f"'{description}' not found on screen"}

        # Try to parse a bounding box from the response
        bbox = _parse_bbox(response_text)
        if not bbox:
            return {
                "found": False,
                "error": (
                    f"Vision model responded but could not parse coordinates. "
                    f"Response: {response_text[:200]}"
                ),
            }

        # Map bbox → actual screen pixel centre point
        click_x, click_y = _bbox_to_screen_coords(bbox, img_w, img_h)

        # Clamp to valid screen bounds so pyautogui never gets an off-screen coord
        import pyautogui

        screen_w, screen_h = pyautogui.size()
        click_x = max(0, min(click_x, screen_w - 1))
        click_y = max(0, min(click_y, screen_h - 1))

        return {
            "found": True,
            "x": click_x,
            "y": click_y,
            "raw_bbox": bbox,
        }

    except Exception as e:
        return {"found": False, "error": f"Vision error: {str(e)}"}


def describe_screen() -> str:
    """
    Take a screenshot and return a detailed natural-language description of what
    is currently visible on screen.

    Uses the configured vision model's multimodal understanding to describe the
    active application,
    visible content, readable text, and overall screen state.

    Returns:
        Human-readable description of the screen, or an error string.
    """
    try:
        b64_image, _, _ = _screenshot_to_base64(resize=True)

        response_text = _chat_with_vision_model(
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Describe what is currently on this screen in detail. "
                        "Include: what application is open, what content is visible, "
                        "any text you can read, and the overall state of the screen."
                    ),
                    "images": [b64_image],
                }
            ],
            options={"num_gpu": Config.VISION_NUM_GPU},
        )

        return response_text

    except Exception as e:
        return f"Could not analyze screen: {str(e)}"


def read_screen_text(region_description: str | None = None) -> str:
    """
    Extract visible text from the screen using the vision model (OCR-like).

    Optionally focus on a specific region of the screen described in natural
    language (e.g. "error message", "title bar", "notification popup").

    Args:
        region_description: Optional focus area. If None, reads all screen text.

    Returns:
        Extracted text content, or an error string.
    """
    try:
        b64_image, _, _ = _screenshot_to_base64(resize=True)

        if region_description:
            # Focused read — useful for "read the error message", "what does the dialog say?"
            prompt = (
                f"Read and extract all text from the '{region_description}' area "
                f"of this screenshot. Return only the text, nothing else."
            )
        else:
            # Full-screen read — useful for "read everything on screen"
            prompt = (
                "Read and extract all visible text from this screenshot. "
                "Return only the text content, organized by location on screen."
            )

        response_text = _chat_with_vision_model(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64_image],
                }
            ],
            options={"num_gpu": Config.VISION_NUM_GPU},
        )

        return response_text

    except Exception as e:
        return f"Could not read screen text: {str(e)}"
