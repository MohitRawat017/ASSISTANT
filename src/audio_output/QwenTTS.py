import re
import torch
import sounddevice as sd
from qwen_tts import Qwen3TTSModel
from src.utils.config import Config


class TTSHandler:
    def __init__(self):
        print(f"Loading Qwen TTS Model on {Config.DEVICE}...")
        
        self.model = Qwen3TTSModel.from_pretrained(
            Config.QWEN_TTS_MODEL_PATH,
            device_map=Config.DEVICE,
            dtype = torch.bfloat16,
            # attn_implementation="flash_attention_2",
        )

        self.ref_audio = Config.QWEN_TTS_REF_AUDIO
        self.ref_text = Config.QWEN_TTS_REF_TEXT
        
        print("Qwen TTS Ready.")
        
    def _clean_text(self, text: str) -> str:
        text = text.replace("*", "").replace("_", "").replace("`", "")
        return re.sub(r"\n+", " ", text).strip()

    

    def speak(self, text):
        clean_text = self._clean_text(text)
        if not clean_text:
            return
        
        prompt_item = self.model.create_voice_clone_prompt(
            ref_audio=self.ref_audio,
            ref_text=self.ref_text,
            x_vector_only_mode=False,
        )

        wavs, sr = self.model.generate_voice_clone(
            text=clean_text,
            language="English",
            voice_clone_prompt=prompt_item,
        )
        
        if wavs and len(wavs) > 0:
            sd.play(wavs[0], samplerate=sr)
            sd.wait()  # Block until playback finishes
