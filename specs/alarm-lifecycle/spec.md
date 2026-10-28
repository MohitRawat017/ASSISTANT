# Alarm lifecycle (Wave 2 R3)

## Contract

An alarm is durable before scheduling is attempted. `set_alarm` confirms success only
when the Windows scheduler returns a definite success and a non-empty stored task
name. Scheduler failure and timeout leave the row recoverable and return its
operation ID, state, and hint.

## State machine

```text
active + pending schedule -> active + scheduled
active + pending schedule -> active + schedule_failed|schedule_unknown
active -> disabled -> active
active -> cancelled
active/overdue -> claimed -> delivered
active/overdue -> claimed -> failed -> active/overdue
active/overdue -> claimed -> delivery_unknown
 delivered -> cleanup pending -> cleanup done|failed|unknown
```

New alarms use `occurrence=once`; recurring scheduling is not implemented yet.
`notified=1` remains a compatibility projection of `delivery_state=succeeded`.
`scheduled_task_name` is the only task identity used for cleanup. A total definite
delivery failure retains the row and scheduler artifacts for retry/reconciliation.

## Unknown-outcome rule

A timeout or post-dispatch transport failure does not prove that an external
provider rejected a notification. It is persisted as `delivery_unknown` and is
never blindly retried. The same rule applies to scheduler registration and task
cleanup. Reconciliation reports these rows and may mark stale claims unknown, but
never sends a notification.

## Concurrency and startup

Delivery workers atomically claim a row with a lease before invoking any channel.
Successful and failed channel outcomes are recorded in a generic attempt table.
Startup reconciliation marks stale claims unknown, reports overdue rows, checks
available scheduler query support, and retains cleanup-pending state. It is safe
and non-fatal; it performs no delivery.

R3 intentionally does not claim complete locale or DST correctness. Existing
Windows date/time formatting remains in place and should receive a separate,
tested scheduling change.
