import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures" / "canonical" / "FX-ASSESS"


def test_fx_assess_is_fingerprinted_and_covers_four_independent_protocols() -> None:
    metadata = json.loads((FIXTURE / "fixture-metadata.json").read_text())
    payload = (FIXTURE / "assessment.json").read_bytes()
    document = json.loads(payload)

    expected_fingerprint = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    assert metadata["payloads"]["assessment.json"] == expected_fingerprint
    assert set(document["protocols"]) == {"reading", "listening", "writing", "speaking"}
    assert document["protocols"]["speaking"]["without_qualified_review"] == "not_evaluable"
    assert document["form_selection"]["fallback"] is None
    assert {
        "double_submission_returns_same_result",
        "missing_audio_never_becomes_user_failure",
        "reading_evidence_only_credits_reading",
        "oral_self_assessment_never_produces_reliable_mastery",
    } <= set(document["normative_cases"])
    assert metadata["network_dependencies"] == []
