"""Authenticated W09 exercise execution routes."""

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
from polyglot.modules.exercises.core.application import (
    AttemptView,
    ContestCorrection,
    CorrectAttempt,
    CorrectionCaseView,
    ExerciseApplicationService,
    MarkCorrectionRead,
    OpenAttempt,
    ResolveCorrectionCase,
    SaveDraft,
    SubmitAttempt,
    UseHint,
)
from polyglot.modules.exercises.core.domain import AnswerKind, CorrectionStrategy, HintLevel
from polyglot.modules.identity.application import (
    CurrentSessionResult,
    IdentityApplicationService,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.ids import Uuid7Generator
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


class OpenAttemptRequest(ClosedModel):
    attempt_id: UUID
    profile_id: UUID
    attempt_no: int = Field(ge=1)
    started_at: datetime


class SaveDraftRequest(ClosedModel):
    draft_payload: dict[str, JsonValue]
    updated_at: datetime


class UseHintRequest(ClosedModel):
    hint_use_id: UUID
    hint_definition_revision_id: UUID
    level: HintLevel
    reason: str = Field(min_length=1, max_length=500)
    answer_state_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    effect_policy_revision_id: UUID
    shown_at: datetime


class SubmitAttemptRequest(ClosedModel):
    kind: AnswerKind
    raw_value: JsonValue
    input_method: str = Field(min_length=1, max_length=80)
    input_locale: str = Field(min_length=2, max_length=40)
    submitted_at: datetime


class SelfAssessAttemptRequest(ClosedModel):
    meaning: float = Field(ge=0, le=1)
    form: float = Field(ge=0, le=1)
    reviewed_at: datetime


class ContestCorrectionRequest(ClosedModel):
    case_id: UUID
    reason_code: str = Field(min_length=1, max_length=80)
    user_comment: str | None = Field(default=None, max_length=2000)
    opened_at: datetime


class MarkCorrectionReadRequest(ClosedModel):
    reviewed_at: datetime


class ResolveCorrectionCaseRequest(ClosedModel):
    case_review_id: UUID
    correction_id: UUID
    decision: str = Field(pattern=r"^(uphold|replace|not_evaluable)$")
    rationale: str = Field(min_length=1, max_length=4000)
    reviewed_at: datetime


class ExerciseInstanceResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    instance_id: UUID
    definition_revision_id: UUID
    language_pack_revision_id: UUID
    primitive_id: str
    response_kinds: tuple[AnswerKind, ...]
    stimulus_contract: dict[str, JsonValue]
    stimulus_revision_ids: tuple[UUID, ...]
    target_bindings: tuple[JsonValue, ...]
    lexical_bindings: tuple[JsonValue, ...]
    grammar_bindings: tuple[JsonValue, ...]
    seed: int


class AttemptResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    attempt_id: UUID
    profile_id: UUID
    instance_id: UUID
    attempt_no: int
    status: str
    terminal_reason: str
    answer_kind: AnswerKind | None
    raw_answer: JsonValue
    input_method: str | None
    input_locale: str | None
    submitted_at: datetime | None
    active_duration_ms: int
    correction_reviewed_at: datetime | None
    version: int
    started_at: datetime
    updated_at: datetime


class CorrectionResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    correction_id: UUID
    attempt_id: UUID
    revision_no: int
    verdict: str
    confidence: float
    target_coverage: float
    strategy: str
    proposed_answer: JsonValue
    alternatives: tuple[str, ...]
    explanation: str
    error_codes: tuple[str, ...]
    criterion_scores: dict[str, float]
    requires_review: bool
    supersedes_correction_id: UUID | None
    is_current: bool
    created_at: datetime


class CorrectionCaseResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    case_id: UUID
    attempt_id: UUID
    status: str
    reason_code: str
    user_comment: str | None
    resolution_correction_id: UUID | None
    version: int
    opened_at: datetime
    resolved_at: datetime | None


def exercises_router(
    service: ExerciseApplicationService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> ExerciseApplicationService:
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

    def attempt_response(response: Response, view: AttemptView) -> AttemptResponse:
        response.headers["ETag"] = f'"{view.version}"'
        return AttemptResponse.model_validate(view)

    def case_response(
        response: Response, view: CorrectionCaseView
    ) -> CorrectionCaseResponse:
        response.headers["ETag"] = f'"{view.version}"'
        return CorrectionCaseResponse.model_validate(view)

    @router.get(
        "/api/v1/exercise-instances/{id}",
        operation_id="get_exercise_instance",
        response_model=ExerciseInstanceResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def get_exercise_instance(
        id: UUID,
        request: Request,
        session_token: SessionCookieToken = None,
    ) -> ExerciseInstanceResponse:
        current = await session_for(request, session_token)
        view = await application_service().get_instance(current.account_id, id)
        return ExerciseInstanceResponse.model_validate(view)

    @router.get(
        "/api/v1/attempts/{id}",
        operation_id="get_attempt",
        response_model=AttemptResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def get_exercise_attempt(
        id: UUID,
        request: Request,
        response: Response,
        session_token: SessionCookieToken = None,
    ) -> AttemptResponse:
        current = await session_for(request, session_token)
        return attempt_response(
            response,
            await application_service().get_attempt(current.account_id, id),
        )

    @router.get(
        "/api/v1/correction-cases/{id}",
        operation_id="get_correction",
        response_model=CorrectionCaseResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def get_exercise_correction(
        id: UUID,
        request: Request,
        session_token: SessionCookieToken = None,
    ) -> CorrectionCaseResponse:
        current = await session_for(request, session_token)
        view = await application_service().get_correction_case(current.account_id, id)
        return CorrectionCaseResponse.model_validate(view)

    @router.post(
        "/api/v1/exercise-instances/{instance_id}/attempts",
        operation_id="open_exercise_attempt",
        response_model=AttemptResponse,
        status_code=201,
        responses=CREATED_ETAG_RESPONSE,
    )
    async def open_exercise_attempt(
        instance_id: UUID,
        payload: OpenAttemptRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> AttemptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().open_attempt(
            current.account_id,
            instance_id,
            OpenAttempt(**payload.model_dump()),
            idempotency_key=idempotency_key,
        )
        return attempt_response(response, view)

    @router.patch(
        "/api/v1/attempts/{attempt_id}/draft",
        operation_id="save_attempt_draft",
        response_model=AttemptResponse,
        responses=ETAG_RESPONSE,
    )
    async def save_attempt_draft(
        attempt_id: UUID,
        payload: SaveDraftRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> AttemptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().save_draft(
            current.account_id,
            attempt_id,
            SaveDraft(**payload.model_dump()),
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
        )
        return attempt_response(response, view)

    @router.post(
        "/api/v1/attempts/{attempt_id}/hints",
        operation_id="use_exercise_hint",
        response_model=AttemptResponse,
        responses=ETAG_RESPONSE,
    )
    async def use_exercise_hint(
        attempt_id: UUID,
        payload: UseHintRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> AttemptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().use_hint(
            current.account_id,
            attempt_id,
            UseHint(**payload.model_dump()),
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
        )
        return attempt_response(response, view)

    @router.post(
        "/api/v1/attempts/{attempt_id}:submit",
        operation_id="submit_exercise_attempt",
        response_model=AttemptResponse,
        responses=ETAG_RESPONSE,
    )
    async def submit_exercise_attempt(
        attempt_id: UUID,
        payload: SubmitAttemptRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> AttemptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().submit_attempt(
            current.account_id,
            attempt_id,
            SubmitAttempt(**payload.model_dump()),
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
        )
        return attempt_response(response, view)

    @router.post(
        "/api/v1/attempts/{attempt_id}:self-assess",
        operation_id="self_assess_exercise_attempt",
        response_model=AttemptResponse,
        responses=ETAG_RESPONSE,
    )
    async def self_assess_exercise_attempt(
        attempt_id: UUID,
        payload: SelfAssessAttemptRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> AttemptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        result = CorrectionStrategy.self_assessment(
            required_criteria=("meaning", "form"),
            passing_score=0.75,
        ).correct({"meaning": payload.meaning, "form": payload.form})
        view = await application_service().correct_attempt(
            current.account_id,
            attempt_id,
            CorrectAttempt(
                correction_id=Uuid7Generator().new(),
                result=result,
                provenance_id=None,
                rubric_revision_id=None,
                proposed_answer={"meaning": payload.meaning, "form": payload.form},
                requires_review=False,
                created_at=payload.reviewed_at,
            ),
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
        )
        return attempt_response(response, view)

    @router.post(
        "/api/v1/attempts/{attempt_id}/correction-case",
        operation_id="contest_correction",
        response_model=CorrectionCaseResponse,
        status_code=201,
        responses=CREATED_ETAG_RESPONSE,
    )
    async def contest_exercise_correction(
        attempt_id: UUID,
        payload: ContestCorrectionRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> CorrectionCaseResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().contest_correction(
            current.account_id,
            attempt_id,
            ContestCorrection(**payload.model_dump()),
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
        )
        return case_response(response, view)

    @router.post(
        "/api/v1/attempts/{attempt_id}:mark-correction-read",
        operation_id="review_correction",
        response_model=AttemptResponse,
        responses=ETAG_RESPONSE,
    )
    async def mark_exercise_correction_read(
        attempt_id: UUID,
        payload: MarkCorrectionReadRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> AttemptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().mark_correction_read(
            current.account_id,
            attempt_id,
            MarkCorrectionRead(**payload.model_dump()),
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
        )
        return attempt_response(response, view)

    @router.post(
        "/api/v1/correction-cases/{case_id}:resolve",
        operation_id="review_correction_case",
        response_model=CorrectionCaseResponse,
        responses=ETAG_RESPONSE,
    )
    async def resolve_exercise_correction_case(
        case_id: UUID,
        payload: ResolveCorrectionCaseRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> CorrectionCaseResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().resolve_correction_case(
            current.account_id,
            case_id,
            ResolveCorrectionCase(**payload.model_dump()),
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
        )
        return case_response(response, view)

    return router


__all__ = ["exercises_router"]
