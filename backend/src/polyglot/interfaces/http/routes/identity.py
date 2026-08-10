from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from polyglot.modules.identity.application import (
    AuthenticateSession,
    ChangePassword,
    IdentityApplicationService,
    RegisterAccount,
    RequestContext,
    RevokeSession,
    UpdateConsent,
    UpdateUserPreferences,
)
from polyglot.modules.identity.domain import ConsentDecision, UserPreferences
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue

SESSION_COOKIE = "__Host-polyglot_session"

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CredentialsRequest(ClosedModel):
    provider_type: Literal["local_password", "oidc"]
    identifier: str | None = Field(default=None, max_length=320)
    password: SecretStr | None = None
    authorization_code: SecretStr | None = None

    @model_validator(mode="after")
    def validate_provider_shape(self) -> "CredentialsRequest":
        if self.provider_type == "local_password":
            if (
                self.identifier is None
                or self.password is None
                or self.authorization_code is not None
            ):
                raise ValueError("local credentials are incomplete")
        elif (
            self.authorization_code is None
            or self.identifier is not None
            or self.password is not None
        ):
            raise ValueError("OIDC credentials are incomplete")
        return self


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


def _context(request: Request) -> RequestContext:
    client_host = request.client.host if request.client is not None else "unknown"
    truncated_ip = client_host if ":" in client_host else ".".join(client_host.split(".")[:3])
    return RequestContext(
        request_id=UUID(request.state.request_id),
        correlation_id=UUID(request.state.correlation_id),
        truncated_ip=truncated_ip,
    )


def _require_origin(request: Request, allowed_origin: str) -> None:
    if request.headers.get("Origin") != allowed_origin:
        raise DomainError(ErrorCode.FORBIDDEN)


def _session_credentials(request: Request) -> tuple[str, str]:
    session_token = request.cookies.get(SESSION_COOKIE)
    csrf_token = request.headers.get("X-CSRF-Token")
    if not session_token:
        raise DomainError(ErrorCode.UNAUTHENTICATED)
    if not csrf_token:
        raise DomainError(ErrorCode.FORBIDDEN)
    return session_token, csrf_token


def _session_token(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise DomainError(ErrorCode.UNAUTHENTICATED)
    return token


def _expected_version(request: Request) -> int:
    value = request.headers.get("If-Match")
    if value is None or len(value) < 3 or not value.startswith('"') or not value.endswith('"'):
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
    )
    async def register_account(
        payload: CredentialsRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
    ) -> AccountResponse:
        _require_origin(request, allowed_origin)
        result = await application_service().register_account(
            RegisterAccount(
                provider_type=payload.provider_type,
                identifier=payload.identifier,
                password=payload.password.get_secret_value() if payload.password else None,
                authorization_code=(
                    payload.authorization_code.get_secret_value()
                    if payload.authorization_code
                    else None
                ),
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
    )
    async def authenticate_session(
        payload: CredentialsRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
    ) -> SessionResponse:
        _require_origin(request, allowed_origin)
        result = await application_service().authenticate_session(
            AuthenticateSession(
                provider_type=payload.provider_type,
                identifier=payload.identifier,
                password=payload.password.get_secret_value() if payload.password else None,
                authorization_code=(
                    payload.authorization_code.get_secret_value()
                    if payload.authorization_code
                    else None
                ),
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
    )
    async def get_current_session(request: Request, response: Response) -> CurrentSessionResponse:
        current = await application_service().get_current_session(_session_token(request))
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
    )
    async def revoke_session(
        request: Request,
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key", max_length=255),
        ] = None,
    ) -> Response:
        _require_origin(request, allowed_origin)
        session_token, csrf_token = _session_credentials(request)
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
    )
    async def change_password(
        payload: ChangePasswordRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
    ) -> AccountResponse:
        _require_origin(request, allowed_origin)
        session_token, csrf_token = _session_credentials(request)
        result = await application_service().change_password(
            ChangePassword(
                session_token=session_token,
                csrf_token=csrf_token,
                current_password=payload.current_password.get_secret_value(),
                new_password=payload.new_password.get_secret_value(),
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
    )
    async def update_user_preferences(
        payload: PreferencesRequest,
        request: Request,
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key", max_length=255),
        ] = None,
    ) -> PreferencesResponse:
        _require_origin(request, allowed_origin)
        session_token, csrf_token = _session_credentials(request)
        preferences = await application_service().update_preferences(
            UpdateUserPreferences(
                session_token=session_token,
                csrf_token=csrf_token,
                expected_version=_expected_version(request),
                idempotency_key=idempotency_key,
                context=_context(request),
                interface_locale=payload.interface_locale,
                timezone=payload.timezone,
                preferred_sprint_minutes=payload.preferred_sprint_minutes,
                accessibility_preferences=payload.accessibility_preferences,
                media_preferences=payload.media_preferences,
            )
        )
        return _preferences_response(preferences)

    @router.put(
        "/api/v1/consents/{purpose}",
        operation_id="update_consent",
        response_model=ConsentResponse,
    )
    async def update_consent(
        purpose: str,
        payload: ConsentRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
    ) -> ConsentResponse:
        _require_origin(request, allowed_origin)
        session_token, csrf_token = _session_credentials(request)
        consent = await application_service().update_consent(
            UpdateConsent(
                session_token=session_token,
                csrf_token=csrf_token,
                purpose_code=purpose,
                status=payload.status,
                policy_revision_id=payload.policy_revision_id,
                expected_version=_expected_version(request),
                idempotency_key=idempotency_key,
                context=_context(request),
            )
        )
        return _consent_response(consent)

    return router
