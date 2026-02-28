# src/asr.py
import numpy as np
import sounddevice as sd
import collections
import webrtcvad
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
        # WebRTC VAD for recording decisions (separate from Whisper VAD)
        # Aggressiveness 0-3: higher = more aggressive noise filtering
        # 2 is good for indoor/office, bump to 3 if still getting noise
        self.vad = webrtcvad.Vad(2)
        print("ASR Ready.")

    def listen(self) -> np.ndarray | None:
        """
        Dynamically record until the user stops speaking.
        Returns audio array, or None if only silence/noise detected.
        """
        SAMPLE_RATE = 16000      # WebRTC VAD requires 8k, 16k, or 32k
        FRAME_MS = 30            # WebRTC VAD works on 10, 20, or 30ms frames
        FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)  # = 480 samples

        # How long to wait after speech stops before finalizing
        # 1.2s is a good balance — long enough for natural pauses, short enough to feel responsive
        SILENCE_TIMEOUT_MS = 1200
        SILENCE_FRAMES = SILENCE_TIMEOUT_MS // FRAME_MS   # = 40 frames

        # Minimum speech to actually process (filters out coughs, clicks)
        MIN_SPEECH_FRAMES = 5    # ~150ms minimum

        # Ring buffer holds recent audio for context before speech starts
        # So we don't miss the first syllable
        pre_speech_buffer = collections.deque(
            maxlen=int(300 / FRAME_MS)  # 300ms of pre-speech context
        )

        speech_frames = []
        silent_frame_count = 0
        is_speaking = False
        speech_frame_count = 0

        print("Listening...")

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype=np.int16,           # WebRTC VAD needs int16
            blocksize=FRAME_SAMPLES,
        ) as stream:
            while True:
                frame, _ = stream.read(FRAME_SAMPLES)
                frame_bytes = frame.tobytes()

                # Ask WebRTC VAD: is this frame speech or not?
                try:
                    is_speech = self.vad.is_speech(frame_bytes, SAMPLE_RATE)
                except Exception:
                    is_speech = False

                if is_speech:
                    if not is_speaking:
                        # Speech just started — add pre-speech buffer for context
                        is_speaking = True
                        speech_frames.extend(list(pre_speech_buffer))
                        print("🎤 Speaking detected...")

                    speech_frames.append(frame)
                    silent_frame_count = 0
                    speech_frame_count += 1

                else:
                    # Not speech — add to pre-speech buffer for context
                    pre_speech_buffer.append(frame)

                    if is_speaking:
                        silent_frame_count += 1
                        speech_frames.append(frame)  # keep some trailing silence

                        if silent_frame_count >= SILENCE_FRAMES:
                            # User has been quiet long enough — done
                            print("✅ Speech ended, processing...")
                            break

        # Filter out recordings that were too short (noise, accidental trigger)
        if speech_frame_count < MIN_SPEECH_FRAMES:
            print("⚠️ Too short, ignoring...")
            return None

        # Combine all frames and convert to float32 for Whisper
        audio = np.concatenate(speech_frames).flatten().astype(np.float32) / 32768.0
        return audio

    def transcribe(self, audio_data: np.ndarray) -> str:
        """
        Transcribe audio with Silero VAD enabled inside Whisper.
        This is the second layer of VAD — filters noise Whisper would hallucinate on.
        """
        if audio_data is None or len(audio_data) == 0:
            return ""

        print("Transcribing...")
        segments, info = self.model.transcribe(
            audio_data,
            beam_size=5,
            language="en",              # set your language — removes language detection overhead
            vad_filter=True,            # ← KEY: enables built-in Silero VAD
            vad_parameters=dict(
                threshold=0.5,              # speech probability threshold (0-1), higher = stricter
                min_speech_duration_ms=250, # ignore speech shorter than 250ms
                max_speech_duration_s=30,   # max chunk size
                min_silence_duration_ms=500,# silence needed to split segments
                speech_pad_ms=100,          # padding around speech segments
            ),
            no_speech_threshold=0.6,    # if Whisper is >60% confident it's silence, skip
            condition_on_previous_text=False,  # prevents hallucination loops
        )

        text = " ".join(seg.text for seg in segments).strip()

        # Post-processing: filter out common Whisper hallucinations on silence
        HALLUCINATION_PHRASES = [
            "thank you", "thanks for watching", "you", "bye", 
            "please subscribe", ".", "..", "...", "[music]", "[silence]",
            "subtitles by", "www.", "translation"
        ]
        text_lower = text.lower().strip(".,!? ")
        if text_lower in HALLUCINATION_PHRASES or len(text) < 2:
            print("⚠️ Hallucination detected, ignoring...")
            return ""

        print(f"📝 Transcribed: {text}")
        return text

    def listen_and_transcribe(self) -> str:
        """Convenience method — full pipeline in one call."""
        audio = self.listen()
        if not isinstance(audio, np.ndarray):
            return ""
        if len(audio) == 0:
            return ""
        return self.transcribe(audio)