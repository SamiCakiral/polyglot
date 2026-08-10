import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

FIXTURE = Path(__file__).resolve().parents[4] / "fixtures/canonical/FX-GYM-IT"
SCHEMA = Path(__file__).resolve().parents[4] / "contracts/fixtures/manifest.schema.json"


def test_fx_gym_it_manifest_is_canonical_and_payload_is_hash_locked() -> None:
    manifest = json.loads((FIXTURE / "manifest.json").read_text())
    metadata = json.loads((FIXTURE / "fixture-metadata.json").read_text())
    payload = (FIXTURE / "gym.json").read_bytes()

    Draft202012Validator(json.loads(SCHEMA.read_text())).validate(manifest)
    assert manifest == {
        "id": "FX-GYM-IT",
        "kind": "positive",
        "expected_status": "accepted",
    }
    assert metadata["schema_version"] == 1
    assert metadata["synthetic"] is True
    assert metadata["network_dependencies"] == []
    assert metadata["linguistic_review"] == "pending_human"
    assert metadata["payloads"] == {
        "gym.json": "sha256:" + hashlib.sha256(payload).hexdigest()
    }

