# Roadmap

**Question this document answers:** What is being built, in what order?

Does not restate why the product exists — see [vision.md](./vision.md).
Does not restate current architecture — see [../architecture/overview.md](../architecture/overview.md).

## How to Read This

- Ordered by priority, not by certainty of date.
- "Now" items are actively being built. "Next" is planned but not started.
  "Later" is directional and may change.

## Now

| Item | Outcome it serves (see vision.md) | Status |
|------|-----------------------------------|--------|
| Stabilization: keep the safe smoke gate green, tidy test markers | Explainable, reliable behavior | Ongoing |

## Done (delivered through Phase 5)

| Phase | Delivered |
|-------|-----------|
| 1 | LangGraph ReAct agent foundation with tool calling |
| 2 | Long-term memory with per-query memory refresh |
| 3 | Telegram text/voice interface and shared assistant runtime |
| 4 | Deterministic Windows PC automation |
| 5 | Screen vision and vision-guided mouse automation (NVIDIA or Ollama) |

## Next

| Item | Outcome it serves |
|------|-------------------|
| New phases, defined as specs under [`specs/`](../../specs/) before implementation | Scoped, reviewable increments that build on the Phase 5 base |

## Later (Directional)

- Deeper voice interaction — the ASR/TTS stack exists; richer voice flows are a natural extension
- More vision-driven autonomy — build on the Phase 5 tool-driven vision base

## Explicitly Deprioritized

Prevents re-proposing already-considered ideas.

- **Non-Windows desktop support** — the automation stack (pywinauto, pycaw) is Windows-native; revisit only as a deliberate platform expansion

## Related Documents

- Why these priorities matter: [vision.md](./vision.md)
- Major decisions affecting scope: [../decisions/](../decisions/)
