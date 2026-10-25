# Testing Standards

**Question this document answers:** What are the rules for testing code in this repository?

Does not cover code style (see [coding.md](./coding.md)) or when tests must
pass before merge (see [git.md](./git.md)).

## Test Types & When to Use Them

The suite is flat in `tests/` (no unit/integration/e2e subfolders) — keep it
that way. Separation happens via pytest markers, not folder structure:

| Marker | Meaning | Runs in CI? |
|--------|---------|-------------|
| `safe_smoke` | Deterministic; no desktop automation, network, Telegram, Google credentials, Ollama calls, or report files | **Yes — the merge gate** |
| `side_effect` | May mutate desktop state, open apps, use network, or write local files | No |
| `requires_network` / `requires_gmail` | Needs internet / Gmail credentials | No |
| `core`, `pc_control`, `file_ops`, `research`, `habits`, `email`, `integration` | Domain grouping for local runs | No |

## Coverage Expectations

- No coverage threshold is configured yet; the safe smoke gate is the merge requirement
- New code must not break the safe smoke suite
- Every bug fix includes a regression test when it can be made deterministic
- New wrapped tools get at least a registration/import check in the safe smoke suite when feasible

## What Must Be Tested

- Tool registry contents (what the agent can call)
- Memory persistence round-trips
- Manager logic that runs without a desktop or network

## What Should Not Be Tested

- Third-party library internals
- Real mouse movement or real windows in CI — local-only, marked `side_effect`
- Generated code

## Test Design Rules

- `safe_smoke` must be deterministic — no real time, network, desktop, or random state without seeding/mocking
- One logical assertion focus per test; descriptive names stating the behavior under test
- No shared mutable state between tests

## Running Tests

```powershell
# CI baseline (safe smoke gate)
python -m pytest --collect-only -q --no-test-report
python -m pytest -q -m safe_smoke --no-test-report

# Full local suite (side effects possible)
python -m pytest

# Quick scripted subset
python tests/run_tests.py --quick
```

`--no-test-report` avoids writing reports under `tests/test_results/`
(gitignored).

## Related Documents

- Code conventions being tested: [coding.md](./coding.md)
- CI enforcement of these rules: [git.md](./git.md)
