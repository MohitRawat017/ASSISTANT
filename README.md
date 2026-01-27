# 🎙️ Desktop Voice Assistant

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![Status](https://img.shields.io/badge/Status-Version%202.0-green?style=for-the-badge)
![Ollama](https://img.shields.io/badge/Backend-Ollama-orange?style=for-the-badge)
![Torch](https://img.shields.io/badge/PyTorch-CUDA%20Enabled-red?style=for-the-badge&logo=pytorch)

A powerful, local-first voice assistant built for low-latency interactions. It listens, thinks, and speaks using state-of-the-art open-source models running entirely on your machine.

---

## 🧠 System Architecture

```mermaid
graph TD
    subgraph Input
        User([User]) -->|Voice| Mic[Microphone]
    end

    subgraph "Processing Core (Local)"
        Mic -->|Audio Buffer| ASR[Faster-Whisper]
        ASR -->|Transcription| App[Application Loop]
        
        App -->|History & Context| LLM[Ollama (Llama 3.2)]
        LLM -->|Streamed Tokens| TTS[Qwen3 TTS / Kokoro]
        
        App -.->|Background Task| Summarizer[Conversation Summarizer]
    end

    subgraph "Action & Output"
        App -->|Command| Tools[Tool Handler]
        Tools -->|Query| Search[Web Search]
        Tools -->|Launch| Apps[App Launcher]
        Tools -->|Control| Spotify[Spotify]
        
        TTS -->|Audio| Speaker([Speakers])
    end

    style App fill:#f9f,stroke:#333,stroke-width:2px
    style LLM fill:#bbf,stroke:#333,stroke-width:2px
    style ASR fill:#bfb,stroke:#333,stroke-width:2px
```

---

## ✨ Key Features (V2)

- **🗣️ Continuous Conversation**: Always-listening loop with `sounddevice` and `Faster-Whisper` for near-instant transcription.
- **⚡ Streaming Responses**: Low-latency token streaming from the LLM directly to the TTS engine.
- **🤖 Local Intelligence**: Powered by **Ollama** (Llama 3.2, Gemma 3) running locally—no data leaves your machine unless you search the web.
- **🎙️ Voice Cloning**: Uses **Qwen3 TTS** to clone a reference voice for natural-sounding speech.
- **🛠️ Integrated Tools**:
  - `search <query>` - Web search with LLM synthesis.
  - `open <app_name>` - Launch local applications.
  - `play <song> spotify` - Direct Spotify control.
- **🧠 Efficient Memory**: Background threads compress conversation history to keep the context window optimized.

---

## 🛠️ Tech Stack

| Component | Technology | Description |
|-----------|------------|-------------|
| **ASR** | `Faster-Whisper` | Optimized Whisper model running int8 quantization. |
| **LLM** | `Ollama` | Hosting Llama 3.2 / Gemma 3 locally (OpenAI-compatible API). |
| **TTS** | `Kokoro / Qwen3 TTS` | High-fidelity voice cloning and synthesis. |
| **Orchestration** | `Python` | Multithreaded application loop for ASR, LLM, and TTS. |

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **NVIDIA GPU** (Recommended for reasonable latency with `faster-whisper` and `Qwen3-TTS`)
- **[Ollama](https://ollama.com/)** installed and running.

### 1. Installation

Clone the repository and set up your environment:

```powershell
# Create venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install core dependencies
pip install -r requirements.txt
```

### 2. PyTorch Setup (CUDA)

To enable GPU acceleration (highly recommended), install the CUDA version of PyTorch:

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 3. Model Setup

Your models live in `models/`. Download them using the included script:

```powershell
python download_model.py
```

### 4. LLM Backend (Ollama)

Start Ollama and pull the required models:

```powershell
ollama serve
ollama pull llama3.2
ollama pull gemma3:12b
```

### 5. Run Assistant

```powershell
python src/app.py
```

---

## 🔮 Roadmap (V3 Goals)

We are actively working on **V3** to transform this into a fully autonomous agent.

### ⚡ Latency & Performance
- [ ] **Ultra-low latency QwenTTS**: Implement stream chunking and caching for prompt embeddings.
- [ ] **Warmup optimization**: Preload models to memory for instant start.

### 🤖 Agents & Tools
- [ ] **Structured Tool Registry**: deeply integrated function-calling capabilities.
- [ ] **Planner Loop**: Reasoning agent that can execute multi-step plans (e.g., "Find a recipe for pasta and add ingredients to my shopping list").
- [ ] **Browser Automation**: Playwright integration for real-world web tasks.

### 🧠 Long-term Memory & RAG
- [ ] **SQLite/Postgres Database**: Persistent storage for user preferences and entities.
- [ ] **RAG Pipeline**: Store transcripts and notes with embeddings traversal.
- [ ] **Memory Classification**: Auto-tagging memories (Ephemeral vs. Core vs. Sensitive).

---

## ⚖️ License

[MIT License](LICENSE)
