# Tsuzi V2 next-wave implementation plan

**Baseline:** `5f63765` (`feat: harden alarm lifecycle`)

## Working order

1. **Restore the current reliability gate.** Update the stale hard-delete
   assertion to the R3 durable-cancellation contract, then fix lifecycle
   migration defaults, legacy cleanup-result handling, and scheduler identity
   preservation. No live provider or Windows action is used.
2. **R8 — persistent conversation state.** Replace process-local `MemorySaver`
   with a SQLite-backed checkpoint saver after validating the installed API.
   Preserve `run_agent()`/`arun_agent()` and existing thread IDs. Define
   latest-checkpoint retention, thread isolation, durable `/clear`, and
   restart/failure behavior.
3. **R8 acceptance gate.** Require restart persistence, isolation, clear,
   checkpoint-failure recovery, compilation, focused tests, and safe-smoke
   checks before starting R6.
4. **R6 — memory safety.** Bound memory injection, fence memory as untrusted
   context, make deduplication category-aware, configure SQLite WAL and busy
   timeout, and move all memory tests to isolated temporary databases.
5. **Documentation and CI cleanup.** Reconcile the stabilization report,
   changelog, roadmap, dependency metadata, and CI collection behavior with
   the verified implementation.

## R8 design and acceptance criteria

- `src/graph/checkpoint.py` owns the version-specific SQLite saver seam.
- The saver uses one durable database under `data/`, `check_same_thread=False`,
  WAL, and a bounded busy timeout. Sync and async graph calls share the same
  tested saver interface.
- `CHECKPOINT_DB_PATH` and `CHECKPOINT_RETENTION` are configurable. The first
  retention policy is `keep_latest`: each thread retains its latest durable
  checkpoint and the latest checkpoint contains the resumable graph state.
- Existing terminal and Telegram thread IDs remain isolated. Empty thread IDs
  receive collision-resistant UUID-based session IDs.
- `/clear` deletes the durable checkpoint rows for the current Telegram thread
  and keeps the same logical thread ID. A failed delete is reported as a
  failure; it is never described as cleared.
- A new process using the same thread ID resumes prior state. A different
  thread ID cannot read it. A failed model/checkpoint operation does not erase
  the previous successful checkpoint.

## R6 design and acceptance criteria

- Apply an explicit total memory budget and per-category limits before prompt
  construction; the budget includes injected memory and the base prompt.
- Wrap stored memory in an explicit untrusted-context boundary and instruct the
  model not to treat memory text as executable instructions.
- Deduplicate only within the same category; category changes are explicit.
- Configure memory SQLite connections with WAL and a busy timeout.
- Every memory test uses `tmp_path` or an equivalent isolated database.
- Tests cover oversized context, category collisions, concurrent writes,
  busy-database recovery, and prompt fencing.

## Current validated blocker

The environment initially lacked the SQLite saver. `langgraph-checkpoint-
sqlite==3.1.2` was installed for API validation and exposes
`langgraph.checkpoint.sqlite.SqliteSaver`, `delete_thread()`, and
`prune(..., strategy="keep_latest")`. The dependency must be recorded in
`requirements.txt`; implementation must not rely on `MemorySaver` fallback.
