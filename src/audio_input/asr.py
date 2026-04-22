import numpy as np
import sounddevice as sd
import collections
import webrtcvad
from faster_whisper import WhisperModel
from src.utils.config import Config


class ASRHandler:  
    def __init__(self):
        """
        Initialize the ASR handler.
        """
        print(f"Loading ASR Model on {Config.DEVICE}...")
        
        self.model = WhisperModel(
            Config.ASR_MODEL_PATH, 
            device=Config.DEVICE,   # "cuda" or "cpu"
            compute_type="float16" if Config.DEVICE == "cuda" else "int8"
        )
        
        # WebRTC VAD for recording decisions
        # Aggressiveness 0-3: higher = more aggressive noise filtering
        # 2 is good for indoor/office, bump to 3 if still getting noise
        self.vad = webrtcvad.Vad(2)
        
        print("ASR Ready.")

    def listen(self) -> np.ndarray | None:
        SAMPLE_RATE = 16000      # WebRTC VAD requires 8k, 16k, or 32k
        FRAME_MS = 30            # WebRTC VAD works on 10, 20, or 30ms frames
        FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)  # = 480 samples

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

        speech_frames = []       # Collected speech audio
        silent_frame_count = 0   # How many silent frames since speech stopped
        is_speaking = False      
        speech_frame_count = 0   # Total speech frames (for minimum check)

        print("Listening...")

        # ==========================================================================
        # MAIN RECORDING LOOP
        # ==========================================================================
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,              # Mono audio
            dtype=np.int16,          # WebRTC VAD needs int16
            blocksize=FRAME_SAMPLES, # Read in frame-sized chunks
        ) as stream:
            while True:
                # Read one frame of audio
                frame, _ = stream.read(FRAME_SAMPLES)
                frame_bytes = frame.tobytes()

                # Ask WebRTC VAD: is this frame speech or not?
                # May raise exception on invalid audio, catch silently
                try:
                    is_speech = self.vad.is_speech(frame_bytes, SAMPLE_RATE)
                except Exception:
                    is_speech = False

                if is_speech:
                    # Speech detected in this frame
                    if not is_speaking:
                        # Speech just started — add pre-speech buffer for context
                        is_speaking = True
                        speech_frames.extend(list(pre_speech_buffer))
                        print("🎤 Speaking detected...")

                    speech_frames.append(frame)
                    silent_frame_count = 0  # Reset silence counter
                    speech_frame_count += 1

                else:
                    # Not speech — add to pre-speech buffer for potential context
                    pre_speech_buffer.append(frame)

                    if is_speaking:
                        # We're in speech mode but this frame is silent
                        silent_frame_count += 1
                        speech_frames.append(frame)  # Keep some trailing silence

                        if silent_frame_count >= SILENCE_FRAMES:
                            # User has been quiet long enough — done recording
                            print("✅ Speech ended, processing...")
                            break

        # Filter out recordings that were too short (noise, accidental trigger)
        if speech_frame_count < MIN_SPEECH_FRAMES:
            print("⚠️ Too short, ignoring...")
            return None

        # Combine all frames and convert to float32 for Whisper
        # int16 range is -32768 to 32767, normalize to -1.0 to 1.0
        audio = np.concatenate(speech_frames).flatten().astype(np.float32) / 32768.0
        return audio

    def transcribe(self, audio_data: np.ndarray) -> str:

        if audio_data is None or len(audio_data) == 0:
            return ""

        print("Transcribing...")
        
        # Transcribe with VAD filtering
        segments, info = self.model.transcribe(
            audio_data,
            beam_size=5,              # Beam search for better accuracy
            language="en",            # Fixed language saves detection time
            vad_filter=True,          # KEY: enables built-in Silero VAD
            vad_parameters=dict(
                threshold=0.5,              # Speech probability threshold
                min_speech_duration_ms=250, # Ignore very short sounds
                max_speech_duration_s=30,   # Max chunk size
                min_silence_duration_ms=500,# Silence needed to split segments
                speech_pad_ms=100,          # Padding around speech
            ),
            no_speech_threshold=0.6,    # Skip if >60% confident it's silence
            condition_on_previous_text=False,  # Prevents hallucination loops
        )

        # Combine all segments into one string
        text = " ".join(seg.text for seg in segments).strip()

        # Post-processing: filter out common Whisper hallucinations on silence
        HALLUCINATION_PHRASES = [
            "thank you", "thanks for watching", "you", "bye", 
            "please subscribe", ".", "..", "...", "[music]", "[silence]",
            "subtitles by", "www.", "translation"
        ]
        text_lower = text.lower().strip(".,!? ")
        
        # If the text is a known hallucination, return empty
        if text_lower in HALLUCINATION_PHRASES or len(text) < 2:
            print("⚠️ Hallucination detected, ignoring...")
            return ""

        print(f"📝 Transcribed: {text}")
        return text

    def listen_and_transcribe(self) -> str:
        audio = self.listen()
        if not isinstance(audio, np.ndarray):
            return ""
        if len(audio) == 0:
            return ""
        return self.transcribe(audio)

    def transcribe_file(self, file_path: str) -> str:

        segments, info = self.model.transcribe(
            file_path,
            language="en",
            vad_filter=True,
            vad_parameters=dict(
                threshold=0.5,
                min_speech_duration_ms=250,
                min_silence_duration_ms=500,
            ),
            no_speech_threshold=0.6,
            condition_on_previous_text=False,
        )
        
        text = " ".join([seg.text for seg in segments]).strip()

        # Filter hallucinations
        HALLUCINATIONS = {"thank you", "thanks for watching", "[music]", ".", ""}
        if text.lower() in HALLUCINATIONS:
            return ""
            
        return text