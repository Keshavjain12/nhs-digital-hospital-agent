"""Structured JSON logging with mandatory redaction.

Brief §17 forbids logging passwords, tokens and unnecessary clinical content. A convention
alone will not survive a deadline, so redaction is applied by the formatter itself: any log
record passing through this handler is scrubbed, whatever the calling code did.

The redaction is deliberately blunt. A false positive costs a debugging inconvenience; a
false negative puts patient data in a log aggregator.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Keys whose values are never written to a log, at any level.
# Mirrors FORBIDDEN_IN_AUDIT_METADATA in docs/security/rbac-and-audit.md §5.
REDACTED_KEYS: frozenset[str] = frozenset(
    {
        # Authentication
        "password",
        "password_hash",
        "new_password",
        "current_password",
        "token",
        "access_token",
        "refresh_token",
        "token_hash",
        "authorization",
        "api_key",
        "llm_api_key",
        "jwt_secret",
        "secret",
        # Direct identifiers
        "nhs_number",
        "nhsnumber",
        "date_of_birth",
        "dateofbirth",
        "email",
        "phone",
        "phone_e164",
        "postcode",
        "address_line1",
        "address_line2",
        # Clinical content
        "content",
        "generated_content",
        "revised_content",
        "symptoms",
        "diagnosis",
        "notes",
        "reason_text",
        "recommended_action",
        "given_name",
        "family_name",
    }
)

REDACTION_PLACEHOLDER = "[redacted]"
_MAX_DEPTH = 6

_STANDARD_RECORD_FIELDS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
        "asctime",
    }
)


def redact(value: Any, *, _depth: int = 0) -> Any:
    """Recursively replace the values of sensitive keys.

    Recursion is depth-limited so a cyclic or pathological structure cannot hang the
    logging path, which must never be able to take the application down.
    """
    if _depth > _MAX_DEPTH:
        return "[truncated]"

    if isinstance(value, dict):
        return {
            key: (
                REDACTION_PLACEHOLDER
                if str(key).lower() in REDACTED_KEYS
                else redact(item, _depth=_depth + 1)
            )
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [redact(item, _depth=_depth + 1) for item in value]

    return value


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per line, with every extra field redacted."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _STANDARD_RECORD_FIELDS and not key.startswith("_")
        }
        if extras:
            payload.update(redact(extras))

        if record.exc_info:
            # Kept server-side only; errors.py never forwards this to a client.
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Route uvicorn's own loggers through our formatter rather than its plain-text one.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(noisy)
        logger.handlers.clear()
        logger.propagate = True

    # RequestContextMiddleware already logs every request with a request id and duration,
    # and deliberately skips the health endpoints. Leaving uvicorn's access log enabled
    # would duplicate each entry with less detail and reinstate the health-check noise the
    # middleware exists to suppress - a container polled every 10s drowns out the rest.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
