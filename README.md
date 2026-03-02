# Tsuzi — AI Voice Assistant

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![Status](https://img.shields.io/badge/Version-1.0-brightgreen?style=for-the-badge)
![Pipeline](https://img.shields.io/badge/Pipeline-Multi--Layer%20AI-purple?style=for-the-badge)
![TTS](https://img.shields.io/badge/TTS-Kokoro%20%7C%20KittenTTS-orange?style=for-the-badge)

> A fully local, multi-layer AI assistant that routes queries through fine-tuned models before reaching any cloud API — keeping costs near-zero, latency sub-second, and privacy intact.

---

## Architecture

Tsuzi uses a 5-layer inference pipeline where most queries never touch a large cloud model:

```
User Query
    │
    ▼
┌─────────────────────────────────────┐
│  Layer 0 — Pre-filter               │  ~0.01ms
│  String match for casual inputs     │
│  "hello" / "thanks" / "ok"          │
└────────────────┬────────────────────┘
                 │ (not casual)
                 ▼
┌─────────────────────────────────────┐
│  Layer 1 — MiniLM Intent Router     │  ~5ms · CPU
│  Fine-tuned BERT classifier         │
│  → casual / productivity /          │
│    system / research / comms        │
└────────────────┬────────────────────┘
                 │ (confidence ≥ 0.60)
                 ▼
┌─────────────────────────────────────┐
│  Layer 2 — Tool Category Lookup     │  ~0ms
│  Narrows tool set to 2–5 options    │
│  based on detected intent           │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Layer 3 — FunctionGemma            │  ~20–50ms · GPU
│  Fine-tuned LoRA on Gemma-270M      │
│  Outputs: {"tool": ..., "args": ...}│
└────────────────┬────────────────────┘
                 │ (valid JSON)
                 ▼
┌─────────────────────────────────────┐
│  Layer 4 — Tool Execution           │  direct
│  Runs the selected tool locally     │
└─────────────────────────────────────┘
                 │ (fallback at any layer)
                 ▼
┌─────────────────────────────────────┐
│  Groq LLM (llama-3.3-70b)          │  ~300–800ms
│  Complex reasoning / unknown intent │
└─────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│  Kokoro / KittenTTS                 │
│  Local neural TTS — spoken response │
└─────────────────────────────────────┘
```

---

## Performance

| Path | Latency | Cloud Cost |
|------|---------|------------|
| Casual pre-filter → LLM | ~350ms | Minimal (short prompt) |
| MiniLM + FunctionGemma → Tool | **~25–55ms** | **Zero** |
| Low-confidence → Groq fallback | ~400–800ms | Low |

The majority of practical voice commands (set timer, open app, web search) resolve in under **60ms** via the local model stack, with zero API cost.

---

## Capabilities

### Productivity
- Set timers and alarms with natural language durations
- Create and query tasks via a local SQLite task list
- Schedule calendar events with natural language dates

### System
- Launch any installed desktop application by name
- Execute shell commands with output capped and safety checks
- Query system info (time, date, status)

### Research
- Real-time web search via DuckDuckGo (no API key required)
- Academic paper search via arXiv
- Stack Overflow code search

### Communication
- Send and read Gmail with app-password auth

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Intent Classification | Fine-tuned MiniLM-L6-v2 (BERT, 22M params, CPU) |
| Tool Selection | Fine-tuned FunctionGemma-270M LoRA (GPU) |
| LLM Fallback | Groq `llama-3.3-70b-versatile` |
| ASR | Faster-Whisper Large-v3 Turbo |
| TTS | Kokoro-82M / KittenTTS |
| Memory | SQLite (LangGraph checkpointer, v2) |
| Tool Retrieval | Sentence-Transformers embedding similarity |

---

## Quick Start

### 1. Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure

```env
# .env
GROQ_API_KEY=your_groq_key
GMAIL_ADDRESS=your_email@gmail.com
GMAIL_APP_PASSWORD=your_app_password
OLLAMA_MODEL=qwen2.5:7b          # optional, for local LLM
```

### 3. Run

```powershell
python -m src.main
```

Set `USE_ASR = True` in `src/main.py` to enable voice input via microphone.

---

## Project Structure

```
src/
├── main.py                    # Entry point
├── tools/
│   ├── pre_filter.py          # Layer 0 — casual query detection
│   ├── intent_router.py       # Layer 1 — MiniLM intent classification
│   ├── tools_by_category.py   # Layer 2 — tool category mapping
│   ├── tool_router.py         # Layer 3 — FunctionGemma tool selection
│   ├── decision_router.py     # Layer 4 — pipeline orchestrator
│   ├── tool_retriever.py      # Embedding-based retrieval (fallback path)
│   └── wrapped_tools.py       # All tool implementations
├── managers/
│   ├── task_manager.py
│   ├── alarm_manager.py
│   └── calendar_manager.py
├── audio_input/
│   └── asr.py                 # Faster-Whisper ASR
├── audio_output/
│   ├── KokoroTTS.py
│   └── kittentts.py
└── utils/
    └── config.py

models/
├── asr/                       # Faster-Whisper weights
├── tts/                       # Kokoro / KittenTTS weights
└── tool_call/
    ├── miniLM/                # Fine-tuned intent classifier
    └── function_gemma/        # Fine-tuned LoRA tool selector
```

---

## Example Interactions

```
You: set a timer for 10 minutes
→ MiniLM: productivity (0.94) → FunctionGemma: set_timer(duration="10 minutes")
Tsuzi: Timer set for 10 minutes, master.

You: find papers on diffusion models
→ MiniLM: research (0.91) → FunctionGemma: search_arxiv(query="diffusion models")
Tsuzi: Found 3 papers on diffusion models...

You: open spotify
→ MiniLM: system (0.97) → FunctionGemma: open_app(app_name="spotify")
Tsuzi: Opening Spotify, master.

You: hey how are you
→ Pre-filter: casual → Groq LLM
Tsuzi: Doing great, master! What can I do for you?
```

---

## License

[MIT](LICENSE)
