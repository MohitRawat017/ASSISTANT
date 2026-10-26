"""Small, provider-neutral reliability primitives.

The envelope deliberately remains a dict so existing wrapped tools can keep
using ``result["success"]`` and ``result["error"]`` while newer callers can
use the stable fields (``code``, ``retryable`` and ``unknown_outcome``).
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from typing import Any, Callable

from src.utils.redaction import redact_string


MAX_PROVIDER_ERROR = 240
_TRANSIENT_CODES = {408, 425, 429}


def stable_operation_id(provider: str, operation: str, key: str | None = None) -> str:
    """Return one stable ID for a logical operation.

    A caller that has a natural idempotency key gets a repeatable UUID5.  When
    no key exists, UUID4 is generated once by the caller and reused for all
    attempts by :func:`execute_with_retry`.
    """
    if key is None:
        return uuid.uuid4().hex
    material = f"tsuzi:{provider}:{operation}:{key}".encode("utf-8")
    return str(uuid.UUID(bytes=hashlib.sha256(material).digest()[:16]))


def _error_text(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, str) and reason.strip():
        text = reason
    else:
        text = str(exc) or exc.__class__.__name__
    # Provider errors may contain request URLs, headers, or response blobs.
    text = redact_string(text, MAX_PROVIDER_ERROR)
    text = re.sub(
        r"(?i)(authorization|api[-_ ]?key|token|password|secret|cookie)"
        r"\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^,;\s]+)",
        r"\1=[REDACTED]",
        text,
    )
    text = re.sub(r"https?://\S+", "[provider-url]", text)
    text = " ".join(text.split())
    return text[:MAX_PROVIDER_ERROR]


def _status(exc: BaseException) -> int | None:
    response = getattr(exc, "resp", None)
    value = getattr(response, "status", None)
    if value is None:
        value = getattr(exc, "status_code", None)
    if value is None:
        value = getattr(exc, "status", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def classify_exception(exc: BaseException, *, dispatched: bool = False) -> dict[str, Any]:
    """Classify an exception without exposing its provider-specific payload."""
    status = _status(exc)
    name = exc.__class__.__name__.lower()
    timeout = isinstance(exc, (TimeoutError,)) or "timeout" in name
    transport = isinstance(exc, (ConnectionError, OSError)) or "transport" in name
    server = status is not None and status >= 500
    transient = timeout or transport or status in _TRANSIENT_CODES or server

    if isinstance(exc, ValueError):
        return {
            "code": "invalid_input",
            "retryable": False,
            "unknown_outcome": False,
            "hint": "Check the request values and try again.",
        }
    if dispatched and transient:
        return {
            "code": "unknown_outcome",
            "retryable": False,
            "unknown_outcome": True,
            "hint": "The provider may have accepted the request; check its current state before retrying.",
        }
    if timeout:
        return {"code": "timeout", "retryable": True, "unknown_outcome": False, "hint": "Try again later."}
    if transport:
        return {"code": "transport_error", "retryable": True, "unknown_outcome": False, "hint": "The provider could not be reached; try again later."}
    if status in _TRANSIENT_CODES or server:
        return {"code": "provider_transient", "retryable": True, "unknown_outcome": False, "hint": "The provider is temporarily unavailable; try again later."}
    if status in (401, 403):
        return {"code": "auth_required", "retryable": False, "unknown_outcome": False, "hint": "Reconnect or re-authorize the provider."}
    if status == 404:
        return {"code": "not_found", "retryable": False, "unknown_outcome": False, "hint": "Check the requested provider resource."}
    return {"code": "provider_error", "retryable": False, "unknown_outcome": False, "hint": "Check the provider request and try again."}


class ToolResult(dict):
    """Canonical result envelope with legacy ``success``/``error`` fields."""

    def __init__(
        self,
        ok: bool,
        *,
        code: str = "ok",
        retryable: bool = False,
        unknown_outcome: bool = False,
        hint: str = "",
        operation_id: str | None = None,
        provider: str = "local",
        attempts: int = 1,
        error: str | None = None,
        **fields: Any,
    ) -> None:
        if not operation_id:
            operation_id = stable_operation_id(provider, code)
        if attempts < 1:
            raise ValueError("attempts must be at least one")
        if ok and (retryable or unknown_outcome):
            raise ValueError("successful results cannot be retryable or unknown")
        if unknown_outcome and retryable:
            raise ValueError("unknown outcomes are never retryable")
        if ok and code != "ok":
            raise ValueError("successful results must use code='ok'")
        if not ok and code == "ok":
            raise ValueError("failed results need a stable non-ok code")
        super().__init__(
            ok=bool(ok),
            code=code,
            retryable=bool(retryable),
            unknown_outcome=bool(unknown_outcome),
            hint=hint,
            operation_id=str(operation_id),
            provider=provider,
            attempts=int(attempts),
            # Compatibility for all existing wrapped tools.
            success=bool(ok),
            error=error if error is not None else (None if ok else hint),
            **fields,
        )

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def with_fields(self, **fields: Any) -> "ToolResult":
        result = ToolResult(**{k: self[k] for k in _ENVELOPE_KEYS}, error=self.get("error"), **fields)
        result.update({k: v for k, v in self.items() if k not in _ENVELOPE_KEYS and k not in {"success", "error"}})
        return result


_ENVELOPE_KEYS = {
    "ok", "code", "retryable", "unknown_outcome", "hint", "operation_id",
    "provider", "attempts",
}


def success_result(*, provider: str, operation_id: str, attempts: int = 1, **fields: Any) -> ToolResult:
    return ToolResult(True, operation_id=operation_id, provider=provider, attempts=attempts, **fields)


def failure_result(
    exc: BaseException | None = None,
    *,
    provider: str,
    operation_id: str,
    attempts: int = 1,
    dispatched: bool = False,
    code: str | None = None,
    hint: str | None = None,
    **fields: Any,
) -> ToolResult:
    classification = classify_exception(exc or RuntimeError("operation failed"), dispatched=dispatched)
    return ToolResult(
        False,
        code=code or classification["code"],
        retryable=classification["retryable"],
        unknown_outcome=classification["unknown_outcome"],
        hint=hint or classification["hint"],
        operation_id=operation_id,
        provider=provider,
        attempts=attempts,
        error=_error_text(exc) if exc else (hint or classification["hint"]),
        **fields,
    )


def execute_with_retry(
    operation: Callable[[], Any],
    *,
    provider: str,
    operation_id: str | None = None,
    max_retries: int = 0,
    safe_to_retry: bool = False,
    sleeper: Callable[[float], None] = time.sleep,
    backoff_base: float = 0.25,
) -> ToolResult:
    """Execute a bounded safe operation; never retry side effects.

    ``operation`` is invoked at most ``max_retries + 1`` times.  An operation
    should set ``safe_to_retry`` only for reads, or for work proven not to have
    reached a provider. A callback may return a ToolResult to preserve a
    provider response envelope.
    """
    op_id = operation_id or stable_operation_id(provider, "operation")
    retries = max(0, int(max_retries)) if safe_to_retry else 0
    attempts = 0
    while True:
        attempts += 1
        try:
            value = operation()
            if isinstance(value, ToolResult):
                if (
                    not value.ok
                    and value.retryable
                    and attempts <= retries
                ):
                    sleeper(backoff_base * (2 ** (attempts - 1)))
                    continue
                value["operation_id"] = op_id
                value["attempts"] = attempts
                return value
            return success_result(provider=provider, operation_id=op_id, attempts=attempts, value=value)
        except Exception as exc:  # provider boundary: classify, sanitize, bound
            classification = classify_exception(exc)
            if attempts <= retries and classification["retryable"]:
                sleeper(backoff_base * (2 ** (attempts - 1)))
                continue
            return failure_result(
                exc,
                provider=provider,
                operation_id=op_id,
                attempts=attempts,
                dispatched=not safe_to_retry,
            )


def execute_google_read(
    request_factory: Callable[[], Any],
    *,
    operation_id: str | None = None,
    max_retries: int = 0,
    sleeper: Callable[[float], None] = time.sleep,
) -> ToolResult:
    """Execute one Google read request per attempt with ``num_retries=0``."""
    return execute_with_retry(
        lambda: request_factory().execute(num_retries=0),
        provider="google",
        operation_id=operation_id,
        max_retries=max_retries,
        safe_to_retry=True,
        sleeper=sleeper,
    )


def execute_google_write(
    request_factory: Callable[[], Any],
    *,
    provider: str,
    operation_id: str | None = None,
) -> ToolResult:
    """Execute a Google side effect exactly once.

    Once ``execute`` is entered, a timeout/transport/5xx is ambiguous and is
    intentionally returned as non-retryable ``unknown_outcome``.
    """
    op_id = operation_id or stable_operation_id(provider, "write")
    try:
        request = request_factory()
    except Exception as exc:
        # Request construction is before dispatch, so a transient failure here
        # is a definite failure (and can be retried by an explicit caller).
        return failure_result(exc, provider=provider, operation_id=op_id, dispatched=False)
    try:
        value = request.execute(num_retries=0)
        return success_result(provider=provider, operation_id=op_id, attempts=1, value=value)
    except Exception as exc:
        return failure_result(exc, provider=provider, operation_id=op_id, dispatched=True)


__all__ = [
    "ToolResult", "classify_exception", "execute_google_read",
    "execute_google_write", "execute_with_retry", "failure_result",
    "stable_operation_id", "success_result", "ResultEnvelope", "Result",
    "retry_call",
]

# Descriptive aliases used by integrations that call this a result envelope.
ResultEnvelope = ToolResult
Result = ToolResult
retry_call = execute_with_retry
