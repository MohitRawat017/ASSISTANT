# Tech Stack

**Question this document answers:** What technologies does this system use, and why were they chosen?

Do not describe *how* components interact here — see
[coding-flow.md](./coding-flow.md). Do not describe *where* code for these
technologies lives — see [folder-structure.md](./folder-structure.md).

## Runtime & Language

| Layer | Choice | Version | Why |
|-------|--------|---------|-----|
| Language | Python | 3.12 | The local-model ecosystem (whisper, torch, langchain) is Python-first |
| Platform | Windows | 11 | The desktop being automated; the automation stack is Windows-native |

## Application Layer

| Concern | Choice | Why |
|---------|--------|-----|
| Agent framework | LangGraph (>= 1.2.17, < 2.0) | ReAct loop, tool calling, durable per-thread state |
| Conversation checkpoints | langgraph-checkpoint-sqlite 3.1.2 | Local SQLite persistence with WAL and bounded busy timeout |
| LLM bindings | langchain-core, langchain-ollama, langchain-openai, langchain-nvidia-ai-endpoints, langchain-groq | One interface across local Ollama and optional cloud providers |
| Telegram | python-telegram-bot 21.11.1 (with job-queue) | Mature async bot with scheduling support |

## Model Layer

| Concern | Choice | Why |
|---------|--------|-----|
| Text model (runtime) | Ollama, default `qwen3.5:4b` | Local, private, no per-call cost |
| Vision | NVIDIA API (`qwen/qwen3.5-122b-a10b`) with Ollama fallback | Fast cloud vision, local privacy escape hatch via `VISION_PROVIDER=ollama` |
| ASR | faster-whisper (large-v3-turbo) | Local speech-to-text for Telegram voice |
| TTS | Kokoro / KittenTTS / QwenTTS | Local voice output options |

## Desktop Automation

| Concern | Choice | Why |
|---------|--------|-----|
| Mouse/keyboard, screenshots | pyautogui | Simple cross-call surface for input automation |
| Window management | pywinauto (uia backend) | Reliable Win11 window enumeration and control |
| Volume | pycaw + comtypes | Windows Core Audio control |
| Brightness | screen-brightness-control | Monitor brightness API |
| Processes | psutil | Process listing and management |
| App launching | AppOpener | Name-based app launching on Windows |

## Integrations

| Concern | Choice | Why |
|---------|--------|-----|
| Google (Gmail, Calendar, Tasks) | google-api-python-client + google-auth-* | Standard Google API stack |
| Web search | ddgs / duckduckgo-search | Keyless search |
| Page extraction | trafilatura, beautifulsoup4 | Readable webpage content for research tools |
| YouTube search | youtube-search-python | Research tooling |
| Optional experiments | playwright, PySide6, opencv-python, websockets, pyaudio | Exploratory; not load-bearing |

## Infrastructure

| Concern | Choice | Why |
|---------|--------|-----|
| CI | GitHub Actions, `windows-latest`, safe-smoke workflow | Matches the target platform; runs only deterministic tests |
| Testing | pytest + pytest-cov | Marker-based split between CI-safe and side-effect tests |
| Config | python-dotenv (`.env`) | Standard, keeps secrets gitignored |

## Explicitly Rejected Alternatives

Prevents re-litigating settled choices. One line each.

- **Cloud-only LLM (OpenAI-only)** — rejected for privacy, cost, and latency; local-first is the contract.
- **Raw multimodal chat for vision** — rejected; the text model decides *what* to do, vision decides *where* (tool-driven vision).
- **Heavy GUI frontend** — rejected; terminal + Telegram cover the use cases (PySide6 remains exploratory).

## Version Policy

- Python >= 3.12 (`.python-version`).
- Dependency floors live in `requirements.txt` — the source of truth for runtime dependencies; `pyproject.toml` stores project metadata and pytest settings only.
- PyTorch is installed separately (CUDA cu121 build) and deliberately kept out of `requirements.txt`.

## Related Documents

- Coding conventions for this stack: [../standards/coding.md](../standards/coding.md)
- Testing tools for this stack: [../standards/testing.md](../standards/testing.md)
