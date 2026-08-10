from __future__ import annotations

import json
import time

from polyglot.modules.lexicon.exchange.parsing import ParseLimits, parse_import


def _payload() -> bytes:
    entries = [
        {
            "source_key": f"fx-{index}",
            "variety_id": "019bfcc0-7cf1-7000-8000-000000000001",
            "form": f"parola-{index}",
        }
        for index in range(100_000)
    ]
    return json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": entries,
        },
        separators=(",", ":"),
    ).encode()


def test_parse_100k_rows_within_local_release_budget() -> None:
    payload = _payload()
    started = time.perf_counter()
    parsed = parse_import(
        payload,
        "polyglot.lexicon.bundle/v1",
        "utf-8",
        ParseLimits(),
    )
    elapsed = time.perf_counter() - started

    assert len(payload) <= ParseLimits().max_bytes
    assert len(parsed.rows) == 100_000
    assert elapsed < 8.0
