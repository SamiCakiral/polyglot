from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from string import hexdigits
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode


class MediaStatus(StrEnum):
    RESERVED = "reserved"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    VERIFYING = "verifying"
    QUARANTINED = "quarantined"
    PROCESSING = "processing"
    READY = "ready"
    REJECTED = "rejected"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"


class MediaKind(StrEnum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    ARCHIVE = "archive"


class QuarantineReason(StrEnum):
    MIME_MISMATCH = "mime_mismatch"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    HOSTILE_ARCHIVE = "hostile_archive"
    RIGHTS_EXPIRED = "rights_expired"
    SIZE_LIMIT = "size_limit"


_LIMITS_BY_KIND = {
    MediaKind.IMAGE: 10 * 1024 * 1024,
    MediaKind.AUDIO: 100 * 1024 * 1024,
    MediaKind.VIDEO: 500 * 1024 * 1024,
    MediaKind.ARCHIVE: 50 * 1024 * 1024,
}
_MIMES_BY_KIND = {
    MediaKind.IMAGE: frozenset({"image/jpeg", "image/png", "image/webp"}),
    MediaKind.AUDIO: frozenset({"audio/mpeg", "audio/wav", "audio/ogg"}),
    MediaKind.VIDEO: frozenset({"video/mp4", "video/webm"}),
    MediaKind.ARCHIVE: frozenset({"application/zip"}),
}


def _invalid(field: str) -> DomainError:
    return DomainError(
        ErrorCode.VALIDATION_FAILED,
        field_errors=[{"location": field, "code": "invalid"}],
    )


def _require_uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise _invalid(field)


def _require_checksum(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in hexdigits for character in value):
        raise _invalid(field)


def _opaque_object_key(*, asset_id: UUID, revision_id: UUID, upload_id: UUID) -> str:
    return f"media/{asset_id.hex}-{revision_id.hex}-{upload_id.hex}"


@dataclass(frozen=True, slots=True)
class MediaRights:
    rights_id: UUID
    license_ref: str
    provenance_ref: str
    expires_at: datetime | None

    def __post_init__(self) -> None:
        _require_uuid7(self.rights_id, "rights_id")
        if not self.license_ref or not self.provenance_ref:
            raise _invalid("rights")

    def is_active_at(self, at: datetime) -> bool:
        return self.expires_at is None or at < self.expires_at


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    start_ms: int
    end_ms: int
    text: str

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms <= self.start_ms or not self.text:
            raise _invalid("transcript_segment")


@dataclass(frozen=True, slots=True)
class MediaRevision:
    asset_id: UUID
    revision_id: UUID
    revision_no: int
    kind: MediaKind
    declared_mime: str
    expected_checksum_sha256: str
    rights: MediaRights
    transcript: str | None
    segments: tuple[TranscriptSegment, ...]

    def __post_init__(self) -> None:
        _require_uuid7(self.asset_id, "asset_id")
        _require_uuid7(self.revision_id, "revision_id")
        _require_checksum(self.expected_checksum_sha256, "expected_checksum_sha256")
        if self.revision_no < 1 or self.declared_mime not in _MIMES_BY_KIND[self.kind]:
            raise _invalid("media_revision")
        if self.segments and self.transcript is None:
            raise _invalid("transcript")
        previous_end = 0
        for segment in self.segments:
            if segment.start_ms < previous_end:
                raise _invalid("transcript_segments")
            previous_end = segment.end_ms


@dataclass(frozen=True, slots=True)
class UploadReservation:
    upload_id: UUID
    object_key: str
    byte_limit: int
    declared_mime: str

    def __post_init__(self) -> None:
        _require_uuid7(self.upload_id, "upload_id")
        if not self.object_key.startswith("media/") or self.object_key.count("/") != 1:
            raise _invalid("object_key")
        if self.byte_limit < 1 or not self.declared_mime:
            raise _invalid("upload")


@dataclass(frozen=True, slots=True)
class UploadInspection:
    detected_mime: str
    size_bytes: int
    actual_checksum_sha256: str
    archive_safe: bool

    def __post_init__(self) -> None:
        _require_checksum(self.actual_checksum_sha256, "actual_checksum_sha256")
        if self.size_bytes < 0 or not self.detected_mime:
            raise _invalid("upload_inspection")


@dataclass(frozen=True, slots=True)
class MediaVariant:
    variant_id: UUID
    name: str
    mime_type: str
    checksum_sha256: str
    object_key: str

    def __post_init__(self) -> None:
        _require_uuid7(self.variant_id, "variant_id")
        _require_checksum(self.checksum_sha256, "variant.checksum_sha256")
        if not self.name or "/" in self.name or not self.mime_type:
            raise _invalid("variant")
        if not self.object_key.startswith("media/") or self.object_key.count("/") != 1:
            raise _invalid("variant.object_key")


@dataclass(frozen=True, slots=True)
class MediaAsset:
    asset_id: UUID
    revision: MediaRevision
    upload: UploadReservation
    status: MediaStatus
    created_at: datetime
    updated_at: datetime
    variants: tuple[MediaVariant, ...] = ()
    quarantine_reason: QuarantineReason | None = None

    def __post_init__(self) -> None:
        _require_uuid7(self.asset_id, "asset_id")
        if self.revision.asset_id != self.asset_id:
            raise _invalid("revision.asset_id")
        if self.status is MediaStatus.QUARANTINED and self.quarantine_reason is None:
            raise _invalid("quarantine_reason")
        if self.status is not MediaStatus.QUARANTINED and self.quarantine_reason is not None:
            raise _invalid("quarantine_reason")
        if len({variant.name for variant in self.variants}) != len(self.variants):
            raise _invalid("variants")

    @classmethod
    def reserve_upload(
        cls,
        *,
        asset_id: UUID,
        revision_id: UUID,
        upload_id: UUID,
        kind: MediaKind,
        declared_mime: str,
        expected_checksum_sha256: str,
        rights: MediaRights,
        now: datetime,
        transcript: str | None = None,
        segments: tuple[TranscriptSegment, ...] = (),
    ) -> MediaAsset:
        revision = MediaRevision(
            asset_id=asset_id,
            revision_id=revision_id,
            revision_no=1,
            kind=kind,
            declared_mime=declared_mime,
            expected_checksum_sha256=expected_checksum_sha256,
            rights=rights,
            transcript=transcript,
            segments=segments,
        )
        return cls(
            asset_id=asset_id,
            revision=revision,
            upload=UploadReservation(
                upload_id=upload_id,
                object_key=_opaque_object_key(
                    asset_id=asset_id,
                    revision_id=revision_id,
                    upload_id=upload_id,
                ),
                byte_limit=_LIMITS_BY_KIND[kind],
                declared_mime=declared_mime,
            ),
            status=MediaStatus.RESERVED,
            created_at=now,
            updated_at=now,
        )

    def begin_upload(self, *, at: datetime) -> MediaAsset:
        return self._transition(MediaStatus.RESERVED, MediaStatus.UPLOADING, at=at)

    def complete_upload(self, *, at: datetime) -> MediaAsset:
        return self._transition(MediaStatus.UPLOADING, MediaStatus.UPLOADED, at=at)

    def begin_verification(self) -> MediaAsset:
        return self._transition(MediaStatus.UPLOADED, MediaStatus.VERIFYING, at=self.updated_at)

    def verify(self, inspection: UploadInspection, *, at: datetime) -> MediaAsset:
        self._require_status(MediaStatus.VERIFYING)
        reason = self._quarantine_reason(inspection, at=at)
        if reason is not None:
            return replace(
                self,
                status=MediaStatus.QUARANTINED,
                updated_at=at,
                quarantine_reason=reason,
            )
        return replace(self, status=MediaStatus.PROCESSING, updated_at=at)

    def add_variant(
        self,
        *,
        variant_id: UUID,
        name: str,
        mime_type: str,
        checksum_sha256: str,
    ) -> MediaAsset:
        self._require_status(MediaStatus.PROCESSING)
        if any(variant.name == name for variant in self.variants):
            raise _invalid("variant.name")
        variant = MediaVariant(
            variant_id=variant_id,
            name=name,
            mime_type=mime_type,
            checksum_sha256=checksum_sha256,
            object_key=f"media/{self.asset_id.hex}-{self.revision.revision_id.hex}-{variant_id.hex}",
        )
        return replace(self, variants=(*self.variants, variant))

    def mark_ready(self, *, at: datetime) -> MediaAsset:
        self._require_status(MediaStatus.PROCESSING)
        if not self.revision.rights.is_active_at(at):
            raise DomainError(ErrorCode.HISTORICAL_RIGHTS_CONFLICT)
        return replace(self, status=MediaStatus.READY, updated_at=at)

    def request_deletion(self) -> MediaAsset:
        if self.status in {MediaStatus.DELETING, MediaStatus.DELETED}:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return replace(self, status=MediaStatus.DELETING, quarantine_reason=None)

    def remove_variant(self, name: str) -> MediaAsset:
        self._require_status(MediaStatus.DELETING)
        variants = tuple(variant for variant in self.variants if variant.name != name)
        if len(variants) == len(self.variants):
            raise DomainError(ErrorCode.NOT_FOUND)
        return replace(self, variants=variants)

    def complete_deletion(self, *, existing_object_keys: tuple[str, ...]) -> MediaAsset:
        self._require_status(MediaStatus.DELETING)
        if self.variants or existing_object_keys:
            raise DomainError(ErrorCode.MEDIA_STILL_REQUIRED)
        return replace(self, status=MediaStatus.DELETED)

    def _quarantine_reason(
        self,
        inspection: UploadInspection,
        *,
        at: datetime,
    ) -> QuarantineReason | None:
        if inspection.detected_mime != self.revision.declared_mime:
            return QuarantineReason.MIME_MISMATCH
        if inspection.size_bytes > self.upload.byte_limit:
            return QuarantineReason.SIZE_LIMIT
        if inspection.actual_checksum_sha256 != self.revision.expected_checksum_sha256:
            return QuarantineReason.CHECKSUM_MISMATCH
        if self.revision.kind is MediaKind.ARCHIVE and not inspection.archive_safe:
            return QuarantineReason.HOSTILE_ARCHIVE
        if not self.revision.rights.is_active_at(at):
            return QuarantineReason.RIGHTS_EXPIRED
        return None

    def _require_status(self, expected: MediaStatus) -> None:
        if self.status is not expected:
            raise DomainError(ErrorCode.INVALID_TRANSITION)

    def _transition(
        self,
        expected: MediaStatus,
        next_status: MediaStatus,
        *,
        at: datetime,
    ) -> MediaAsset:
        self._require_status(expected)
        return replace(self, status=next_status, updated_at=at)
