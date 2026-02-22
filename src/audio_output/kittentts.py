import os
import re
import threading
import numpy as np
import sounddevice as sd
import onnxruntime as ort

if os.name == 'nt':
    local_dir = os.path.dirname(os.path.abspath(__file__))
    local_dll = os.path.join(local_dir, "espeak-ng", "libespeak-ng.dll")
    local_exe = os.path.join(local_dir, "espeak-ng", "espeak-ng.exe")
    if os.path.exists(local_dll):
        print("Using local portable eSpeak NG installation...")
        os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = local_dll
        os.environ["PHONEMIZER_ESPEAK_PATH"] = local_exe
    else:
        os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = r"C:\Program Files\eSpeak NG\libespeak-ng.dll"
        os.environ["PHONEMIZER_ESPEAK_PATH"] = r"C:\Program Files\eSpeak NG\espeak-ng.exe"

from kittentts import KittenTTS

KITTEN_MODEL_ID = "KittenML/kitten-tts-mini-0.8"
KITTEN_VOICE    = "Rosie"
KITTEN_SR       = 24000


class TTSHandler:
    def __init__(self):
        available_providers = ort.get_available_providers()
        if 'CUDAExecutionProvider' in available_providers:
            print("GPU acceleration enabled: CUDAExecutionProvider found!")
        else:
            print("WARNING: CUDA not detected by ONNX Runtime.")

        print(f"Loading KittenTTS model ({KITTEN_MODEL_ID})...")
        self.model = KittenTTS(KITTEN_MODEL_ID)
        self.voice = KITTEN_VOICE
        self._playback_lock = threading.Lock()
        self._stop_event = threading.Event()
        print("KittenTTS Ready.")

    def _clean_text(self, text: str) -> str:
        text = text.replace("*", "").replace("_", "").replace("`", "")
        return re.sub(r"\n+", " ", text).strip()

    def _synthesise(self, text: str) -> np.ndarray:
        audio = self.model.generate(text, voice=self.voice)
        if not isinstance(audio, np.ndarray):
            audio = np.array(audio, dtype=np.float32)
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        return audio

    def _play(self, audio: np.ndarray) -> None:
        with self._playback_lock:
            self._stop_event.clear()
            sd.play(audio, samplerate=KITTEN_SR)
            while sd.get_stream().active:
                if self._stop_event.is_set():
                    sd.stop()
                    break
                threading.Event().wait(0.05)

    def speak(self, text: str) -> threading.Thread:
        clean = self._clean_text(text)
        if not clean:
            return
        t = threading.Thread(target=lambda: self._play(self._synthesise(clean)), daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop_event.set()
        sd.stop()


if __name__ == "__main__":
    handler = TTSHandler()
    t = handler.speak("Hello! Running through the ONNX execution provider.")
    t.join()