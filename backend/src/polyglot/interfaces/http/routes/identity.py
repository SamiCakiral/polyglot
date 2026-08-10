from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response, Security, status
from fastapi.security import APIKeyCookie
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from polyglot.modules.identity.application import (
    AuthenticateSession,
    ChangePassword,
    IdentityApplicationService,
    RegisterAccount,
    RequestContext,
    RevokeSession,
    SessionContinuation,
    UpdateConsent,
    UpdateUserPreferences,
)
from polyglot.modules.identity.domain import ConsentDecision, UserPreferences
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue

SESSION_COOKIE = "__Host-polyglot_session"

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]
OriginHeader = Annotated[str, Header(alias="Origin")]
CsrfHeader = Annotated[str, Header(alias="X-CSRF-Token")]
IfMatchHeader = Annotated[str, Header(alias="If-Match")]
_session_cookie_security = APIKeyCookie(
    name=SESSION_COOKIE,
    scheme_name="SessionCookie",
    auto_error=False,
)
SessionCookieToken = Annotated[str | None, Security(_session_cookie_security)]


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LocalCredentialsRequest(ClosedModel):
    provider_type: Literal["local_password"]
    identifier: str = Field(max_length=320)
    password: SecretStr


class OidcCredentialsRequest(ClosedModel):
    provider_type: Literal["oidc"]
    authorization_code: SecretStr


CredentialsRequest = Annotated[
    LocalCredentialsRequest | OidcCredentialsRequest,
    Field(discriminator="provider_type"),
]


class ChangePasswordRequest(ClosedModel):
    current_password: SecretStr
    new_password: SecretStr


class PreferencesRequest(ClosedModel):
    interface_locale: str | None = Field(default=None, max_length=35)
    timezone: str | None = Field(default=None, max_length=120)
    preferred_sprint_minutes: int | None = None
    accessibility_preferences: dict[str, JsonValue] | None = None
    media_preferences: dict[str, JsonValue] | None = None


class ConsentRequest(ClosedModel):
    status: Literal["granted", "withdrawn"]
    policy_revision_id: UUID


class AccountResponse(ClosedModel):
    account_id: UUID
    version: int


class SessionResponse(ClosedModel):
    session_id: UUID
    account_id: UUID
    roles: list[str]
    csrf_token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime


class PreferencesResponse(ClosedModel):
    account_id: UUID
    interface_locale: str
    timezone: str
    day_cutover_local_time: str
    preferred_sprint_minutes: int
    accessibility_preferences: dict[str, JsonValue]
    media_preferences: dict[str, JsonValue]
    version: int
    updated_at: datetime


class ConsentResponse(ClosedModel):
    consent_id: UUID
    account_id: UUID
    purpose_code: str
    status: Literal["granted", "withdrawn"]
    policy_revision_id: UUID
    version: int
    decided_at: datetime
    withdrawn_at: datetime | None


class CurrentSessionResponse(SessionResponse):
    preferences: PreferencesResponse
    consents: list[ConsentResponse]


class ProblemResponse(ClosedModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str
    code: str
    message_key: str
    request_id: str
    correlation_id: str
    retryable: bool
    details: dict[str, JsonValue] | None = None
    field_errors: list[dict[str, JsonValue]] | None = None


IDENTITY_PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    problem_status: {
        "model": ProblemResponse,
        "content": {
            "application/problem+json": {
                "schema": {"$ref": "#/components/schemas/ProblemResponse"}
            }
        },
    }
    for problem_status in (401, 403, 409, 422, 423, 429, 503)
}


def _credential_values(
    payload: CredentialsRequest,
) -> tuple[str | None, str | None, str | None]:
    if isinstance(payload, LocalCredentialsRequest):
        return payload.identifier, payload.password.get_secret_value(), None
    return None, None, payload.authorization_code.get_secret_value()


def _context(request: Request) -> RequestContext:
    client_host = request.client.host if request.client is not None else "unknown"
    truncated_ip = client_host if ":" in client_host else ".".join(client_host.split(".")[:3])
    return RequestContext(
        request_id=UUID(request.state.request_id),
        correlation_id=UUID(request.state.correlation_id),
        truncated_ip=truncated_ip,
        origin=request.headers.get("Origin", "unknown"),
    )


def _require_origin(origin: str, allowed_origin: str) -> None:
    if origin != allowed_origin:
        raise DomainError(ErrorCode.FORBIDDEN)


def _session_credentials(
    session_token: str | None,
    csrf_token: str,
) -> tuple[str, str]:
    if not session_token:
        raise DomainError(ErrorCode.UNAUTHENTICATED)
    return session_token, csrf_token


def _session_token(token: str | None) -> str:
    if not token:
        raise DomainError(ErrorCode.UNAUTHENTICATED)
    return token


def _expected_version(value: str) -> int:
    if len(value) < 3 or not value.startswith('"') or not value.endswith('"'):
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    raw = value[1:-1]
    if not raw.isdigit():
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    return int(raw)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _apply_session_continuation(
    response: Response,
    continuation: SessionContinuation,
) -> None:
    if continuation.rotated:
        _set_session_cookie(response, continuation.session_token)
        response.headers["X-CSRF-Token"] = continuation.csrf_token


def _preferences_response(preferences: UserPreferences) -> PreferencesResponse:
    return PreferencesResponse(
        account_id=preferences.account_id,
        interface_locale=preferences.interface_locale,
        timezone=preferences.timezone,
        day_cutover_local_time=preferences.day_cutover_local_time.isoformat(),
        preferred_sprint_minutes=preferences.preferred_sprint_minutes,
        accessibility_preferences=preferences.accessibility_preferences,
        media_preferences=preferences.media_preferences,
        version=preferences.version,
        updated_at=preferences.updated_at,
    )


def _consent_response(consent: ConsentDecision) -> ConsentResponse:
    return ConsentResponse(
        consent_id=consent.consent_id,
        account_id=consent.account_id,
        purpose_code=consent.purpose_code,
        status=consent.status.value,
        policy_revision_id=consent.policy_revision_id,
        version=consent.version,
        decided_at=consent.decided_at,
        withdrawn_at=consent.withdrawn_at,
    )


def identity_router(
    service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> IdentityApplicationService:
        if service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        return service

    @router.post(
        "/api/v1/accounts",
        operation_id="register_account",
        response_model=AccountResponse,
        status_code=status.HTTP_201_CREATED,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def register_account(
        payload: CredentialsRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
    ) -> AccountResponse:
        _require_origin(origin, allowed_origin)
        identifier, password, authorization_code = _credential_values(payload)
        result = await application_service().register_account(
            RegisterAccount(
                provider_type=payload.provider_type,
                identifier=identifier,
                password=password,
                authorization_code=authorization_code,
                idempotency_key=idempotency_key,
                context=_context(request),
            )
        )
        return AccountResponse(account_id=result.account_id, version=result.version)

    @router.post(
        "/api/v1/session",
        operation_id="authenticate_session",
        response_model=SessionResponse,
        status_code=status.HTTP_201_CREATED,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def authenticate_session(
        payload: CredentialsRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
    ) -> SessionResponse:
        _require_origin(origin, allowed_origin)
        identifier, password, authorization_code = _credential_values(payload)
        result = await application_service().authenticate_session(
            AuthenticateSession(
                provider_type=payload.provider_type,
                identifier=identifier,
                password=password,
                authorization_code=authorization_code,
                idempotency_key=idempotency_key,
                context=_context(request),
            )
        )
        _set_session_cookie(response, result.session_token)
        return SessionResponse(
            session_id=result.session_id,
            account_id=result.account_id,
            roles=list(result.roles),
            csrf_token=result.csrf_token,
            idle_expires_at=result.idle_expires_at,
            absolute_expires_at=result.absolute_expires_at,
        )

    @router.get(
        "/api/v1/session",
        operation_id="get_current_session",
        response_model=CurrentSessionResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def get_current_session(
        request: Request,
        response: Response,
        session_token: SessionCookieToken = None,
    ) -> CurrentSessionResponse:
        current = await application_service().get_current_session(
            _session_token(session_token),
            _context(request),
        )
        _set_session_cookie(response, current.session_token)
        return CurrentSessionResponse(
            session_id=current.session_id,
            account_id=current.account_id,
            roles=list(current.roles),
            csrf_token=current.csrf_token,
            idle_expires_at=current.idle_expires_at,
            absolute_expires_at=current.absolute_expires_at,
            preferences=_preferences_response(current.preferences),
            consents=[_consent_response(consent) for consent in current.consents],
        )

    @router.delete(
        "/api/v1/session",
        operation_id="revoke_session",
        status_code=status.HTTP_204_NO_CONTENT,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def revoke_session(
        request: Request,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key", max_length=255),
        ] = None,
    ) -> Response:
        _require_origin(origin, allowed_origin)
        session_token, csrf_token = _session_credentials(session_token, csrf_token)
        await application_service().revoke_session(
            RevokeSession(
                session_token=session_token,
                csrf_token=csrf_token,
                idempotency_key=idempotency_key,
                context=_context(request),
            )
        )
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        _clear_session_cookie(response)
        return response

    @router.put(
        "/api/v1/account/password",
        operation_id="change_password",
        response_model=AccountResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def change_password(
        payload: ChangePasswordRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> AccountResponse:
        _require_origin(origin, allowed_origin)
        session_token, csrf_token = _session_credentials(session_token, csrf_token)
        result = await application_service().change_password(
            ChangePassword(
                session_token=session_token,
                csrf_token=csrf_token,
                current_password=payload.current_password.get_secret_value(),
                new_password=payload.new_password.get_secret_value(),
                expected_version=_expected_version(if_match),
                idempotency_key=idempotency_key,
                context=_context(request),
            )
        )
        _clear_session_cookie(response)
        return AccountResponse(account_id=result.account_id, version=result.version)

    @router.patch(
        "/api/v1/account/preferences",
        operation_id="update_user_preferences",
        response_model=PreferencesResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def update_user_preferences(
        payload: PreferencesRequest,
        request: Request,
        response: Response,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key", max_length=255),
        ] = None,
    ) -> PreferencesResponse:
        _require_origin(origin, allowed_origin)
        session_token, csrf_token = _session_credentials(session_token, csrf_token)
        result = await application_service().update_preferences(
            UpdateUserPreferences(
                session_token=session_token,
                csrf_token=csrf_token,
                expected_version=_expected_version(if_match),
                idempotency_key=idempotency_key,
                context=_context(request),
                interface_locale=payload.interface_locale,
                timezone=payload.timezone,
                preferred_sprint_minutes=payload.preferred_sprint_minutes,
                accessibility_preferences=payload.accessibility_preferences,
                media_preferences=payload.media_preferences,
            )
        )
        _apply_session_continuation(response, result.continuation)
        return _preferences_response(result.preferences)

    @router.put(
        "/api/v1/consents/{purpose}",
        operation_id="update_consent",
        response_model=ConsentResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def update_consent(
        purpose: str,
        payload: ConsentRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> ConsentResponse:
        _require_origin(origin, allowed_origin)
        session_token, csrf_token = _session_credentials(session_token, csrf_token)
        result = await application_service().update_consent(
            UpdateConsent(
                session_token=session_token,
                csrf_token=csrf_token,
                purpose_code=purpose,
                status=payload.status,
                policy_revision_id=payload.policy_revision_id,
                expected_version=_expected_version(if_match),
                idempotency_key=idempotency_key,
                context=_context(request),
            )
        )
        _apply_session_continuation(response, result.continuation)
        return _consent_response(result.consent)

    return router
