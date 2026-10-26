# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Debug console tracing (`DEBUG_MODE`) now defaults to **off**; set
  `DEBUG_MODE=true` in `.env` to restore the verbose stdout trace. JSONL
  agent traces stay on for explainability (per the product vision) but are
  redacted at the write choke point — sensitive fields, Bearer tokens and
  `sk-`-style keys become `[REDACTED]`, long values are truncated with an
  explicit marker — and trace files older than `TRACE_RETENTION_DAYS`
  (default 14) are pruned after each write; the active daily file also rotates
  at `TRACE_MAX_BYTES` (default 5 MB) with `TRACE_BACKUP_COUNT` backups (ADR
  0001).

### Fixed

- Removed imports of nonexistent manager modules so the alarm manager and tool
  registry can load; added deterministic registry, OAuth, and privacy checks to
  the CI workflow.
- Google access tokens with a refresh token now refresh silently; explicit
  browser recovery is available with `python -m src.tools.google.auth`.
- `data/screenshots/` grew without bound: only the newest
  `SCREENSHOT_MAX_FILES` (default 50) screenshots are kept; the rest are
  deleted after each new capture.
- `logs/reminders.log` and `logs/reminder_failures.log` grew without bound:
  both now use rotating handlers (1 MB per file, 2 backups kept).

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
