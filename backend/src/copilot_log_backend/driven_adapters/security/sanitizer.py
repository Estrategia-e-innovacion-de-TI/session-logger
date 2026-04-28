from __future__ import annotations

import re
from typing import Any, Mapping

PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"
)

STRING_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "[REDACTED:GITHUB_TOKEN]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), "[REDACTED:GITHUB_TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED:AWS_ACCESS_KEY_ID]"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "[REDACTED:AWS_ACCESS_KEY_ID]"),
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}\b"), "[REDACTED:OPENAI_KEY]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{10,}\b"), "[REDACTED:ANTHROPIC_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "[REDACTED:JWT]"),
    (re.compile(r"(?i)(password\s*[:=]\s*)([^\s,;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(secret\s*[:=]\s*)([^\s,;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)([^\s,;]+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(bearer\s+)([A-Za-z0-9\-._~+/]+=*)"), r"\1[REDACTED]"),
]

SENSITIVE_KEY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"token",
        r"password",
        r"passwd",
        r"pwd",
        r"secret",
        r"api[_-]?key",
        r"access[_-]?key",
        r"authorization",
        r"credential",
        r"private[_-]?key",
        r"openai[_-]?key",
        r"anthropic[_-]?key",
        r"github[_-]?token",
        r"aws[_-]?(?:secret[_-]?access[_-]?key|access[_-]?key)",
    )
]


class RegexSanitizer:
    def sanitize(self, value: Any, key: str | None = None) -> Any:
        if value is None:
            return None
        if self._is_sensitive_key(key):
            return "[REDACTED]"
        if isinstance(value, str):
            return self._sanitize_string(value, key=key)
        if isinstance(value, Mapping):
            return {
                str(child_key): self.sanitize(child_value, key=str(child_key))
                for child_key, child_value in value.items()
            }
        if isinstance(value, list):
            return [self.sanitize(item, key=key) for item in value]
        if isinstance(value, tuple):
            return [self.sanitize(item, key=key) for item in value]
        return value

    def _is_sensitive_key(self, key: str | None) -> bool:
        if not key:
            return False
        return any(pattern.search(key) for pattern in SENSITIVE_KEY_PATTERNS)

    def _sanitize_string(self, value: str, key: str | None = None) -> str:
        if self._is_sensitive_key(key):
            return "[REDACTED]"

        sanitized = value
        if PRIVATE_KEY_PATTERN.search(sanitized):
            sanitized = PRIVATE_KEY_PATTERN.sub("[REDACTED:PRIVATE_KEY]", sanitized)

        for pattern, replacement in STRING_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)

        return sanitized
