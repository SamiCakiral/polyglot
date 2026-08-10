"""Authenticated W11 curriculum and module enrollment routes."""

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
from polyglot.modules.curriculum.application import (
    CompleteEnrollment,
    CurriculumApplicationService,
    EnrollInModule,
    EnrollmentView,
    PauseEnrollment,
)
from polyglot.modules.identity.application import (
    CurrentSessionResult,
    IdentityApplicationService,
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


class EnrollInModuleRequest(ClosedModel):
    enrollment_id: UUID
    module_revision_id: UUID
    pedagogical_day: date
    waiver_refs: tuple[str, ...] = Field(default=(), max_length=100)


class PauseEnrollmentRequest(ClosedModel):
    paused_at: datetime


class CompleteEnrollmentRequest(ClosedModel):
    completed_at: datetime


class ModuleResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    module_id: UUID
    module_code: str
    module_revision_id: UUID
    primary_intention: str
    nominal_days: int
    max_days: int
    min_minutes: int
    max_minutes: int
    entry_profile_codes: tuple[str, ...]


class EnrollmentResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    enrollment_id: UUID
    profile_id: UUID
    module_revision_id: UUID
    module_code: str
    nominal_days: int
    max_days: int
    status: str
    current_day_ordinal: int
    started_on_pedagogical_day: date | None
    completed_at: datetime | None
    terminal_at: datetime | None
    paused_at: datetime | None
    waiver_refs: tuple[str, ...]
    migration_map_revision_id: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime


def curriculum_router(
    service: CurriculumApplicationService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> CurriculumApplicationService:
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

    def enrollment_response(response: Response, view: EnrollmentView) -> EnrollmentResponse:
        response.headers["ETag"] = f'"{view.version}"'
        return EnrollmentResponse.model_validate(view)

    @router.get(
        "/api/v1/modules",
        operation_id="list_learning_modules",
        response_model=list[ModuleResponse],
        responses=PROBLEM_RESPONSES,
    )
    async def list_learning_modules(
        request: Request,
        session_token: SessionCookieToken = None,
    ) -> list[ModuleResponse]:
        current = await session_for(request, session_token)
        modules = await application_service().list_modules(current.account_id)
        return [ModuleResponse.model_validate(item) for item in modules]

    @router.get(
        "/api/v1/module-enrollments/{id}",
        operation_id="get_module_enrollment",
        response_model=EnrollmentResponse,
        responses=ETAG_RESPONSE,
    )
    async def get_module_enrollment(
        id: UUID,
        request: Request,
        response: Response,
        session_token: SessionCookieToken = None,
    ) -> EnrollmentResponse:
        current = await session_for(request, session_token)
        view = await application_service().get_enrollment(current.account_id, id)
        return enrollment_response(response, view)

    @router.post(
        "/api/v1/language-profiles/{profile_id}/module-enrollments",
        operation_id="enroll_in_module",
        response_model=EnrollmentResponse,
        status_code=201,
        responses=CREATED_ETAG_RESPONSE,
    )
    async def enroll_in_module(
        profile_id: UUID,
        payload: EnrollInModuleRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> EnrollmentResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().enroll(
            current.account_id,
            profile_id,
            EnrollInModule(**payload.model_dump()),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        return enrollment_response(response, view)

    @router.post(
        "/api/v1/module-enrollments/{id}:pause",
        operation_id="pause_module_enrollment",
        response_model=EnrollmentResponse,
        responses=ETAG_RESPONSE,
    )
    async def pause_module_enrollment(
        id: UUID,
        payload: PauseEnrollmentRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> EnrollmentResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().pause(
            current.account_id,
            id,
            PauseEnrollment(**payload.model_dump()),
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        return enrollment_response(response, view)

    @router.post(
        "/api/v1/module-enrollments/{id}:complete",
        operation_id="complete_module_enrollment",
        response_model=EnrollmentResponse,
        responses=ETAG_RESPONSE,
    )
    async def complete_module_enrollment(
        id: UUID,
        payload: CompleteEnrollmentRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> EnrollmentResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().complete(
            current.account_id,
            id,
            CompleteEnrollment(**payload.model_dump()),
            expected_version=expected_version(if_match),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        return enrollment_response(response, view)

    return router


__all__ = ["curriculum_router"]
