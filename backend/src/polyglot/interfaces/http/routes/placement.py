from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response, Security, status
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
from polyglot.modules.identity.application import IdentityApplicationService
from polyglot.modules.language_profiles.onboarding import EntryPath
from polyglot.modules.placement.domain import SkillEstimate
from polyglot.modules.placement.persistence import (
    PlacementItemView,
    PlacementRunView,
    SqlPlacementService,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]
OriginHeader = Annotated[str, Header(alias="Origin")]
CsrfHeader = Annotated[str, Header(alias="X-CSRF-Token")]
IfMatchHeader = Annotated[str, Header(alias="If-Match")]
_session_cookie_security = APIKeyCookie(
    name=SESSION_COOKIE, scheme_name="SessionCookie", auto_error=False
)
SessionCookieToken = Annotated[str | None, Security(_session_cookie_security)]


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartPlacementRequest(ClosedModel):
    pack_revision_id: UUID
    entry_path: EntryPath
    seed: str = Field(min_length=1, max_length=255)


class PlacementAnswerRequest(ClosedModel):
    item_instance_id: UUID
    answer: dict[str, JsonValue]
    elapsed_seconds: int = Field(ge=0, le=1200)


class PlacementChoiceRequest(ClosedModel):
    choice: str = Field(pattern="^(accept|start_easier|challenge|start_now)$")


class PlacementSkillResponse(ClosedModel):
    skill_ref: str
    status: str
    lower_bound: int | None
    probable_level: int | None
    upper_bound: int | None
    confidence: float
    independent_evidence_count: int


class PlacementItemResponse(ClosedModel):
    item_instance_id: UUID
    ordinal: int
    primitive_ref: str
    primary_skill_ref: str
    payload: dict[str, JsonValue]
    estimated_seconds: int


class PlacementRunResponse(ClosedModel):
    run_id: UUID
    profile_id: UUID
    status: str
    version: int
    elapsed_seconds: int
    current_item: PlacementItemResponse | None
    estimates: list[PlacementSkillResponse]
    stop_reason: str | None
    provider_status: str | None


def _skill(item: SkillEstimate) -> PlacementSkillResponse:
    return PlacementSkillResponse(
        skill_ref=item.skill_ref,
        status=item.status.value,
        lower_bound=item.lower_bound,
        probable_level=item.probable_level,
        upper_bound=item.upper_bound,
        confidence=item.confidence,
        independent_evidence_count=item.independent_evidence_count,
    )


def _item(item: PlacementItemView | None) -> PlacementItemResponse | None:
    return PlacementItemResponse(**asdict(item)) if item is not None else None


def _run(view: PlacementRunView) -> PlacementRunResponse:
    return PlacementRunResponse(
        run_id=view.run_id,
        profile_id=view.profile_id,
        status=view.status.value,
        version=view.version,
        elapsed_seconds=view.elapsed_seconds,
        current_item=_item(view.current_item),
        estimates=[_skill(item) for item in view.estimates],
        stop_reason=view.stop_reason,
        provider_status=view.provider_status,
    )


def placement_router(
    service: SqlPlacementService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def placement_service() -> SqlPlacementService:
        if service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        return service

    async def account_for(
        request: Request,
        session_token: str | None,
        csrf_token: str | None = None,
        origin: str | None = None,
    ) -> UUID:
        if identity_service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        if origin is not None:
            _require_origin(origin, allowed_origin)
        current = await identity_service.get_current_session(
            _session_token(session_token), _context(request)
        )
        if csrf_token is not None and csrf_token != current.csrf_token:
            raise DomainError(ErrorCode.FORBIDDEN)
        return current.account_id

    @router.post(
        "/api/v1/language-profiles/{profile_id}/placement-runs",
        operation_id="start_placement_run",
        response_model=PlacementRunResponse,
        status_code=status.HTTP_201_CREATED,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def start_run(
        profile_id: UUID,
        payload: StartPlacementRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> PlacementRunResponse:
        actor = await account_for(request, session_token, csrf_token, origin)
        view = await placement_service().start(
            actor_id=actor,
            profile_id=profile_id,
            pack_revision_id=payload.pack_revision_id,
            entry_path=payload.entry_path,
            seed=f"{payload.seed}:{idempotency_key}",
        )
        response.headers["ETag"] = f'"{view.version}"'
        return _run(view)

    @router.get(
        "/api/v1/placement-runs/{run_id}",
        operation_id="get_placement_run",
        response_model=PlacementRunResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def get_run(
        run_id: UUID,
        request: Request,
        response: Response,
        session_token: SessionCookieToken = None,
    ) -> PlacementRunResponse:
        actor = await account_for(request, session_token)
        view = await placement_service().get_run(actor_id=actor, run_id=run_id)
        response.headers["ETag"] = f'"{view.version}"'
        return _run(view)

    @router.get(
        "/api/v1/placement-runs/{run_id}/current-item",
        operation_id="get_current_placement_item",
        response_model=PlacementItemResponse | None,
    )
    async def current_item(
        run_id: UUID,
        request: Request,
        session_token: SessionCookieToken = None,
    ) -> PlacementItemResponse | None:
        actor = await account_for(request, session_token)
        view = await placement_service().get_run(actor_id=actor, run_id=run_id)
        return _item(view.current_item)

    @router.post(
        "/api/v1/placement-runs/{run_id}/responses",
        operation_id="submit_placement_response",
        response_model=PlacementRunResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def submit_response(
        run_id: UUID,
        payload: PlacementAnswerRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        if_match: IfMatchHeader,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> PlacementRunResponse:
        actor = await account_for(request, session_token, csrf_token, origin)
        try:
            expected_version = _expected_version(if_match)
        except ValueError as error:
            raise HTTPException(status_code=428, detail="A valid If-Match is required") from error
        view = await placement_service().submit(
            actor_id=actor,
            run_id=run_id,
            item_instance_id=payload.item_instance_id,
            answer=payload.answer,
            elapsed_seconds=payload.elapsed_seconds,
            idempotency_key=idempotency_key,
            expected_version=expected_version,
        )
        response.headers["ETag"] = f'"{view.version}"'
        return _run(view)

    @router.post(
        "/api/v1/placement-runs/{run_id}:choose",
        operation_id="choose_placement_start",
        response_model=PlacementRunResponse,
    )
    async def choose(
        run_id: UUID,
        payload: PlacementChoiceRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        if_match: IfMatchHeader,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> PlacementRunResponse:
        actor = await account_for(request, session_token, csrf_token, origin)
        try:
            expected_version = _expected_version(if_match)
        except ValueError as error:
            raise HTTPException(status_code=428, detail="A valid If-Match is required") from error
        view = await placement_service().choose(
            actor_id=actor,
            run_id=run_id,
            choice=payload.choice,
            idempotency_key=idempotency_key,
            expected_version=expected_version,
        )
        response.headers["ETag"] = f'"{view.version}"'
        return _run(view)

    return router
