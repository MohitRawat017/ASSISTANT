import sys
import types

import pytest


@pytest.mark.safe_smoke
def test_screen_vision_parses_supported_bbox_formats():
    from src.vision.screen_vision import _parse_bbox

    assert _parse_bbox('{"bbox_2d": [10, 20, 30, 40]}') == [10, 20, 30, 40]
    assert _parse_bbox("Some text [1, 2, 3, 4]") == [1, 2, 3, 4]
    assert _parse_bbox("<box>(5,6),(7,8)</box>") == [5, 6, 7, 8]
    assert _parse_bbox('{"bbox_2d": null}') is None


@pytest.mark.safe_smoke
def test_screen_vision_scales_normalized_coordinates(monkeypatch):
    fake_pyautogui = types.SimpleNamespace(size=lambda: (1920, 1080))
    monkeypatch.setitem(sys.modules, "pyautogui", fake_pyautogui)

    from src.vision.screen_vision import _bbox_to_screen_coords

    assert _bbox_to_screen_coords([500, 500, 700, 700], 1280, 720) == (1152, 648)


@pytest.mark.safe_smoke
def test_screen_vision_scales_resized_pixel_coordinates(monkeypatch):
    fake_pyautogui = types.SimpleNamespace(size=lambda: (1920, 1080))
    monkeypatch.setitem(sys.modules, "pyautogui", fake_pyautogui)

    from src.vision.screen_vision import _bbox_to_screen_coords

    assert _bbox_to_screen_coords([640, 360, 1280, 720], 1280, 720) == (1440, 810)


@pytest.mark.safe_smoke
def test_screen_vision_uses_configured_ollama_host(monkeypatch):
    calls = {}

    class FakeClient:
        def __init__(self, host):
            calls["host"] = host

        def chat(self, **kwargs):
            calls["kwargs"] = kwargs
            return {"message": {"content": "ok"}}

    fake_ollama = types.SimpleNamespace(Client=FakeClient)
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)

    from src.utils.config import Config
    from src.vision.screen_vision import _chat_with_vision_model

    monkeypatch.setattr(Config, "VISION_PROVIDER", "ollama")
    monkeypatch.setattr(Config, "VISION_MODEL_HOST", "http://example.test:11434")
    monkeypatch.setattr(Config, "VISION_MODEL", "vision-test-model")

    result = _chat_with_vision_model([{"role": "user", "content": "describe"}])

    assert result == "ok"
    assert calls["host"] == "http://example.test:11434"
    assert calls["kwargs"]["model"] == "vision-test-model"


@pytest.mark.safe_smoke
def test_screen_vision_auto_falls_back_to_ollama_without_nvidia_key(monkeypatch):
    calls = {}

    class FakeClient:
        def __init__(self, host):
            calls["host"] = host

        def chat(self, **kwargs):
            calls["kwargs"] = kwargs
            return {"message": {"content": "ollama ok"}}

    monkeypatch.setitem(sys.modules, "ollama", types.SimpleNamespace(Client=FakeClient))

    from src.utils.config import Config
    from src.vision.screen_vision import _chat_with_vision_model

    monkeypatch.setattr(Config, "VISION_PROVIDER", "auto")
    monkeypatch.setattr(Config, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(Config, "VISION_MODEL_HOST", "http://local.test:11434")

    assert _chat_with_vision_model([{"role": "user", "content": "describe"}]) == "ollama ok"
    assert calls["host"] == "http://local.test:11434"


@pytest.mark.safe_smoke
def test_screen_vision_uses_nvidia_provider(monkeypatch):
    calls = {}

    class FakeHumanMessage:
        def __init__(self, content):
            self.content = content

    class FakeChatNVIDIA:
        def __init__(self, **kwargs):
            calls["client_kwargs"] = kwargs

        def invoke(self, messages):
            calls["messages"] = messages
            return types.SimpleNamespace(content="nvidia ok")

    fake_core = types.ModuleType("langchain_core")
    fake_messages = types.ModuleType("langchain_core.messages")
    fake_messages.HumanMessage = FakeHumanMessage
    fake_nvidia = types.ModuleType("langchain_nvidia_ai_endpoints")
    fake_nvidia.ChatNVIDIA = FakeChatNVIDIA
    monkeypatch.setitem(sys.modules, "langchain_core", fake_core)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", fake_messages)
    monkeypatch.setitem(sys.modules, "langchain_nvidia_ai_endpoints", fake_nvidia)

    from src.utils.config import Config
    from src.vision.screen_vision import _chat_with_vision_model

    monkeypatch.setattr(Config, "VISION_PROVIDER", "nvidia")
    monkeypatch.setattr(Config, "NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setattr(Config, "VISION_MODEL", "qwen/qwen3.5-122b-a10b")
    monkeypatch.setattr(Config, "VISION_TEMPERATURE", 0.6)
    monkeypatch.setattr(Config, "VISION_TOP_P", 0.95)
    monkeypatch.setattr(Config, "VISION_MAX_COMPLETION_TOKENS", 16384)

    result = _chat_with_vision_model(
        [{"role": "user", "content": "describe", "images": ["abc123"]}]
    )

    assert result == "nvidia ok"
    assert calls["client_kwargs"] == {
        "model": "qwen/qwen3.5-122b-a10b",
        "api_key": "nvapi-test",
        "temperature": 0.6,
        "top_p": 0.95,
        "max_completion_tokens": 16384,
    }
    assert calls["messages"][0].content == [
        {"type": "text", "text": "describe"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,abc123"},
        },
    ]


@pytest.mark.safe_smoke
def test_screen_vision_forced_nvidia_requires_key(monkeypatch):
    from src.utils.config import Config
    from src.vision.screen_vision import _chat_with_vision_model

    monkeypatch.setattr(Config, "VISION_PROVIDER", "nvidia")
    monkeypatch.setattr(Config, "NVIDIA_API_KEY", "")

    with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
        _chat_with_vision_model([{"role": "user", "content": "describe"}])


@pytest.mark.safe_smoke
def test_windows_scheduler_uses_collision_resistant_names():
    from src.scheduler_windows import WindowsScheduler

    alarm_id = "12345678-1234-5678-9abc-def012345678"

    assert WindowsScheduler.task_name_for_alarm(alarm_id) == (
        "TsuziReminder_12345678-1234-5678-9abc-def012345678"
    )
    assert WindowsScheduler.bat_filename_for_alarm(alarm_id) == (
        "reminder_12345678-1234-5678-9abc-def012345678.bat"
    )
