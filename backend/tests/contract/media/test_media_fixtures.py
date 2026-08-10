import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator

from polyglot.modules.media.domain import (
    MediaAsset,
    MediaKind,
    MediaRights,
    MediaStatus,
    QuarantineReason,
    UploadInspection,
)
from polyglot.modules.media.ports import DeterministicTtsPort, TtsAvailability, TtsRequest, TtsVoice
from polyglot.modules.media.shadowing import ShadowingAvailability, ShadowingPrompt

ROOT = Path(__file__).resolve().parents[4]
FIXTURE_ROOT = ROOT / "fixtures" / "canonical" / "FX-MEDIA"
FIXTURE = FIXTURE_ROOT / "media.json"
MANIFEST_SCHEMA = json.loads((ROOT / "contracts/fixtures/manifest.schema.json").read_text())


def test_fx_media_manifest_uses_the_w00_contract() -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text())

    Draft202012Validator(MANIFEST_SCHEMA).validate(manifest)
    assert manifest == {
        "id": "FX-MEDIA",
        "kind": "positive",
        "expected_status": "accepted",
    }


def test_fx_media_metadata_pins_reproducibility_and_executable_oracles() -> None:
    metadata = json.loads((FIXTURE_ROOT / "fixture-metadata.json").read_text())

    assert metadata == {
        "schema_version": 1,
        "synthetic": True,
        "seed": 5015,
        "clock": "2026-08-10T12:00:00+00:00",
        "payloads": {
            "media.json": f"sha256:{hashlib.sha256(FIXTURE.read_bytes()).hexdigest()}"
        },
        "oracles": [
            "fixed_audio_checksum_matches",
            "retired_voice_has_no_fallback",
            "missing_audio_uses_transcript_alternative",
            "deceptive_mime_quarantined",
            "hostile_archive_quarantined",
            "expired_rights_quarantined",
            "false_checksum_quarantined",
        ],
        "network_dependencies": [],
    }


@pytest.mark.parametrize(
    ("case_name", "kind", "expected_reason"),
    (
        ("hostile_archive", MediaKind.ARCHIVE, QuarantineReason.HOSTILE_ARCHIVE),
        ("rights_expired", MediaKind.AUDIO, QuarantineReason.RIGHTS_EXPIRED),
    ),
)
def test_fx_media_executes_hostile_archive_and_expired_rights_oracles(
    case_name: str,
    kind: MediaKind,
    expected_reason: QuarantineReason,
) -> None:
    payload = json.loads(FIXTURE.read_text())
    metadata = json.loads((FIXTURE_ROOT / "fixture-metadata.json").read_text())
    audio = payload["audio"]
    case = payload[case_name]
    rights = case if case_name == "rights_expired" else audio["rights"]

    assert case.get("expected_status") == "quarantined"
    assert case.get("expected_reason") == expected_reason.value

    clock = datetime.fromisoformat(metadata["clock"])
    asset = MediaAsset.reserve_upload(
        asset_id=UUID(audio["asset_id"]),
        revision_id=UUID(audio["revision_id"]),
        upload_id=UUID("019fe015-0000-7000-8000-000000000004"),
        kind=kind,
        declared_mime=case.get("declared_mime", audio["declared_mime"]),
        expected_checksum_sha256=audio["checksum_sha256"],
        rights=MediaRights(
            rights_id=UUID(audio["rights_id"]),
            license_ref=rights["license_ref"],
            provenance_ref=rights["provenance_ref"],
            expires_at=datetime.fromisoformat(rights["expires_at"]),
        ),
        now=clock,
    )
    result = (
        asset.begin_upload(at=clock)
        .complete_upload(at=clock)
        .begin_verification()
        .verify(
            UploadInspection(
                detected_mime=case.get("detected_mime", audio["detected_mime"]),
                size_bytes=1,
                actual_checksum_sha256=audio["checksum_sha256"],
                archive_safe=case.get("archive_safe", True),
            ),
            at=clock,
        )
    )

    assert result.status.value == case["expected_status"]
    assert result.quarantine_reason is expected_reason


def test_fx_media_is_local_complete_and_exercises_explicit_degradation() -> None:
    payload = json.loads(FIXTURE.read_text())
    audio = payload["audio"]
    audio_bytes = base64.b64decode(audio["audio_base64"])
    assert hashlib.sha256(audio_bytes).hexdigest() == audio["checksum_sha256"]
    assert payload["voice_removed"]["availability"] == "retired"
    assert payload["media_absent"]["expected_shadowing_state"] == "alternative_available"

    absent = ShadowingPrompt.from_fixture(
        audio=None,
        transcript=payload["media_absent"]["transcript"],
    )
    assert absent.availability is ShadowingAvailability.ALTERNATIVE_AVAILABLE

    port = DeterministicTtsPort(
        voices=(TtsVoice("bruno-it", "it-IT", TtsAvailability.AVAILABLE, "fixture-v1"),)
    )
    retired = port.synthesize(TtsRequest("Ciao", "it-IT", payload["voice_removed"]["voice_id"], {}))
    assert retired.availability is TtsAvailability.RETIRED
    assert retired.voice_id == "alice-it"


def test_fx_media_rejects_deceptive_mime_and_false_checksum() -> None:
    payload = json.loads(FIXTURE.read_text())
    audio = payload["audio"]
    asset = MediaAsset.reserve_upload(
        asset_id=UUID(audio["asset_id"]),
        revision_id=UUID(audio["revision_id"]),
        upload_id=UUID("019fe015-0000-7000-8000-000000000004"),
        kind=MediaKind.AUDIO,
        declared_mime=audio["declared_mime"],
        expected_checksum_sha256=audio["checksum_sha256"],
        rights=MediaRights(
            rights_id=UUID(audio["rights_id"]),
            license_ref=audio["rights"]["license_ref"],
            provenance_ref=audio["rights"]["provenance_ref"],
            expires_at=datetime.fromisoformat(audio["rights"]["expires_at"]),
        ),
        now=datetime.fromisoformat("2026-08-10T12:00:00+00:00"),
    )
    deceptive = (
        asset.begin_upload(at=asset.created_at)
        .complete_upload(at=asset.created_at)
        .begin_verification()
        .verify(
            UploadInspection(
                detected_mime=payload["mime_deceptive"]["detected_mime"],
                size_bytes=1,
                actual_checksum_sha256=audio["checksum_sha256"],
                archive_safe=True,
            ),
            at=asset.created_at,
        )
    )
    assert deceptive.status is MediaStatus.QUARANTINED

    corrupted = (
        asset.begin_upload(at=asset.created_at)
        .complete_upload(at=asset.created_at)
        .begin_verification()
        .verify(
            UploadInspection(
                detected_mime=audio["detected_mime"],
                size_bytes=1,
                actual_checksum_sha256=payload["checksum_false"]["actual_checksum_sha256"],
                archive_safe=True,
            ),
            at=asset.created_at,
        )
    )
    assert corrupted.status is MediaStatus.QUARANTINED
