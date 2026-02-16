# 🎙️ Desktop Voice Assistant

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![Status](https://img.shields.io/badge/Status-Version%202.0-green?style=for-the-badge)
![Ollama](https://img.shields.io/badge/Backend-Ollama-orange?style=for-the-badge)
![Torch](https://img.shields.io/badge/PyTorch-CUDA%20Enabled-red?style=for-the-badge&logo=pytorch)

A powerful, local-first voice assistant with intelligent function routing. Uses a fine-tuned FunctionGemma model to route user requests to the right backend managers—all running entirely on your machine.

---

## 🧠 System Architecture

```mermaid
graph TD
    subgraph Input
        User([User]) -->|Voice/Text| Input[Input Handler]
    end

    subgraph "Processing Core (Local)"
        Input -->|Audio Buffer| ASR[Faster-Whisper ASR]
        ASR -->|Text| Router[FunctionGemma Router]
        Input -->|Text| Router

        Router -->|Action Functions| Executor[Function Executor]
        Router -->|Passthrough| LLM[Ollama - Llama 3.2]

        Executor --> Managers[Managers Layer]
        Managers --> DB[(SQLite DBs)]
        Managers --> API[External APIs]

        LLM -->|Streamed Response| TTS[Qwen3 TTS / Kokoro]
        Executor -->|Result| TTS
    end

    subgraph "Managers (6 total)"
        Managers --> TaskMgr[TaskManager]
        Managers --> AlarmMgr[AlarmManager]
        Managers --> TimerMgr[TimerManager]
        Managers --> CalMgr[CalendarManager]
        Managers --> WeatherMgr[WeatherManager]
        Managers --> NewsMgr[NewsManager]
    end

    subgraph "Output"
        TTS -->|Audio| Speaker([Speakers])
    end

    style Router fill:#f9f,stroke:#333,stroke-width:2px
    style Executor fill:#bbf,stroke:#333,stroke-width:2px
    style LLM fill:#bfb,stroke:#333,stroke-width:2px
```

---

## ✨ Key Features

### 🎯 Intelligent Routing (FunctionGemma)
- **Model-based classification**: Every request is routed through a fine-tuned Gemma model that decides whether to:
  - Execute an action (timer, alarm, calendar, task, search)
  - Query system info (aggregates all manager states)
  - Pass through to LLM for conversation (thinking/nonthinking modes)
- **Fast-path shortcuts**: App launching and Spotify bypass the model for instant response

### 🗂️ Manager Architecture
Six independent managers handle different domains:
- **TaskManager** → SQLite (`data/tasks.db`) - To-do list management
- **AlarmManager** → SQLite (`data/alarms.db`) - Persistent alarms
- **TimerManager** → In-memory - Countdown timers (ephemeral)
- **CalendarManager** → SQLite (`data/calendar.db`) - Event scheduling
- **WeatherManager** → Open-Meteo API - Current weather + forecast
- **NewsManager** → DuckDuckGo + optional Ollama curation - Headline aggregation

### ⚡ Performance Features
- **Streaming responses**: LLM tokens → TTS in real-time (optional threaded mode)
- **Background summarization**: Conversation history compressed via separate thread
- **Lazy initialization**: Managers load independently; one failure doesn't crash everything

### 🛠️ Integrated Actions
```
"Set a timer for 10 minutes"        → TimerManager
"Wake me up at 7am"                 → AlarmManager
"Schedule meeting tomorrow at 3pm"  → CalendarManager
"Add buy groceries to my tasks"    → TaskManager
"Search for Italian recipes"        → Web search (DuckDuckGo)
"What's on my schedule?"            → get_system_info (all managers)
"Explain quantum computing"         → LLM passthrough (thinking mode)
"Hello there!"                      → LLM passthrough (nonthinking mode)
```

---

## 🛠️ Tech Stack

| Component | Technology | Description |
|-----------|------------|-------------|
| **ASR** | `Faster-Whisper` | Int8-quantized Whisper for low-latency transcription |
| **Router** | `FunctionGemma` | Fine-tuned Gemma 2B for function classification |
| **LLM** | `Ollama` (Llama 3.2) | Local inference with OpenAI-compatible API |
| **TTS** | `Kokoro / Qwen3 TTS` | Voice synthesis with optional voice cloning |
| **Storage** | `SQLite` | Lightweight persistence for tasks/alarms/calendar |
| **APIs** | DuckDuckGo, Open-Meteo | Web search and weather data |

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **NVIDIA GPU** (Recommended for `faster-whisper` and `FunctionGemma`)
- **[Ollama](https://ollama.com/)** installed and running

### 1. Installation

```powershell
# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. PyTorch Setup (CUDA)

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 3. Model Setup

Download ASR and TTS models:

```powershell
python download_model.py
```

Place your FunctionGemma model in:
```
models/tool_call/functiongemma/
  ├── model.safetensors
  ├── config.json
  ├── tokenizer.json
  └── ...
```

### 4. LLM Backend (Ollama)

```powershell
ollama serve
ollama pull llama3.2
ollama pull gemma3:12b
```

### 5. Run Assistant

```powershell
python -m src.main
```

**Configuration flags** (edit `src/main.py`):
- `USE_ASR = False` → Set to `True` to use microphone input instead of text
- `USE_THREADING = False` → Set to `True` for parallel TTS streaming
- `DEBUG_ROUTER = True` → Print routing decisions to console

---

## 📁 Project Structure

```
src/
├── main.py                    # Main entry point (NEW)
├── app.py                     # Legacy reference (not tracked in git)
├── router.py                  # FunctionGemma routing engine
├── function_executor.py       # Dispatches routed functions to managers
│
├── managers/                  # Data management layer
│   ├── __init__.py
│   ├── task_manager.py        # To-do list (SQLite)
│   ├── alarm_manager.py       # Persistent alarms (SQLite)
│   ├── timer_manager.py       # In-memory countdown timers
│   ├── calendar_manager.py    # Event scheduling (SQLite)
│   ├── weather_manager.py     # Weather API integration
│   └── news_manager.py        # News aggregation + AI curation
│
├── audio_input/
│   └── asr.py                 # Faster-Whisper handler
│
├── audio_output/
│   ├── KokoroTTS.py           # Kokoro TTS engine
│   └── QwenTTS.py             # Qwen3 TTS engine (alternative)
│
├── tools/
│   ├── web_search.py          # DuckDuckGo search wrapper
│   └── spotify.py             # Spotify integration
│
└── utils/
    └── config.py              # Centralized configuration

data/                           # Auto-created by managers
├── tasks.db
├── alarms.db
└── calendar.db
```

---

## 🔮 Roadmap (V3 Goals)

### ⚡ Latency & Performance
- [ ] **Ultra-low latency TTS**: Stream chunking + prompt embedding caching
- [ ] **Model warmup**: Preload all models at startup for instant first response
- [ ] **torch.compile()**: Enable PyTorch 2.0 compilation for router speedup

### 🤖 Agents & Tools
- [ ] **Planner agent**: Multi-step reasoning ("Find recipe → add ingredients to shopping list")
- [ ] **Browser automation**: Playwright integration for web tasks
- [ ] **Extended tools**: Email, calendar sync, smart home control

### 🧠 Long-term Memory & RAG
- [ ] **Vector database**: ChromaDB/Qdrant for conversation history retrieval
- [ ] **Entity tracking**: Persistent memory of people, places, preferences
- [ ] **Memory classification**: Auto-tag ephemeral vs. core memories

---

## ⚖️ License

[MIT License](LICENSE)
