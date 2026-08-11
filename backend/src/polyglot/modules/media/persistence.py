from __future__ import annotations

# ruff: noqa: E501
import hashlib
import io
import json
import zipfile
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.media.application import (
    MediaView,
    ReserveMediaUpload,
    SynthesizeSpeech,
    TtsCapabilitiesView,
    TtsSynthesisView,
    TtsVoiceView,
)
from polyglot.modules.media.domain import (
    MediaAsset,
    MediaKind,
    MediaRights,
    MediaStatus,
    TranscriptSegment,
    UploadInspection,
)
from polyglot.modules.media.ports import ObjectStoragePort, TtsAvailability, TtsPort, TtsRequest
from polyglot.modules.media.storage import LocalSignedUrlSigner, SignedObjectGrant
from polyglot.platform.clock import Clock, SystemClock
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.json_types import JsonValue
from polyglot.platform.persistence.records import CommandReceipt
from polyglot.platform.persistence.repositories import SqlCommandReceiptStore

SIGNED_URL_LIFETIME = timedelta(minutes=10)
UPLOAD_RESERVATION_LIFETIME = timedelta(minutes=15)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _uuid(value: object) -> UUID:
    return UUID(str(value))


def _detect_mime(content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"RIFF") and content[8:12] == b"WAVE":
        return "audio/wav"
    if content.startswith(b"OggS"):
        return "audio/ogg"
    if content.startswith(b"ID3") or content[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
        return "audio/mpeg"
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return "video/mp4"
    if content.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"
    if content.startswith(b"PK\x03\x04"):
        return "application/zip"
    return "application/octet-stream"


def _archive_is_safe(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > 1000:
                return False
            total = 0
            for member in members:
                path = member.filename.replace("\\", "/")
                if path.startswith("/") or ".." in path.split("/"):
                    return False
                total += member.file_size
                if total > 200 * 1024 * 1024:
                    return False
            return archive.testzip() is None
    except (OSError, zipfile.BadZipFile, RuntimeError):
        return False


class SqlMediaService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        storage: ObjectStoragePort,
        signer: LocalSignedUrlSigner,
        tts: TtsPort,
        *,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._sessions = sessions
        self._storage = storage
        self._signer = signer
        self._tts = tts
        self._clock = clock or SystemClock()
        self._ids = id_generator or Uuid7Generator(self._clock)

    async def reserve_upload(
        self, actor_id: UUID, command: ReserveMediaUpload, *, idempotency_key: str
    ) -> MediaView:
        now = self._clock.now()
        fingerprint = canonical_json_fingerprint(
            {
                "kind": command.kind.value,
                "declared_mime": command.declared_mime,
                "expected_size": command.expected_size,
                "expected_checksum_sha256": command.expected_checksum_sha256,
                "license_ref": command.license_ref,
                "provenance_ref": command.provenance_ref,
                "rights_expires_at": None if command.rights_expires_at is None else command.rights_expires_at.isoformat(),
                "retention_expires_at": None if command.retention_expires_at is None else command.retention_expires_at.isoformat(),
                "transcript": command.transcript,
                "segments": [
                    {
                        "start_ms": segment.start_ms,
                        "end_ms": segment.end_ms,
                        "text": segment.text,
                    }
                    for segment in command.segments
                ],
            }
        )
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            existing = (
                (
                    await session.execute(
                        text(
                            "SELECT media_id,request_fingerprint FROM media.media_uploads "
                            "WHERE owner_account_id=:owner AND idempotency_key=:key"
                        ),
                        {"owner": actor_id, "key": idempotency_key},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                view = await self._read_view(session, _uuid(existing["media_id"]), now)
                assert view is not None
                return view

            media_id = self._ids.new()
            revision_id = self._ids.new()
            rights_id = self._ids.new()
            upload_id = self._ids.new()
            rights = MediaRights(
                rights_id=rights_id,
                license_ref=command.license_ref,
                provenance_ref=command.provenance_ref,
                expires_at=command.rights_expires_at,
            )
            segments = tuple(
                TranscriptSegment(value.start_ms, value.end_ms, value.text)
                for value in command.segments
            )
            asset = MediaAsset.reserve_upload(
                asset_id=media_id,
                revision_id=revision_id,
                upload_id=upload_id,
                kind=command.kind,
                declared_mime=command.declared_mime,
                expected_checksum_sha256=command.expected_checksum_sha256,
                rights=rights,
                now=now,
                transcript=command.transcript,
                segments=segments,
            )
            if command.expected_size < 0 or command.expected_size > asset.upload.byte_limit:
                raise DomainError(ErrorCode.MEDIA_QUOTA_EXCEEDED)
            await session.execute(
                text(
                    "INSERT INTO media.media_assets "
                    "(media_id,owner_account_id,editorial_owner_id,media_type,status,privacy_class,"
                    "current_revision_id,expires_at,deletion_requested_at,quarantine_reason,version,created_at,updated_at) "
                    "VALUES (:media,:owner,NULL,:kind,'reserved',:privacy,NULL,:expires,NULL,NULL,1,:now,:now)"
                ),
                {
                    "media": media_id,
                    "owner": actor_id,
                    "kind": command.kind.value,
                    "privacy": "sensitive" if command.kind.value in {"audio", "video"} else "personal",
                    "expires": command.retention_expires_at,
                    "now": now,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO media.media_rights "
                    "(rights_id,media_id,owner_account_id,license_ref,provenance_ref,expires_at,created_at) "
                    "VALUES (:rights,:media,:owner,:license,:provenance,:expires,:now)"
                ),
                {
                    "rights": rights_id,
                    "media": media_id,
                    "owner": actor_id,
                    "license": command.license_ref,
                    "provenance": command.provenance_ref,
                    "expires": command.rights_expires_at,
                    "now": now,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO media.media_revisions "
                    "(media_revision_id,media_id,owner_account_id,rights_id,revision_no,storage_key,"
                    "declared_mime,detected_mime,sha256,size_bytes,duration_ms,variety_id,transcript_text,processing_version,created_at) "
                    "VALUES (:revision,:media,:owner,:rights,1,:key,:mime,NULL,:checksum,NULL,NULL,NULL,:transcript,NULL,:now)"
                ),
                {
                    "revision": revision_id,
                    "media": media_id,
                    "owner": actor_id,
                    "rights": rights_id,
                    "key": asset.upload.object_key,
                    "mime": command.declared_mime,
                    "checksum": command.expected_checksum_sha256,
                    "transcript": command.transcript,
                    "now": now,
                },
            )
            await session.execute(
                text(
                    "UPDATE media.media_assets SET current_revision_id=:revision WHERE media_id=:media"
                ),
                {"revision": revision_id, "media": media_id},
            )
            for ordinal, segment in enumerate(segments, start=1):
                await session.execute(
                    text(
                        "INSERT INTO media.media_segments "
                        "(segment_id,media_revision_id,media_id,owner_account_id,ordinal,start_ms,end_ms,transcript_text,created_at) "
                        "VALUES (:segment,:revision,:media,:owner,:ordinal,:start,:end,:transcript,:now)"
                    ),
                    {
                        "segment": self._ids.new(),
                        "revision": revision_id,
                        "media": media_id,
                        "owner": actor_id,
                        "ordinal": ordinal,
                        "start": segment.start_ms,
                        "end": segment.end_ms,
                        "transcript": segment.text,
                        "now": now,
                    },
                )
            await session.execute(
                text(
                    "INSERT INTO media.media_uploads "
                    "(upload_id,media_id,media_revision_id,owner_account_id,reserved_by_actor_id,"
                    "expected_size,expected_sha256,declared_mime,byte_limit,status,reserved_at,expires_at,"
                    "version,idempotency_key,request_fingerprint) VALUES "
                    "(:upload,:media,:revision,:owner,:owner,:size,:checksum,:mime,:limit,'reserved',"
                    ":now,:expires,1,:idem,:fingerprint)"
                ),
                {
                    "upload": upload_id,
                    "media": media_id,
                    "revision": revision_id,
                    "owner": actor_id,
                    "size": command.expected_size,
                    "checksum": command.expected_checksum_sha256,
                    "mime": command.declared_mime,
                    "limit": asset.upload.byte_limit,
                    "now": now,
                    "expires": now + UPLOAD_RESERVATION_LIFETIME,
                    "idem": idempotency_key,
                    "fingerprint": fingerprint,
                },
            )
            view = await self._read_view(session, media_id, now)
            assert view is not None
            return view

    async def put_signed_upload(self, upload_id: UUID, token: str, content: bytes) -> None:
        grant = self._verify_token(token, method="PUT", resource_id=upload_id)
        if len(content) > grant.max_bytes:
            raise DomainError(ErrorCode.MEDIA_QUOTA_EXCEEDED)
        self._storage.write_private(grant.object_key, content)

    async def complete_upload(
        self, actor_id: UUID, upload_id: UUID, *, idempotency_key: str
    ) -> MediaView:
        now = self._clock.now()
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            command_id, replay_ref = await self._reserve_command(
                session,
                actor_id=actor_id,
                aggregate_id=upload_id,
                command_type="media.complete_upload",
                idempotency_key=idempotency_key,
                expected_version=None,
                payload={"upload_id": str(upload_id)},
                now=now,
            )
            if replay_ref is not None:
                replay = await self._read_view(session, replay_ref, now)
                if replay is None:
                    raise DomainError(ErrorCode.NOT_FOUND)
                return replay
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT u.*,a.created_at,a.updated_at,a.media_type,a.status AS asset_status,"
                            "a.privacy_class,a.expires_at AS retention_expires_at,a.quarantine_reason,"
                            "r.storage_key,r.transcript_text,rt.rights_id,rt.license_ref,rt.provenance_ref,"
                            "rt.expires_at AS rights_expires_at FROM media.media_uploads u "
                            "JOIN media.media_assets a ON a.media_id=u.media_id "
                            "JOIN media.media_revisions r ON r.media_revision_id=u.media_revision_id "
                            "JOIN media.media_rights rt ON rt.rights_id=r.rights_id "
                            "WHERE u.upload_id=:upload FOR UPDATE OF u,a"
                        ),
                        {"upload": upload_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if row["status"] == "ready" or row["status"] == "quarantined":
                view = await self._read_view(session, _uuid(row["media_id"]), now)
                assert view is not None
                await self._complete_command(session, command_id, view)
                return view
            if now >= row["expires_at"]:
                raise DomainError(ErrorCode.MEDIA_NOT_READY)
            content = self._storage.read_private(str(row["storage_key"]))
            if content is None:
                raise DomainError(ErrorCode.MEDIA_NOT_READY)
            detected_mime = _detect_mime(content)
            checksum = hashlib.sha256(content).hexdigest()
            archive_safe = detected_mime != "application/zip" or _archive_is_safe(content)
            asset = await self._domain_asset(session, row)
            inspection_checksum = (
                checksum if len(content) == int(row["expected_size"]) else "0" * 64
            )
            processing = (
                asset.begin_upload(at=now)
                .complete_upload(at=now)
                .begin_verification()
                .verify(
                    UploadInspection(
                        detected_mime,
                        len(content),
                        inspection_checksum,
                        archive_safe,
                    ),
                    at=now,
                )
            )
            if processing.status is MediaStatus.QUARANTINED:
                reason = processing.quarantine_reason
                assert reason is not None
                await session.execute(
                    text(
                        "UPDATE media.media_assets SET status='quarantined',quarantine_reason=:reason,"
                        "version=version+1,updated_at=:now WHERE media_id=:media"
                    ),
                    {"reason": reason.value, "now": now, "media": row["media_id"]},
                )
                await session.execute(
                    text(
                        "UPDATE media.media_uploads SET status='quarantined',uploaded_at=:now,completed_at=:now,"
                        "detected_mime=:mime,actual_sha256=:checksum,actual_size=:size,scan_result=:reason,"
                        "version=version+1 WHERE upload_id=:upload"
                    ),
                    {
                        "now": now,
                        "mime": detected_mime,
                        "checksum": checksum,
                        "size": len(content),
                        "reason": reason.value,
                        "upload": upload_id,
                    },
                )
            else:
                variant_id = self._ids.new()
                ready = processing.add_variant(
                    variant_id=variant_id,
                    name="normalized",
                    mime_type=detected_mime,
                    checksum_sha256=checksum,
                ).mark_ready(at=now)
                variant = ready.variants[-1]
                self._storage.write_private(variant.object_key, content)
                await session.execute(
                    text(
                        "UPDATE media.media_revisions SET detected_mime=:mime,size_bytes=:size,"
                        "processing_version='LOCAL_MEDIA_V0' WHERE media_revision_id=:revision"
                    ),
                    {"mime": detected_mime, "size": len(content), "revision": row["media_revision_id"]},
                )
                await session.execute(
                    text(
                        "INSERT INTO media.media_variants "
                        "(variant_id,media_revision_id,media_id,owner_account_id,variant_type,storage_key,"
                        "mime_type,sha256,size_bytes,created_at) VALUES "
                        "(:variant,:revision,:media,:owner,'normalized',:key,:mime,:checksum,:size,:now)"
                    ),
                    {
                        "variant": variant_id,
                        "revision": row["media_revision_id"],
                        "media": row["media_id"],
                        "owner": actor_id,
                        "key": variant.object_key,
                        "mime": detected_mime,
                        "checksum": checksum,
                        "size": len(content),
                        "now": now,
                    },
                )
                await session.execute(
                    text(
                        "UPDATE media.media_assets SET status='ready',version=version+1,updated_at=:now "
                        "WHERE media_id=:media"
                    ),
                    {"now": now, "media": row["media_id"]},
                )
                await session.execute(
                    text(
                        "UPDATE media.media_uploads SET status='ready',uploaded_at=:now,completed_at=:now,"
                        "detected_mime=:mime,actual_sha256=:checksum,actual_size=:size,scan_result='clean',"
                        "version=version+1 WHERE upload_id=:upload"
                    ),
                    {
                        "now": now,
                        "mime": detected_mime,
                        "checksum": checksum,
                        "size": len(content),
                        "upload": upload_id,
                    },
                )
            view = await self._read_view(session, _uuid(row["media_id"]), now)
            assert view is not None
            await self._complete_command(session, command_id, view)
            return view

    async def get_media(self, actor_id: UUID, media_id: UUID) -> MediaView:
        now = self._clock.now()
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            view = await self._read_view(session, media_id, now)
            if view is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            return view

    async def read_signed_media(self, media_id: UUID, token: str) -> tuple[bytes, str]:
        grant = self._verify_token(token, method="GET", resource_id=media_id)
        content = self._storage.read_private(grant.object_key)
        if content is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        return content, _detect_mime(content)

    async def delete_media(
        self,
        actor_id: UUID,
        media_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> MediaView:
        now = self._clock.now()
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            command_id, replay_ref = await self._reserve_command(
                session,
                actor_id=actor_id,
                aggregate_id=media_id,
                command_type="media.delete",
                idempotency_key=idempotency_key,
                expected_version=expected_version,
                payload={"media_id": str(media_id)},
                now=now,
            )
            if replay_ref is not None:
                replay = await self._read_view(session, replay_ref, now)
                if replay is None:
                    raise DomainError(ErrorCode.NOT_FOUND)
                return replay
            row = (
                (
                    await session.execute(
                        text("SELECT status,version FROM media.media_assets WHERE media_id=:media FOR UPDATE"),
                        {"media": media_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if row["status"] == "deleted":
                view = await self._read_view(session, media_id, now)
                assert view is not None
                await self._complete_command(session, command_id, view)
                return view
            if int(row["version"]) != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if row["status"] not in {"ready", "quarantined", "rejected", "failed"}:
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            keys = tuple(
                (
                    await session.execute(
                        text(
                            "SELECT storage_key FROM media.media_revisions WHERE media_id=:media "
                            "UNION ALL SELECT storage_key FROM media.media_variants WHERE media_id=:media"
                        ),
                        {"media": media_id},
                    )
                ).scalars()
            )
            await session.execute(
                text(
                    "UPDATE media.media_assets SET status='deleting',deletion_requested_at=:now,"
                    "quarantine_reason=NULL,version=version+1,updated_at=:now WHERE media_id=:media"
                ),
                {"now": now, "media": media_id},
            )
            for key in keys:
                self._storage.delete_private(str(key))
            await session.execute(
                text(
                    "UPDATE media.media_assets SET status='deleted',version=version+1,updated_at=:now "
                    "WHERE media_id=:media"
                ),
                {"now": now, "media": media_id},
            )
            view = await self._read_view(session, media_id, now)
            assert view is not None
            await self._complete_command(session, command_id, view)
            return view

    async def tts_capabilities(self, language: str) -> TtsCapabilitiesView:
        async with self._sessions() as session:
            header = (
                (
                    await session.execute(
                        text(
                            "SELECT catalog_revision_id,provider_code,provider_version "
                            "FROM media.tts_voice_catalog_revisions ORDER BY published_at DESC LIMIT 1"
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if header is None:
                raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
            rows = (
                await session.execute(
                    text(
                        "SELECT voice_id,language_tags,formats,limits,availability "
                        "FROM media.tts_voice_capabilities WHERE catalog_revision_id=:catalog "
                        "AND :language=ANY(language_tags) ORDER BY voice_id"
                    ),
                    {"catalog": header["catalog_revision_id"], "language": language},
                )
            ).mappings()
            return TtsCapabilitiesView(
                catalog_revision_id=_uuid(header["catalog_revision_id"]),
                provider_code=str(header["provider_code"]),
                provider_version=str(header["provider_version"]),
                voices=tuple(
                    TtsVoiceView(
                        voice_id=str(row["voice_id"]),
                        language_tags=tuple(row["language_tags"]),
                        formats=tuple(row["formats"]),
                        limits=cast(dict[str, JsonValue], row["limits"]),
                        availability=str(row["availability"]),
                    )
                    for row in rows
                ),
            )

    async def _assessment_speech_text(
        self,
        actor_id: UUID,
        run_id: UUID,
        item_id: UUID,
    ) -> str:
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            script = await session.scalar(
                text(
                    "SELECT item.solution_snapshot->>'audio_script' "
                    "FROM assessments.assessment_runs AS run "
                    "JOIN assessments.assessment_section_definitions AS section "
                    "ON section.form_id=run.form_id "
                    "JOIN assessments.assessment_items AS item "
                    "ON item.section_definition_id=section.section_definition_id "
                    "WHERE run.assessment_run_id=:run AND item.item_id=:item "
                    "AND run.status='in_progress' AND item.media_ref IS NOT NULL"
                ),
                {"run": run_id, "item": item_id},
            )
            if not isinstance(script, str) or not script:
                raise DomainError(ErrorCode.NOT_FOUND)
            return script

    async def _record_assessment_play(
        self,
        session: AsyncSession,
        actor_id: UUID,
        run_id: UUID,
        item_id: UUID,
        idempotency_key: str,
        now: datetime,
    ) -> None:
        maximum = await session.scalar(
            text(
                "SELECT item.max_plays FROM assessments.assessment_runs AS run "
                "JOIN assessments.assessment_section_definitions AS section "
                "ON section.form_id=run.form_id "
                "JOIN assessments.assessment_items AS item "
                "ON item.section_definition_id=section.section_definition_id "
                "WHERE run.assessment_run_id=:run AND item.item_id=:item"
            ),
            {"run": run_id, "item": item_id},
        )
        if maximum is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        play_count = int(
            await session.scalar(
                text(
                    "SELECT count(*) FROM assessments.assessment_item_plays "
                    "WHERE assessment_run_id=:run AND item_id=:item"
                ),
                {"run": run_id, "item": item_id},
            )
            or 0
        )
        if play_count >= int(maximum):
            raise DomainError(ErrorCode.RESPONSE_CONFLICT)
        await session.execute(
            text(
                "INSERT INTO assessments.assessment_item_plays "
                "(play_id,assessment_run_id,item_id,owner_account_id,idempotency_key,played_at) "
                "VALUES (:play,:run,:item,:owner,:key,:now)"
            ),
            {
                "play": self._ids.new(),
                "run": run_id,
                "item": item_id,
                "owner": actor_id,
                "key": idempotency_key,
                "now": now,
            },
        )

    async def synthesize(
        self, actor_id: UUID, command: SynthesizeSpeech, *, idempotency_key: str
    ) -> TtsSynthesisView:
        now = self._clock.now()
        speech_text = command.text
        if command.assessment_run_id is not None and command.assessment_item_id is not None:
            speech_text = await self._assessment_speech_text(
                actor_id,
                command.assessment_run_id,
                command.assessment_item_id,
            )
        if not speech_text or len(speech_text) > 5000:
            raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
        fingerprint_payload: dict[str, JsonValue] = {
                "text": speech_text,
                "locale": command.locale,
                "voice_id": command.voice_id,
                "parameters": dict(command.parameters),
                "assessment_run_id": (
                    None
                    if command.assessment_run_id is None
                    else str(command.assessment_run_id)
                ),
                "assessment_item_id": (
                    None
                    if command.assessment_item_id is None
                    else str(command.assessment_item_id)
                ),
        }
        request_fingerprint = canonical_json_fingerprint(fingerprint_payload)
        request_id = self._ids.new()
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            existing = (
                (
                    await session.execute(
                        text(
                            "SELECT request_fingerprint,voice_id,availability,cache_key,media_id,status "
                            "FROM media.tts_synthesis_requests "
                            "WHERE owner_account_id=:owner AND idempotency_key=:key"
                        ),
                        {"owner": actor_id, "key": idempotency_key},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if existing["request_fingerprint"] != request_fingerprint:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                if existing["status"] != "completed":
                    raise DomainError(ErrorCode.RESPONSE_CONFLICT)
                media = None
                if existing["media_id"] is not None:
                    media = await self._read_view(session, _uuid(existing["media_id"]), now)
                return TtsSynthesisView(
                    str(existing["voice_id"]),
                    str(existing["availability"]),
                    cast(str | None, existing["cache_key"]),
                    media,
                )
            if command.assessment_run_id is not None and command.assessment_item_id is not None:
                await self._record_assessment_play(
                    session,
                    actor_id,
                    command.assessment_run_id,
                    command.assessment_item_id,
                    idempotency_key,
                    now,
                )
            await session.execute(
                text(
                    "INSERT INTO media.tts_synthesis_requests "
                    "(request_id,owner_account_id,idempotency_key,request_fingerprint,voice_id,"
                    "availability,cache_key,media_id,status,created_at,completed_at) VALUES "
                    "(:request,:owner,:key,:fingerprint,:voice,NULL,NULL,NULL,'started',:now,NULL)"
                ),
                {
                    "request": request_id,
                    "owner": actor_id,
                    "key": idempotency_key,
                    "fingerprint": request_fingerprint,
                    "voice": command.voice_id,
                    "now": now,
                },
            )
        capabilities = await self.tts_capabilities(command.locale)
        voice = next((item for item in capabilities.voices if item.voice_id == command.voice_id), None)
        if voice is None:
            synthesis_view = TtsSynthesisView(
                command.voice_id, TtsAvailability.RETIRED.value, None, None
            )
            await self._complete_tts_request(actor_id, request_id, synthesis_view, now)
            return synthesis_view
        result = self._tts.synthesize(
            TtsRequest(speech_text, command.locale, command.voice_id, command.parameters)
        )
        if result.availability is not TtsAvailability.AVAILABLE or result.audio is None or result.cache_key is None:
            synthesis_view = TtsSynthesisView(
                command.voice_id, result.availability.value, result.cache_key, None
            )
            await self._complete_tts_request(actor_id, request_id, synthesis_view, now)
            return synthesis_view
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            cached_media = await session.scalar(
                text(
                    "SELECT media_id FROM media.tts_cache_entries "
                    "WHERE owner_account_id=:owner AND cache_key=:cache"
                ),
                {"owner": actor_id, "cache": result.cache_key},
            )
            if cached_media is not None:
                await session.execute(
                    text(
                        "UPDATE media.tts_cache_entries SET last_accessed_at=:now "
                        "WHERE owner_account_id=:owner AND cache_key=:cache"
                    ),
                    {"now": now, "owner": actor_id, "cache": result.cache_key},
                )
                media_view = await self._read_view(session, _uuid(cached_media), now)
                assert media_view is not None
                await self._complete_tts_request_in_session(
                    session,
                    request_id,
                    TtsSynthesisView(
                        command.voice_id, result.availability.value, result.cache_key, media_view
                    ),
                    now,
                )
                return TtsSynthesisView(
                    command.voice_id, result.availability.value, result.cache_key, media_view
                )

            media_id = self._ids.new()
            revision_id = self._ids.new()
            rights_id = self._ids.new()
            cache_entry_id = self._ids.new()
            storage_key = f"media/{media_id.hex}-{revision_id.hex}-{cache_entry_id.hex}"
            checksum = hashlib.sha256(result.audio).hexdigest()
            self._storage.write_private(storage_key, result.audio)
            await session.execute(
                text(
                    "INSERT INTO media.media_assets "
                    "(media_id,owner_account_id,editorial_owner_id,media_type,status,privacy_class,"
                    "current_revision_id,expires_at,deletion_requested_at,quarantine_reason,version,created_at,updated_at) "
                    "VALUES (:media,:owner,NULL,'audio','ready','personal',NULL,:expires,NULL,NULL,1,:now,:now)"
                ),
                {"media": media_id, "owner": actor_id, "expires": now + timedelta(days=30), "now": now},
            )
            await session.execute(
                text(
                    "INSERT INTO media.media_rights "
                    "(rights_id,media_id,owner_account_id,license_ref,provenance_ref,expires_at,created_at) "
                    "VALUES (:rights,:media,:owner,'generated-local','tts:macos-say',:expires,:now)"
                ),
                {"rights": rights_id, "media": media_id, "owner": actor_id, "expires": now + timedelta(days=30), "now": now},
            )
            await session.execute(
                text(
                    "INSERT INTO media.media_revisions "
                    "(media_revision_id,media_id,owner_account_id,rights_id,revision_no,storage_key,"
                    "declared_mime,detected_mime,sha256,size_bytes,processing_version,created_at) "
                    "VALUES (:revision,:media,:owner,:rights,1,:key,'audio/mpeg','audio/mpeg',"
                    ":checksum,:size,'MACOS_TTS_V0',:now)"
                ),
                {
                    "revision": revision_id,
                    "media": media_id,
                    "owner": actor_id,
                    "rights": rights_id,
                    "key": storage_key,
                    "checksum": checksum,
                    "size": len(result.audio),
                    "now": now,
                },
            )
            await session.execute(
                text("UPDATE media.media_assets SET current_revision_id=:revision WHERE media_id=:media"),
                {"revision": revision_id, "media": media_id},
            )
            await session.execute(
                text(
                    "INSERT INTO media.tts_cache_entries "
                    "(cache_entry_id,owner_account_id,catalog_revision_id,voice_id,cache_key,media_id,"
                    "media_revision_id,locale,parameters,status,created_at,last_accessed_at) VALUES "
                    "(:entry,:owner,:catalog,:voice,:cache,:media,:revision,:locale,CAST(:parameters AS jsonb),"
                    "'ready',:now,:now)"
                ),
                {
                    "entry": cache_entry_id,
                    "owner": actor_id,
                    "catalog": capabilities.catalog_revision_id,
                    "voice": command.voice_id,
                    "cache": result.cache_key,
                    "media": media_id,
                    "revision": revision_id,
                    "locale": command.locale,
                    "parameters": _json(command.parameters),
                    "now": now,
                },
            )
            media_view = await self._read_view(session, media_id, now)
            assert media_view is not None
            await self._complete_tts_request_in_session(
                session,
                request_id,
                TtsSynthesisView(
                    command.voice_id, result.availability.value, result.cache_key, media_view
                ),
                now,
            )
            return TtsSynthesisView(
                command.voice_id, result.availability.value, result.cache_key, media_view
            )

    async def _complete_tts_request(
        self,
        actor_id: UUID,
        request_id: UUID,
        view: TtsSynthesisView,
        now: datetime,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._complete_tts_request_in_session(session, request_id, view, now)

    @staticmethod
    async def _complete_tts_request_in_session(
        session: AsyncSession,
        request_id: UUID,
        view: TtsSynthesisView,
        now: datetime,
    ) -> None:
        await session.execute(
            text(
                "UPDATE media.tts_synthesis_requests SET availability=:availability,"
                "cache_key=:cache,media_id=:media,status='completed',completed_at=:now "
                "WHERE request_id=:request AND status='started'"
            ),
            {
                "availability": view.availability,
                "cache": view.cache_key,
                "media": None if view.media is None else view.media.media_id,
                "now": now,
                "request": request_id,
            },
        )

    async def _domain_asset(self, session: AsyncSession, row: object) -> MediaAsset:
        item = cast(dict[str, object], row)
        segment_rows = (
            await session.execute(
                text(
                    "SELECT start_ms,end_ms,transcript_text FROM media.media_segments "
                    "WHERE media_revision_id=:revision ORDER BY ordinal"
                ),
                {"revision": item["media_revision_id"]},
            )
        ).mappings()
        return MediaAsset.reserve_upload(
            asset_id=_uuid(item["media_id"]),
            revision_id=_uuid(item["media_revision_id"]),
            upload_id=_uuid(item["upload_id"]),
            kind=MediaKind(str(item["media_type"])),
            declared_mime=str(item["declared_mime"]),
            expected_checksum_sha256=str(item["expected_sha256"]),
            rights=MediaRights(
                _uuid(item["rights_id"]),
                str(item["license_ref"]),
                str(item["provenance_ref"]),
                cast(datetime | None, item["rights_expires_at"]),
            ),
            transcript=cast(str | None, item["transcript_text"]),
            segments=tuple(
                TranscriptSegment(
                    int(value["start_ms"]),
                    int(value["end_ms"]),
                    str(value["transcript_text"]),
                )
                for value in segment_rows
            ),
            now=cast(datetime, item["created_at"]),
        )

    async def _reserve_command(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        aggregate_id: UUID,
        command_type: str,
        idempotency_key: str,
        expected_version: int | None,
        payload: dict[str, JsonValue],
        now: datetime,
    ) -> tuple[UUID, UUID | None]:
        receipt = CommandReceipt(
            command_id=self._ids.new(),
            command_type=command_type,
            actor_id=actor_id,
            aggregate_type="media",
            aggregate_id=aggregate_id,
            idempotency_key=idempotency_key,
            request_fingerprint=canonical_json_fingerprint(payload),
            expected_version=expected_version,
            received_at=now,
            result_ref=None,
            result_payload=None,
            status="started",
            expires_at=now + timedelta(hours=24),
        )
        reservation = await SqlCommandReceiptStore(session).reserve(receipt)
        if reservation.created:
            return reservation.receipt.command_id, None
        if reservation.receipt.status != "succeeded" or reservation.receipt.result_ref is None:
            raise DomainError(ErrorCode.RESPONSE_CONFLICT)
        return reservation.receipt.command_id, reservation.receipt.result_ref

    @staticmethod
    async def _complete_command(
        session: AsyncSession, command_id: UUID, view: MediaView
    ) -> None:
        await SqlCommandReceiptStore(session).complete(
            command_id=command_id,
            status="succeeded",
            result_ref=view.media_id,
            result_payload={"resource_id": str(view.media_id), "version": view.version},
        )

    async def _read_view(
        self, session: AsyncSession, media_id: UUID, now: datetime
    ) -> MediaView | None:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT a.*,r.media_revision_id,r.storage_key,r.declared_mime,r.detected_mime,"
                        "r.sha256,r.size_bytes,r.transcript_text,u.upload_id,u.byte_limit,u.expires_at AS upload_expires_at "
                        "FROM media.media_assets a JOIN media.media_revisions r "
                        "ON r.media_revision_id=a.current_revision_id LEFT JOIN media.media_uploads u "
                        "ON u.media_revision_id=r.media_revision_id WHERE a.media_id=:media"
                    ),
                    {"media": media_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        upload_url = None
        read_url = None
        url_expires_at = None
        if row["status"] == "reserved" and row["upload_id"] is not None:
            url_expires_at = min(cast(datetime, row["upload_expires_at"]), now + SIGNED_URL_LIFETIME)
            token = self._signer.issue(
                SignedObjectGrant(
                    "PUT",
                    str(row["upload_id"]),
                    str(row["storage_key"]),
                    url_expires_at,
                    int(row["byte_limit"]),
                )
            )
            upload_url = f"/api/v1/media/uploads/{row['upload_id']}/content?token={token}"
        if row["status"] == "ready":
            variant = (
                (
                    await session.execute(
                        text(
                            "SELECT storage_key,mime_type FROM media.media_variants "
                            "WHERE media_revision_id=:revision AND variant_type='normalized'"
                        ),
                        {"revision": row["media_revision_id"]},
                    )
                )
                .mappings()
                .one_or_none()
            )
            object_key = str(variant["storage_key"] if variant is not None else row["storage_key"])
            url_expires_at = now + SIGNED_URL_LIFETIME
            token = self._signer.issue(
                SignedObjectGrant("GET", str(media_id), object_key, url_expires_at, 0)
            )
            read_url = f"/api/v1/media/{media_id}/content?token={token}"
        return MediaView(
            media_id=_uuid(row["media_id"]),
            media_revision_id=_uuid(row["media_revision_id"]),
            upload_id=None if row["upload_id"] is None else _uuid(row["upload_id"]),
            media_type=str(row["media_type"]),
            status=str(row["status"]),
            privacy_class=str(row["privacy_class"]),
            declared_mime=str(row["declared_mime"]),
            detected_mime=cast(str | None, row["detected_mime"]),
            size_bytes=cast(int | None, row["size_bytes"]),
            checksum_sha256=str(row["sha256"]),
            quarantine_reason=cast(str | None, row["quarantine_reason"]),
            transcript=cast(str | None, row["transcript_text"]),
            upload_url=upload_url,
            read_url=read_url,
            url_expires_at=url_expires_at,
            created_at=cast(datetime, row["created_at"]),
            updated_at=cast(datetime, row["updated_at"]),
            version=int(row["version"]),
        )

    def _verify_token(
        self, token: str, *, method: str, resource_id: UUID
    ) -> SignedObjectGrant:
        try:
            return self._signer.verify(
                token,
                method=method,
                resource_id=str(resource_id),
                now=self._clock.now(),
            )
        except ValueError as error:
            raise DomainError(ErrorCode.FORBIDDEN) from error

    @staticmethod
    async def _set_actor(session: AsyncSession, actor_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"), {"actor": str(actor_id)}
        )
