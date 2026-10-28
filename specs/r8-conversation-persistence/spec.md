# R8 — Persistent conversation state

## Goal

Conversation state must survive process restart while remaining isolated by
thread and locally persisted.

## Scope

- Replace `MemorySaver` in `src/graph/agent.py`.
- Add a tested SQLite saver adapter in `src/graph/checkpoint.py`.
- Preserve the existing sync/async agent entry points and thread IDs.
- Make Telegram `/clear` delete the current durable thread.

## Contract

1. A successful invocation persists its graph checkpoint.
2. A later process using the same `thread_id` resumes that state.
3. Different thread IDs never share conversation state.
4. `/clear` removes the current thread's checkpoints and reports failure if the
   durable delete fails.
5. The latest checkpoint is retained per thread; older checkpoints are pruned
   through the saver API after a successful write.
6. Checkpoint failures do not delete the last known-good checkpoint.

## Acceptance tests

- Sync restart persistence with a deterministic fake agent/model.
- Async restart persistence with the same thread ID.
- Terminal/Telegram thread isolation.
- `/clear` removes durable state and the next invocation starts fresh.
- Checkpoint write failure preserves the previous checkpoint.
- SQLite busy-timeout/WAL configuration is observable without live services.
- Existing safe-smoke, compilation, and registry tests remain green.

## Out of scope

- Cloud checkpoint storage.
- Cross-user sharing.
- R6 memory-budget behavior; R6 starts only after this gate passes.
