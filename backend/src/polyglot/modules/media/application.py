from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from polyglot.modules.media.domain import MediaKind
from polyglot.platform.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class TranscriptSegmentInput:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True, slots=True)
class ReserveMediaUpload:
    kind: MediaKind
    declared_mime: str
    expected_size: int
    expected_checksum_sha256: str
    license_ref: str
    provenance_ref: str
    rights_expires_at: datetime | None
    retention_expires_at: datetime | None
    transcript: str | None = None
    segments: tuple[TranscriptSegmentInput, ...] = ()


@dataclass(frozen=True, slots=True)
class MediaView:
    media_id: UUID
    media_revision_id: UUID
    upload_id: UUID | None
    media_type: str
    status: str
    privacy_class: str
    declared_mime: str
    detected_mime: str | None
    size_bytes: int | None
    checksum_sha256: str
    quarantine_reason: str | None
    transcript: str | None
    upload_url: str | None
    read_url: str | None
    url_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class TtsVoiceView:
    voice_id: str
    language_tags: tuple[str, ...]
    formats: tuple[str, ...]
    limits: dict[str, JsonValue]
    availability: str


@dataclass(frozen=True, slots=True)
class TtsCapabilitiesView:
    catalog_revision_id: UUID
    provider_code: str
    provider_version: str
    voices: tuple[TtsVoiceView, ...]


@dataclass(frozen=True, slots=True)
class SynthesizeSpeech:
    text: str
    locale: str
    voice_id: str
    parameters: dict[str, str]


@dataclass(frozen=True, slots=True)
class TtsSynthesisView:
    voice_id: str
    availability: str
    cache_key: str | None
    media: MediaView | None


class MediaApplicationService(Protocol):
    async def reserve_upload(
        self, actor_id: UUID, command: ReserveMediaUpload, *, idempotency_key: str
    ) -> MediaView: ...

    async def put_signed_upload(self, upload_id: UUID, token: str, content: bytes) -> None: ...

    async def complete_upload(
        self, actor_id: UUID, upload_id: UUID, *, idempotency_key: str
    ) -> MediaView: ...

    async def get_media(self, actor_id: UUID, media_id: UUID) -> MediaView: ...

    async def read_signed_media(self, media_id: UUID, token: str) -> tuple[bytes, str]: ...

    async def delete_media(
        self,
        actor_id: UUID,
        media_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> MediaView: ...

    async def tts_capabilities(self, language: str) -> TtsCapabilitiesView: ...

    async def synthesize(
        self, actor_id: UUID, command: SynthesizeSpeech, *, idempotency_key: str
    ) -> TtsSynthesisView: ...
