"""Authenticated progress, evidence and recommendation queries."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Protocol
from uuid import UUID

from fastapi import APIRouter, Query, Request, Security
from fastapi.security import APIKeyCookie
from pydantic import BaseModel, ConfigDict

from polyglot.interfaces.http.routes.identity import (
    IDENTITY_PROBLEM_RESPONSES,
    SESSION_COOKIE,
    _context,
    _session_token,
)
from polyglot.modules.identity.application import IdentityApplicationService
from polyglot.modules.progress.application import (
    ProgressOverviewView,
    RecommendationPageView,
)
from polyglot.platform.errors import DomainError, ErrorCode

SessionCookieToken = Annotated[
    str | None,
    Security(APIKeyCookie(name=SESSION_COOKIE, scheme_name="SessionCookie", auto_error=False)),
]


class ProgressService(Protocol):
    async def get_overview(
        self,
        actor_id: UUID,
        profile_id: UUID,
        *,
        cursor: str | None,
        limit: int,
    ) -> ProgressOverviewView: ...

    async def list_recommendations(
        self,
        actor_id: UUID,
        profile_id: UUID,
        *,
        cursor: str | None,
        limit: int,
        as_of: datetime,
    ) -> RecommendationPageView: ...


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ModalityProgressResponse(ClosedModel):
    modality: str
    status: str
    score: float | None
    confidence: float
    freshness: float | None
    coverage: float
    observed_facet_count: int
    expected_facet_count: int


class MasteryFacetResponse(ClosedModel):
    target_type: str
    target_id: str
    facet_key: str
    modality: str
    operation: str
    status: str
    mastery_base: float
    mastery_current: float
    confidence: float
    freshness: float
    effective_mass: float
    success_count: int
    failure_count: int
    context_count: int
    session_count: int
    delay_band_count: int
    transfer_count: int
    last_evidence_at: datetime | None
    next_verification_at: datetime | None
    policy_revision: str
    projection_version: int
    evidence_ids: tuple[UUID, ...]
    ineligibility_reasons: tuple[str, ...]


class ProgressOverviewResponse(ClosedModel):
    profile_id: UUID
    modalities: tuple[ModalityProgressResponse, ...]
    facets: tuple[MasteryFacetResponse, ...]
    next_cursor: str | None
    policy_revision: str
    has_global_score: bool


class RecommendationResponse(ClosedModel):
    recommendation_id: UUID
    target_type: str
    target_id: str
    facet_key: str
    need_id: UUID | None
    reason_code: str
    reason_params: dict[str, Any]
    missing_evidence_spec: dict[str, Any]
    proposed_activity: dict[str, Any]
    priority: float
    urgency: float
    estimated_duration_ms: int
    policy_revision: str
    authorized_fact_ids: tuple[UUID, ...]
    created_at: datetime
    expires_at: datetime | None


class RecommendationPageResponse(ClosedModel):
    profile_id: UUID
    items: tuple[RecommendationResponse, ...]
    next_cursor: str | None


def progress_router(
    service: ProgressService | None,
    identity_service: IdentityApplicationService | None,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> ProgressService:
        if service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        return service

    async def current_account(request: Request, token: str | None) -> UUID:
        if identity_service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        current = await identity_service.get_current_session(
            _session_token(token),
            _context(request),
        )
        return current.account_id

    @router.get(
        "/api/v1/language-profiles/{id}/progress",
        operation_id="get_progress_overview",
        response_model=ProgressOverviewResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def get_progress_overview(
        id: UUID,
        request: Request,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        session_token: SessionCookieToken = None,
    ) -> ProgressOverviewResponse:
        account_id = await current_account(request, session_token)
        view = await application_service().get_overview(
            account_id,
            id,
            cursor=cursor,
            limit=limit,
        )
        return ProgressOverviewResponse.model_validate(view)

    @router.get(
        "/api/v1/language-profiles/{id}/recommendations",
        operation_id="list_recommendations",
        response_model=RecommendationPageResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def list_recommendations(
        id: UUID,
        request: Request,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        session_token: SessionCookieToken = None,
    ) -> RecommendationPageResponse:
        account_id = await current_account(request, session_token)
        view = await application_service().list_recommendations(
            account_id,
            id,
            cursor=cursor,
            limit=limit,
            as_of=datetime.now(UTC),
        )
        return RecommendationPageResponse.model_validate(view)

    return router
