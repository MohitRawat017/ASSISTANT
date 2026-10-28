# 0002: External Provider Reliability Contract

**Status:** Accepted
**Date:** 2026-10-27

## Context

Provider calls can fail before dispatch, during transport, or after a provider
has accepted a side effect. Legacy wrapped tools only exposed `success` and
an error string, so callers could not distinguish a safe retry from an
ambiguous outcome. LangGraph tool invocation itself may contain side effects
and must not be replayed by a provider retry policy.

## Decision

Provider-facing operations return a dict-compatible `ToolResult` envelope with
`ok`, stable `code`, `retryable`, `unknown_outcome`, `hint`, `operation_id`,
`provider`, and `attempts`. `success` and `error` remain populated for legacy
wrapped tools.

Only safe reads retry classified transient failures, using an injected sleeper
and a bounded attempt count. Writes execute once with provider retries disabled.
A timeout, transport failure, or 5xx after dispatch returns
`unknown_outcome=true` and `retryable=false`; callers must inspect provider
state before trying again. Provider errors are sanitized and truncated.

Timeouts are configured at Ollama, vision, and Google request boundaries.
The LangGraph invocation and provider selection are not automatically retried
or switched after failure.

## Consequences

Callers can give honest recovery guidance and preserve exactly-once behavior
for side effects. Read operations may incur bounded backoff delays. An
ambiguous write requires provider-state reconciliation by the user or a later
workflow; the system intentionally does not guess or resend it.

## Alternatives Considered

- Retrying the entire LangGraph run: rejected because a prior tool call may
  already have changed the desktop or a provider.
- Treating every timeout as a safe retry: rejected because a write may have
  completed even when its response was lost.
- Replacing legacy result dictionaries: rejected to preserve existing wrapped
  tools and agent compatibility.
