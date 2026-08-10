"""Authenticated four-modality assessment routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response, Security
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
from polyglot.modules.assessments.application import (
    AssessmentApplicationService,
    AssessmentRunView,
    PrepareAssessment,
    ResolveAssessmentReview,
    SaveAssessmentResponse,
)
from polyglot.modules.assessments.domain import AssessmentModality
from polyglot.modules.identity.application import CurrentSessionResult, IdentityApplicationService
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
CREATED_ETAG_RESPONSE: dict[int | str, dict[str, Any]] = {
    **PROBLEM_RESPONSES,
    201: ETAG_RESPONSE[200],
}


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyRequest(ClosedModel):
    pass


class PrepareAssessmentRequest(ClosedModel):
    run_id: UUID
    modality: AssessmentModality
    seed: str = Field(min_length=1, max_length=160)
    target_snapshot: dict[str, JsonValue] = Field(default_factory=dict)
    capabilities: tuple[str, ...] = Field(default=(), max_length=40)


class SaveAssessmentResponseRequest(ClosedModel):
    answer: dict[str, JsonValue]
    expected_response_version: int = Field(ge=0)


class ResolveAssessmentReviewRequest(ClosedModel):
    rubric_revision: str = Field(min_length=1, max_length=80)
    criterion_scores: dict[str, JsonValue]
    annotations: tuple[dict[str, JsonValue], ...] = Field(default=(), max_length=200)


class AssessmentItemResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    item_id: UUID
    section_id: UUID
    ordinal: int
    item_kind: str
    answer_kind: str
    weight: float
    coverage_targets: tuple[str, ...]
    prompt: dict[str, JsonValue]
    media_ref: str | None
    max_plays: int | None
    answer: dict[str, JsonValue] | None
    response_version: int
    saved_at: datetime | None


class AssessmentSectionResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    section_id: UUID
    ordinal: int
    section_type: str
    title: str
    instructions: str
    weight: float
    status: str
    items: tuple[AssessmentItemResponse, ...]


class AssessmentResultResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    result_id: UUID
    modality: str
    status: str
    score: float | None
    band: str | None
    confidence: float
    coverage: float
    integrity_factor: float
    limiting_criteria: tuple[str, ...]
    policy_revision: str
    created_at: datetime


class AssessmentRunResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    run_id: UUID
    profile_id: UUID
    modality: str
    status: str
    protocol_code: str
    form_code: str
    time_limit_ms: int
    pause_allowed: bool
    prepared_at: datetime
    started_at: datetime | None
    deadline_at: datetime | None
    paused_at: datetime | None
    remaining_time_ms: int | None
    submitted_at: datetime | None
    completed_at: datetime | None
    server_now: datetime
    sections: tuple[AssessmentSectionResponse, ...]
    result: AssessmentResultResponse | None
    version: int


def assessments_router(
    service: AssessmentApplicationService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> AssessmentApplicationService:
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

    def run_response(response: Response, view: AssessmentRunView) -> AssessmentRunResponse:
        response.headers["ETag"] = f'"{view.version}"'
        return AssessmentRunResponse.model_validate(view)

    @router.post(
        "/api/v1/language-profiles/{profile_id}/assessments",
        operation_id="prepare_assessment",
        response_model=AssessmentRunResponse,
        status_code=201,
        responses=CREATED_ETAG_RESPONSE,
    )
    async def prepare_assessment(
        profile_id: UUID,
        payload: PrepareAssessmentRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> AssessmentRunResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().prepare(
            current.account_id,
            profile_id,
            PrepareAssessment(**payload.model_dump()),
            idempotency_key=idempotency_key,
        )
        return run_response(response, view)

    @router.get(
        "/api/v1/assessments/{id}",
        operation_id="get_assessment_run",
        response_model=AssessmentRunResponse,
        responses=ETAG_RESPONSE,
    )
    async def get_assessment_run(
        id: UUID,
        request: Request,
        response: Response,
        session_token: SessionCookieToken = None,
    ) -> AssessmentRunResponse:
        current = await session_for(request, session_token)
        return run_response(response, await application_service().get_run(current.account_id, id))

    async def transition(
        action: str,
        run_id: UUID,
        request: Request,
        response: Response,
        idempotency_key: str,
        origin: str,
        csrf_token: str,
        if_match: str,
        session_token: str | None,
    ) -> AssessmentRunResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        method = getattr(application_service(), action)
        view = await method(
            current.account_id,
            run_id,
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
        )
        return run_response(response, view)

    @router.post(
        "/api/v1/assessments/{run_id}:start",
        operation_id="start_assessment",
        response_model=AssessmentRunResponse,
        responses=ETAG_RESPONSE,
    )
    async def start_assessment(
        run_id: UUID,
        _: EmptyRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> AssessmentRunResponse:
        return await transition(
            "start",
            run_id,
            request,
            response,
            idempotency_key,
            origin,
            csrf_token,
            if_match,
            session_token,
        )

    @router.patch(
        "/api/v1/assessments/{run_id}/responses/{item_id}",
        operation_id="save_assessment_response",
        response_model=AssessmentRunResponse,
        responses=ETAG_RESPONSE,
    )
    async def save_assessment_response(
        run_id: UUID,
        item_id: UUID,
        payload: SaveAssessmentResponseRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> AssessmentRunResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().save_response(
            current.account_id,
            run_id,
            item_id,
            SaveAssessmentResponse(**payload.model_dump()),
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
        )
        return run_response(response, view)

    def add_transition_route(path: str, action: str) -> None:
        async def endpoint(
            run_id: UUID,
            _: EmptyRequest,
            request: Request,
            response: Response,
            idempotency_key: IdempotencyKey,
            origin: OriginHeader,
            csrf_token: CsrfHeader,
            if_match: IfMatchHeader,
            session_token: SessionCookieToken = None,
        ) -> AssessmentRunResponse:
            return await transition(
                action,
                run_id,
                request,
                response,
                idempotency_key,
                origin,
                csrf_token,
                if_match,
                session_token,
            )

        router.add_api_route(
            path,
            endpoint,
            methods=["POST"],
            operation_id=f"{action}_assessment",
            response_model=AssessmentRunResponse,
            responses=ETAG_RESPONSE,
        )

    add_transition_route("/api/v1/assessments/{run_id}:pause", "pause")
    add_transition_route("/api/v1/assessments/{run_id}:resume", "resume")
    add_transition_route("/api/v1/assessments/{run_id}:submit", "submit")

    @router.post(
        "/api/v1/assessments/{run_id}:resolve-review",
        operation_id="resolve_assessment_review",
        response_model=AssessmentRunResponse,
        responses=ETAG_RESPONSE,
    )
    async def resolve_assessment_review(
        run_id: UUID,
        payload: ResolveAssessmentReviewRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> AssessmentRunResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        if not {"content_reviewer", "administrator"}.intersection(current.roles):
            raise DomainError(ErrorCode.FORBIDDEN)
        view = await application_service().resolve_review(
            current.account_id,
            run_id,
            ResolveAssessmentReview(**payload.model_dump()),
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
        )
        return run_response(response, view)

    return router
