# 🎙️ Desktop Voice Assistant

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![Status](https://img.shields.io/badge/Status-Version%202.0-green?style=for-the-badge)
![Backend](https://img.shields.io/badge/Backend-LangGraph%20%2B%20Groq-orange?style=for-the-badge)

A powerful, local-first voice assistant (Tsuzi) with intelligent function routing via LangGraph. Uses a ReAct Agent powered by Llama 3.x (Groq / OpenRouter) to seamlessly answer queries and invoke tools on your machine.

---

## 🧠 System Architecture

```mermaid
graph TD
    subgraph Input
        User([User]) -->|Voice/Text| Input[Input Handler]
    end

    subgraph "Processing Core"
        Input -->|Audio Buffer| ASR[Faster-Whisper ASR]
        ASR -->|Text| Router[LangGraph ReAct Agent]
        Input -->|Text| Router

        Router -->|Tool Use| ToolGroup[Dynamic Tool Selector]
        Router -->|Conversation| Memory[(SQLite Checkpointer)]
        
        ToolGroup --> Productivity[Productivity]
        ToolGroup --> System[System]
        ToolGroup --> Research[Research]
        ToolGroup --> Comm[Communication]
        
        Router -->|Response Text| TTS[Kokoro / KittenTTS]
    end

    subgraph "Managers & Services"
        Productivity --> TaskMgr[TaskManager]
        Productivity --> AlarmMgr[AlarmManager]
        Productivity --> CalMgr[CalendarManager]
        Research --> Web[Web/ArXiv/StackOverflow]
        Comm --> Email[Email Services]
        System --> OS[OS Commands]
    end

    subgraph "Output"
        TTS -->|Audio| Speaker([Speakers])
    end

    style Router fill:#f9f,stroke:#333,stroke-width:2px
    style ToolGroup fill:#bbf,stroke:#333,stroke-width:2px
```

---

## ✨ Key Features

### 🎯 Intelligent Routing (ReAct Agent)
- **LangGraph Architecture**: Tsuzi uses a robust LangGraph ReAct agent loop for multi-step reasoning and tool execution.
- **Dynamic Tool Selection**: A local keyword heuristic pre-filters tools (Productivity, System, Research, Communication) before sending them to the LLM to save tokens and improve latency.
- **Short-term Memory**: Powered by LangGraph's `SqliteSaver` to remember conversation state (thread checkpointer).

### 🗂️ Tool Categories
Tools are grouped modularly to provide broad capability:
- **Productivity**: Set alarms, logic timers, manage SQLite tasks list, create calendar events, check system info.
- **System**: Launch local applications, run terminal commands (OS-level).
- **Research**: DuckDuckGo web search, ArXiv paper search, StackOverflow search.
- **Communication**: Send and read emails.

### ⚡ Performance Features
- **Streaming audio**: High quality TTS generated using Kokoro or KittenTTS.
- **Stateful Threading**: Context-aware interactions across a single session using LangGraph checkpoints.
- **ASR Fallback**: Revert to fast text-based input if microphone is unavailable.

### 🛠️ Example Interactions
```
"Set a timer for 10 minutes"              → Productivity (set_timer)
"Wake me up at 7am"                       → Productivity (set_alarm)
"Schedule meeting tomorrow at 3pm"        → Productivity (create_calendar_event)
"Find recent papers on quantum computing" → Research (search_arxiv)
"Open Spotify"                            → System (open_app)
```

---

## 🛠️ Tech Stack

| Component | Technology | Description |
|-----------|------------|-------------|
| **ASR** | `Faster-Whisper` | Fast local transcription |
| **Agent** | `LangGraph` | Stateful ReAct Agent for complex routing |
| **LLM** | `Groq / OpenRouter` | Llama-3.x inference for tool calling |
| **TTS** | `Kokoro / KittenTTS` | Fast, local voice synthesis |
| **Memory** | `SQLite / LangGraph` | Checkpointer for conversation state |

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- API Keys: 
  - `GROQ_API_KEY` (or `OPENROUTER_API_KEY`) for reasoning
  - `EMAIL_USER` / `EMAIL_PASS` (if using communication tools)

### 1. Installation

```powershell
# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Setup

Create a `.env` file in the root directory:
```env
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key
EMAIL_USER=your_email@gmail.com
EMAIL_PASS=your_app_password
```

### 3. Model Setup (ASR/TTS)

Download necessary local models:

```powershell
python download_model.py
```

### 4. Run Assistant

```powershell
python -m src.main
```

**Configuration flags** (edit `src/main.py`):
- `USE_ASR = True` → Use microphone (set `False` for text input mode)
- `DEBUG_MODE = True` → Print routing decisions, tokens, and timing

---

## 📁 Project Structure

```
src/
├── main.py                    # Main pipeline
├── graph/                     # LangGraph Agent definition
│   └── agent.py               # ReAct checkpointer and logic
├── tools/                     # Action tools and groups
│   ├── tool_group.py          # Dynamic tool loader
│   └── wrapped_tools.py       # Langchain tool wrappers
├── managers/                  # Data persistence and domain logic
│   ├── task_manager.py
│   ├── alarm_manager.py
│   └── calendar_manager.py
├── audio_input/
│   └── asr.py                 # Faster-Whisper handler
├── audio_output/
│   ├── KokoroTTS.py           # Kokoro integration
│   └── kittentts.py           # Kitten TTS integration
└── utils/
    └── config.py              # Environment configuration
```

---

## ⚖️ License

[MIT License](LICENSE)
