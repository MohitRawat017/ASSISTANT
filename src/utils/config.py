import os
from dotenv import load_dotenv

# Load .env file from project root
# This must be called before any os.getenv() calls
load_dotenv()

import torch


class Config:
    
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    
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

    MEMORY_DIR = os.path.join(BASE_DIR, "data", "memory")

    GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
    REMINDER_EMAIL = os.getenv("REMINDER_EMAIL", "")  # Defaults to GMAIL_ADDRESS if empty

    _debug_raw = os.getenv("DEBUG_MODE", "true").strip().lower()
    DEBUG_MODE = _debug_raw in ("1", "true", "yes", "on")
    DEBUG_LOG_DIR = os.path.join(BASE_DIR, "logs", "agent_traces")

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    _tg_uid = os.getenv("TELEGRAM_ALLOWED_USER_ID", "0")
    TELEGRAM_ALLOWED_USER_ID = int(_tg_uid) if _tg_uid.isdigit() else 0

    # Phase 5 — Vision model settings for screen understanding
    # VISION_NUM_GPU:
    #   0  -> CPU-only inference
    #   >0 -> GPU offload layers for faster inference
    VISION_MODEL = os.getenv("VISION_MODEL", "qwen3.5:4b")
    VISION_MODEL_HOST = os.getenv("VISION_MODEL_HOST", "http://localhost:11434")
    _vision_num_gpu_raw = os.getenv("VISION_NUM_GPU", "99")
    VISION_NUM_GPU = int(_vision_num_gpu_raw) if _vision_num_gpu_raw.lstrip("-").isdigit() else 0
