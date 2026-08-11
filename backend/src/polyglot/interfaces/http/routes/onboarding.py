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
from polyglot.modules.identity.application import IdentityApplicationService
from polyglot.modules.language_profiles.onboarding import (
    EntryPath,
    OnboardingState,
    PlacementBand,
    PlacementChoice,
    SkillDimension,
    SkillEstimate,
)
from polyglot.modules.language_profiles.onboarding_persistence import OnboardingApplicationService
from polyglot.platform.errors import DomainError, ErrorCode

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]
OriginHeader = Annotated[str, Header(alias="Origin")]
CsrfHeader = Annotated[str, Header(alias="X-CSRF-Token")]
IfMatchHeader = Annotated[str, Header(alias="If-Match")]
_session_cookie_security = APIKeyCookie(
    name=SESSION_COOKIE, scheme_name="SessionCookie", auto_error=False
)
SessionCookieToken = Annotated[str | None, Security(_session_cookie_security)]
_ETAG_RESPONSE: dict[int | str, dict[str, Any]] = {
    **IDENTITY_PROBLEM_RESPONSES,
    404: IDENTITY_PROBLEM_RESPONSES[422],
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


class StartOnboardingRequest(ClosedModel):
    entry_path: EntryPath


class SkillEstimateRequest(ClosedModel):
    dimension: SkillDimension
    band: PlacementBand
    confidence: float = Field(ge=0, le=1)
    evidence_count: int = Field(ge=0)


class RecordPlacementRequest(ClosedModel):
    detected_band: PlacementBand
    confidence: float = Field(ge=0, le=1)
    skills: list[SkillEstimateRequest] = Field(min_length=6, max_length=6)


class ChoosePlacementRequest(ClosedModel):
    choice: PlacementChoice


class SkillEstimateResponse(ClosedModel):
    dimension: SkillDimension
    band: PlacementBand
    confidence: float
    evidence_count: int


class OnboardingResponse(ClosedModel):
    profile_id: UUID
    entry_path: EntryPath
    detected_band: PlacementBand | None
    resolved_band: PlacementBand
    placement_confidence: float | None
    skill_profile: tuple[SkillEstimateResponse, ...]
    placement_choice: PlacementChoice | None
    calibration_sessions_remaining: int
    can_train: bool
    is_provisional: bool
    version: int
    created_at: datetime
    updated_at: datetime


def _response(state: OnboardingState) -> OnboardingResponse:
    return OnboardingResponse(
        profile_id=state.profile_id,
        entry_path=state.entry_path,
        detected_band=state.detected_band,
        resolved_band=state.resolved_band,
        placement_confidence=state.placement_confidence,
        skill_profile=tuple(
            SkillEstimateResponse(
                dimension=item.dimension,
                band=item.band,
                confidence=item.confidence,
                evidence_count=item.evidence_count,
            )
            for item in state.skill_profile
        ),
        placement_choice=state.placement_choice,
        calibration_sessions_remaining=state.calibration_sessions_remaining,
        can_train=state.can_train,
        is_provisional=state.is_provisional,
        version=state.version,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


def _required_version(if_match: str | None) -> int:
    if if_match is None:
        raise HTTPException(status_code=428, detail="If-Match is required")
    return _expected_version(if_match)


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def onboarding_router(
    service: OnboardingApplicationService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> OnboardingApplicationService:
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

    @router.get(
        "/api/v1/language-profiles/{profile_id}/onboarding",
        operation_id="get_onboarding_state",
        response_model=OnboardingResponse,
        responses=_ETAG_RESPONSE,
    )
    async def get_onboarding_state(
        profile_id: UUID,
        request: Request,
        response: Response,
        session_token: SessionCookieToken = None,
    ) -> OnboardingResponse:
        account_id = await account_for(request, session_token)
        state = await application_service().get(profile_id, account_id)
        _etag(response, state.version)
        return _response(state)

    @router.put(
        "/api/v1/language-profiles/{profile_id}/onboarding",
        operation_id="start_onboarding",
        response_model=OnboardingResponse,
        responses=_ETAG_RESPONSE,
    )
    async def start_onboarding(
        profile_id: UUID,
        payload: StartOnboardingRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> OnboardingResponse:
        account_id = await account_for(request, session_token, csrf_token, origin)
        state = await application_service().start(
            profile_id=profile_id,
            account_id=account_id,
            entry_path=payload.entry_path,
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        _etag(response, state.version)
        return _response(state)

    @router.patch(
        "/api/v1/language-profiles/{profile_id}/onboarding/placement",
        operation_id="record_placement_profile",
        response_model=OnboardingResponse,
        responses=_ETAG_RESPONSE,
    )
    async def record_placement_profile(
        profile_id: UUID,
        payload: RecordPlacementRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        if_match: IfMatchHeader,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> OnboardingResponse:
        account_id = await account_for(request, session_token, csrf_token, origin)
        state = await application_service().record_placement(
            profile_id=profile_id,
            account_id=account_id,
            detected_band=payload.detected_band,
            confidence=payload.confidence,
            skills=tuple(
                SkillEstimate(
                    dimension=item.dimension,
                    band=item.band,
                    confidence=item.confidence,
                    evidence_count=item.evidence_count,
                )
                for item in payload.skills
            ),
            expected_version=_required_version(if_match),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        _etag(response, state.version)
        return _response(state)

    @router.post(
        "/api/v1/language-profiles/{profile_id}/onboarding:choose",
        operation_id="choose_placement",
        response_model=OnboardingResponse,
        responses=_ETAG_RESPONSE,
    )
    async def choose_placement(
        profile_id: UUID,
        payload: ChoosePlacementRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        if_match: IfMatchHeader,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> OnboardingResponse:
        account_id = await account_for(request, session_token, csrf_token, origin)
        state = await application_service().choose(
            profile_id=profile_id,
            account_id=account_id,
            choice=payload.choice,
            expected_version=_required_version(if_match),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        _etag(response, state.version)
        return _response(state)

    return router
