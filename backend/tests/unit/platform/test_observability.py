import json
import logging

from polyglot.platform.observability import JsonLogFormatter


def test_json_log_formatter_emits_only_the_closed_operational_fields() -> None:
    record = logging.LogRecord(
        "polyglot.http",
        logging.INFO,
        __file__,
        10,
        "request_completed",
        (),
        None,
    )
    record.request_id = "request-1"
    record.correlation_id = "correlation-1"
    record.method = "GET"
    record.path = "/api/v1/health/ready"
    record.status_code = 200
    record.duration_ms = 4.2
    record.password = "must-not-leak"

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["event"] == "request_completed"
    assert payload["request_id"] == "request-1"
    assert payload["status_code"] == 200
    assert "password" not in payload
    assert "must-not-leak" not in json.dumps(payload)
