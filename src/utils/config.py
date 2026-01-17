import os
from dotenv import load_dotenv

load_dotenv()

import torch

class Config:
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    MODELS_DIR = os.path.join(BASE_DIR, "models")
    
    ASR_MODEL_PATH = os.path.join(MODELS_DIR, "asr")
    TTS_CONFIG_PATH = os.path.join(MODELS_DIR, "tts/config.json")
    TTS_MODEL_PATH = os.path.join(MODELS_DIR, "tts/kokoro-v1_0.pth")

    # Audio Settings
    SAMPLE_RATE_REC = 16000
    SAMPLE_RATE_PLAY = 24000
    RECORD_DURATION = 4  # seconds
    
    # GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")