"""
================================================================================
TSUZI ASSISTANT - AUTOMATIC SPEECH RECOGNITION (ASR)
================================================================================

This module handles speech-to-text conversion using Faster-Whisper, an
optimized version of OpenAI's Whisper model.

KEY COMPONENTS:
===============
1. DUAL VAD (Voice Activity Detection):
   - WebRTC VAD: Detects when user is speaking (fast, lightweight)
   - Silero VAD: Built into Whisper, filters noise in transcription

2. RECORDING PIPELINE:
   - Continuous audio capture from microphone
   - WebRTC VAD detects speech start/end
   - Pre-speech buffer catches first syllable
   - Silence timeout determines when to stop

3. TRANSCRIPTION:
   - Faster-Whisper model (CTranslate2 optimized)
   - Post-processing to remove hallucinations
   - Language-specific optimization (English)

WHY FASTER-WHISPER:
==================
- 4x faster than original Whisper
- Lower memory usage (CTranslate2)
- Supports GPU and CPU
- Same accuracy as original

VAD EXPLAINED:
==============
Voice Activity Detection determines if audio contains speech or silence.

WebRTC VAD (used for recording):
- Very fast, runs on raw audio
- Aggressiveness levels 0-3
- We use level 2 (balanced)

Silero VAD (used in transcription):
- Built into Faster-Whisper
- More accurate but slower
- Filters noise during transcription

================================================================================
KEY CONCEPTS FOR INTERVIEW:
================================================================================

Q: Why use TWO different VAD systems?
A: WebRTC VAD is for RECORDING decisions (when to start/stop recording).
   It's fast and lightweight. Silero VAD is for TRANSCRIPTION quality.
   It's more accurate and filters noise that Whisper might hallucinate on.

Q: What are "hallucinations" in speech recognition?
A: When Whisper transcribes silence/noise, it sometimes outputs random
   phrases like "thank you" or "subtitles by...". We filter these out
   in post-processing.

Q: What is the pre-speech buffer and why is it needed?
A: VAD takes ~30ms to detect speech. Without buffering, we'd miss the
   first syllable. The buffer keeps 300ms of audio BEFORE speech was
   detected, ensuring complete capture.

================================================================================
"""

import numpy as np
import sounddevice as sd
import collections
import webrtcvad
from faster_whisper import WhisperModel
from src.utils.config import Config


class ASRHandler:
    """
    Handles speech recognition with intelligent recording and transcription.
    
    COMPONENTS:
    ===========
    1. WhisperModel: The actual transcription model
       - Loaded on GPU if available, CPU otherwise
       - Uses float16 on GPU, int8 on CPU (quantization for speed)
    
    2. WebRTC VAD: Lightweight voice activity detector
       - Aggressiveness 2 (0-3 scale)
       - Used for recording decisions, not transcription
    
    USAGE:
    ======
    # One-shot: Listen, transcribe, return text
    handler = ASRHandler()
    text = handler.listen_and_transcribe()
    
    # Or step by step:
    audio = handler.listen()        # Record until silence
    text = handler.transcribe(audio)  # Convert to text
    
    # Transcribe existing file:
    text = handler.transcribe_file("recording.ogg")
    """
    
    def __init__(self):
        """
        Initialize the ASR handler.
        
        LOADS TWO MODELS:
        1. WhisperModel: Large model for transcription (~1GB)
        2. WebRTC VAD: Tiny, built into webrtcvad package
        
        The Whisper model takes a few seconds to load on first init.
        Subsequent inits (if singleton pattern used) would be instant.
        """
        print(f"Loading ASR Model on {Config.DEVICE}...")
        
        self.model = WhisperModel(
            Config.ASR_MODEL_PATH,  # Path to model weights
            device=Config.DEVICE,   # "cuda" or "cpu"
            # Quantization: float16 for GPU, int8 for CPU
            compute_type="float16" if Config.DEVICE == "cuda" else "int8"
        )
        
        # WebRTC VAD for recording decisions
        # Aggressiveness 0-3: higher = more aggressive noise filtering
        # 2 is good for indoor/office, bump to 3 if still getting noise
        self.vad = webrtcvad.Vad(2)
        
        print("ASR Ready.")

    def listen(self) -> np.ndarray | None:
        """
        Dynamically record until the user stops speaking.
        
        RECORDING ALGORITHM:
        ====================
        1. Continuously capture audio in small frames (30ms)
        2. For each frame, ask WebRTC VAD: "is this speech?"
        3. If speech detected:
           - Add pre-speech buffer (catches first syllable)
           - Start recording
           - Reset silence counter
        4. If silence detected while recording:
           - Increment silence counter
           - If silence > 1.2 seconds, stop recording
        5. If recording too short (<150ms), discard as noise
        
        TIMING CONSTANTS:
        =================
        - SAMPLE_RATE = 16000 Hz: Required by WebRTC VAD
        - FRAME_MS = 30 ms: WebRTC VAD frame size
        - SILENCE_TIMEOUT = 1200 ms: Wait this long after speech stops
        - MIN_SPEECH_FRAMES = 5: Minimum ~150ms to filter coughs/clicks
        
        PRE-SPEECH BUFFER:
        ==================
        VAD takes time to detect speech. Without buffering, we'd miss
        the beginning of the first word. The buffer keeps 300ms of
        audio BEFORE speech was detected.
        
        Returns:
            Audio as numpy array (float32), or None if no valid speech
        """
        # ==========================================================================
        # CONSTANTS FOR RECORDING
        # ==========================================================================
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

        speech_frames = []       # Collected speech audio
        silent_frame_count = 0   # How many silent frames since speech stopped
        is_speaking = False      # Currently in speech mode?
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

        # ==========================================================================
        # POST-RECORDING PROCESSING
        # ==========================================================================
        
        # Filter out recordings that were too short (noise, accidental trigger)
        if speech_frame_count < MIN_SPEECH_FRAMES:
            print("⚠️ Too short, ignoring...")
            return None

        # Combine all frames and convert to float32 for Whisper
        # int16 range is -32768 to 32767, normalize to -1.0 to 1.0
        audio = np.concatenate(speech_frames).flatten().astype(np.float32) / 32768.0
        return audio

    def transcribe(self, audio_data: np.ndarray) -> str:
        """
        Transcribe audio with Silero VAD enabled inside Whisper.
        
        This is the second layer of VAD — filters noise Whisper would
        hallucinate on. Even if WebRTC VAD let some noise through,
        Silero VAD catches it during transcription.
        
        TRANSCRIPTION PARAMETERS:
        =========================
        - beam_size=5: Beam search width (higher = better, slower)
        - language="en": Skip language detection, assume English
        - vad_filter=True: Enable Silero VAD
        - no_speech_threshold=0.6: Skip segments that are >60% silence
        
        HALLUCINATION FILTERING:
        ========================
        Whisper sometimes outputs "phantom" text on silence:
        - "Thank you", "Thanks for watching"
        - "Subtitles by...", "[music]"
        
        We filter these out in post-processing.
        
        Args:
            audio_data: Audio as numpy array (float32, 16kHz)
            
        Returns:
            Transcribed text, or empty string if no valid speech
        """
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
        """
        Convenience method — full pipeline in one call.
        
        Combines listen() and transcribe() for simple usage.
        
        Returns:
            Transcribed text, or empty string if no valid speech
        """
        audio = self.listen()
        if not isinstance(audio, np.ndarray):
            return ""
        if len(audio) == 0:
            return ""
        return self.transcribe(audio)

    def transcribe_file(self, file_path: str) -> str:
        """
        Transcribe an audio file (e.g., Telegram .ogg voice notes).
        
        Faster-Whisper handles .ogg/opus natively — no conversion needed!
        This is a major advantage over original Whisper.
        
        Supported formats:
        - .ogg, .opus (Telegram voice notes)
        - .wav, .mp3, .m4a
        - Most other audio formats
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Transcribed text, or empty string if no valid speech
        """
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


# =============================================================================
# INTERVIEW QUESTIONS FOR THIS FILE
# =============================================================================
"""
Q1: Why use Faster-Whisper instead of OpenAI's original Whisper?
A: Faster-Whisper uses CTranslate2, which provides:
   - 4x faster inference
   - Lower memory usage
   - Same accuracy
   - Better GPU utilization
   Original Whisper is still great, but Faster-Whisper is optimized
   for real-time applications like this assistant.

Q2: What is VAD and why use two different ones?
A: Voice Activity Detection determines if audio is speech or silence.
   WebRTC VAD: Used for RECORDING decisions (fast, runs on raw bytes)
   Silero VAD: Used for TRANSCRIPTION quality (accurate, built into Whisper)
   
   Two layers means: WebRTC catches when to record, Silero catches
   noise that might cause hallucinations.

Q3: What causes hallucinations in speech recognition?
A: Whisper is trained to always output text. When given silence:
   - It "imagines" speech from noise
   - Common outputs: "Thank you", "Subtitles by...", "[music]"
   - These come from training data (YouTube subtitles, etc.)
   We filter these post-transcription.

Q4: What is the pre-speech buffer?
A: VAD takes ~30ms to detect speech. Without buffering, we'd miss
   the start of the first word ("Hello" → "ello").
   The buffer keeps 300ms of audio before speech was detected.

Q5: Why 16kHz sample rate?
A: WebRTC VAD only works with 8kHz, 16kHz, or 32kHz.
   16kHz is standard for speech recognition (telephone quality).
   CD quality (44.1kHz) is unnecessary for speech and wastes memory.

Q6: What's the difference between beam_size and greedy decoding?
A: beam_size=1 is greedy (take most likely next token).
   beam_size=5 explores 5 most likely paths and takes best overall.
   Higher beam = better accuracy but slower. 5 is a good balance.

Q7: What does condition_on_previous_text=False do?
A: When True, Whisper considers previous transcript when generating
   next segment. This can cause "looping" hallucinations where it
   repeats the same phrase. False prevents this at slight accuracy cost.

Q8: How would you add multi-language support?
A: 1. Remove language="en" to enable auto-detection
   2. Or add parameter: language="hi" for Hindi
   3. For mixed language, use: language=None, task="transcribe"
   The model supports 99+ languages.

Q9: What are the performance characteristics?
A: On GPU (RTX 3060): ~0.3x realtime (3 second audio = 1 second to transcribe)
   On CPU: ~1-2x realtime depending on model size
   "turbo" model is fastest with minimal accuracy loss.

Q10: How does int8 quantization help on CPU?
A: int8 uses 8-bit integers instead of 32-bit floats:
   - 4x smaller model memory
   - 2-4x faster inference on CPU
   - Minimal accuracy loss (quantization-aware training)
   Essential for real-time CPU inference.
"""