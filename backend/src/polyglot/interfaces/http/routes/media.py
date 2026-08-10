"""Private media upload, delivery and local TTS routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, Security
from fastapi.responses import Response as BinaryResponse
from fastapi.security import APIKeyCookie
from pydantic import BaseModel, ConfigDict, Field

from polyglot.interfaces.http.routes.identity import (
    IDENTITY_PROBLEM_RESPONSES,
    SESSION_COOKIE,
    _context,
    _expected_version,
    _require_origin,
    _session_token,
)
from polyglot.modules.identity.application import CurrentSessionResult, IdentityApplicationService
from polyglot.modules.media.application import (
    MediaApplicationService,
    MediaView,
    ReserveMediaUpload,
    SynthesizeSpeech,
    TranscriptSegmentInput,
    TtsCapabilitiesView,
    TtsSynthesisView,
)
from polyglot.modules.media.domain import MediaKind
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]
OriginHeader = Annotated[str, Header(alias="Origin")]
CsrfHeader = Annotated[str, Header(alias="X-CSRF-Token")]
IfMatchHeader = Annotated[str, Header(alias="If-Match")]
SessionCookieToken = Annotated[
    str | None,
    Security(APIKeyCookie(name=SESSION_COOKIE, scheme_name="SessionCookie", auto_error=False)),
]
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    **IDENTITY_PROBLEM_RESPONSES,
    428: IDENTITY_PROBLEM_RESPONSES[422],
}
ETAG_RESPONSE: dict[int | str, dict[str, Any]] = {
    **PROBLEM_RESPONSES,
    200: {
        "headers": {
            "ETag": {
                "description": "Quoted optimistic concurrency version.",
                "schema": {"type": "string"},
            }
        }
    },
}


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyRequest(ClosedModel):
    pass


class TranscriptSegmentRequest(ClosedModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=20000)


class ReserveMediaUploadRequest(ClosedModel):
    kind: MediaKind
    declared_mime: str = Field(min_length=1, max_length=120)
    expected_size: int = Field(ge=0, le=500 * 1024 * 1024)
    expected_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license_ref: str = Field(min_length=1, max_length=240)
    provenance_ref: str = Field(min_length=1, max_length=240)
    rights_expires_at: datetime | None = None
    retention_expires_at: datetime | None = None
    transcript: str | None = Field(default=None, max_length=200000)
    segments: tuple[TranscriptSegmentRequest, ...] = Field(default=(), max_length=5000)


class SynthesizeSpeechRequest(ClosedModel):
    text: str = Field(min_length=1, max_length=5000)
    locale: str = Field(min_length=2, max_length=40)
    voice_id: str = Field(min_length=1, max_length=120)
    parameters: dict[str, str] = Field(default_factory=dict)


class MediaResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

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


class TtsVoiceResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    voice_id: str
    language_tags: tuple[str, ...]
    formats: tuple[str, ...]
    limits: dict[str, JsonValue]
    availability: str


class TtsCapabilitiesResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    catalog_revision_id: UUID
    provider_code: str
    provider_version: str
    voices: tuple[TtsVoiceResponse, ...]


class TtsSynthesisResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    voice_id: str
    availability: str
    cache_key: str | None
    media: MediaResponse | None


def media_router(
    service: MediaApplicationService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> MediaApplicationService:
        if service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        return service

    async def session_for(
        request: Request,
        session_token: str | None,
        csrf_token: str | None = None,
        origin: str | None = None,
    ) -> CurrentSessionResult:
        if identity_service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        if origin is not None:
            _require_origin(origin, allowed_origin)
        current = await identity_service.get_current_session(
            _session_token(session_token), _context(request)
        )
        if csrf_token is not None and csrf_token != current.csrf_token:
            raise DomainError(ErrorCode.FORBIDDEN)
        return current

    def expected_version(if_match: str | None) -> int:
        if if_match is None:
            raise HTTPException(status_code=428, detail="If-Match is required")
        return _expected_version(if_match)

    def media_response(response: Response, view: MediaView) -> MediaResponse:
        response.headers["ETag"] = f'"{view.version}"'
        return MediaResponse.model_validate(view)

    @router.get(
        "/api/v1/media/tts/capabilities",
        operation_id="get_tts_capabilities",
        response_model=TtsCapabilitiesResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def get_tts_capabilities(
        request: Request,
        language: Annotated[str, Query(min_length=2, max_length=40)],
        session_token: SessionCookieToken = None,
    ) -> TtsCapabilitiesResponse:
        await session_for(request, session_token)
        view: TtsCapabilitiesView = await application_service().tts_capabilities(language)
        return TtsCapabilitiesResponse.model_validate(view)

    @router.post(
        "/api/v1/media/tts/syntheses",
        operation_id="synthesize_speech",
        response_model=TtsSynthesisResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def synthesize_speech(
        payload: SynthesizeSpeechRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> TtsSynthesisResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view: TtsSynthesisView = await application_service().synthesize(
            current.account_id,
            SynthesizeSpeech(**payload.model_dump()),
            idempotency_key=idempotency_key,
        )
        return TtsSynthesisResponse.model_validate(view)

    @router.post(
        "/api/v1/media/uploads",
        operation_id="reserve_media_upload",
        response_model=MediaResponse,
        status_code=201,
        responses={**PROBLEM_RESPONSES, 201: ETAG_RESPONSE[200]},
    )
    async def reserve_media_upload(
        payload: ReserveMediaUploadRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> MediaResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        segments = tuple(TranscriptSegmentInput(**item.model_dump()) for item in payload.segments)
        data = payload.model_dump(exclude={"segments"})
        view = await application_service().reserve_upload(
            current.account_id,
            ReserveMediaUpload(**data, segments=segments),
            idempotency_key=idempotency_key,
        )
        return media_response(response, view)

    @router.put(
        "/api/v1/media/uploads/{upload_id}/content",
        operation_id="put_signed_media_upload",
        status_code=204,
        response_model=None,
        responses=PROBLEM_RESPONSES,
    )
    async def put_signed_media_upload(
        upload_id: UUID,
        request: Request,
        token: Annotated[str, Query(min_length=20, max_length=2000)],
    ) -> Response:
        raw_length = request.headers.get("content-length")
        if raw_length is not None:
            try:
                content_length = int(raw_length)
            except ValueError as error:
                raise DomainError(ErrorCode.VALIDATION_FAILED) from error
            if content_length < 0:
                raise DomainError(ErrorCode.VALIDATION_FAILED)
            if content_length > 500 * 1024 * 1024:
                raise DomainError(ErrorCode.MEDIA_QUOTA_EXCEEDED)
        await application_service().put_signed_upload(upload_id, token, await request.body())
        return Response(status_code=204)

    @router.post(
        "/api/v1/media/uploads/{upload_id}:complete",
        operation_id="complete_media_upload",
        response_model=MediaResponse,
        responses=ETAG_RESPONSE,
    )
    async def complete_media_upload(
        upload_id: UUID,
        _: EmptyRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> MediaResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().complete_upload(
            current.account_id, upload_id, idempotency_key=idempotency_key
        )
        return media_response(response, view)

    @router.get(
        "/api/v1/media/{media_id}",
        operation_id="get_media",
        response_model=MediaResponse,
        responses=ETAG_RESPONSE,
    )
    async def get_media(
        media_id: UUID,
        request: Request,
        response: Response,
        session_token: SessionCookieToken = None,
    ) -> MediaResponse:
        current = await session_for(request, session_token)
        return media_response(
            response, await application_service().get_media(current.account_id, media_id)
        )

    @router.get(
        "/api/v1/media/{media_id}/content",
        operation_id="read_signed_media",
        response_class=BinaryResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def read_signed_media(
        media_id: UUID,
        token: Annotated[str, Query(min_length=20, max_length=2000)],
    ) -> BinaryResponse:
        content, mime = await application_service().read_signed_media(media_id, token)
        return BinaryResponse(content=content, media_type=mime)

    @router.delete(
        "/api/v1/media/{media_id}",
        operation_id="delete_media",
        response_model=MediaResponse,
        responses=ETAG_RESPONSE,
    )
    async def delete_media(
        media_id: UUID,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> MediaResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().delete_media(
            current.account_id,
            media_id,
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
        )
        return media_response(response, view)

    return router
