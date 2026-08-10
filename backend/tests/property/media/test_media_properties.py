from datetime import UTC, datetime, timedelta
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.media.domain import (
    MediaAsset,
    MediaKind,
    MediaRights,
    MediaStatus,
    QuarantineReason,
    UploadInspection,
)

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
CHECKSUM = "b42889b8ad8c42faf5fcf7eaf1753381801a92cee18fa7e4297030e5fab93eb2"


def asset() -> MediaAsset:
    return MediaAsset.reserve_upload(
        asset_id=UUID("019fe015-0000-7000-8000-000000000001"),
        revision_id=UUID("019fe015-0000-7000-8000-000000000002"),
        upload_id=UUID("019fe015-0000-7000-8000-000000000004"),
        kind=MediaKind.AUDIO,
        declared_mime="audio/mpeg",
        expected_checksum_sha256=CHECKSUM,
        rights=MediaRights(
            rights_id=UUID("019fe015-0000-7000-8000-000000000003"),
            license_ref="rights:fixture:media",
            provenance_ref="FX-MEDIA/audio",
            expires_at=NOW + timedelta(days=1),
        ),
        now=NOW,
    )


@given(actual=st.text(alphabet="0123456789abcdef", min_size=64, max_size=64).filter(lambda v: v != CHECKSUM))
def test_nonmatching_checksum_can_never_reach_processing(actual: str) -> None:
    inspected = (
        asset()
        .begin_upload(at=NOW)
        .complete_upload(at=NOW)
        .begin_verification()
        .verify(
            UploadInspection(
                detected_mime="audio/mpeg",
                size_bytes=1,
                actual_checksum_sha256=actual,
                archive_safe=True,
            ),
            at=NOW,
        )
    )

    assert inspected.status is MediaStatus.QUARANTINED
    assert inspected.quarantine_reason is QuarantineReason.CHECKSUM_MISMATCH
