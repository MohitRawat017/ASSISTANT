# Coding Flow

**Question this document answers:** How does a single unit of work move through this system, end to end?

This describes runtime flow (a query passing through the assistant). It does
not describe development process — for how a code change gets from idea to
merged, see [../standards/git.md](../standards/git.md).

## Entry Points

| Entry Point | Trigger | Handled By |
|-------------|---------|------------|
| Terminal chat | User types a query in the terminal loop | `src/main.py` runtime |
| Telegram text | Allowed user sends the bot a message | `src/interfaces/telegram_bot.py` |
| Telegram voice | Voice note from Telegram | ASR (`src/audio_input/asr.py`) → same path as text |

## Primary Flow

1. A query arrives from terminal or Telegram (voice is transcribed to text first).
2. The shared runtime in `src/main.py` hands it to the LangGraph agent with the thread's durable SQLite checkpoint state; long-term memory is refreshed from one bounded local store per query.
3. The agent's ReAct loop decides: answer directly, or call tools from the registry in `src/tools/wrapped_tools.py`.
4. Tool execution fans out to implementation modules: Google tools, PC automation, services, Telegram.
5. Vision requests take a sub-flow: screenshot → describe/locate the element via NVIDIA or Ollama vision (`src/vision/screen_vision.py`) → coordinates mapped back to real screen pixels → mouse/keyboard automation runs.
6. The agent composes a short final response.
7. Output: printed or sent to the interface, optionally spoken via TTS, and the full tool trace is appended to `logs/agent_traces/agent_trace_YYYYMMDD.jsonl` (query source, thread id, tool calls, results, final response, duration, errors).

Conversation checkpoints live in `data/checkpoints.db` by default. Terminal and
Telegram thread IDs are distinct. Telegram `/clear` deletes only the current
thread's checkpoint rows; it does not affect long-term memory or other threads.

```
[Terminal / Telegram text|voice] → [ASR if voice] → [LangGraph ReAct agent]
    → [wrapped tool registry] → [Google / PC automation / services / Telegram]
    → [vision sub-flow: screenshot → vision model → pixel coords → mouse]
    → [final response] → [interface + optional TTS + JSONL trace]
```

## Error Handling Flow

- Tool failures: returned to the agent as actionable messages; the runtime does not crash on a bad tool call.
- Vision unavailability: import/provider failures degrade gracefully — vision tools report that they are unavailable instead of killing the assistant.
- Telegram boundary: messages from user ids other than `TELEGRAM_ALLOWED_USER_ID` are rejected before reaching the agent.
- Every query's outcome, including errors, lands in the JSONL trace for postmortems.

## Cross-Cutting Concerns

Where these are enforced, without repeating their rules:

- Configuration: `.env` is loaded and normalized once in `src/utils/config.py`; modules read `Config`, never raw env vars.
- Observability: JSONL traces are always written through the redaction/retention
  boundary; `DEBUG_MODE=true` additionally enables the concise console trace.
- Auth boundary: the Telegram allowlist; Google credentials live in gitignored token/credential files.
- State boundary: checkpoints and long-term memory are local SQLite stores;
  stored memory is fenced as untrusted context and bounded before prompt use.

## Related Documents

- Components referenced above: [overview.md](./overview.md)
- Where this code lives: [folder-structure.md](./folder-structure.md)
- Code-level conventions: [../standards/coding.md](../standards/coding.md)
