import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.media.application import ReserveMediaUpload, SynthesizeSpeech
from polyglot.modules.media.domain import MediaKind
from polyglot.modules.media.persistence import SqlMediaService
from polyglot.modules.media.ports import (
    DeterministicTtsPort,
    TtsAvailability,
    TtsVoice,
)
from polyglot.modules.media.storage import FilesystemObjectStorage, LocalSignedUrlSigner
from polyglot.platform.errors import DomainError, ErrorCode

from .conftest import ACCOUNT_ID, NOW


@dataclass
class MutableClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


class SequenceIds:
    def __init__(self) -> None:
        self.value = 100

    def new(self) -> UUID:
        self.value += 1
        return UUID(f"019feb39-0000-7000-8000-{self.value:012x}")


def media_service(
    factory: async_sessionmaker[AsyncSession], root: Path, clock: MutableClock
) -> SqlMediaService:
    return SqlMediaService(
        factory,
        FilesystemObjectStorage(root),
        LocalSignedUrlSigner(b"media-test-signing-secret-at-least-32-bytes"),
        DeterministicTtsPort(
            voices=(TtsVoice("Alice", "it-IT", TtsAvailability.AVAILABLE, "local-v1"),)
        ),
        clock=clock,
        id_generator=SequenceIds(),
    )


def token_from(url: str | None) -> str:
    assert url is not None
    return parse_qs(urlparse(url).query)["token"][0]


async def test_private_upload_verifies_derives_reads_and_deletes(
    runtime_factory: async_sessionmaker[AsyncSession],
    seeded_account: UUID,
    tmp_path: Path,
) -> None:
    clock = MutableClock(NOW)
    service = media_service(runtime_factory, tmp_path, clock)
    audio = b"ID3\x04\x00\x00\x00\x00\x00\x00fixture-mp3"
    checksum = hashlib.sha256(audio).hexdigest()
    reserved = await service.reserve_upload(
        seeded_account,
        ReserveMediaUpload(
            kind=MediaKind.AUDIO,
            declared_mime="audio/mpeg",
            expected_size=len(audio),
            expected_checksum_sha256=checksum,
            license_ref="private-user-recording",
            provenance_ref="integration-test",
            rights_expires_at=NOW + timedelta(days=1),
            retention_expires_at=NOW + timedelta(days=1),
            transcript="Ciao, come stai?",
        ),
        idempotency_key="reserve-audio",
    )
    replay = await service.reserve_upload(
        seeded_account,
        ReserveMediaUpload(
            kind=MediaKind.AUDIO,
            declared_mime="audio/mpeg",
            expected_size=len(audio),
            expected_checksum_sha256=checksum,
            license_ref="private-user-recording",
            provenance_ref="integration-test",
            rights_expires_at=NOW + timedelta(days=1),
            retention_expires_at=NOW + timedelta(days=1),
            transcript="Ciao, come stai?",
        ),
        idempotency_key="reserve-audio",
    )
    assert replay.media_id == reserved.media_id
    assert reserved.upload_id is not None
    await service.put_signed_upload(
        reserved.upload_id,
        token_from(reserved.upload_url),
        audio,
    )
    ready = await service.complete_upload(
        seeded_account, reserved.upload_id, idempotency_key="complete-audio"
    )
    completed_replay = await service.complete_upload(
        seeded_account, reserved.upload_id, idempotency_key="complete-audio"
    )

    assert ready.status == "ready"
    assert completed_replay.media_id == ready.media_id
    assert ready.detected_mime == "audio/mpeg"
    content, mime = await service.read_signed_media(ready.media_id, token_from(ready.read_url))
    assert content == audio and mime == "audio/mpeg"

    deleted = await service.delete_media(
        seeded_account,
        ready.media_id,
        expected_version=ready.version,
        idempotency_key="delete-audio",
    )
    deleted_replay = await service.delete_media(
        seeded_account,
        ready.media_id,
        expected_version=ready.version,
        idempotency_key="delete-audio",
    )
    assert deleted.status == "deleted"
    assert deleted_replay.version == deleted.version
    assert not tuple((tmp_path / "media").glob("*"))


async def test_deceptive_mime_is_quarantined_and_never_gets_read_url(
    runtime_factory: async_sessionmaker[AsyncSession],
    seeded_account: UUID,
    tmp_path: Path,
) -> None:
    service = media_service(runtime_factory, tmp_path, MutableClock(NOW))
    content = b"MZ-hostile-executable"
    reserved = await service.reserve_upload(
        seeded_account,
        ReserveMediaUpload(
            MediaKind.AUDIO,
            "audio/mpeg",
            len(content),
            hashlib.sha256(content).hexdigest(),
            "private",
            "hostile-fixture",
            NOW + timedelta(days=1),
            NOW + timedelta(days=1),
        ),
        idempotency_key="hostile",
    )
    assert reserved.upload_id is not None
    await service.put_signed_upload(reserved.upload_id, token_from(reserved.upload_url), content)
    quarantined = await service.complete_upload(
        seeded_account, reserved.upload_id, idempotency_key="complete-hostile"
    )

    assert quarantined.status == "quarantined"
    assert quarantined.quarantine_reason == "mime_mismatch"
    assert quarantined.read_url is None


async def test_tts_cache_is_exact_and_returns_private_signed_audio(
    runtime_factory: async_sessionmaker[AsyncSession],
    seeded_account: UUID,
    tmp_path: Path,
) -> None:
    service = media_service(runtime_factory, tmp_path, MutableClock(NOW))
    command = SynthesizeSpeech("Ciao, come stai?", "it-IT", "Alice", {"speed": "normal"})

    first = await service.synthesize(ACCOUNT_ID, command, idempotency_key="tts-1")
    replay = await service.synthesize(ACCOUNT_ID, command, idempotency_key="tts-1")
    second = await service.synthesize(ACCOUNT_ID, command, idempotency_key="tts-2")

    assert first.availability == second.availability == "available"
    assert first.cache_key == second.cache_key
    assert first.media is not None and second.media is not None
    assert first.media.media_id == second.media.media_id
    assert replay.media is not None and replay.media.media_id == first.media.media_id
    assert first.media.read_url is not None

    with pytest.raises(DomainError) as caught:
        await service.synthesize(
            ACCOUNT_ID,
            SynthesizeSpeech("Un altro testo", "it-IT", "Alice", {"speed": "normal"}),
            idempotency_key="tts-1",
        )
    assert caught.value.code is ErrorCode.IDEMPOTENCY_CONFLICT


async def test_expired_signed_upload_is_rejected(
    runtime_factory: async_sessionmaker[AsyncSession],
    seeded_account: UUID,
    tmp_path: Path,
) -> None:
    clock = MutableClock(NOW)
    service = media_service(runtime_factory, tmp_path, clock)
    content = b"ID3fixture"
    reserved = await service.reserve_upload(
        seeded_account,
        ReserveMediaUpload(
            MediaKind.AUDIO,
            "audio/mpeg",
            len(content),
            hashlib.sha256(content).hexdigest(),
            "private",
            "expiry-test",
            NOW + timedelta(days=1),
            NOW + timedelta(days=1),
        ),
        idempotency_key="expiring",
    )
    clock.instant += timedelta(minutes=11)

    with pytest.raises(DomainError) as caught:
        assert reserved.upload_id is not None
        await service.put_signed_upload(
            reserved.upload_id, token_from(reserved.upload_url), content
        )
    assert caught.value.code is ErrorCode.FORBIDDEN


async def test_signed_tokens_are_bound_to_the_path_resource(
    runtime_factory: async_sessionmaker[AsyncSession],
    seeded_account: UUID,
    tmp_path: Path,
) -> None:
    service = media_service(runtime_factory, tmp_path, MutableClock(NOW))
    content = b"ID3fixture"
    reserved = await service.reserve_upload(
        seeded_account,
        ReserveMediaUpload(
            MediaKind.AUDIO,
            "audio/mpeg",
            len(content),
            hashlib.sha256(content).hexdigest(),
            "private",
            "binding-test",
            NOW + timedelta(days=1),
            NOW + timedelta(days=1),
        ),
        idempotency_key="bound-token",
    )
    with pytest.raises(DomainError) as caught:
        await service.put_signed_upload(
            UUID("019feb39-0000-7000-8000-000000009999"),
            token_from(reserved.upload_url),
            content,
        )
    assert caught.value.code is ErrorCode.FORBIDDEN
