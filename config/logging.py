import logging
import re
from collections.abc import Mapping
from typing import Any

SENSITIVE_KEYS = re.compile(
    r"(authorization|cookie|password|secret|token|api[-_]?key|client[-_]?secret)",
    re.IGNORECASE,
)
SENSITIVE_ASSIGNMENTS = re.compile(
    r"(?i)\b(authorization|password|secret|token|api[-_]?key|client[-_]?secret)"
    r"\b(\s*[:=]\s*)([^\s,;]+)"
)


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]" if SENSITIVE_KEYS.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return SENSITIVE_ASSIGNMENTS.sub(r"\1\2[REDACTED]", value)
    return value


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.msg)
        if record.args:
            record.args = redact(record.args)
        return True


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True

