from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from polyglot.interfaces.http.routes.identity import (
    CsrfHeader,
    IdempotencyKey,
    IfMatchHeader,
    OriginHeader,
    ProblemResponse,
    SessionCookieToken,
    _context,
    _expected_version,
    _require_origin,
    _session_token,
)
from polyglot.modules.identity.application import (
    CurrentSessionResult,
    IdentityApplicationService,
)
from polyglot.modules.practice.application import (
    CreatePracticePreset,
    CreatePracticeStack,
    PracticePresetView,
    PracticeRunView,
    PracticeService,
    PracticeStackView,
    StackInjectionView,
)
from polyglot.modules.practice.domain import (
    PracticeDirection,
    PracticeMode,
    PracticeStackKind,
    StackMember,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StackMemberModel(ClosedModel):
    sense_id: UUID
    sense_revision_id: UUID
    label: str = Field(min_length=1, max_length=500)
    definition: str = Field(min_length=1, max_length=2000)
    source_kind: str = Field(min_length=1, max_length=40)
    source_ref: str = Field(min_length=1, max_length=500)


class CreatePracticeStackRequest(ClosedModel):
    name: str = Field(min_length=1, max_length=200)
    stack_kind: PracticeStackKind
    language_pack_revision_id: UUID | None = None
    pedagogical_day: date | None = None
    source_list_snapshot_id: UUID | None = None
    source_refs: tuple[str, ...] = Field(default=(), max_length=100)
    members: tuple[StackMemberModel, ...] = Field(default=(), max_length=5000)
    created_at: datetime


class CombinePracticeStacksRequest(ClosedModel):
    profile_id: UUID
    stack_ids: tuple[UUID, ...] = Field(min_length=2, max_length=31)
    name: str = Field(min_length=1, max_length=200)
    created_at: datetime


class PracticeStackResponse(ClosedModel):
    stack_id: UUID
    profile_id: UUID
    language_pack_revision_id: UUID
    name: str
    stack_kind: PracticeStackKind
    pedagogical_day: date | None
    source_refs: tuple[str, ...]
    checksum: str
    created_at: datetime
    members: tuple[StackMemberModel, ...]


class PracticeStackPageResponse(ClosedModel):
    items: tuple[PracticeStackResponse, ...]


class InjectPracticeStackRequest(ClosedModel):
    requested_at: datetime


class StackInjectionResponse(ClosedModel):
    injection_id: UUID
    profile_id: UUID
    stack_id: UUID
    status: str
    version: int
    requested_at: datetime


class CreatePracticePresetRequest(ClosedModel):
    name: str = Field(min_length=1, max_length=200)
    stack_ids: tuple[UUID, ...] = Field(min_length=1, max_length=31)
    direction: PracticeDirection
    mode: PracticeMode
    settings: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: datetime


class PracticePresetResponse(ClosedModel):
    preset_id: UUID
    profile_id: UUID
    preset_revision_id: UUID
    revision_no: int
    name: str
    stack_ids: tuple[UUID, ...]
    direction: PracticeDirection
    mode: PracticeMode
    settings: dict[str, JsonValue]
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class PracticePresetPageResponse(ClosedModel):
    items: tuple[PracticePresetResponse, ...]


class StartPracticeRunRequest(ClosedModel):
    started_at: datetime


class AtRequest(ClosedModel):
    at: datetime


class PracticeRunResponse(ClosedModel):
    run_id: UUID
    profile_id: UUID
    preset_id: UUID
    preset_revision_id: UUID
    status: str
    current_position: int
    member_count: int
    version: int
    direction: PracticeDirection
    mode: PracticeMode
    current_item: StackMemberModel | None
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {
        "model": ProblemResponse,
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemResponse"}}
        },
    }
    for status in (401, 403, 409, 422, 428, 503)
}


def _stack_response(view: PracticeStackView) -> PracticeStackResponse:
    return PracticeStackResponse.model_validate(view, from_attributes=True)


def _preset_response(view: PracticePresetView) -> PracticePresetResponse:
    return PracticePresetResponse.model_validate(view, from_attributes=True)


def _run_response(view: PracticeRunView) -> PracticeRunResponse:
    return PracticeRunResponse.model_validate(view, from_attributes=True)


def _injection_response(view: StackInjectionView) -> StackInjectionResponse:
    return StackInjectionResponse.model_validate(view, from_attributes=True)


def practice_router(
    service: PracticeService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> PracticeService:
        if service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        return service

    async def current_session(
        request: Request,
        token: str | None,
        *,
        csrf: str | None = None,
        origin: str | None = None,
    ) -> CurrentSessionResult:
        if identity_service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        if origin is not None:
            _require_origin(origin, allowed_origin)
        current = await identity_service.get_current_session(
            _session_token(token), _context(request)
        )
        if csrf is not None and current.csrf_token != csrf:
            raise DomainError(ErrorCode.FORBIDDEN)
        return current

    def expected(value: str) -> int:
        try:
            return _expected_version(value)
        except ValueError as error:
            raise HTTPException(status_code=428, detail="If-Match is required") from error

    @router.post(
        "/api/v1/language-profiles/{profile_id}/practice-stacks",
        operation_id="create_practice_stack",
        response_model=PracticeStackResponse,
        status_code=201,
        responses=PROBLEM_RESPONSES,
    )
    async def create_practice_stack(
        profile_id: UUID,
        payload: CreatePracticeStackRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf: CsrfHeader,
        token: SessionCookieToken = None,
    ) -> PracticeStackResponse:
        current = await current_session(request, token, csrf=csrf, origin=origin)
        command = CreatePracticeStack(
            name=payload.name,
            stack_kind=payload.stack_kind,
            language_pack_revision_id=payload.language_pack_revision_id,
            pedagogical_day=payload.pedagogical_day,
            source_list_snapshot_id=payload.source_list_snapshot_id,
            source_refs=payload.source_refs,
            members=tuple(StackMember(**item.model_dump()) for item in payload.members),
            created_at=payload.created_at,
        )
        return _stack_response(
            await application_service().create_stack(
                current.account_id,
                profile_id,
                command,
                idempotency_key=idempotency_key,
            )
        )

    @router.get(
        "/api/v1/language-profiles/{profile_id}/practice-stacks",
        operation_id="list_practice_stacks",
        response_model=PracticeStackPageResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def list_practice_stacks(
        profile_id: UUID,
        request: Request,
        token: SessionCookieToken = None,
    ) -> PracticeStackPageResponse:
        current = await current_session(request, token)
        views = await application_service().list_stacks(current.account_id, profile_id)
        return PracticeStackPageResponse(items=tuple(_stack_response(view) for view in views))

    @router.get(
        "/api/v1/practice-stacks/{stack_id}",
        operation_id="get_practice_stack",
        response_model=PracticeStackResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def get_practice_stack(
        stack_id: UUID,
        request: Request,
        token: SessionCookieToken = None,
    ) -> PracticeStackResponse:
        current = await current_session(request, token)
        return _stack_response(await application_service().get_stack(current.account_id, stack_id))

    @router.post(
        "/api/v1/practice-stacks:combine",
        operation_id="combine_practice_stacks",
        response_model=PracticeStackResponse,
        status_code=201,
        responses=PROBLEM_RESPONSES,
    )
    async def combine_practice_stacks(
        payload: CombinePracticeStacksRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf: CsrfHeader,
        token: SessionCookieToken = None,
    ) -> PracticeStackResponse:
        current = await current_session(request, token, csrf=csrf, origin=origin)
        return _stack_response(
            await application_service().combine_stacks(
                current.account_id,
                payload.profile_id,
                stack_ids=payload.stack_ids,
                name=payload.name,
                created_at=payload.created_at,
                idempotency_key=idempotency_key,
            )
        )

    @router.post(
        "/api/v1/practice-stacks/{stack_id}:inject-next-sprint",
        operation_id="inject_practice_stack_into_next_sprint",
        response_model=StackInjectionResponse,
        status_code=201,
        responses=PROBLEM_RESPONSES,
    )
    async def inject_practice_stack(
        stack_id: UUID,
        payload: InjectPracticeStackRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf: CsrfHeader,
        token: SessionCookieToken = None,
    ) -> StackInjectionResponse:
        current = await current_session(request, token, csrf=csrf, origin=origin)
        return _injection_response(
            await application_service().inject_stack(
                current.account_id,
                stack_id,
                requested_at=payload.requested_at,
                idempotency_key=idempotency_key,
            )
        )

    @router.post(
        "/api/v1/language-profiles/{profile_id}/practice-presets",
        operation_id="create_practice_preset",
        response_model=PracticePresetResponse,
        status_code=201,
        responses=PROBLEM_RESPONSES,
    )
    async def create_practice_preset(
        profile_id: UUID,
        payload: CreatePracticePresetRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf: CsrfHeader,
        token: SessionCookieToken = None,
    ) -> PracticePresetResponse:
        current = await current_session(request, token, csrf=csrf, origin=origin)
        return _preset_response(
            await application_service().create_preset(
                current.account_id,
                profile_id,
                CreatePracticePreset(**payload.model_dump()),
                idempotency_key=idempotency_key,
            )
        )

    @router.get(
        "/api/v1/language-profiles/{profile_id}/practice-presets",
        operation_id="list_practice_presets",
        response_model=PracticePresetPageResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def list_practice_presets(
        profile_id: UUID,
        request: Request,
        token: SessionCookieToken = None,
    ) -> PracticePresetPageResponse:
        current = await current_session(request, token)
        views = await application_service().list_presets(current.account_id, profile_id)
        return PracticePresetPageResponse(items=tuple(_preset_response(view) for view in views))

    @router.post(
        "/api/v1/practice-presets/{preset_id}/runs",
        operation_id="start_practice_run",
        response_model=PracticeRunResponse,
        status_code=201,
        responses=PROBLEM_RESPONSES,
    )
    async def start_practice_run(
        preset_id: UUID,
        payload: StartPracticeRunRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf: CsrfHeader,
        token: SessionCookieToken = None,
    ) -> PracticeRunResponse:
        current = await current_session(request, token, csrf=csrf, origin=origin)
        return _run_response(
            await application_service().start_run(
                current.account_id,
                preset_id,
                started_at=payload.started_at,
                idempotency_key=idempotency_key,
            )
        )

    @router.get(
        "/api/v1/practice-runs/{run_id}",
        operation_id="get_practice_run",
        response_model=PracticeRunResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def get_practice_run(
        run_id: UUID,
        request: Request,
        response: Response,
        token: SessionCookieToken = None,
    ) -> PracticeRunResponse:
        current = await current_session(request, token)
        view = await application_service().get_run(current.account_id, run_id)
        response.headers["ETag"] = f'"{view.version}"'
        return _run_response(view)

    async def mutate_run(
        run_id: UUID,
        action: str,
        payload: AtRequest,
        request: Request,
        response: Response,
        idempotency_key: str,
        origin: str,
        csrf: str,
        if_match: str,
        token: str | None,
    ) -> PracticeRunResponse:
        current = await current_session(request, token, csrf=csrf, origin=origin)
        version = expected(if_match)
        if action == "advance":
            view = await application_service().advance_run(
                current.account_id,
                run_id,
                expected_version=version,
                advanced_at=payload.at,
                idempotency_key=idempotency_key,
            )
        else:
            view = await application_service().transition_run(
                current.account_id,
                run_id,
                action=action,
                expected_version=version,
                changed_at=payload.at,
                idempotency_key=idempotency_key,
            )
        response.headers["ETag"] = f'"{view.version}"'
        return _run_response(view)

    def add_run_command(action: str) -> None:
        async def command(
            run_id: UUID,
            payload: AtRequest,
            request: Request,
            response: Response,
            idempotency_key: IdempotencyKey,
            origin: OriginHeader,
            csrf: CsrfHeader,
            if_match: IfMatchHeader,
            token: SessionCookieToken = None,
        ) -> PracticeRunResponse:
            return await mutate_run(
                run_id,
                action,
                payload,
                request,
                response,
                idempotency_key,
                origin,
                csrf,
                if_match,
                token,
            )

        router.add_api_route(
            f"/api/v1/practice-runs/{{run_id}}:{action}",
            command,
            methods=["POST"],
            operation_id=f"{action}_practice_run",
            response_model=PracticeRunResponse,
            responses=PROBLEM_RESPONSES,
        )

    for action in ("advance", "interrupt", "resume", "abandon"):
        add_run_command(action)

    return router
