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

        try:
            print("Attempting to load with Flash Attention 2...")
            self.model = Qwen3TTSModel.from_pretrained(
                Config.QWEN_TTS_MODEL_PATH,
                device_map=Config.DEVICE,
                dtype=torch.bfloat16,
                attn_implementation="flash_attention_2"
            )
            print("Success! Using Flash Attention 2.")
        except Exception as e:
            print(f"Flash Attention 2 failed ({e}). Falling back to SDPA (Standard).")
            self.model = Qwen3TTSModel.from_pretrained(
                Config.QWEN_TTS_MODEL_PATH,
                device_map=Config.DEVICE,
                dtype=torch.bfloat16,
                attn_implementation="sdpa"
            )

        if hasattr(torch, "compile"):
            try:
                print("Compiling model for speed (this takes a minute)...")
                self.model.model = torch.compile(self.model.model, mode="reduce-overhead")
            except Exception as e:
                print(f"Compile failed, skipping: {e}")

        self.ref_audio = Config.QWEN_TTS_REF_AUDIO
        self.ref_text = Config.QWEN_TTS_REF_TEXT
        
        self.prompt_item = self.model.create_voice_clone_prompt( 
            ref_audio=self.ref_audio,
            ref_text=self.ref_text,
            x_vector_only_mode=False,
        )

        self.audio_queue = queue.Queue()
        self.stop_signal = False
        self.is_speaking = False
        
        self.play_thread = threading.Thread(target=self._audio_player, daemon=True)
        self.play_thread.start()

        print("Warming up GPU...")
        with torch.inference_mode():
            self.model.generate_voice_clone(text="Ready.", language="English", voice_clone_prompt=self.prompt_item)
        print("Qwen TTS Ready.")

    def _audio_player(self):
        while True:
            if self.is_speaking and self.audio_queue.qsize() < 2:
                time.sleep(0.1) 
                continue

            item = self.audio_queue.get()
            if item is None: break

            audio, sr = item
            
            sd.play(audio, sr)
            sd.wait()

    def chunk_text(self, text, max_words=8):
            """
            LATENCY TUNING:
            max_words (int): The Hyperparameter.
            - Low (4-6): Lowest latency, but might cut mid-sentence (robotic).
            - High (10-15): Better flow, but higher risk of buffer underrun (lag).
            """
            words = text.split()
            current_chunk = []
            
            for word in words:
                current_chunk.append(word)
                
                if len(current_chunk) >= max_words or word.endswith('.'):
                    yield " ".join(current_chunk)
                    current_chunk = []
            
            if current_chunk:
                yield " ".join(current_chunk)

    def speak(self, text):
        clean_text = self._clean_text(text)
        if not clean_text: return

        self.stop_signal = False
        self.is_speaking = True

        max_words = 12
        chunks = list(self.chunk_text(clean_text, max_words=max_words)) 
        
        print(f"Split into {len(chunks)} chunks (Target: {max_words} words/chunk).")

        for i, chunk in enumerate(chunks):
            if self.stop_signal: break
            
            start_t = time.time()
            with torch.inference_mode():
                wavs, sr = self.model.generate_voice_clone(
                    text=chunk,
                    language="English",
                    voice_clone_prompt=self.prompt_item,
                )
            
            gen_time = time.time() - start_t
            print(f"Chunk {i+1} [{len(chunk.split())} words]: {gen_time:.2f}s")
            
            if wavs:
                silence = np.zeros(int(sr * 0.05)) 
                final_audio = np.concatenate((wavs[0], silence))
                self.audio_queue.put((final_audio, sr))
        self.is_speaking = False # Done adding chunks

    def _clean_text(self, text):
        text = text.replace("*", "").replace("_", "").replace("`", "")
        text = re.sub(r'\*.*?\*', '', text)
        return re.sub(r"\n+", " ", text).strip()

    def stop(self):
        self.stop_signal = True
        with self.audio_queue.mutex:
            self.audio_queue.queue.clear()