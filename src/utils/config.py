import os
from dotenv import load_dotenv

load_dotenv()

import torch

class Config:
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    MODELS_DIR = os.path.join(BASE_DIR, "models")
    
    ASR_MODEL_PATH = os.path.join(MODELS_DIR, "asr/faster-whisper-large-v3-turbo-ct2")
    
    # Kokoro TTS Settings
    TTS_CONFIG_PATH = os.path.join(MODELS_DIR, "tts/Kokoro-82M/config.json")
    TTS_MODEL_PATH = os.path.join(MODELS_DIR, "tts/Kokoro-82M/kokoro-v1_0.pth")
    
    # Qwen TTS Settings
    QWEN_TTS_MODEL_PATH = os.path.join(MODELS_DIR, "tts/Qwen3-TTS-12Hz-0.6B-Base")
    QWEN_TTS_REF_AUDIO = os.path.join(BASE_DIR, "src/audio_output/audio_ref2.wav")
    QWEN_TTS_REF_TEXT = "that sound's fun wait are you asking me out to go on a date Alright i'll go on a date with you"
    # QWEN_TTS_REF_TEXT = "I sence your warmth on my skin , flowing from your touch"

    # Audio Settings
    SAMPLE_RATE_REC = 16000
    SAMPLE_RATE_PLAY = 24000
    RECORD_DURATION = 6.5  # seconds
    
    # GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

    # FunctionGemma model path
    FUNCTION_GEMMA_PATH = os.path.join(MODELS_DIR, "tool_call/functiongemma")
