"""Authenticated W07 memory scheduling routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, Security
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
from polyglot.modules.lexicon.memory.application import (
    ArchiveMemoryPrompt,
    CreateMemoryPrompt,
    DeleteMemoryPrompt,
    ResetMemoryPrompt,
    RestoreMemoryPrompt,
    ResumeMemoryPrompt,
    SubmitMemoryReview,
    SuspendMemoryPrompt,
)
from polyglot.modules.lexicon.memory.domain import MemoryAggregate
from polyglot.modules.lexicon.memory.persistence import DueMemoryPrompt
from polyglot.modules.lexicon.memory.policy import (
    HintLevel,
    ReviewVerdict,
    SchedulerPolicy,
)
from polyglot.modules.lexicon.memory.ports import MemoryRating
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


class CreateMemoryPromptRequest(ClosedModel):
    prompt_id: UUID
    target_ref: UUID
    target_revision_id: UUID
    direction: str = Field(min_length=1, max_length=80)
    modality: str = Field(min_length=1, max_length=40)
    operation: str = Field(min_length=1, max_length=80)
    protocol_id: str = Field(min_length=1, max_length=120)
    protocol_revision: int = Field(ge=1)
    rating_semantics_id: str = Field(min_length=1, max_length=120)
    scheduler_policy_id: UUID
    created_at: datetime


class SubmitMemoryReviewRequest(ClosedModel):
    review_id: UUID
    opportunity_id: UUID
    attempt_id: UUID | None = None
    response_ref: str | None = Field(default=None, max_length=512)
    correction_ref: str | None = Field(default=None, max_length=512)
    verdict: ReviewVerdict
    highest_hint: HintLevel
    rating: MemoryRating
    certified_recall: bool
    answer_revealed: bool = False
    exposure_only: bool = False
    incidental_production: bool = False
    self_reported: bool = False
    active_duration_ms: int = Field(ge=0, le=3_600_000)
    scheduled_at: datetime
    reviewed_at: datetime
    certification_ref: str = Field(min_length=1, max_length=512)
    certified_operation: str = Field(min_length=1, max_length=80)
    certified_protocol_id: str = Field(min_length=1, max_length=120)
    certified_protocol_revision: int = Field(ge=1)
    certified_target_revision_id: UUID


class AtRequest(ClosedModel):
    at: datetime


class ResumeMemoryPromptRequest(ClosedModel):
    resumption_id: UUID
    resumed_at: datetime


class ResetMemoryPromptRequest(ClosedModel):
    reset_id: UUID
    reason: str = Field(min_length=1, max_length=500)
    reset_at: datetime


class RestoreMemoryPromptRequest(ClosedModel):
    resumption_id: UUID
    restored_at: datetime


class MergeMemoryPromptsRequest(ClosedModel):
    canonical_prompt_id: UUID
    source_prompt_ids: tuple[UUID, ...] = Field(min_length=2, max_length=100)
    expected_versions: dict[UUID, int] = Field(min_length=2, max_length=100)
    merged_at: datetime


class DeleteMemoryPromptRequest(ClosedModel):
    deleted_at: datetime


class MemoryScheduleResponse(ClosedModel):
    state: str
    due_at: datetime
    reps: int
    lapses: int
    projection_version: int
    scheduler_kind: str
    scheduler_version: str
    parameter_set_id: str
    policy_revision: int


class MemoryPromptResponse(ClosedModel):
    prompt_id: UUID
    profile_id: UUID
    target_ref: UUID
    target_revision_id: UUID
    direction: str
    modality: str
    operation: str
    protocol_id: str
    protocol_revision: int
    status: str
    version: int
    schedule: MemoryScheduleResponse


class DueMemoryPromptResponse(ClosedModel):
    prompt: MemoryPromptResponse
    overdue_seconds: int
    reason: str


class DueMemoryPromptPageResponse(ClosedModel):
    items: tuple[DueMemoryPromptResponse, ...]
    next_cursor: str | None
    cutoff: datetime


def _prompt_response(aggregate: MemoryAggregate) -> MemoryPromptResponse:
    prompt = aggregate.prompt
    schedule = aggregate.schedule
    return MemoryPromptResponse(
        prompt_id=prompt.prompt_id,
        profile_id=prompt.profile_id,
        target_ref=prompt.target_ref,
        target_revision_id=prompt.target_revision_id,
        direction=prompt.direction,
        modality=prompt.modality,
        operation=prompt.operation,
        protocol_id=prompt.protocol_id,
        protocol_revision=prompt.protocol_revision,
        status=prompt.status.value,
        version=prompt.version,
        schedule=MemoryScheduleResponse(
            state=schedule.state.value,
            due_at=schedule.due_at,
            reps=schedule.reps,
            lapses=schedule.lapses,
            projection_version=schedule.projection_version,
            scheduler_kind=schedule.scheduler_kind,
            scheduler_version=schedule.scheduler_version,
            parameter_set_id=schedule.parameter_set_id,
            policy_revision=schedule.policy_revision,
        ),
    )


class MemoryService(Protocol):
    async def create(
        self,
        actor_id: UUID,
        command: CreateMemoryPrompt,
        policy: SchedulerPolicy,
        *,
        idempotency_key: str,
    ) -> MemoryAggregate: ...

    async def submit_review(
        self,
        actor_id: UUID,
        prompt_id: UUID,
        command: SubmitMemoryReview,
        policy: SchedulerPolicy,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> MemoryAggregate: ...

    async def transition(
        self,
        actor_id: UUID,
        prompt_id: UUID,
        command: object,
        policy: SchedulerPolicy,
        *,
        expected_version: int,
        idempotency_key: str,
        session_id: UUID | None = None,
    ) -> MemoryAggregate: ...

    async def merge(
        self,
        actor_id: UUID,
        source_prompt_ids: tuple[UUID, ...],
        expected_versions: dict[UUID, int],
        canonical_prompt_id: UUID,
        merged_at: datetime,
        policy: SchedulerPolicy,
        *,
        idempotency_key: str,
    ) -> MemoryAggregate: ...

    async def list_due(
        self,
        actor_id: UUID,
        profile_id: UUID,
        cutoff: datetime,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[tuple[DueMemoryPrompt, ...], str | None]: ...


def memory_router(
    service: MemoryService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()
    policy = SchedulerPolicy.default()

    def application_service() -> MemoryService:
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

    def with_etag(response: Response, aggregate: MemoryAggregate) -> MemoryPromptResponse:
        response.headers["ETag"] = f'"{aggregate.prompt.version}"'
        return _prompt_response(aggregate)

    @router.post(
        "/api/v1/language-profiles/{profile_id}/memory-prompts",
        operation_id="create_memory_prompt",
        response_model=MemoryPromptResponse,
        status_code=201,
        responses=CREATED_ETAG_RESPONSE,
    )
    async def create_memory_prompt(
        profile_id: UUID,
        payload: CreateMemoryPromptRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> MemoryPromptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        aggregate = await application_service().create(
            current.account_id,
            CreateMemoryPrompt(profile_id=profile_id, **payload.model_dump()),
            policy,
            idempotency_key=idempotency_key,
        )
        return with_etag(response, aggregate)

    @router.post(
        "/api/v1/memory-prompts/{prompt_id}/reviews",
        operation_id="submit_memory_review",
        response_model=MemoryPromptResponse,
        responses=ETAG_RESPONSE,
    )
    async def submit_memory_review(
        prompt_id: UUID,
        payload: SubmitMemoryReviewRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> MemoryPromptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        aggregate = await application_service().submit_review(
            current.account_id,
            prompt_id,
            SubmitMemoryReview(
                **payload.model_dump(),
                idempotency_key=idempotency_key,
            ),
            policy,
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
        )
        return with_etag(response, aggregate)

    async def run_transition(
        *,
        current: CurrentSessionResult,
        prompt_id: UUID,
        command: object,
        if_match: str,
        idempotency_key: str,
        response: Response,
        include_session: bool = False,
    ) -> MemoryPromptResponse:
        aggregate = await application_service().transition(
            current.account_id,
            prompt_id,
            command,
            policy,
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
            session_id=current.session_id if include_session else None,
        )
        return with_etag(response, aggregate)

    @router.post(
        "/api/v1/memory-prompts/{prompt_id}:suspend",
        operation_id="suspend_memory_prompt",
        response_model=MemoryPromptResponse,
        responses=ETAG_RESPONSE,
    )
    async def suspend_memory_prompt(
        prompt_id: UUID,
        payload: AtRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> MemoryPromptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        return await run_transition(
            current=current,
            prompt_id=prompt_id,
            command=SuspendMemoryPrompt(payload.at),
            if_match=if_match,
            idempotency_key=idempotency_key,
            response=response,
        )

    @router.post(
        "/api/v1/memory-prompts/{prompt_id}:resume",
        operation_id="resume_memory_prompt",
        response_model=MemoryPromptResponse,
        responses=ETAG_RESPONSE,
    )
    async def resume_memory_prompt(
        prompt_id: UUID,
        payload: ResumeMemoryPromptRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> MemoryPromptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        return await run_transition(
            current=current,
            prompt_id=prompt_id,
            command=ResumeMemoryPrompt(**payload.model_dump()),
            if_match=if_match,
            idempotency_key=idempotency_key,
            response=response,
        )

    @router.post(
        "/api/v1/memory-prompts/{prompt_id}:reset",
        operation_id="reset_memory_prompt",
        response_model=MemoryPromptResponse,
        responses=ETAG_RESPONSE,
    )
    async def reset_memory_prompt(
        prompt_id: UUID,
        payload: ResetMemoryPromptRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> MemoryPromptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        return await run_transition(
            current=current,
            prompt_id=prompt_id,
            command=ResetMemoryPrompt(**payload.model_dump()),
            if_match=if_match,
            idempotency_key=idempotency_key,
            response=response,
        )

    @router.post(
        "/api/v1/memory-prompts/{prompt_id}:archive",
        operation_id="archive_memory_prompt",
        response_model=MemoryPromptResponse,
        responses=ETAG_RESPONSE,
    )
    async def archive_memory_prompt(
        prompt_id: UUID,
        payload: AtRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> MemoryPromptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        return await run_transition(
            current=current,
            prompt_id=prompt_id,
            command=ArchiveMemoryPrompt(payload.at),
            if_match=if_match,
            idempotency_key=idempotency_key,
            response=response,
        )

    @router.post(
        "/api/v1/memory-prompts/{prompt_id}:restore",
        operation_id="restore_memory_prompt",
        response_model=MemoryPromptResponse,
        responses=ETAG_RESPONSE,
    )
    async def restore_memory_prompt(
        prompt_id: UUID,
        payload: RestoreMemoryPromptRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> MemoryPromptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        return await run_transition(
            current=current,
            prompt_id=prompt_id,
            command=RestoreMemoryPrompt(
                **payload.model_dump(),
                target_revision_available=False,
            ),
            if_match=if_match,
            idempotency_key=idempotency_key,
            response=response,
        )

    @router.delete(
        "/api/v1/memory-prompts/{prompt_id}",
        operation_id="delete_memory_prompt",
        response_model=MemoryPromptResponse,
        responses=ETAG_RESPONSE,
    )
    async def delete_memory_prompt(
        prompt_id: UUID,
        payload: DeleteMemoryPromptRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> MemoryPromptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        return await run_transition(
            current=current,
            prompt_id=prompt_id,
            command=DeleteMemoryPrompt(payload.deleted_at, reauthenticated=False),
            if_match=if_match,
            idempotency_key=idempotency_key,
            response=response,
            include_session=True,
        )

    @router.post(
        "/api/v1/memory-prompts:merge",
        operation_id="merge_memory_prompts",
        response_model=MemoryPromptResponse,
        responses=ETAG_RESPONSE,
    )
    async def merge_memory_prompts(
        payload: MergeMemoryPromptsRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> MemoryPromptResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        if set(payload.source_prompt_ids) != set(payload.expected_versions):
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        aggregate = await application_service().merge(
            current.account_id,
            payload.source_prompt_ids,
            payload.expected_versions,
            payload.canonical_prompt_id,
            payload.merged_at,
            policy,
            idempotency_key=idempotency_key,
        )
        return with_etag(response, aggregate)

    @router.get(
        "/api/v1/memory-prompts/due",
        operation_id="list_due_memory_prompts",
        response_model=DueMemoryPromptPageResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def list_due_memory_prompts(
        request: Request,
        profile_id: Annotated[UUID, Query()],
        cutoff: Annotated[datetime, Query()],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
        session_token: SessionCookieToken = None,
    ) -> DueMemoryPromptPageResponse:
        current = await session_for(request, session_token)
        items, next_cursor = await application_service().list_due(
            current.account_id,
            profile_id,
            cutoff,
            limit=limit,
            cursor=cursor,
        )
        return DueMemoryPromptPageResponse(
            items=tuple(
                DueMemoryPromptResponse(
                    prompt=_prompt_response(item.aggregate),
                    overdue_seconds=item.overdue_seconds,
                    reason=item.reason,
                )
                for item in items
            ),
            next_cursor=next_cursor,
            cutoff=cutoff,
        )

    return router


__all__ = ["MemoryService", "memory_router"]
