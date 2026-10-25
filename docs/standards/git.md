# Git Standards

**Question this document answers:** What are the rules for branches, commits, and pull requests?

Does not cover code or test quality itself — see [coding.md](./coding.md) and
[testing.md](./testing.md). This document covers process, not content.

## Branching Model

- Default branch: `main`
- Long-running dev branch: `V2_LG` (exists; the safe-smoke workflow covers it)
- Feature branches: `[prefix]/[short-description]`, e.g. `feat/vision-tools`
- Branch naming prefixes: `feat/`, `fix/`, `chore/`, `docs/`, `refactor/`

## Commit Messages

Format: Conventional Commits (history is mixed; new commits follow this).

```
<type>(<scope>): <short summary>

<optional body explaining why, not what>
```

- Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- Subject line: imperative mood, no trailing period, ≤ 72 characters

## Pull Requests

- One logical change per PR
- PR description must state: what changed, why, and how it was verified
- Required before merge:
  - [ ] Safe smoke workflow passing
  - [ ] No unresolved conversations
  - [ ] No secrets in the diff

## Merge Strategy

- Merge method: merge commit (current practice on `main`)
- Who can merge: the repo owner after review; agents never merge their own PRs without explicit approval

## Agent-Specific Notes

- Coding agents must not force-push to `main` or protected branches.
- Never commit `.env`, `token.json`, `src/credentials/`, `logs/`, `data/`, or `models/`.
- `*.bak` files are gitignored — do not commit backup copies.

## Related Documents

- What "passing CI" checks: [testing.md](./testing.md), [coding.md](./coding.md)
- Recording the reasoning behind a significant change: [../decisions/](../decisions/)
