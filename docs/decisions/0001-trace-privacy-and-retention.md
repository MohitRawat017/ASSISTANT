# 0001: Trace privacy and bounded retention

**Status:** Accepted
**Date:** 2026-10-26

## Context

The product vision (`docs/product/vision.md`) promises that "any failed query
is explainable from the JSONL trace". Delivering that promise, the agent
writes every query, tool call, tool result and final response to
`logs/agent_traces/agent_trace_YYYYMMDD.jsonl` — unconditionally, unredacted
and unbounded. That collides with three realities of a single-user,
local-first assistant that also talks to cloud APIs (Gmail, NVIDIA vision,
OpenRouter, Telegram):

1. Tool arguments and user queries routinely carry credentials — Gmail app
   passwords, bot tokens, API keys pasted into a query. They were being
   written verbatim to disk.
2. Nothing ever deleted trace files, old screenshots
   (`data/screenshots/`) or the reminder logs (`logs/reminders.log`,
   `logs/reminder_failures.log`) — every one of them grows forever.
3. The verbose DEBUG stdout trace defaulted to on (`DEBUG_MODE` defaulted
   `true`), which is the wrong default for a log that mirrors unredacted
   tool traffic to the console.

Disabling trace writing entirely was not an option: it would break the
explainability promise.

## Decision

Traces stay ON, but are REDACTED and BOUNDED:

- A single redaction helper (`src/utils/redaction.py`) is applied at the
  trace write choke point (`_write_trace_record` in `src/graph/agent.py`),
  so every current and future trace writer is covered. Values stored under
  sensitive keys (password, passwd, secret, token, api_key, apikey,
  authorization, cookie, credential, private_key, passphrase) collapse to
  `[REDACTED]` at any nesting depth; high-confidence patterns scrub Bearer
  tokens, `sk-`-style API keys and `secret: value` assignments inside plain
  strings; common mail/notification personal-data fields (`to`, `cc`, `bcc`,
  `body`, `recipient`, `phone`) are also redacted; long values are truncated with an explicit
  `…[truncated N chars]` marker. Diagnostic structure (tool names,
  duration, thread ids, timestamps) is preserved.
- The three DEBUG stdout prints are routed through the same redaction.
- `DEBUG_MODE` now defaults to **false** — a user-visible behavior change.
  Console tracing becomes an explicit opt-in (`DEBUG_MODE=true`); JSONL
  traces remain the always-on record.
- Retention is bounded and configurable: `TRACE_RETENTION_DAYS` (default
  14) prunes old `agent_trace_*.jsonl` files after each write, while
  `TRACE_MAX_BYTES` (default 5 MB) and `TRACE_BACKUP_COUNT` (default 3)
  rotate the active day's trace;
  `SCREENSHOT_MAX_FILES` (default 50) caps `data/screenshots/`; the two
  reminder logs rotate at 1 MB with 2 backups.

## Consequences

- Easier: sharing a trace file for debugging no longer risks leaking
  credentials; disk usage from traces/screenshots/logs is capped by
  defaults instead of by vigilance.
- Harder: redaction is pattern-based, so secrets in unusual shapes (a
  password embedded in free-form prose without a `key: value` shape) can
  still reach the trace — redaction reduces exposure, it does not certify
  the logs secret-free. Users who want zero secrets on disk must keep them
  out of queries and tool args.
- Constrained: the explainability promise now depends on redaction keeping
  diagnostic fields intact — future trace writers must go through
  `_write_trace_record` (or apply `redact_value` themselves).
- Behavioral: users who relied on seeing the console trace without setting
  `DEBUG_MODE` must now set it explicitly.

## Alternatives Considered

- **Turn traces off by default** — rejected: directly breaks the
  "explainable from the trace" product promise, which is the reason the
  JSONL log exists.
- **Redact at each tool boundary instead of the write choke point** —
  rejected: every new tool would have to remember to redact; one choke
  point covers all callers and keeps tool behavior untouched.
- **Aggressive value patterns (any long random-looking string)** —
  rejected: mangles normal text (URLs, file paths, ids) and destroys the
  explainability the traces exist for; key-based matching plus a few
  high-confidence patterns is the right trade.
- **Logrotate / OS-level retention** — rejected: this is a portable,
  single-user app (Windows Task Scheduler for reminders); in-process
  rotation and date-based pruning keep it dependency-free.
