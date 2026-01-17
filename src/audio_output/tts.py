import re
import torch
import sounddevice as sd
from kokoro import KPipeline, KModel
from src.utils.config import Config

class TTSHandler:
    def __init__(self):
        print(f"Loading TTS Model on {Config.DEVICE}...")
        self.k_model = KModel(
            repo_id="hexgrad/Kokoro-82M", 
            config=Config.TTS_CONFIG_PATH,
            model=Config.TTS_MODEL_PATH
        )
        self.k_model.to(Config.DEVICE).eval()
        
        self.pipeline = KPipeline(
            lang_code='a',
            model=self.k_model,
            device=Config.DEVICE
        )
        print("Kokoro TTS Ready.")

    def _clean_text(self, text: str) -> str:
        text = text.replace("*", "").replace("_", "").replace("`", "")
        return re.sub(r"\n+", " ", text).strip()

    def speak(self, text):
        clean_text = self._clean_text(text)
        if not clean_text:
            return

        generator = self.pipeline(clean_text, voice='af_heart', speed=1)
        
        for result in generator:
            if result.audio is not None:
                audio = result.audio.cpu().numpy()
                sd.play(audio, samplerate=Config.SAMPLE_RATE_PLAY)
                sd.wait() # Block until this sentence finishes