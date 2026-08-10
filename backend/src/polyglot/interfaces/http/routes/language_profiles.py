"""Authenticated W03 language-profile routes."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Any
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
from polyglot.modules.language_profiles.application import (
    DiagnosticRunSummary,
    FoundationRunSummary,
    LanguageProfileApplicationService,
)
from polyglot.modules.language_profiles.domain import LanguageProfileStatus, LearnerLanguageProfile
from polyglot.platform.errors import DomainError, ErrorCode

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]
OriginHeader = Annotated[str, Header(alias="Origin")]
CsrfHeader = Annotated[str, Header(alias="X-CSRF-Token")]
IfMatchHeader = Annotated[str, Header(alias="If-Match")]
_session_cookie_security = APIKeyCookie(
    name=SESSION_COOKIE, scheme_name="SessionCookie", auto_error=False
)
SessionCookieToken = Annotated[str | None, Security(_session_cookie_security)]
_ETAG_OPENAPI = {
    "headers": {
        "ETag": {
            "description": "Quoted optimistic concurrency version.",
            "schema": {"type": "string"},
        }
    }
}
PRECONDITION_RESPONSES: dict[int | str, dict[str, Any]] = {
    428: IDENTITY_PROBLEM_RESPONSES[422]
}
RESOURCE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **IDENTITY_PROBLEM_RESPONSES,
    **PRECONDITION_RESPONSES,
    200: _ETAG_OPENAPI,
}
CREATED_RESOURCE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **IDENTITY_PROBLEM_RESPONSES,
    **PRECONDITION_RESPONSES,
    201: _ETAG_OPENAPI,
}


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateProfileRequest(ClosedModel):
    target_variety_id: UUID
    native_variety_id: UUID


class UpdateGoalsRequest(ClosedModel):
    goals: list[str] = Field(max_length=32)


class StartDiagnosticRequest(ClosedModel):
    policy_revision_id: UUID
    pack_revision_id: UUID
    seed: str = Field(min_length=1, max_length=255)


class SubmitDiagnosticResponseRequest(ClosedModel):
    item_revision_id: UUID
    ordinal: int = Field(ge=1)
    answer: dict[str, Any]


class StartFoundationRunRequest(ClosedModel):
    pack_revision_id: UUID
    foundation_revision_id: UUID
    seed: str = Field(min_length=1, max_length=255)


class FoundationAnswerRequest(ClosedModel):
    item_revision_id: UUID
    answer: dict[str, Any]
    revealed: bool = False


class CompleteFoundationGateRequest(ClosedModel):
    answers: list[FoundationAnswerRequest] = Field(min_length=1, max_length=32)


class ProfileResponse(ClosedModel):
    profile_id: UUID
    account_id: UUID
    target_variety_id: UUID
    native_variety_id: UUID
    status: str
    current_phase: str
    goals: list[str]
    interests: list[str]
    excluded_themes: list[str]
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    deleted_at: datetime | None


class ProfilesResponse(ClosedModel):
    items: list[ProfileResponse]


class DiagnosticResponse(ClosedModel):
    diagnostic_run_id: UUID
    profile_id: UUID
    status: str
    policy_revision_id: UUID
    pack_revision_id: UUID
    started_at: datetime
    expires_at: datetime
    version: int
    completed_at: datetime | None
    classification: str | None
    confidence: float | None
    stop_reason: str | None


class FoundationResponse(ClosedModel):
    foundation_run_id: UUID
    profile_id: UUID
    status: str
    pack_revision_id: UUID
    foundation_revision_id: UUID
    started_at: datetime
    expires_at: datetime
    version: int
    completed_at: datetime | None
    session_count: int
    gate_passed: bool | None
    gate_reasons: list[str]


def _profile_response(profile: LearnerLanguageProfile) -> ProfileResponse:
    return ProfileResponse(
        profile_id=profile.profile_id,
        account_id=profile.account_id,
        target_variety_id=profile.target_variety_id,
        native_variety_id=profile.native_variety_id,
        status=profile.status.value,
        current_phase=profile.current_phase.value,
        goals=list(profile.goals),
        interests=list(profile.interests),
        excluded_themes=list(profile.excluded_themes),
        version=profile.version,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        archived_at=profile.archived_at,
        deleted_at=profile.deleted_at,
    )


def _diagnostic_response(summary: DiagnosticRunSummary) -> DiagnosticResponse:
    return DiagnosticResponse(**asdict(summary))


def _foundation_response(summary: FoundationRunSummary) -> FoundationResponse:
    payload = asdict(summary)
    payload["gate_reasons"] = list(summary.gate_reasons)
    return FoundationResponse(**payload)


def _required_version(if_match: str | None) -> int:
    if if_match is None:
        raise HTTPException(status_code=428, detail="If-Match is required")
    return _expected_version(if_match)


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def language_profiles_router(
    service: LanguageProfileApplicationService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> LanguageProfileApplicationService:
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
        "/api/v1/language-profiles",
        operation_id="list_language_profiles",
        response_model=ProfilesResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def list_language_profiles(
        request: Request, session_token: SessionCookieToken = None
    ) -> ProfilesResponse:
        account_id = await account_for(request, session_token)
        profiles = await application_service().list_profiles(account_id)
        return ProfilesResponse(items=[_profile_response(profile) for profile in profiles])

    @router.post(
        "/api/v1/language-profiles",
        operation_id="create_language_profile",
        response_model=ProfileResponse,
        status_code=status.HTTP_201_CREATED,
        responses=CREATED_RESOURCE_RESPONSES,
    )
    async def create_language_profile(
        payload: CreateProfileRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> ProfileResponse:
        account_id = await account_for(request, session_token, csrf_token, origin)
        result = await application_service().create_profile(
            account_id=account_id,
            target_variety_id=payload.target_variety_id,
            native_variety_id=payload.native_variety_id,
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        _etag(response, result.profile.version)
        return _profile_response(result.profile)

    @router.get(
        "/api/v1/language-profiles/{id}",
        operation_id="get_language_profile",
        response_model=ProfileResponse,
        responses=RESOURCE_RESPONSES,
    )
    async def get_language_profile(
        id: UUID, request: Request, response: Response, session_token: SessionCookieToken = None
    ) -> ProfileResponse:
        account_id = await account_for(request, session_token)
        profile = await application_service().get_profile(id, account_id)
        _etag(response, profile.version)
        return _profile_response(profile)

    @router.patch(
        "/api/v1/language-profiles/{profile_id}/goals",
        operation_id="update_learning_goals",
        response_model=ProfileResponse,
        responses=RESOURCE_RESPONSES,
    )
    async def update_learning_goals(
        profile_id: UUID,
        payload: UpdateGoalsRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> ProfileResponse:
        account_id = await account_for(request, session_token, csrf_token, origin)
        result = await application_service().update_goals(
            profile_id=profile_id,
            account_id=account_id,
            goals=tuple(payload.goals),
            expected_version=_required_version(if_match),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        _etag(response, result.profile.version)
        return _profile_response(result.profile)

    @router.post(
        "/api/v1/language-profiles/{profile_id}/diagnostics",
        operation_id="start_diagnostic",
        response_model=DiagnosticResponse,
        status_code=status.HTTP_201_CREATED,
        responses=CREATED_RESOURCE_RESPONSES,
    )
    async def start_diagnostic(
        profile_id: UUID,
        payload: StartDiagnosticRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> DiagnosticResponse:
        account_id = await account_for(request, session_token, csrf_token, origin)
        summary = await application_service().start_diagnostic(
                profile_id=profile_id,
                account_id=account_id,
                policy_revision_id=payload.policy_revision_id,
                pack_revision_id=payload.pack_revision_id,
                seed=payload.seed,
                expected_version=_required_version(if_match),
                idempotency_key=idempotency_key,
                context=_context(request),
            )
        _etag(response, summary.version)
        return _diagnostic_response(summary)

    @router.get(
        "/api/v1/diagnostics/{id}",
        operation_id="get_diagnostic_summary",
        response_model=DiagnosticResponse,
        responses=RESOURCE_RESPONSES,
    )
    async def get_diagnostic(
        id: UUID, request: Request, response: Response, session_token: SessionCookieToken = None
    ) -> DiagnosticResponse:
        account_id = await account_for(request, session_token)
        summary = await application_service().get_diagnostic(id, account_id)
        _etag(response, summary.version)
        return _diagnostic_response(summary)

    @router.post(
        "/api/v1/diagnostics/{run_id}/responses",
        operation_id="submit_diagnostic_response",
        responses=RESOURCE_RESPONSES,
    )
    async def submit_diagnostic_response(
        run_id: UUID,
        payload: SubmitDiagnosticResponseRequest,
        request: Request,
        response: Response,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        idempotency_key: IdempotencyKey,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> DiagnosticResponse:
        account_id = await account_for(request, session_token, csrf_token, origin)
        summary = await application_service().submit_diagnostic_response(
            run_id=run_id,
            account_id=account_id,
            item_revision_id=payload.item_revision_id,
            ordinal=payload.ordinal,
            answer=payload.answer,
            expected_version=_required_version(if_match),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        _etag(response, summary.version)
        return _diagnostic_response(summary)

    @router.post(
        "/api/v1/diagnostics/{run_id}:complete",
        operation_id="complete_diagnostic",
        responses=RESOURCE_RESPONSES,
    )
    async def complete_diagnostic(
        run_id: UUID,
        request: Request,
        response: Response,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        idempotency_key: IdempotencyKey,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> DiagnosticResponse:
        account_id = await account_for(request, session_token, csrf_token, origin)
        summary = await application_service().complete_diagnostic(
            run_id=run_id,
            account_id=account_id,
            expected_version=_required_version(if_match),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        _etag(response, summary.version)
        return _diagnostic_response(summary)

    @router.post(
        "/api/v1/language-profiles/{profile_id}/foundation-runs",
        operation_id="start_foundation_run",
        status_code=status.HTTP_201_CREATED,
        responses=CREATED_RESOURCE_RESPONSES,
    )
    async def start_foundation_run(
        profile_id: UUID,
        payload: StartFoundationRunRequest,
        request: Request,
        response: Response,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        idempotency_key: IdempotencyKey,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> FoundationResponse:
        account_id = await account_for(request, session_token, csrf_token, origin)
        summary = await application_service().start_foundation_run(
            profile_id=profile_id,
            account_id=account_id,
            pack_revision_id=payload.pack_revision_id,
            foundation_revision_id=payload.foundation_revision_id,
            seed=payload.seed,
            expected_version=_required_version(if_match),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        _etag(response, summary.version)
        return _foundation_response(summary)

    @router.post(
        "/api/v1/foundation-runs/{run_id}:complete",
        operation_id="complete_foundation_gate",
        responses=RESOURCE_RESPONSES,
    )
    async def complete_foundation_gate(
        run_id: UUID,
        payload: CompleteFoundationGateRequest,
        request: Request,
        response: Response,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        idempotency_key: IdempotencyKey,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> FoundationResponse:
        account_id = await account_for(request, session_token, csrf_token, origin)
        summary = await application_service().complete_foundation_gate(
            run_id=run_id,
            account_id=account_id,
            answers=tuple(
                (item.item_revision_id, item.answer, item.revealed) for item in payload.answers
            ),
            expected_version=_required_version(if_match),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        _etag(response, summary.version)
        return _foundation_response(summary)

    def transition_route(
        *, command_type: str, event_type: str, profile_status: LanguageProfileStatus
    ) -> Any:
        async def route(
            profile_id: UUID,
            request: Request,
            response: Response,
            idempotency_key: IdempotencyKey,
            origin: OriginHeader,
            csrf_token: CsrfHeader,
            if_match: IfMatchHeader,
            session_token: SessionCookieToken = None,
        ) -> ProfileResponse:
            account_id = await account_for(request, session_token, csrf_token, origin)
            result = await application_service().transition_profile(
                profile_id=profile_id,
                account_id=account_id,
                status=profile_status,
                command_type=command_type,
                event_type=event_type,
                expected_version=_required_version(if_match),
                idempotency_key=idempotency_key,
                context=_context(request),
            )
            _etag(response, result.profile.version)
            return _profile_response(result.profile)

        return route

    for path, command_type, event_type, profile_status, method, operation_id in (
        (
            "/api/v1/language-profiles/{profile_id}:pause",
            "PauseLanguageProfile",
            "language_profile_paused",
            LanguageProfileStatus.PAUSED,
            "POST",
            "pause_language_profile",
        ),
        (
            "/api/v1/language-profiles/{profile_id}:archive",
            "ArchiveLanguageProfile",
            "language_profile_archived",
            LanguageProfileStatus.ARCHIVED,
            "POST",
            "archive_language_profile",
        ),
        (
            "/api/v1/language-profiles/{profile_id}:restore",
            "RestoreLanguageProfile",
            "language_profile_restored",
            LanguageProfileStatus.ACTIVE,
            "POST",
            "restore_language_profile",
        ),
        (
            "/api/v1/language-profiles/{profile_id}",
            "DeleteLanguageProfile",
            "language_profile_deletion_requested",
            LanguageProfileStatus.DELETING,
            "DELETE",
            "delete_language_profile",
        ),
    ):
        router.add_api_route(
            path,
            transition_route(
                command_type=command_type,
                event_type=event_type,
                profile_status=profile_status,
            ),
            methods=[method],
            operation_id=operation_id,
            response_model=ProfileResponse,
            responses=RESOURCE_RESPONSES,
        )

    @router.get(
        "/api/v1/foundation-runs/{id}",
        operation_id="get_foundation_run",
        response_model=FoundationResponse,
        responses=RESOURCE_RESPONSES,
    )
    async def get_foundation_run(
        id: UUID, request: Request, response: Response, session_token: SessionCookieToken = None
    ) -> FoundationResponse:
        account_id = await account_for(request, session_token)
        summary = await application_service().get_foundation_run(id, account_id)
        _etag(response, summary.version)
        return _foundation_response(summary)

    return router
