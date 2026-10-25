# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - 2026-10-25

The Version 2 wrap: all phases through Phase 5 plus the stabilization pass,
with the agent core rebuilt and tracked in git.

### Added

- Canonical knowledge base under `docs/` (architecture, standards, product,
  glossary, decisions) bootstrapped from the project template.
- Community health files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `SECURITY.md`, issue templates, pull request template, `CODEOWNERS`, and
  `dependabot.yml`.
- `.env.example` documenting the runtime's environment variables.
- `CHANGELOG.md`, `LICENSE`, `.editorconfig`, `.gitattributes`, and
  `.vscode/extensions.json`.
- Feature specification workflow under `specs/`.

### Changed

- Rebuilt the LangGraph agent core (`src/graph/agent.py`) as local-first
  Ollama (`langchain-ollama`) with MemorySaver checkpointer, per-query
  memory refresh into the system prompt, and source-aware debug tracing
  plus JSONL query logs; the module is tracked in git again after being
  accidentally untracked and lost in `d40e0e0`.
- Reconciled `requirements.txt` with actual imports: removed stale entries
  (`openai`, `langchain-groq`, `duckduckgo-search`, `transformers`,
  experiments) and added missing ones (`webrtcvad`, `soundfile`,
  `onnxruntime`).
- Telegram voice messages reuse one cached Whisper ASR handler instead of
  reloading the model per message.
- `AlarmManager` reports errors via `logging` instead of `print`.

### Fixed

- Long-term memory dedup no longer lets short inputs ("hi") overwrite
  unrelated memories via the substring rule; `search()` escapes SQL LIKE
  wildcards so `%`/`_` match literally.
- Hardening pass across reminder delivery and Google tools: Gmail app
  passwords stripped of grouping spaces, email subjects sanitized against
  header injection, SMTP and Telegram sends time-bounded, alarm delivery
  marked notified only when a channel succeeded, invalid alarm times
  rejected before reaching Task Scheduler.

## [0.1.0] - 2026-04-23

### Added

- Phase 1: LangGraph ReAct agent foundation with tool calling and multi-step
  execution.
- Phase 2: Long-term memory with per-query memory refresh.
- Phase 3: Telegram text/voice interface and shared assistant runtime.
- Phase 4: Deterministic Windows PC automation (apps, windows,
  mouse/keyboard, volume, brightness, screenshots).
- Phase 5: Screen vision and vision-guided mouse automation with NVIDIA or
  local Ollama vision models.
- Debug tool-call tracing and JSONL query/result logs.
