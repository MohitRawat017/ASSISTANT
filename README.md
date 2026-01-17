# Desktop Voice Assistant

A powerful, local-first voice assistant built with Python. It leverages state-of-the-art models for speech recognition (Faster Whisper) and text-to-speech (Kokoro), powered by Google's Gemini 1.5 Flash for intelligent responses.

---

## 🚀 Version 1.0 (Current)

The current V1 implementation focuses on a seamless conversational experience with high-quality audio processing.

### ✅ Core Features
- **Continuous Listening**: The assistant enters a listening loop, ready to transcribe your speech.
- **High-Performance ASR**: Uses **Faster Whisper** (int8 quantization) on CUDA for near-instant speech-to-text.
- **Intelligent Brain**: Integrated with **Gemini 2.5 Flash** for fast, witty, and helpful responses.
- **Natural TTS**: Uses **Kokoro-82M** (running locally on GPU) to generate extremely natural-sounding speech.
- **Conversation Loop**: Listens, thinks, and speaks in a continuous cycle.
- **Graceful Exit**: Say "exit", "quit", or "stop" to end the session.

### 🏗 Architecture
- **Input**: Microphone capture (SoundDevice) -> Faster Whisper (ASR).
- **Processing**: Text -> Gemini 2.5 Flash API.
- **Output**: Text Response -> Kokoro TTS -> Audio Playback.
- **Tech Stack**: Python, PyTorch (CUDA), SoundDevice, Faster Whisper, Kokoro, Google GenAI.

### 📂 Project Structure
```text
assistant/
├── models/
│   ├── asr/ (Faster Whisper)
│   └── tts/ (Kokoro-82M)
├── src/
│   ├── audio_input/
│   │   └── asr.py        # Speech-to-Text handler
│   ├── audio_output/
│   │   └── tts.py        # Text-to-Speech handler
│   ├── utils/
│   │   └── config.py     # Central configuration
│   └── app.py            # Main application loop
├── requirements.txt
└── .env                  # API Keys
```

---

## 🛣 Version 2.0 (Planned)

The next major iteration (V2) will focus on **Action** and **Control**, transforming the assistant from a chatbot into a true desktop operator.

### � Coming Soon
- **Desktop Control**: Ability to open applications, manage windows, and control system volume.
- **Tool Use**: The LLM will be equipped with function calling to interact with the OS.
- **Automation**: Perform basic tasks like "Play Spotify", "Open Chrome", or "Search for [X]".
- **Enhanced Memory**: Short-term context retention for multi-turn tasks.

---

## � Setup & Usage

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   # Ensure PyTorch with CUDA is installed
   ```

2. **Environment Variables**:
   Create a `.env` file:
   ```env
   GEMINI_API_KEY=your_key_here
   ```

3. **Run the Assistant**:
   ```bash
   python -m src.app
   ```
