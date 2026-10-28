"""
Trace redaction helpers — keep agent traces useful for debugging without
storing credentials.

The product promise (docs/product/vision.md) is that any failed query is
explainable from the JSONL trace, so traces stay ON but are REDACTED and
BOUNDED: sensitive dict fields collapse to [REDACTED], high-confidence
secret patterns are scrubbed inside plain strings, and long values are
truncated with an explicit marker. Pure stdlib, no I/O — callers decide
where to apply it (the agent trace writer is the choke point).
"""

import re

# Replacement marker used for every scrubbed value.
REDACTED = "[REDACTED]"

# Lowercase substrings identifying sensitive dict keys — a value stored
# under any key containing one of these is replaced entirely by [REDACTED],
# at any nesting depth.
SENSITIVE_KEY_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "api-key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "private_key",
    "passphrase",
)

# Common personal-data fields used by the mail and notification tools. These
# are redacted by field name even when the value itself is not credential-like.
SENSITIVE_EXACT_KEYS = {
    "to",
    "cc",
    "bcc",
    "body",
    "email_body",
    "recipient",
    "phone",
}

# High-confidence secret patterns for plain strings. Deliberately small —
# anything more aggressive starts mangling normal text:
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._\-]{8,}")
_SK_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}")
_OTHER_KEY_RE = re.compile(
    r"\b(?:gh[pous]_[A-Za-z0-9_\-]{20,}|github_pat_[A-Za-z0-9_\-]{20,}"
    r"|xox[baprs]-[A-Za-z0-9_\-]{10,}|AIza[A-Za-z0-9_\-]{20,}"
    r"|ya29\.[A-Za-z0-9_\-]{10,})\b"
)
# key=value / "key": "value" assignments whose key names a secret — the
# value is dropped, the key text is kept so the record stays explainable.
_SECRET_KV_RE = re.compile(
    r"(?i)(['\"]?[A-Za-z0-9_-]*(?:password|passwd|secret|passphrase"
    r"|token|api[_-]?key|apikey|authorization|credentials?|private[_-]?key|cookie)"
    r"[A-Za-z0-9_-]*['\"]?)"
    r"(\s*[=:]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;&)\]}]+)"
)
_PERSONAL_KV_RE = re.compile(
    r"(?i)(['\"]?(?:to|cc|bcc|body|email_body|recipient|phone)['\"]?)"
    r"(\s*[=:]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;&)\]}]+)"
)

# Length caps (chars) applied by the agent trace writer, per field.
MAX_QUERY_LEN = 2000
MAX_ARG_LEN = 1000
MAX_RESULT_LEN = 2000
MAX_RESPONSE_LEN = 2000


def redact_string(value: str, max_len: int) -> str:
    """Scrub secret-looking substrings, then truncate long strings.

    Truncation keeps the head and appends an explicit marker so a reader
    can tell the value was shortened, not silently cut.
    """
    text = _BEARER_RE.sub(REDACTED, value)
    text = _SK_KEY_RE.sub(REDACTED, text)
    text = _OTHER_KEY_RE.sub(REDACTED, text)
    text = _SECRET_KV_RE.sub(r"\1\2" + REDACTED, text)
    text = _PERSONAL_KV_RE.sub(r"\1\2" + REDACTED, text)
    if len(text) > max_len:
        dropped = len(text) - max_len
        return f"{text[:max_len]}…[truncated {dropped} chars]"
    return text


def redact_value(obj, max_len: int):
    """Recursively redact and bound a value for trace/log output.

    dict: values whose key contains a sensitive marker become [REDACTED];
    other values are recursed. list/tuple: recursed. str: scrubbed and
    bounded via redact_string. Anything else (int, float, bool, None) is
    diagnostic and preserved as-is.
    """
    if isinstance(obj, dict):
        out = {}
        for key, val in obj.items():
            if isinstance(key, str) and (
                key.lower() in SENSITIVE_EXACT_KEYS
                or any(marker in key.lower() for marker in SENSITIVE_KEY_MARKERS)
            ):
                out[key] = REDACTED
            else:
                out[key] = redact_value(val, max_len)
        return out
    if isinstance(obj, (list, tuple)):
        items = [redact_value(item, max_len) for item in obj]
        return tuple(items) if isinstance(obj, tuple) else items
    if isinstance(obj, str):
        return redact_string(obj, max_len)
    return obj
