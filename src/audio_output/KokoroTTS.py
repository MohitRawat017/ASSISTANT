"""
================================================================================
TSUZI ASSISTANT - TEXT-TO-SPEECH (TTS) OUTPUT
================================================================================

This module handles text-to-speech conversion using Kokoro TTS, a lightweight
and fast speech synthesis model that runs locally.

WHY KOKORO TTS:
===============
- Lightweight: 82M parameters (runs on CPU fine)
- Fast: Real-time or near real-time synthesis
- Natural sounding: Good prosody and intonation
- Local: No API calls, works offline
- Multiple voices: Various accent/gender options

ALTERNATIVES CONSIDERED:
=======================
- ElevenLabs: Best quality but expensive, cloud-only
- Azure TTS: Good quality, cloud, costs money
- Coqui TTS: Open source, but heavier models
- Qwen-TTS: Multi-language, but larger model
- pyttsx3: Built-in, but robotic sound

KOKORO VOICE OPTIONS:
====================
- af_heart: Female voice with warm tone (used here)
- am_michael: Male voice
- af_sarah: Female voice, different style
- And more...

================================================================================
KEY CONCEPTS FOR INTERVIEW:
================================================================================

Q: Why run TTS locally instead of using cloud APIs?
A: 1. Privacy: Voice data stays on device
   2. Offline: Works without internet
   3. Cost: No per-character charges
   4. Latency: No network round-trip
   5. Reliability: No API downtime

Q: What is the sample rate and why does it matter?
A: 24000 Hz = 24kHz. Higher = better quality but larger files.
   16kHz is phone quality, 44.1kHz is CD quality.
   24kHz is a good balance for voice.

================================================================================
"""

import re
import sounddevice as sd
from kokoro import KPipeline, KModel
from src.utils.config import Config


class TTSHandler:
    """
    Handles text-to-speech synthesis using Kokoro TTS.
    
    COMPONENTS:
    ===========
    1. KModel: The neural network that generates audio
    2. KPipeline: Preprocesses text and orchestrates synthesis
    
    USAGE:
    ======
    tts = TTSHandler()
    tts.speak("Hello, how can I help you?")
    
    FLOW:
    =====
    1. Text is cleaned (remove markdown, etc.)
    2. Pipeline tokenizes and processes text
    3. Model generates audio samples
    4. Audio is played through speakers
    """
    
    def __init__(self):
        """
        Initialize the TTS handler.
        
        LOADS TWO COMPONENTS:
        1. KModel: The neural network weights
        2. KPipeline: Text processing and synthesis pipeline
        
        The model loads faster on GPU but works fine on CPU.
        ~82M parameters means ~330MB in float32.
        """
        print(f"Loading TTS Model on {Config.DEVICE}...")
        
        # Load the model weights
        self.k_model = KModel(
            repo_id="hexgrad/Kokoro-82M",     # Hugging Face repo
            config=Config.TTS_CONFIG_PATH,     # Model configuration
            model=Config.TTS_MODEL_PATH        # Weights file
        )
        
        # Move to GPU/CPU and set to evaluation mode
        self.k_model.to(Config.DEVICE).eval()
        
        # Create the synthesis pipeline
        self.pipeline = KPipeline(
            lang_code='a',           # 'a' = American English
            model=self.k_model,
            device=Config.DEVICE
        )
        
        print("Kokoro TTS Ready.")

    def clean_text(self, text: str) -> str:
        """
        Clean text for TTS synthesis.
        
        WHY CLEAN?
        ==========
        - Markdown (*, _, `) would be spoken literally
        - Newlines break sentence flow
        - Special characters may confuse the model
        
        Args:
            text: Raw text from LLM response
            
        Returns:
            Cleaned text suitable for speech synthesis
        """
        # Remove markdown formatting characters
        text = text.replace("*", "").replace("_", "").replace("`", "")
        
        # Replace multiple newlines with single space
        return re.sub(r"\n+", " ", text).strip()

    def speak(self, text):
        """
        Speak text using Kokoro TTS.
        
        SYNTHESIS PROCESS:
        ==================
        1. Clean the text (remove formatting)
        2. Create generator from pipeline
        3. For each chunk (sentence), generate audio
        4. Play audio through speakers
        
        WHY GENERATOR?
        ==============
        Long texts are split into chunks. The pipeline returns
        a generator that yields (graphemes, phonemes, audio) tuples.
        This allows streaming synthesis - play first chunk while
        generating the next.
        
        Args:
            text: Text to speak (will be cleaned before synthesis)
        """
        # Clean text for speech
        clean = self.clean_text(text)
        if not clean:
            return

        # Create synthesis generator
        # voice='af_heart' = female voice with warm tone
        # speed=1 = normal speed (lower = slower, higher = faster)
        generator = self.pipeline(clean, voice='af_heart', speed=1)
        
        # Iterate through chunks and play
        for result in generator:
            if result.audio is not None:
                # Convert to numpy for sounddevice
                audio = result.audio.cpu().numpy()
                
                # Play audio and wait for completion
                sd.play(audio, samplerate=Config.SAMPLE_RATE_PLAY)
                sd.wait()  # Blocking - wait until audio finishes


# =============================================================================
# INTERVIEW QUESTIONS FOR THIS FILE
# =============================================================================
"""
Q1: What is the difference between TTS and ASR?
A: ASR (Automatic Speech Recognition) = Speech to Text
   TTS (Text-to-Speech) = Text to Speech
   They are opposite operations. In this assistant:
   - ASR: User speaks → text (for LLM)
   - TTS: LLM response → audio (for user)

Q2: Why use sounddevice for playback?
A: sounddevice is a Python wrapper for PortAudio:
   - Cross-platform (Windows, Mac, Linux)
   - Low latency
   - Simple API (play, wait)
   - Works with numpy arrays directly
   Alternatives: pyaudio, simpleaudio

Q3: What is eval() mode in PyTorch?
A: eval() sets the model to evaluation mode:
   - Disables dropout layers
   - Disables batch normalization updates
   - Ensures deterministic output
   Always call before inference!

Q4: Why clean text before synthesis?
A: TTS models expect natural language text:
   - "*hello*" → model might say "asterisk hello asterisk"
   - Newlines → might cause awkward pauses
   - URLs → might be read character by character
   Cleaning ensures natural-sounding output.

Q5: How would you add different voices?
A: Change the voice parameter in pipeline():
   - voice='am_michael' for male voice
   - voice='af_sarah' for different female voice
   Or let user choose via configuration.

Q6: What's the latency of TTS synthesis?
A: Depends on text length and hardware:
   - Short phrase (~10 words): ~100-300ms on GPU
   - Longer text: Generated in chunks, first chunk plays quickly
   Kokoro is optimized for real-time synthesis.

Q7: How would you save audio to file instead of playing?
A: Use scipy.io.wavfile or soundfile:
   import soundfile as sf
   sf.write('output.wav', audio, Config.SAMPLE_RATE_PLAY)

Q8: What is lang_code in KPipeline?
A: Specifies the language for pronunciation:
   - 'a' = American English
   - 'b' = British English
   - Other codes for other supported languages
   Affects phoneme generation and pronunciation.

Q9: Why call sd.wait() after sd.play()?
A: sd.play() is non-blocking - starts playback in background.
   sd.wait() blocks until playback completes.
   Without wait(), the loop would overwrite audio mid-playback.

Q10: How would you add speed control?
A: Add a speed parameter to speak():
    def speak(self, text, speed=1.0):
        generator = self.pipeline(clean, voice='af_heart', speed=speed)
    
    speed < 1 = slower, speed > 1 = faster
    Could be controlled by user preference or memory.
"""