# Folder Structure

**Question this document answers:** Where does code, configuration, and content live in this repository?

Do not describe *why* a technology was chosen here — see
[tech-stack.md](./tech-stack.md). Do not describe *how requests flow* between
these folders — see [coding-flow.md](./coding-flow.md).

## Top-Level Layout

```
repo-root/
├── .github/           # Workflows, issue/PR templates, CODEOWNERS, dependabot
├── docs/              # This knowledge base
├── specs/             # Feature specifications (one folder per feature)
├── src/               # Application source code
├── tests/             # pytest suite (safe smoke gate + side-effect tests)
├── download_model.py  # Fetches local ASR/TTS models into models/
├── requirements.txt   # Runtime dependencies (source of truth)
└── pyproject.toml     # Project metadata + pytest markers
```

## `src/` Layout

```
src/
├── main.py                    # Terminal + Telegram runtime entry point
├── scheduler_windows.py       # Windows-specific scheduling support
├── graph/                     # LangGraph agent core (tracked again since 2.0.0)
├── tools/
│   ├── wrapped_tools.py       # Tool registry the agent sees
│   ├── google/                # Gmail, Calendar, Tasks integrations
│   └── pc_automation/         # Windows automation helpers
├── interfaces/
│   └── telegram_bot.py        # Telegram bot interface
├── managers/
│   └── alarm_manager.py       # Alarm scheduling
├── memory/
│   └── long_term_memory.py    # Persistent memory under data/memory/
├── services/                  # Reminder delivery, email service
├── vision/
│   └── screen_vision.py       # Screen understanding + element finding
├── audio_input/
│   └── asr.py                 # Speech recognition
├── audio_output/              # TTS engines + reference audio
└── utils/
    └── config.py              # Environment-driven configuration
```

## Placement Rules

Rules an agent or engineer can apply without asking:

1. New capabilities = an implementation module in `src/tools/<domain>/` (or the relevant service module) **plus** a wrapped tool registered in `src/tools/wrapped_tools.py`. The agent never imports implementations directly.
2. Helpers shared across modules go in `src/utils/`.
3. Tests live in `tests/` as `test_<subject>.py`. The suite is flat today — keep it flat.
4. Generated data (`models/`, `data/`, `logs/`) is never committed — all gitignored.
5. Nothing executable belongs in `docs/`.

## Naming Conventions

- Modules and packages: `snake_case`
- Classes: `PascalCase`; constants: `UPPER_CASE`
- Test files: `test_*.py`, named after the subject under test
- Docs and spec folders: `kebab-case` files (`coding-flow.md`, `feature-template/`)

## Deliberately Untracked Paths

`.gitignore` intentionally excludes `src/app.py`, several
`src/managers/` experiments, all credentials (`token.json`,
`src/credentials/`, `.env`), local-only notes, and generated artifacts.
Check `.gitignore` before assuming a missing file is an accident.

## Related Documents

- Component responsibilities: [overview.md](./overview.md)
- File and code style rules: [../standards/coding.md](../standards/coding.md)
