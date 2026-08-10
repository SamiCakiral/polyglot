from __future__ import annotations

import hashlib
import json
from pathlib import Path

from polyglot.modules.lexicon.exchange.parsing import ParseLimits, parse_import

FIXTURE = Path(__file__).parents[4] / "fixtures" / "canonical" / "FX-IMPORTS"


def test_fx_imports_is_complete_checksum_locked_and_offline() -> None:
    manifest = json.loads((FIXTURE / "manifest.json").read_text())
    metadata = json.loads((FIXTURE / "fixture-metadata.json").read_text())
    cases = json.loads((FIXTURE / "imports.json").read_text())

    assert manifest == {
        "id": "FX-IMPORTS",
        "kind": "positive",
        "expected_status": "accepted",
    }
    assert metadata["network_dependencies"] == []
    assert set(metadata["oracles"]) == {
        "valid_json",
        "valid_csv",
        "partial_selection",
        "interactive_conflict",
        "stale_preview",
        "hostile_zip",
        "homonym_distinct",
        "mwe_preserved",
        "revert_reused_blocked",
        "synthetic_volume",
    }
    digest = hashlib.sha256((FIXTURE / "imports.json").read_bytes()).hexdigest()
    assert metadata["payloads"]["imports.json"] == f"sha256:{digest}"
    assert cases["schema_version"] == 1


def test_fx_imports_positive_payloads_execute_with_bounded_parser() -> None:
    cases = json.loads((FIXTURE / "imports.json").read_text())
    valid_json = json.dumps(cases["valid_json"]["payload"]).encode()
    valid_csv = cases["valid_csv"]["payload"].encode()

    parsed_json = parse_import(
        valid_json,
        cases["valid_json"]["format_id"],
        "utf-8",
        ParseLimits(max_rows=100),
    )
    parsed_csv = parse_import(
        valid_csv,
        cases["valid_csv"]["format_id"],
        "utf-8",
        ParseLimits(max_rows=100),
    )

    assert tuple(row.normalized_form for row in parsed_json.rows) == (
        "andare via",
        "piano",
    )
    assert len(parsed_csv.rows) == 2
    assert cases["synthetic_volume"]["max_rows"] == 10_000


def test_fx_imports_executes_the_declared_synthetic_volume() -> None:
    entries = [
        {
            "source_key": f"fx-{index}",
            "variety_id": "019bfcc0-7cf1-7000-8000-000000000001",
            "form": f"parola-{index}",
        }
        for index in range(10_000)
    ]
    payload = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": entries,
        }
    ).encode()

    parsed = parse_import(
        payload,
        "polyglot.lexicon.bundle/v1",
        "utf-8",
        ParseLimits(max_rows=10_000),
    )

    assert len(parsed.rows) == 10_000
    assert parsed.rows[-1].source_key == "fx-9999"
