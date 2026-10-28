# ADR 0003: Durable alarm lifecycle and unknown outcomes

- **Status:** Accepted
- **Date:** 2026-10-27

## Decision

Alarm persistence owns the lifecycle of scheduling, delivery, and cleanup. New
rows receive a stable operation ID and durable target/occurrence, lifecycle,
schedule, delivery, claim/lease, attempt, error/hint, and cleanup fields. Existing
`time`, `notified`, and `scheduled_task_name` columns remain compatible with old
SQLite files and standalone workers.

A worker must atomically claim an eligible alarm before delivery. Channel results
are recorded generically by channel and run. At least one definite success marks
the alarm delivered; definite total failure retains it for retry/reconciliation.
An ambiguous external result becomes `delivery_unknown`, and the worker never
blindly resends it. Cleanup is an independent transition, so cleanup failure is
reconcilable without changing delivery truth.

Scheduler commands validate subprocess return codes. A timeout is unknown, while
a returned non-zero code is a definite scheduler failure. Stored task names, not
reconstructed guesses, are used for cleanup. Test seams inject the command runner
and clock while preserving the Windows `schtasks` command and 15-second timeout.

Startup reconciliation is a separate, non-fatal, no-send service. It detects
stale claims, overdue rows, schedule attention, missing tasks when query support
exists, and cleanup-pending rows. It reports or transitions bookkeeping safely;
it does not send notifications.

## Consequences

The user-facing alarm tool can no longer report success for an empty scheduler
registration. Rows may remain after a failed schedule or delivery, which is
intentional and makes recovery observable. Locale and DST behavior remain the
existing Windows implementation and are not declared solved by this ADR.
