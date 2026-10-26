import os
import math
from dotenv import load_dotenv

# Load .env file from project root
# This must be called before any os.getenv() calls
load_dotenv()

try:
    import torch
except ImportError:
    torch = None


class Config:
    
    DEVICE = "cuda" if torch and torch.cuda.is_available() else "cpu"
    
    # config.py -> utils -> src -> [project_root]
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    MODELS_DIR = os.path.join(BASE_DIR, "models")
    
    ASR_MODEL_PATH = os.path.join(MODELS_DIR, "asr/faster-whisper-large-v3-turbo-ct2")
    
    TTS_CONFIG_PATH = os.path.join(MODELS_DIR, "tts/Kokoro-82M/config.json")
    TTS_MODEL_PATH = os.path.join(MODELS_DIR, "tts/Kokoro-82M/kokoro-v1_0.pth")
    
    # Qwen TTS: Alternative TTS model (currently not used, but available)
    QWEN_TTS_MODEL_PATH = os.path.join(MODELS_DIR, "tts/Qwen3-TTS-12Hz-0.6B-Base")
    QWEN_TTS_REF_AUDIO = os.path.join(BASE_DIR, "src/audio_output/audio_ref2.wav")
    QWEN_TTS_REF_TEXT = "that sound's fun wait are you asking me out to go on a date Alright i'll go on a date with you"

    SAMPLE_RATE_REC = 16000     # Recording sample rate (Hz)
    SAMPLE_RATE_PLAY = 24000    # Playback sample rate (Hz)
    RECORD_DURATION = 6.5       # Default recording duration (seconds) - used for fixed-length recording
    
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

    # Main assistant runtime — local Ollama (local-first contract)
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # Reliability budgets. An unset provider timeout preserves client-library
    # defaults; setting one bounds the provider call without replaying the
    # LangGraph invocation. Retry counts apply only to safe reads.
    _ollama_timeout_raw = os.getenv("OLLAMA_TIMEOUT_SECONDS", os.getenv("OLLAMA_TIMEOUT", "300"))
    try:
        parsed_ollama_timeout = float(_ollama_timeout_raw) if _ollama_timeout_raw else None
        OLLAMA_TIMEOUT = (
            parsed_ollama_timeout
            if parsed_ollama_timeout is not None
            and math.isfinite(parsed_ollama_timeout)
            and parsed_ollama_timeout > 0
            else None
        )
    except ValueError:
        OLLAMA_TIMEOUT = None
    _ollama_retries_raw = os.getenv("OLLAMA_MAX_RETRIES", "0")
    OLLAMA_MAX_RETRIES = min(3, int(_ollama_retries_raw)) if _ollama_retries_raw.isdigit() else 0

    MEMORY_DIR = os.path.join(BASE_DIR, "data", "memory")

    GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
    REMINDER_EMAIL = os.getenv("REMINDER_EMAIL", "")  # Defaults to GMAIL_ADDRESS if empty

    # Debug console trace is OFF by default (ADR 0001): JSONL traces stay on
    # (redacted + bounded) for explainability; set DEBUG_MODE=true to opt in
    # to the verbose stdout trace.
    _debug_raw = os.getenv("DEBUG_MODE", "false").strip().lower()
    DEBUG_MODE = _debug_raw in ("1", "true", "yes", "on")
    DEBUG_LOG_DIR = os.path.join(BASE_DIR, "logs", "agent_traces")

    # Days to keep logs/agent_traces/agent_trace_*.jsonl files; older trace
    # files are pruned after each write (bounded retention, ADR 0001).
    _trace_retention_raw = os.getenv("TRACE_RETENTION_DAYS", "14")
    TRACE_RETENTION_DAYS = max(
        0, int(_trace_retention_raw)
    ) if _trace_retention_raw.isdigit() else 14

    # Keep the active day's trace bounded as well as age-limited. Rotated
    # files use the same date prefix and are included in age pruning.
    _trace_max_bytes_raw = os.getenv("TRACE_MAX_BYTES", "5000000")
    TRACE_MAX_BYTES = max(
        1, int(_trace_max_bytes_raw)
    ) if _trace_max_bytes_raw.isdigit() else 5_000_000
    _trace_backup_raw = os.getenv("TRACE_BACKUP_COUNT", "3")
    TRACE_BACKUP_COUNT = max(
        0, int(_trace_backup_raw)
    ) if _trace_backup_raw.isdigit() else 3

    # Maximum number of *.png files kept in data/screenshots; the oldest are
    # deleted after each new screenshot so the folder stays bounded.
    _screenshot_max_raw = os.getenv("SCREENSHOT_MAX_FILES", "50")
    SCREENSHOT_MAX_FILES = max(
        1, int(_screenshot_max_raw)
    ) if _screenshot_max_raw.isdigit() else 50

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    _tg_uid = os.getenv("TELEGRAM_ALLOWED_USER_ID", "0")
    TELEGRAM_ALLOWED_USER_ID = int(_tg_uid) if _tg_uid.isdigit() else 0

    # Phase 5 — Vision model settings for screen understanding
    # VISION_NUM_GPU:
    #   0  -> CPU-only inference
    #   >0 -> GPU offload layers for faster inference
    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
    VISION_PROVIDER = os.getenv("VISION_PROVIDER", "auto").strip().lower()
    DEFAULT_NVIDIA_VISION_MODEL = "qwen/qwen3.5-122b-a10b"
    DEFAULT_OLLAMA_VISION_MODEL = "qwen3.5:4b"
    _vision_model_raw = os.getenv("VISION_MODEL", "").strip()
    if _vision_model_raw:
        VISION_MODEL = _vision_model_raw
    elif VISION_PROVIDER == "nvidia" or (VISION_PROVIDER == "auto" and NVIDIA_API_KEY):
        VISION_MODEL = DEFAULT_NVIDIA_VISION_MODEL
    else:
        VISION_MODEL = DEFAULT_OLLAMA_VISION_MODEL

    _vision_temperature_raw = os.getenv("VISION_TEMPERATURE", "0.6")
    try:
        VISION_TEMPERATURE = float(_vision_temperature_raw)
    except ValueError:
        VISION_TEMPERATURE = 0.6

    _vision_top_p_raw = os.getenv("VISION_TOP_P", "0.95")
    try:
        VISION_TOP_P = float(_vision_top_p_raw)
    except ValueError:
        VISION_TOP_P = 0.95

    _vision_max_tokens_raw = os.getenv("VISION_MAX_COMPLETION_TOKENS", "16384")
    VISION_MAX_COMPLETION_TOKENS = (
        int(_vision_max_tokens_raw)
        if _vision_max_tokens_raw.isdigit()
        else 16384
    )
    VISION_MODEL_HOST = os.getenv("VISION_MODEL_HOST", "http://localhost:11434")
    _vision_num_gpu_raw = os.getenv("VISION_NUM_GPU", "99")
    VISION_NUM_GPU = int(_vision_num_gpu_raw) if _vision_num_gpu_raw.lstrip("-").isdigit() else 0
    _vision_timeout_raw = os.getenv("VISION_TIMEOUT_SECONDS", os.getenv("VISION_TIMEOUT", "120"))
    try:
        parsed_vision_timeout = float(_vision_timeout_raw) if _vision_timeout_raw else None
        VISION_TIMEOUT = (
            parsed_vision_timeout
            if parsed_vision_timeout is not None
            and math.isfinite(parsed_vision_timeout)
            and parsed_vision_timeout > 0
            else None
        )
    except ValueError:
        VISION_TIMEOUT = None
    _vision_retries_raw = os.getenv("VISION_MAX_RETRIES", "0")
    VISION_MAX_RETRIES = min(3, int(_vision_retries_raw)) if _vision_retries_raw.isdigit() else 0

    _google_timeout_raw = os.getenv("GOOGLE_TIMEOUT_SECONDS", os.getenv("GOOGLE_TIMEOUT", "30"))
    try:
        parsed_google_timeout = float(_google_timeout_raw) if _google_timeout_raw else None
        GOOGLE_TIMEOUT = (
            parsed_google_timeout
            if parsed_google_timeout is not None
            and math.isfinite(parsed_google_timeout)
            and parsed_google_timeout > 0
            else None
        )
    except ValueError:
        GOOGLE_TIMEOUT = None
    _google_retries_raw = os.getenv("GOOGLE_MAX_RETRIES", "2")
    GOOGLE_MAX_RETRIES = min(3, int(_google_retries_raw)) if _google_retries_raw.isdigit() else 2
