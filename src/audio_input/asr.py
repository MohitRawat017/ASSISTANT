import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from src.utils.config import Config

class ASRHandler:
    def __init__(self):
        print(f"Loading ASR Model on {Config.DEVICE}...")
        self.model = WhisperModel(
            Config.ASR_MODEL_PATH,
            device=Config.DEVICE,
            compute_type="float16" if Config.DEVICE == "cuda" else "int8"
        )
        print("ASR Ready.")

    def listen(self, duration=Config.RECORD_DURATION):
        print("Listening...")
        audio = sd.rec( 
            int(duration * Config.SAMPLE_RATE_REC),
            samplerate=Config.SAMPLE_RATE_REC,
            channels=1,
            dtype=np.float32
        )
        sd.wait() # Wait for recording to finish
        return audio.flatten()

    def transcribe(self, audio_data):
        print("Transcribing...")
        segments, _ = self.model.transcribe(audio_data, beam_size=5)
        text = " ".join(seg.text for seg in segments).strip()
        return text 
