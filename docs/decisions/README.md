# Decisions

**Question this document answers:** Where is the reasoning behind significant past decisions recorded?

This folder holds Architecture Decision Records (ADRs) — the **why** behind
choices that would otherwise get re-litigated or silently reversed. It does
not hold current state (see `../architecture/`) or current rules (see
`../standards/`); it holds the history of *why* those became what they are.

## When to Add a Record

Add an ADR when a decision is:

- Hard or costly to reverse
- Likely to be questioned again later ("why don't we just use X?")
- A deviation from a default/common approach

Do not add an ADR for routine, easily reversible choices.

## File Naming

```
NNNN-short-title.md
```

Example: `0001-use-postgres-over-mongodb.md`. Numbers are sequential and never reused.

## Required Format

```markdown
# NNNN: Title

**Status:** Proposed | Accepted | Superseded by NNNN
**Date:** YYYY-MM-DD

## Context
What problem or question forced this decision?

## Decision
What was decided, stated plainly.

## Consequences
What becomes easier, harder, or is now constrained as a result.

## Alternatives Considered
What else was evaluated, and why it wasn't chosen.
```

## Updating a Decision

Never edit or delete an old ADR to reflect a new choice. Instead, create a
new ADR and mark the old one's status as `Superseded by NNNN`. History must
stay intact.

## Related Documents

- Current architecture resulting from these decisions: [../architecture/overview.md](../architecture/overview.md)
- Current standards resulting from these decisions: [../standards/](../standards/)
