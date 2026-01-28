import re
import torch
import sounddevice as sd
import threading
import queue
import time
import numpy as np 
from qwen_tts import Qwen3TTSModel
from src.utils.config import Config

class TTSHandler:
    def __init__(self):
        print(f"Loading Qwen TTS Model on {Config.DEVICE}...")

        # FIX 1: Enable SDPA and Torch Compile
        self.model = Qwen3TTSModel.from_pretrained(
            Config.QWEN_TTS_MODEL_PATH,
            device_map=Config.DEVICE,
            dtype=torch.bfloat16,
            attn_implementation="sdpa" 
        )
        
        try:
            self.model = torch.compile(self.model, mode="reduce-overhead")
        except:
            print("Torch compile failed, falling back to standard mode.")

        self.ref_audio = Config.QWEN_TTS_REF_AUDIO
        self.ref_text = Config.QWEN_TTS_REF_TEXT

        self.prompt_item = self.model.create_voice_clone_prompt(
            ref_audio=self.ref_audio,
            ref_text=self.ref_text,
            x_vector_only_mode=False,
        )

        self.audio_queue = queue.Queue()
        self.stop_signal = False
        
        self.play_thread = threading.Thread(target=self._audio_player, daemon=True)
        self.play_thread.start()

        # Warmup: Run a dummy generation so the first real user query isn't slow
        print("Warming up GPU...")
        with torch.inference_mode():
             self.model.generate_voice_clone(text="Warmup", language="English", voice_clone_prompt=self.prompt_item)
        print("Qwen TTS Ready.")

    def _audio_player(self):
        while True:
            item = self.audio_queue.get()
            
            if item is None: 
                break

            audio, sr = item
            
            # Play audio
            sd.play(audio, sr)
            sd.wait() 

    def chunk_text(self, text: str):
        sentences = re.split(r'(?<=[.?!])\s+', text)
        for s in sentences:
            if s.strip(): yield s.strip()

    def speak(self, text: str):
        clean_text = self._clean_text(text)
        if not clean_text: return

        self.stop_signal = False
        chunks = list(self.chunk_text(clean_text))

        print(f"Processing {len(chunks)} sentences...")

        for i, chunk in enumerate(chunks):
            if self.stop_signal: break
            
            start = time.time()
            with torch.inference_mode():
                wavs, sr = self.model.generate_voice_clone(
                    text=chunk,
                    language="English",
                    voice_clone_prompt=self.prompt_item,
                )
            
            # Latency Check
            gen_time = time.time() - start
            print(f"Generated chunk {i+1}/{len(chunks)} in {gen_time:.2f}s")

            if wavs:
                # Add tiny silence (0.1s) to smooth transitions between chunks
                silence = np.zeros(int(sr * 0.1))
                combined = np.concatenate((wavs[0], silence))
                self.audio_queue.put((combined, sr))

    def _clean_text(self, text: str) -> str:
        text = text.replace("*", "").replace("_", "").replace("`", "")
        return re.sub(r"\n+", " ", text).strip()