import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from polyglot.modules.lexicon.memory.fixtures import load_and_run_memory_fixture

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures/canonical/FX-MEMORY"
MANIFEST_SCHEMA = json.loads((ROOT / "contracts/fixtures/manifest.schema.json").read_text())


def test_fx_memory_manifest_and_metadata_are_reproducible_offline() -> None:
    manifest = json.loads((FIXTURE / "manifest.json").read_text())
    metadata = json.loads((FIXTURE / "fixture-metadata.json").read_text())
    payload = FIXTURE / "memory.json"

    Draft202012Validator(MANIFEST_SCHEMA).validate(manifest)
    assert manifest == {
        "id": "FX-MEMORY",
        "kind": "positive",
        "expected_status": "accepted",
    }
    assert metadata["network_dependencies"] == []
    assert metadata["clock"] == "2026-01-05T09:00:00+00:00"
    assert metadata["payloads"]["memory.json"] == (
        f"sha256:{hashlib.sha256(payload.read_bytes()).hexdigest()}"
    )


def test_fx_memory_executes_frozen_history_and_replay_oracles() -> None:
    report = load_and_run_memory_fixture(FIXTURE)

    assert report.history_count == 4
    assert report.replay_count == 100
    assert report.final_due_at.isoformat() == "2026-01-19T09:00:00+00:00"
    assert report.directions_independent is True
    assert report.non_evaluable_suppressed is True


def test_fx_memory_names_the_full_w07_risk_surface() -> None:
    payload = json.loads((FIXTURE / "memory.json").read_text())
    assert set(payload["cases"]) >= {
        "new",
        "learning",
        "review",
        "relearning",
        "early_review",
        "late_review",
        "duplicate_review",
        "suspended",
        "reset_preserves_history",
        "compatible_merge",
        "incompatible_merge",
        "imported_sm2_provenance_only",
        "timezone_change_no_retroactive_shift",
        "answer_revealed_no_review",
        "uncertified_operation_no_review",
    }
