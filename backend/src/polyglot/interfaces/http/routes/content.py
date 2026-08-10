from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Security, status
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
from polyglot.modules.content.application import (
    ApproveContentRevision,
    ContentApplicationService,
    ContentReference,
    CreateContentDraft,
    EditorialActor,
    PublishContentRevision,
    RetireContentRevision,
    ReviseContentDraft,
    ValidateContentRevision,
)
from polyglot.modules.content.persistence import (
    ContentRevisionPage,
    StoredContentRevision,
    StoredValidationFinding,
    StoredValidationReport,
)
from polyglot.modules.identity.application import IdentityApplicationService
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]
OriginHeader = Annotated[str, Header(alias="Origin")]
CsrfHeader = Annotated[str, Header(alias="X-CSRF-Token")]
IfMatchHeader = Annotated[str, Header(alias="If-Match")]
PageLimit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(min_length=1, max_length=1024)]
_session_cookie_security = APIKeyCookie(
    name=SESSION_COOKIE, scheme_name="SessionCookie", auto_error=False
)
SessionCookieToken = Annotated[str | None, Security(_session_cookie_security)]


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContentReferenceRequest(ClosedModel):
    reference_kind: str = Field(min_length=1, max_length=120)
    revision_id: UUID


class CreateContentDraftRequest(ClosedModel):
    content_type: str = Field(min_length=1, max_length=120)
    variety_id: UUID
    payload: dict[str, JsonValue]
    provenance_id: UUID
    rights_ref: str = Field(min_length=1, max_length=500)
    pinned_revision_refs: tuple[ContentReferenceRequest, ...] = ()


class ReviseContentDraftRequest(ClosedModel):
    payload: dict[str, JsonValue]
    provenance_id: UUID
    rights_ref: str = Field(min_length=1, max_length=500)
    pinned_revision_refs: tuple[ContentReferenceRequest, ...] = ()


class ValidateContentRevisionRequest(ClosedModel):
    validator_set_revision_id: UUID


class ApproveContentRevisionRequest(ClosedModel):
    reason_code: str = Field(min_length=1, max_length=120)


class PublishContentRevisionRequest(ClosedModel):
    publication_provenance_id: UUID
    channel_code: str = Field(min_length=1, max_length=40)
    compatibility_range: str = Field(min_length=1, max_length=120)


class ContentRevisionResponse(ClosedModel):
    content_revision_id: UUID
    content_id: UUID
    revision_no: int
    status: str
    payload: dict[str, JsonValue]
    payload_checksum: str
    provenance_id: UUID
    rights_ref: str
    pinned_revision_refs: tuple[dict[str, JsonValue], ...]
    created_by_actor_id: UUID
    approved_by_actor_id: UUID | None
    created_at: datetime
    validated_at: datetime | None
    approved_at: datetime | None
    published_at: datetime | None
    retired_at: datetime | None
    version: int | None = None
    report_id: UUID | None = None
    manifest_id: UUID | None = None


class ContentRevisionPageResponse(ClosedModel):
    items: tuple[ContentRevisionResponse, ...]
    next_cursor: str | None


class ValidationFindingResponse(ClosedModel):
    finding_id: UUID
    ordinal: int
    validator_code: str
    severity: str
    path: str
    message_code: str
    redacted_value: str | None


class ValidationReportResponse(ClosedModel):
    report_id: UUID
    subject_revision_id: UUID
    validator_set_revision_id: UUID
    status: str
    started_at: datetime
    completed_at: datetime
    summary_checksum: str
    findings: tuple[ValidationFindingResponse, ...]


def _references(
    references: tuple[ContentReferenceRequest, ...],
) -> tuple[ContentReference, ...]:
    return tuple(
        ContentReference(reference.reference_kind, reference.revision_id)
        for reference in references
    )


def _revision_response(
    revision: StoredContentRevision,
    *,
    version: int | None = None,
    report_id: UUID | None = None,
    manifest_id: UUID | None = None,
) -> ContentRevisionResponse:
    response = ContentRevisionResponse.model_validate(revision, from_attributes=True)
    return response.model_copy(
        update={
            "version": version,
            "report_id": report_id,
            "manifest_id": manifest_id,
        }
    )


def _page_response(page: ContentRevisionPage) -> ContentRevisionPageResponse:
    return ContentRevisionPageResponse(
        items=tuple(_revision_response(revision) for revision in page.items),
        next_cursor=page.next_cursor,
    )


def _finding_response(finding: StoredValidationFinding) -> ValidationFindingResponse:
    return ValidationFindingResponse.model_validate(finding, from_attributes=True)


def _report_response(report: StoredValidationReport) -> ValidationReportResponse:
    return ValidationReportResponse(
        report_id=report.report_id,
        subject_revision_id=report.subject_revision_id,
        validator_set_revision_id=report.validator_set_revision_id,
        status=report.status,
        started_at=report.started_at,
        completed_at=report.completed_at,
        summary_checksum=report.summary_checksum,
        findings=tuple(_finding_response(finding) for finding in report.findings),
    )


def content_router(
    service: ContentApplicationService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> ContentApplicationService:
        if service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        return service

    async def actor_for(
        request: Request,
        session_token: str | None,
        csrf_token: str | None = None,
        origin: str | None = None,
    ) -> EditorialActor:
        if identity_service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        if origin is not None:
            _require_origin(origin, allowed_origin)
        current = await identity_service.get_current_session(
            _session_token(session_token), _context(request)
        )
        if csrf_token is not None and csrf_token != current.csrf_token:
            raise DomainError(ErrorCode.FORBIDDEN)
        return EditorialActor(
            actor_id=current.account_id,
            roles=frozenset(current.roles),
            session_id=current.session_id,
        )

    @router.post(
        "/api/v1/authoring/drafts",
        operation_id="create_content_draft",
        response_model=ContentRevisionResponse,
        status_code=status.HTTP_201_CREATED,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def create_content_draft(
        payload: CreateContentDraftRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> ContentRevisionResponse:
        actor = await actor_for(request, session_token, csrf_token, origin)
        result = await application_service().create_draft(
            CreateContentDraft(
                actor=actor,
                content_type=payload.content_type,
                variety_id=payload.variety_id,
                payload=payload.payload,
                provenance_id=payload.provenance_id,
                rights_ref=payload.rights_ref,
                pinned_revision_refs=_references(payload.pinned_revision_refs),
                idempotency_key=idempotency_key,
                context=_context(request),
            )
        )
        return _revision_response(result.revision, version=result.version)

    @router.patch(
        "/api/v1/authoring/drafts/{draft_id}",
        operation_id="revise_content_draft",
        response_model=ContentRevisionResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def revise_content_draft(
        draft_id: UUID,
        payload: ReviseContentDraftRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> ContentRevisionResponse:
        actor = await actor_for(request, session_token, csrf_token, origin)
        result = await application_service().revise_draft(
            ReviseContentDraft(
                actor=actor,
                revision_id=draft_id,
                payload=payload.payload,
                provenance_id=payload.provenance_id,
                rights_ref=payload.rights_ref,
                pinned_revision_refs=_references(payload.pinned_revision_refs),
                expected_version=_expected_version(if_match),
                idempotency_key=idempotency_key,
                context=_context(request),
            )
        )
        return _revision_response(result.revision, version=result.version)

    @router.post(
        "/api/v1/authoring/drafts/{draft_id}:validate",
        operation_id="validate_content_revision",
        response_model=ContentRevisionResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def validate_content_revision(
        draft_id: UUID,
        payload: ValidateContentRevisionRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> ContentRevisionResponse:
        actor = await actor_for(request, session_token, csrf_token, origin)
        result = await application_service().validate_revision(
            ValidateContentRevision(
                actor=actor,
                revision_id=draft_id,
                validator_set_revision_id=payload.validator_set_revision_id,
                expected_version=_expected_version(if_match),
                idempotency_key=idempotency_key,
                context=_context(request),
            )
        )
        return _revision_response(
            result.revision,
            version=result.version,
            report_id=result.report_id,
        )

    @router.post(
        "/api/v1/authoring/drafts/{draft_id}:approve",
        operation_id="approve_content_revision",
        response_model=ContentRevisionResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def approve_content_revision(
        draft_id: UUID,
        payload: ApproveContentRevisionRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> ContentRevisionResponse:
        actor = await actor_for(request, session_token, csrf_token, origin)
        result = await application_service().approve_revision(
            ApproveContentRevision(
                actor=actor,
                revision_id=draft_id,
                expected_version=_expected_version(if_match),
                reason_code=payload.reason_code,
                idempotency_key=idempotency_key,
                context=_context(request),
            )
        )
        return _revision_response(result.revision, version=result.version)

    @router.post(
        "/api/v1/authoring/drafts/{draft_id}:publish",
        operation_id="publish_content_revision",
        response_model=ContentRevisionResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def publish_content_revision(
        draft_id: UUID,
        payload: PublishContentRevisionRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> ContentRevisionResponse:
        actor = await actor_for(request, session_token, csrf_token, origin)
        result = await application_service().publish_revision(
            PublishContentRevision(
                actor=actor,
                revision_id=draft_id,
                publication_provenance_id=payload.publication_provenance_id,
                channel_code=payload.channel_code,
                compatibility_range=payload.compatibility_range,
                expected_version=_expected_version(if_match),
                idempotency_key=idempotency_key,
                context=_context(request),
            )
        )
        return _revision_response(
            result.revision,
            version=result.version,
            manifest_id=result.manifest_id,
        )

    @router.post(
        "/api/v1/content/{content_id}/revisions/{revision_id}:retire",
        operation_id="retire_content_revision",
        response_model=ContentRevisionResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def retire_content_revision(
        content_id: UUID,
        revision_id: UUID,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> ContentRevisionResponse:
        actor = await actor_for(request, session_token, csrf_token, origin)
        result = await application_service().retire_revision(
            RetireContentRevision(
                actor=actor,
                content_id=content_id,
                revision_id=revision_id,
                expected_version=_expected_version(if_match),
                idempotency_key=idempotency_key,
                context=_context(request),
            )
        )
        return _revision_response(result.revision, version=result.version)

    @router.get(
        "/api/v1/authoring/drafts",
        operation_id="list_content_drafts",
        response_model=ContentRevisionPageResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def list_content_drafts(
        request: Request,
        limit: PageLimit = 20,
        cursor: Cursor = None,
        session_token: SessionCookieToken = None,
    ) -> ContentRevisionPageResponse:
        actor = await actor_for(request, session_token)
        return _page_response(
            await application_service().list_drafts(actor=actor, limit=limit, cursor=cursor)
        )

    @router.get(
        "/api/v1/authoring/drafts/{draft_id}",
        operation_id="get_content_draft",
        response_model=ContentRevisionResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def get_content_draft(
        draft_id: UUID,
        request: Request,
        session_token: SessionCookieToken = None,
    ) -> ContentRevisionResponse:
        actor = await actor_for(request, session_token)
        return _revision_response(
            await application_service().get_draft(actor=actor, revision_id=draft_id)
        )

    @router.get(
        "/api/v1/authoring/content/{id}/history",
        operation_id="get_content_history",
        response_model=ContentRevisionPageResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def get_content_history(
        id: UUID,
        request: Request,
        limit: PageLimit = 20,
        cursor: Cursor = None,
        session_token: SessionCookieToken = None,
    ) -> ContentRevisionPageResponse:
        actor = await actor_for(request, session_token)
        return _page_response(
            await application_service().get_history(
                actor=actor, content_id=id, limit=limit, cursor=cursor
            )
        )

    @router.get(
        "/api/v1/validation-reports/{id}",
        operation_id="get_validation_report",
        response_model=ValidationReportResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def get_validation_report(
        id: UUID,
        request: Request,
        session_token: SessionCookieToken = None,
    ) -> ValidationReportResponse:
        actor = await actor_for(request, session_token)
        return _report_response(
            await application_service().get_validation_report(actor=actor, report_id=id)
        )

    return router
