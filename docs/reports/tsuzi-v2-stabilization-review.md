# Tsuzi V2 Stabilization — Review and Implementation Plan

**Review date:** 2026-10-27
**Audit baseline:** `5e728c1` (`chore/v2-release`)
**Review scope:** the pasted comparative audit and the uncommitted Wave 1 changes present in the working tree.
**Status:** Historical Wave 1 baseline. R2/R3 findings and the R8/R6 follow-up
are tracked in [`tsuzi-v2-next-wave-plan.md`](./tsuzi-v2-next-wave-plan.md).

## 1. Executive verdict

The comparative audit is directionally correct and its dependency order should
be retained. The other agent implemented a useful subset of Wave 1, but its
first pass was not ready to accept because CI still skipped the manager tests,
OAuth recovery had no real entry point, and the privacy implementation did not
fully bound or sanitize all persisted output.

The current working tree has been corrected for the Wave 1 scope:

- R1: the broken manager package export is fixed and registry/import coverage is
  exercised in CI.
- R4: expired refreshable Google tokens refresh silently; explicit browser
  recovery is available through `python -m src.tools.google.auth`.
- R10: trace redaction, field-level mail/privacy masking, age retention, active
  file rotation, screenshot retention/path validation, and reminder-log
  sanitization are covered by deterministic tests.

At this historical baseline, R2, R3, R5, R6, R7, R8, and R9 remained staged
for later waves.
They should not be implemented out of order, especially R3 before the R2
error contract and R6/R8 concurrently in `src/graph/agent.py`.

## 2. Review of the other agent's implementation

| Area | Verdict | Review result |
|---|---|---|
| Managers package | Correct core fix | `src/managers/__init__.py` now exports only the existing `AlarmManager`. The old imports of nonexistent modules were the confirmed P0 defect. |
| Registry CI | Initially incomplete; corrected | The first workflow collected `test_managers.py` but filtered it with `-m safe_smoke`, while the class had no marker. The alarm class is now marked and the workflow runs registry/manager smoke explicitly. The remaining stale manager classes are still excluded and are not falsely reported as fixed. |
| Google refresh | Correct policy, incomplete recovery | Silent refresh was correctly decoupled from `allow_interactive`. The first pass still allowed raw missing-file errors and told users to run an interactive flow that had no command. A guarded helper, typed recovery path, CLI entry point, and tests now close that gap. |
| Trace redaction | Good foundation, insufficient boundary | The write choke point and DEBUG default were correct. The first pass missed common environment/provider key formats, mail personal-data fields, active-file size limits, and unsanitized reminder errors. Those are now covered. |
| Screenshot retention | Incomplete | The first pass capped files but allowed path traversal, non-PNG names, and zero-value deletion behavior. Filenames are now confined to PNG basenames and the configured minimum is one file. |
| Documentation | Partially stale | README, `.env.example`, coding-flow documentation, ADR, and changelog now describe the new DEBUG/auth/retention behavior. |

The original audit's claim that `get_memory_store` used the wrong import path
was independently rejected during review: `from src.memory import
LongTermMemory` matches the package export. That path was deliberately left
unchanged.

## 3. Current verification

Executed locally with an ephemeral Python 3.12 environment and no live
credentials, network writes, desktop automation, or email sends:

| Check | Result |
|---|---:|
| Safe-smoke + registry + marked alarm tests | **18 passed**, 23 deselected |
| OAuth and privacy regression tests | **33 passed** |
| Selected Wave 1 test collection | **74 collected** |
| Python bytecode compilation | **passed** |
| `git diff --check` | **passed** |

An unfiltered run that included all of `tests/test_managers.py` produced 22
expected failures from legacy task/calendar/habit manager imports plus the
then-unupdated alarm deletion assertion; those
modules do not exist in the repository. They are intentionally not counted as
Wave 1 passes and remain a Wave 5 test-cleanup decision.

The Windows desktop runtime, Task Scheduler, live Google APIs, Telegram, and
Ollama were not exercised on this Linux host. The CI workflow now installs the
deterministic dependencies and runs the selected Wave 1 regression files, but a
GitHub Actions run should still be observed before merging.

## 4. Corrected implementation roadmap

### Gate 0 — Baseline and scope control

1. Confirm branch, commit, status, and the exact audit snapshot.
2. Record baseline failures before each wave; classify them as product defects,
   stale tests, missing dependencies, or platform-only tests.
3. Never run `tests/mail.py`, live Google tests, destructive memory tests, or
   desktop tests in the safe lane.
4. Keep each wave reviewable and stop at its acceptance gate.

### Wave 1 — correctness and privacy (current)

**R1 — managers and registry**

- Keep only real manager exports.
- Keep a deterministic registry import test with offline module stubs.
- Run only the marked alarm-manager subset in the safe lane; do not claim the
  legacy task/calendar/habit manager tests are repaired.

**R4 — OAuth lifecycle**

- Refresh expired credentials silently when a refresh token exists.
- Never delete a stale token automatically.
- Return an actionable typed reauthorization error when recovery is needed.
- Use the explicit module command for browser authorization.

**R10 — privacy and retention**

- Keep JSONL traces enabled for explainability.
- Redact credential keys, provider token formats, and common mail/notification
  personal-data fields before persistence.
- Bound query/result fields and rotate the active daily trace by size.
- Age-prune trace files, cap screenshots, validate screenshot paths, and rotate
  both reminder logs.

**Wave 1 gate:** the selected safe lane and deterministic regression lane pass;
the diff contains no credentials; docs match the runtime behavior; no later-wave
behavior is silently introduced.

### Wave 2 — reliability contract

#### R2 first: timeouts, retries, and `ToolResult`

Define the contract before touching alarm or vision behavior:

```text
ok=true                         definite success
ok=false, code=...              definite failure
retryable=true                  safe to retry the operation
unknown_outcome=true            a side effect may have happened; never blindly retry
hint=...                        user/model-facing recovery guidance
```

Apply it to Ollama, vision providers, Google service construction/execution,
and side-effecting mail/calendar/task tools. Use generous configurable local
model deadlines, bounded retry counts, and sanitized/truncated provider detail.

#### R3 second: honest alarms

- Scheduler registration failure must be returned as failure, never success.
- A total delivery failure must retain the pending alarm and scheduled work or
  enter an explicit retry/reconciliation state.
- Add startup reconciliation for missed fires and expose list/delete lifecycle
  tools.
- Define duplicate behavior for delivery and cleanup using the R2 unknown-outcome
  state before adding retries.

**Wave 2 gate:** simulated timeout, provider error, scheduler failure, channel
failure, and process restart cases have deterministic tests; no side-effecting
test reaches a real service.

### Wave 3 — durable state and bounded memory

#### R8: persistent conversation state

Validate the installed LangGraph checkpoint API, then use SQLite persistence
with the existing thread IDs. Define `/clear`, retention, compaction, and
cross-channel isolation before implementation.

#### R6: memory safety

- Share one memory store instance instead of constructing one per query.
- Add a character/token budget and an explicit untrusted-memory fence.
- Make dedup category-aware and conservative; record overwrites.
- Use isolated temporary databases, WAL/busy timeout, and closed connections.

Run R8 and R6 sequentially because both modify `src/graph/agent.py` and both
affect context sizing.

### Wave 4 — desktop correctness and approvals

#### R5: vision coordinates and post-action verification

First port normalized coordinates based on the exact image dimensions and apply
DPI/monitor offsets. Then add configurable post-action verification that reports
`verified=false` rather than fictional success. Keep the coordinate math unit
tests platform-independent.

#### R7: risk-tiered approvals

- Tag tools read-only, low-risk, or destructive.
- Start with terminal confirmation; then add Telegram approvals with expiry and
  persisted decisions.
- Replace arbitrary `Popen(app_name)` fallback with resolved executable
  allowlisting and an approval boundary.
- Add a persistent emergency stop.

Run R5 and R7 sequentially because both touch `wrapped_tools.py`.

### Wave 5 — regression suite and hygiene

Implement the scripted-model agent tests only after the runtime contracts are
stable. Then:

- repair or quarantine stale manager/signature tests;
- move the live SMTP script out of `tests/`;
- replace phantom markers/categories;
- isolate all memory tests from the real database;
- decide whether to regenerate or remove the stale `uv.lock`;
- update tech-stack/testing docs and add ADRs for the R2 contract and approval
  policy.

## 5. Subagent roster and scheduling

The main agent owns scope, baseline capture, integration, final diff review, and
acceptance gates. At most two independent read-only or implementation agents
should run in parallel. Agents receive a file allowlist and must not commit,
modify credentials, run live side effects, or broaden their wave.

| Agent | Responsibility | Files / boundaries | Dependency |
|---|---|---|---|
| Reviewer A | Audit imports, CI, and OAuth | `src/managers/__init__.py`, `src/tools/google/auth.py`, tests, workflow | Wave 1 review |
| Reviewer B | Audit privacy and retention | `src/graph/agent.py`, `src/utils`, screenshot/reminder logging, docs | Wave 1 review |
| R1 implementer | Manager export and registry smoke | managers package, registry test, minimal workflow | none |
| R4 implementer | OAuth refresh and explicit reauth | `src/tools/google/auth.py`, auth tests/docs | none |
| R10 implementer | Redaction, bounded traces, retention | redaction/config/agent/screenshot/reminder, tests/docs | none |
| R2 implementer | External-call contract | agent, config, Google tools, vision, wrapper result helpers | R1/R4/R10 accepted |
| R3 implementer | Alarm state machine | wrapped tools, alarm manager, scheduler, reminder service, startup | R2 accepted |
| R8 implementer | SQLite conversation checkpointing | agent, requirements, persistence tests | Wave 2 accepted |
| R6 implementer | Memory budget and safe dedup | memory, agent prompt state, tests | R8 plan settled; run sequentially with R8 |
| R5 implementer | Coordinates and verification | vision, vision wrappers, pure math tests | R2 accepted; run before/after R7 as needed |
| R7 implementer | Approvals and launch policy | approvals service, wrapped tools, Telegram, app launcher | R2 accepted; run sequentially with R5 |
| R9 implementer | Deterministic agent tests and hygiene | tests, CI, runner, docs/scripts | R1–R8 stabilized |

Recommended schedule:

```text
Wave 1: reviewers (parallel) → R1 + R4 (parallel) → R10 → main-agent gate
Wave 2: R2 → main-agent gate → R3 → main-agent gate
Wave 3: R8 → R6 → main-agent gate
Wave 4: R5 → R7 → main-agent gate
Wave 5: R9 → full review
```

## 6. Additional recommendations

1. Do not use the number of legacy tests as a quality metric. The 28 stale
   manager tests reference modules absent from the repository; they need a
   separate cleanup decision rather than a CI exclusion disguised as success.
2. Treat `unknown_outcome` as a first-class state for email, calendar, tasks,
   alarms, and desktop actions. A timeout after dispatch is not equivalent to a
   failed operation.
3. Keep cloud fallback opt-in. A local-first failure must never silently send
   user data to a cloud model or vision provider.
4. Add a small ADR before R2 and R7. Error and approval semantics are public
   behavior and should not live only in implementation details.
5. The untracked `handover.md` currently says no changes were made, which is no
   longer true. It should be updated or removed by the repository owner before
   committing; it was not used as an authority over the actual working tree.
