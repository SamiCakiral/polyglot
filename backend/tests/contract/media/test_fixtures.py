import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from polyglot.modules.media.domain import (
    MediaAsset,
    MediaKind,
    MediaRights,
    MediaStatus,
    UploadInspection,
)
from polyglot.modules.media.ports import DeterministicTtsPort, TtsAvailability, TtsRequest, TtsVoice
from polyglot.modules.media.shadowing import ShadowingAvailability, ShadowingPrompt

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures" / "canonical" / "FX-MEDIA" / "media.json"


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
