from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

_OPERATIONAL_FIELDS = (
    "request_id",
    "correlation_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "job_id",
    "error_code",
)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        for name in _OPERATIONAL_FIELDS:
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def configure_local_logging() -> None:
    logger = logging.getLogger("polyglot")
    if any(getattr(handler, "_polyglot_json", False) for handler in logger.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    handler._polyglot_json = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
