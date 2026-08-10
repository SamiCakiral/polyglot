from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures" / "canonical" / "FX-EVIDENCE"


def test_fx_evidence_is_fingerprinted_and_covers_normative_replay_cases() -> None:
    metadata = json.loads((FIXTURE / "fixture-metadata.json").read_text())
    payload = (FIXTURE / "evidence.json").read_bytes()
    document = json.loads(payload)

    assert metadata["payloads"]["evidence.json"] == f"sha256:{hashlib.sha256(payload).hexdigest()}"
    assert {case["case"] for case in document["golden_cases"]} == {
        "single_success",
        "three_immediate_successes",
        "delayed_transfer",
    }
    assert {
        "duplicate_delivery_is_idempotent",
        "replacement_invalidates_without_deletion",
        "reading_never_credits_listening",
        "rebuild_fingerprint_matches_incremental",
    } <= set(document["replay_oracles"])
    assert metadata["network_dependencies"] == []
