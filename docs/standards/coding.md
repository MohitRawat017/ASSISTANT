# Coding Standards

**Question this document answers:** What are the rules for writing code in this repository?

Does not cover testing rules (see [testing.md](./testing.md)) or commit/PR
rules (see [git.md](./git.md)).

## Language & Style

- Python 3.12; 4-space indentation, UTF-8, LF (enforced by `.editorconfig`).
- No formatter/linter is configured yet. Match the style of the module you are editing. When a tool (e.g. Ruff) is adopted, wire it into CI and update this section first.
- Style is not hand-debated in review; correctness and structure are.

## Naming Conventions

- Variables/functions/modules: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_CASE` (see `src/utils/config.py`)
- Files: snake_case modules; tests `test_*.py` — see [../architecture/folder-structure.md](../architecture/folder-structure.md)

## Function & Module Design

- Max recommended function length: ~40 lines — a signal to extract, not a hard limit
- Public functions/modules must have a single, statable responsibility
- Prefer composition; the codebase has no inheritance hierarchies — keep it that way unless a decision record says otherwise
- New agent capabilities = implementation module + wrapped tool; never expose internals directly to the agent

## Error Handling

- Never swallow exceptions silently — the failure must reach the agent, the trace, or the log
- Optional integrations (vision, torch, TTS engines) degrade gracefully on `ImportError`; the runtime keeps running
- Validate at trust boundaries: env values are normalized with defaults in `src/utils/config.py`; Telegram input passes the allowlist before anything runs

## Comments & Self-Documenting Code

- Comments explain **why**, not **what**
- Deliberate shortcuts with a known ceiling get a `shortcut:` comment naming the ceiling and upgrade path
- Tool docstrings matter twice: they are documentation **and** the agent's tool descriptions

## Dependencies

- `requirements.txt` is the source of truth; every new dependency gets an inline comment stating its purpose
- Do not add PyTorch/CUDA builds to `requirements.txt` — installed separately per README
- Prefer the standard library and already-installed packages before adding anything new; new third-party dependencies require one reviewer sign-off

## Agent-Specific Notes

- Coding agents must follow this document exactly as written; if a rule seems outdated, propose an update rather than silently deviating.
- Do not introduce new patterns not already present in the codebase without a corresponding decision record — see [../decisions/](../decisions/).

## Related Documents

- Tools/languages available: [../architecture/tech-stack.md](../architecture/tech-stack.md)
- Test expectations for new code: [testing.md](./testing.md)
