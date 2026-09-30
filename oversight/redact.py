"""Keep secrets out of audit logs and queues.

The safety model still sees the full parameters (it has to, to judge them); only what
is written to disk is redacted.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[redacted]"

_SECRET_KEY = re.compile(r"(?i)(pass(word|wd)?|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|credential|authorization|cookie)")
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[redacted private key]"),
    (
        re.compile(r"(?i)([A-Za-z0-9_]*(?:api[_-]?key|secret|password|passwd|token|access[_-]?key)[A-Za-z0-9_]*)(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|\S+)"),
        r"\1\2" + REDACTED,
    ),
    (re.compile(r"\bsk[_-][A-Za-z0-9_-]{8,}"), REDACTED),  # sk_live_..., sk-ant-...
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTED),  # AWS access key id
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), REDACTED),  # GitHub tokens
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer " + REDACTED),
]


def redact_text(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


def redact(value: Any, key: str = "") -> Any:
    """Recursively redact secrets in params. Keys that name a secret lose their whole value."""
    if isinstance(value, dict):
        return {k: redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, key) for v in value]
    if isinstance(value, str):
        if key and _SECRET_KEY.search(key):
            return REDACTED
        return redact_text(value)
    return value
