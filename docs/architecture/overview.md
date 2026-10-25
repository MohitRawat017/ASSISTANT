# Architecture Overview

**Question this document answers:** What is this system, and what problem does it solve?

## Purpose

Tsuzi exists to give one person a private, on-device desktop assistant instead
of a cloud-hosted one. It serves a single owner-operator on Windows 11 by
combining conversational agent abilities (reasoning, tool calling, memory)
with real-world effect: opening apps, managing tasks and calendar events,
sending mail and reminders, answering from Telegram, and seeing the screen
well enough to click UI elements by description.

## System Boundaries

What this system **is responsible for**:

- Interpreting natural-language requests and deciding which tools to call (ReAct agent)
- Executing productivity, communication, PC-control, and vision tools on the owner's machine
- Persisting long-term memory and per-thread conversation state
- Exposing the same assistant runtime over terminal and Telegram
- Producing debug traces and JSONL query logs

What this system **is explicitly not responsible for**:

- Multi-user or hosted serving — single-user by design
- Desktop control on macOS/Linux — the automation stack is Windows-native
- Training or fine-tuning models — it consumes existing Ollama/NVIDIA models
- Being a general-purpose chat UI — it is a tool-driven assistant, not raw chat

## Major Components

| Component | Responsibility |
|-----------|-----------------|
| Terminal + Telegram runtime (`src/main.py`) | Starts the shared assistant runtime; terminal chat loop and Telegram wiring |
| LangGraph agent (`src/graph/agent.py`) | ReAct loop, tool calling, prompt flow, debug tracing |
| Tool registry (`src/tools/wrapped_tools.py`) | The compact, documented tool surface the agent sees |
| Google tools (`src/tools/google/`) | Gmail send/read/search, Calendar, Tasks via Google APIs |
| PC automation (`src/tools/pc_automation/`) | App launch, window management, screenshots, mouse/keyboard, volume/brightness, system status |
| Telegram interface (`src/interfaces/telegram_bot.py`) | Remote text/voice access and push notifications |
| Vision (`src/vision/screen_vision.py`) | Screen description, text extraction, locating UI elements by description |
| Memory (`src/memory/long_term_memory.py`) | Persistent long-term memory under `data/memory/` |
| Services (`src/services/`) | Reminder delivery (email + Telegram), email service |
| Managers (`src/managers/`) | Alarm scheduling |
| Audio (`src/audio_input/`, `src/audio_output/`) | Speech recognition (faster-whisper) and TTS engines (Kokoro, KittenTTS, QwenTTS) |
| Configuration (`src/utils/config.py`) | Environment-driven configuration loaded from `.env` |

For how a request moves through these components, see
[coding-flow.md](./coding-flow.md).
For the technologies each component is built with, see
[tech-stack.md](./tech-stack.md).
For where each component lives in the repo, see
[folder-structure.md](./folder-structure.md).

## Non-Negotiable Constraints

Constraints that shape every future decision.

- **Local-first**: the core runtime works with local Ollama and no cloud key; NVIDIA vision is optional.
- **Secrets stay out of the repo**: `.env`, `token.json`, and `src/credentials/` are gitignored.
- **Safe smoke gate**: the deterministic `safe_smoke` suite must keep passing in CI on every PR.

## Related Documents

- Product rationale: [../product/vision.md](../product/vision.md)
- Architectural decisions and their history: [../decisions/](../decisions/)
