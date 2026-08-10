from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from polyglot.modules.media.domain import (
    MediaAsset,
    MediaKind,
    MediaRights,
    MediaStatus,
    QuarantineReason,
    UploadInspection,
)
from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
ASSET_ID = UUID("019fe015-0000-7000-8000-000000000001")
REVISION_ID = UUID("019fe015-0000-7000-8000-000000000002")
RIGHTS_ID = UUID("019fe015-0000-7000-8000-000000000003")
UPLOAD_ID = UUID("019fe015-0000-7000-8000-000000000004")
CHECKSUM = "b42889b8ad8c42faf5fcf7eaf1753381801a92cee18fa7e4297030e5fab93eb2"


def rights(*, expires_at: datetime | None = None) -> MediaRights:
    return MediaRights(
        rights_id=RIGHTS_ID,
        license_ref="rights:fixture:media",
        provenance_ref="FX-MEDIA/audio",
        expires_at=expires_at or NOW + timedelta(days=1),
    )


def reserved_asset(*, media_rights: MediaRights | None = None) -> MediaAsset:
    return MediaAsset.reserve_upload(
        asset_id=ASSET_ID,
        revision_id=REVISION_ID,
        upload_id=UPLOAD_ID,
        kind=MediaKind.AUDIO,
        declared_mime="audio/mpeg",
        expected_checksum_sha256=CHECKSUM,
        rights=media_rights or rights(),
        now=NOW,
    )


def safe_inspection() -> UploadInspection:
    return UploadInspection(
        detected_mime="audio/mpeg",
        size_bytes=1024,
        actual_checksum_sha256=CHECKSUM,
        archive_safe=True,
    )


def test_asset_moves_from_private_upload_to_ready_then_deleted() -> None:
    asset = reserved_asset()
    assert asset.status is MediaStatus.RESERVED
    assert "@" not in asset.upload.object_key
    assert "/" not in asset.upload.object_key.removeprefix("media/")

    asset = asset.begin_upload(at=NOW)
    asset = asset.complete_upload(at=NOW + timedelta(seconds=1))
    asset = asset.begin_verification()
    asset = asset.verify(safe_inspection(), at=NOW + timedelta(seconds=2))
    assert asset.status is MediaStatus.PROCESSING

    asset = asset.add_variant(
        variant_id=UUID("019fe015-0000-7000-8000-000000000005"),
        name="normalized",
        mime_type="audio/mpeg",
        checksum_sha256=CHECKSUM,
    )
    asset = asset.mark_ready(at=NOW + timedelta(seconds=3))
    assert asset.status is MediaStatus.READY

    asset = asset.request_deletion()
    asset = asset.remove_variant("normalized")
    asset = asset.complete_deletion(existing_object_keys=())
    assert asset.status is MediaStatus.DELETED


def test_deceptive_mime_and_checksum_failure_stay_quarantined() -> None:
    deceptive = (
        reserved_asset()
        .begin_upload(at=NOW)
        .complete_upload(at=NOW)
        .begin_verification()
        .verify(
            UploadInspection(
                detected_mime="application/x-msdownload",
                size_bytes=1024,
                actual_checksum_sha256=CHECKSUM,
                archive_safe=True,
            ),
            at=NOW,
        )
    )
    assert deceptive.status is MediaStatus.QUARANTINED
    assert deceptive.quarantine_reason is QuarantineReason.MIME_MISMATCH

    corrupted = (
        reserved_asset()
        .begin_upload(at=NOW)
        .complete_upload(at=NOW)
        .begin_verification()
        .verify(
            UploadInspection(
                detected_mime="audio/mpeg",
                size_bytes=1024,
                actual_checksum_sha256="0" * 64,
                archive_safe=True,
            ),
            at=NOW,
        )
    )
    assert corrupted.status is MediaStatus.QUARANTINED
    assert corrupted.quarantine_reason is QuarantineReason.CHECKSUM_MISMATCH


def test_hostile_or_oversized_upload_is_quarantined_before_processing() -> None:
    hostile = (
        MediaAsset.reserve_upload(
            asset_id=ASSET_ID,
            revision_id=REVISION_ID,
            upload_id=UPLOAD_ID,
            kind=MediaKind.ARCHIVE,
            declared_mime="application/zip",
            expected_checksum_sha256=CHECKSUM,
            rights=rights(),
            now=NOW,
        )
        .begin_upload(at=NOW)
        .complete_upload(at=NOW)
        .begin_verification()
        .verify(
            UploadInspection(
                detected_mime="application/zip",
                size_bytes=1024,
                actual_checksum_sha256=CHECKSUM,
                archive_safe=False,
            ),
            at=NOW,
        )
    )
    assert hostile.status is MediaStatus.QUARANTINED
    assert hostile.quarantine_reason is QuarantineReason.HOSTILE_ARCHIVE

    oversized = (
        reserved_asset()
        .begin_upload(at=NOW)
        .complete_upload(at=NOW)
        .begin_verification()
        .verify(
            UploadInspection(
                detected_mime="audio/mpeg",
                size_bytes=100 * 1024 * 1024 + 1,
                actual_checksum_sha256=CHECKSUM,
                archive_safe=True,
            ),
            at=NOW,
        )
    )
    assert oversized.status is MediaStatus.QUARANTINED
    assert oversized.quarantine_reason is QuarantineReason.SIZE_LIMIT


def test_expired_rights_cannot_enter_processing_and_orphans_block_deletion() -> None:
    expired = rights(expires_at=NOW - timedelta(seconds=1))
    asset = (
        reserved_asset(media_rights=expired)
        .begin_upload(at=NOW)
        .complete_upload(at=NOW)
        .begin_verification()
        .verify(safe_inspection(), at=NOW)
    )
    assert asset.status is MediaStatus.QUARANTINED
    assert asset.quarantine_reason is QuarantineReason.RIGHTS_EXPIRED

    deleting = reserved_asset().request_deletion()
    with pytest.raises(DomainError) as blocked:
        deleting.complete_deletion(existing_object_keys=(deleting.upload.object_key,))
    assert blocked.value.code is ErrorCode.MEDIA_STILL_REQUIRED


def test_illegal_transition_never_skips_verification() -> None:
    with pytest.raises(DomainError) as blocked:
        reserved_asset().mark_ready(at=NOW)
    assert blocked.value.code is ErrorCode.INVALID_TRANSITION
