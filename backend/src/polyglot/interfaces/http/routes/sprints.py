"""Authenticated deterministic sprint planning and execution routes."""

from __future__ import annotations

from datetime import date, datetime
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
from polyglot.modules.identity.application import (
    CurrentSessionResult,
    IdentityApplicationService,
)
from polyglot.modules.sprints.application import (
    AbandonExerciseBlock,
    ComposeDailySession,
    ComposeFreePractice,
    InterruptSprintRun,
    SessionPlanView,
    SkipExerciseBlock,
    SprintApplicationService,
    SprintRunView,
    StartSprintRun,
    StopSprintRun,
)
from polyglot.platform.errors import DomainError, ErrorCode

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


class ComposeDailyRequest(ClosedModel):
    plan_id: UUID
    snapshot_id: UUID
    pedagogical_day: date
    budget_minutes: int = Field(ge=10, le=60, multiple_of=5)


class ComposeFreeRequest(ComposeDailyRequest):
    target_refs: tuple[str, ...] = Field(min_length=1, max_length=80)
    primitive_ids: tuple[str, ...] = Field(min_length=1, max_length=16)
    modalities: tuple[str, ...] = Field(min_length=1, max_length=4)
    challenge: str
    allow_novelty: bool
    vocabulary_list_snapshot_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    context_family_ref: str | None = Field(default=None, max_length=240)
    private_context: str | None = Field(default=None, max_length=4000)


class StartRunRequest(ClosedModel):
    run_id: UUID


class ReasonRequest(ClosedModel):
    reason: str = Field(min_length=1, max_length=240)


class PlanBlockResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    block_id: UUID
    ordinal: int
    family: str
    roles: tuple[str, ...]
    reason_codes: tuple[str, ...]
    modalities: tuple[str, ...]
    p50_seconds: int
    p80_seconds: int
    required: bool
    delayed_recode_id: UUID | None
    exercise_instance_ids: tuple[UUID, ...]


class SessionPlanResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    plan_id: UUID
    plan_revision_id: UUID
    snapshot_id: UUID
    profile_id: UUID
    plan_kind: str
    pedagogical_day: date
    budget_minutes: int
    status: str
    failure_code: str | None
    total_p50_seconds: int
    total_p80_seconds: int
    novelty_points: float
    plan_fingerprint: str
    blocks: tuple[PlanBlockResponse, ...]
    version: int
    created_at: datetime
    updated_at: datetime


class SprintBlockResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    block_id: UUID
    session_plan_block_id: UUID
    ordinal: int
    family: str
    status: str
    required: bool
    reason: str | None
    exercise_instance_ids: tuple[UUID, ...]
    version: int


class SprintRunResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    run_id: UUID
    plan_id: UUID
    plan_revision_id: UUID
    profile_id: UUID
    plan_kind: str
    pedagogical_day: date
    status: str
    current_block_id: UUID | None
    blocks: tuple[SprintBlockResponse, ...]
    started_at: datetime
    interrupted_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime
    stop_reason: str | None
    active_duration_ms: int
    consumes_module_day: bool
    version: int
    updated_at: datetime


def sprints_router(
    service: SprintApplicationService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> SprintApplicationService:
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

    def plan_response(response: Response, view: SessionPlanView) -> SessionPlanResponse:
        response.headers["ETag"] = f'"{view.version}"'
        return SessionPlanResponse.model_validate(view)

    def run_response(response: Response, view: SprintRunView) -> SprintRunResponse:
        response.headers["ETag"] = f'"{view.version}"'
        return SprintRunResponse.model_validate(view)

    @router.get(
        "/api/v1/session-plans/{id}",
        operation_id="get_session_plan",
        response_model=SessionPlanResponse,
        responses=ETAG_RESPONSE,
    )
    async def get_session_plan(
        id: UUID,
        request: Request,
        response: Response,
        session_token: SessionCookieToken = None,
    ) -> SessionPlanResponse:
        current = await session_for(request, session_token)
        return plan_response(response, await application_service().get_plan(current.account_id, id))

    @router.post(
        "/api/v1/language-profiles/{profile_id}/daily-plans",
        operation_id="compose_daily_session",
        response_model=SessionPlanResponse,
        status_code=201,
        responses=CREATED_ETAG_RESPONSE,
    )
    async def compose_daily_session(
        profile_id: UUID,
        payload: ComposeDailyRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> SessionPlanResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().compose_daily(
            current.account_id,
            profile_id,
            ComposeDailySession(**payload.model_dump()),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        return plan_response(response, view)

    @router.post(
        "/api/v1/language-profiles/{profile_id}/free-practice-plans",
        operation_id="compose_free_practice",
        response_model=SessionPlanResponse,
        status_code=201,
        responses=CREATED_ETAG_RESPONSE,
    )
    async def compose_free_practice(
        profile_id: UUID,
        payload: ComposeFreeRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> SessionPlanResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().compose_free(
            current.account_id,
            profile_id,
            ComposeFreePractice(**payload.model_dump()),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        return plan_response(response, view)

    async def plan_transition(
        plan_id: UUID,
        request: Request,
        response: Response,
        idempotency_key: str,
        origin: str,
        csrf_token: str,
        if_match: str,
        session_token: str | None,
        action: str,
    ) -> SessionPlanResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        method = (
            application_service().prepare
            if action == "prepare"
            else application_service().cancel_plan
        )
        view = await method(
            current.account_id,
            plan_id,
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        return plan_response(response, view)

    @router.post(
        "/api/v1/session-plans/{plan_id}:prepare",
        operation_id="prepare_session_plan",
        response_model=SessionPlanResponse,
        responses=ETAG_RESPONSE,
    )
    async def prepare_session_plan(
        plan_id: UUID,
        payload: EmptyRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> SessionPlanResponse:
        del payload
        return await plan_transition(
            plan_id,
            request,
            response,
            idempotency_key,
            origin,
            csrf_token,
            if_match,
            session_token,
            "prepare",
        )

    @router.post(
        "/api/v1/session-plans/{plan_id}:cancel",
        operation_id="cancel_session_plan",
        response_model=SessionPlanResponse,
        responses=ETAG_RESPONSE,
    )
    async def cancel_session_plan(
        plan_id: UUID,
        payload: EmptyRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> SessionPlanResponse:
        del payload
        return await plan_transition(
            plan_id,
            request,
            response,
            idempotency_key,
            origin,
            csrf_token,
            if_match,
            session_token,
            "cancel",
        )

    @router.post(
        "/api/v1/session-plans/{plan_id}/runs",
        operation_id="start_sprint_run",
        response_model=SprintRunResponse,
        status_code=201,
        responses=CREATED_ETAG_RESPONSE,
    )
    async def start_sprint_run(
        plan_id: UUID,
        payload: StartRunRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> SprintRunResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().start_run(
            current.account_id,
            plan_id,
            StartSprintRun(**payload.model_dump()),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        return run_response(response, view)

    @router.get(
        "/api/v1/sprint-runs/{id}",
        operation_id="get_sprint_run",
        response_model=SprintRunResponse,
        responses=ETAG_RESPONSE,
    )
    async def get_sprint_run(
        id: UUID,
        request: Request,
        response: Response,
        session_token: SessionCookieToken = None,
    ) -> SprintRunResponse:
        current = await session_for(request, session_token)
        return run_response(response, await application_service().get_run(current.account_id, id))

    async def run_transition(
        run_id: UUID,
        request: Request,
        response: Response,
        idempotency_key: str,
        origin: str,
        csrf_token: str,
        if_match: str,
        session_token: str | None,
        action: str,
        reason: str | None = None,
    ) -> SprintRunResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        app_service = application_service()
        version = expected_version(if_match)
        context = _context(request)
        if action == "interrupt":
            view = await app_service.interrupt_run(
                current.account_id,
                run_id,
                InterruptSprintRun(reason or ""),
                expected_version=version,
                idempotency_key=idempotency_key,
                context=context,
            )
        elif action == "stop":
            view = await app_service.stop_run(
                current.account_id,
                run_id,
                StopSprintRun(reason or ""),
                expected_version=version,
                idempotency_key=idempotency_key,
                context=context,
            )
        elif action == "resume":
            view = await app_service.resume_run(
                current.account_id,
                run_id,
                expected_version=version,
                idempotency_key=idempotency_key,
                context=context,
            )
        else:
            view = await app_service.complete_run(
                current.account_id,
                run_id,
                expected_version=version,
                idempotency_key=idempotency_key,
                context=context,
            )
        return run_response(response, view)

    @router.post(
        "/api/v1/sprint-runs/{run_id}:interrupt",
        operation_id="interrupt_sprint_run",
        response_model=SprintRunResponse,
        responses=ETAG_RESPONSE,
    )
    async def interrupt_sprint_run(
        run_id: UUID,
        payload: ReasonRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> SprintRunResponse:
        return await run_transition(
            run_id,
            request,
            response,
            idempotency_key,
            origin,
            csrf_token,
            if_match,
            session_token,
            "interrupt",
            payload.reason,
        )

    @router.post(
        "/api/v1/sprint-runs/{run_id}:resume",
        operation_id="resume_sprint_run",
        response_model=SprintRunResponse,
        responses=ETAG_RESPONSE,
    )
    async def resume_sprint_run(
        run_id: UUID,
        payload: EmptyRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> SprintRunResponse:
        del payload
        return await run_transition(
            run_id,
            request,
            response,
            idempotency_key,
            origin,
            csrf_token,
            if_match,
            session_token,
            "resume",
        )

    @router.post(
        "/api/v1/sprint-runs/{run_id}:stop",
        operation_id="stop_sprint_run",
        response_model=SprintRunResponse,
        responses=ETAG_RESPONSE,
    )
    async def stop_sprint_run(
        run_id: UUID,
        payload: ReasonRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> SprintRunResponse:
        return await run_transition(
            run_id,
            request,
            response,
            idempotency_key,
            origin,
            csrf_token,
            if_match,
            session_token,
            "stop",
            payload.reason,
        )

    @router.post(
        "/api/v1/sprint-runs/{run_id}:complete",
        operation_id="complete_sprint_run",
        response_model=SprintRunResponse,
        responses=ETAG_RESPONSE,
    )
    async def complete_sprint_run(
        run_id: UUID,
        payload: EmptyRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> SprintRunResponse:
        del payload
        return await run_transition(
            run_id,
            request,
            response,
            idempotency_key,
            origin,
            csrf_token,
            if_match,
            session_token,
            "complete",
        )

    async def block_transition(
        run_id: UUID,
        block_id: UUID,
        payload: ReasonRequest,
        request: Request,
        response: Response,
        idempotency_key: str,
        origin: str,
        csrf_token: str,
        if_match: str,
        session_token: str | None,
        action: str,
    ) -> SprintRunResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        command = (
            SkipExerciseBlock(payload.reason)
            if action == "skip"
            else AbandonExerciseBlock(payload.reason)
        )
        method = (
            application_service().skip_block
            if action == "skip"
            else application_service().abandon_block
        )
        view = await method(
            current.account_id,
            run_id,
            block_id,
            command,  # type: ignore[arg-type]
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        return run_response(response, view)

    @router.post(
        "/api/v1/sprint-runs/{run_id}/blocks/{block_id}:skip",
        operation_id="skip_exercise_block",
        response_model=SprintRunResponse,
        responses=ETAG_RESPONSE,
    )
    async def skip_exercise_block(
        run_id: UUID,
        block_id: UUID,
        payload: ReasonRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> SprintRunResponse:
        return await block_transition(
            run_id,
            block_id,
            payload,
            request,
            response,
            idempotency_key,
            origin,
            csrf_token,
            if_match,
            session_token,
            "skip",
        )

    @router.post(
        "/api/v1/sprint-runs/{run_id}/blocks/{block_id}:abandon",
        operation_id="abandon_exercise_block",
        response_model=SprintRunResponse,
        responses=ETAG_RESPONSE,
    )
    async def abandon_exercise_block(
        run_id: UUID,
        block_id: UUID,
        payload: ReasonRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> SprintRunResponse:
        return await block_transition(
            run_id,
            block_id,
            payload,
            request,
            response,
            idempotency_key,
            origin,
            csrf_token,
            if_match,
            session_token,
            "abandon",
        )

    return router


__all__ = ["sprints_router"]
