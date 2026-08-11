from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response, Security, status
from fastapi.security import APIKeyCookie
from pydantic import BaseModel, ConfigDict

from polyglot.interfaces.http.routes.identity import (
    IDENTITY_PROBLEM_RESPONSES,
    SESSION_COOKIE,
    _context,
    _expected_version,
    _require_origin,
    _session_token,
)
from polyglot.modules.identity.application import IdentityApplicationService
from polyglot.modules.identity.language_persistence import AccountLanguageApplicationService
from polyglot.modules.identity.languages import (
    AccountLanguage,
    LanguageRelationship,
    SelfAssessedBand,
)
from polyglot.platform.errors import DomainError, ErrorCode

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


class CreateAccountLanguageRequest(ClosedModel):
    variety_id: UUID
    relationship: LanguageRelationship
    self_assessed_band: SelfAssessedBand
    use_for_explanations: bool = True
    use_for_contrasts: bool = True


class ReviseAccountLanguageRequest(ClosedModel):
    relationship: LanguageRelationship
    self_assessed_band: SelfAssessedBand
    use_for_explanations: bool
    use_for_contrasts: bool


class AccountLanguageResponse(ClosedModel):
    account_language_id: UUID
    variety_id: UUID
    relationship: LanguageRelationship
    self_assessed_band: SelfAssessedBand
    use_for_explanations: bool
    use_for_contrasts: bool
    grants_mastery: bool
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class AccountLanguagePageResponse(ClosedModel):
    items: tuple[AccountLanguageResponse, ...]


def _response(language: AccountLanguage) -> AccountLanguageResponse:
    return AccountLanguageResponse(
        account_language_id=language.account_language_id,
        variety_id=language.variety_id,
        relationship=language.relationship,
        self_assessed_band=language.self_assessed_band,
        use_for_explanations=language.use_for_explanations,
        use_for_contrasts=language.use_for_contrasts,
        grants_mastery=language.grants_mastery,
        version=language.version,
        created_at=language.created_at,
        updated_at=language.updated_at,
        archived_at=language.archived_at,
    )


_ETAG_RESPONSE: dict[int | str, dict[str, Any]] = {
    **IDENTITY_PROBLEM_RESPONSES,
    200: {
        "headers": {
            "ETag": {
                "description": "Quoted optimistic concurrency version.",
                "schema": {"type": "string"},
            }
        }
    },
}


def _etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


def account_languages_router(
    service: AccountLanguageApplicationService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> AccountLanguageApplicationService:
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
        "/api/v1/account-languages",
        operation_id="list_account_languages",
        response_model=AccountLanguagePageResponse,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def list_account_languages(
        request: Request, session_token: SessionCookieToken = None
    ) -> AccountLanguagePageResponse:
        account_id = await account_for(request, session_token)
        languages = await application_service().list_languages(account_id)
        return AccountLanguagePageResponse(items=tuple(map(_response, languages)))

    @router.post(
        "/api/v1/account-languages",
        operation_id="create_account_language",
        response_model=AccountLanguageResponse,
        status_code=status.HTTP_201_CREATED,
        responses=IDENTITY_PROBLEM_RESPONSES,
    )
    async def create_account_language(
        payload: CreateAccountLanguageRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> AccountLanguageResponse:
        account_id = await account_for(request, session_token, csrf_token, origin)
        language = await application_service().create_language(
            account_id=account_id,
            variety_id=payload.variety_id,
            relationship=payload.relationship,
            self_assessed_band=payload.self_assessed_band,
            use_for_explanations=payload.use_for_explanations,
            use_for_contrasts=payload.use_for_contrasts,
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        _etag(response, language.version)
        return _response(language)

    @router.patch(
        "/api/v1/account-languages/{language_id}",
        operation_id="revise_account_language",
        response_model=AccountLanguageResponse,
        responses=_ETAG_RESPONSE,
    )
    async def revise_account_language(
        language_id: UUID,
        payload: ReviseAccountLanguageRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        if_match: IfMatchHeader,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> AccountLanguageResponse:
        account_id = await account_for(request, session_token, csrf_token, origin)
        language = await application_service().revise_language(
            account_id=account_id,
            language_id=language_id,
            relationship=payload.relationship,
            self_assessed_band=payload.self_assessed_band,
            use_for_explanations=payload.use_for_explanations,
            use_for_contrasts=payload.use_for_contrasts,
            expected_version=_expected_version(if_match),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        _etag(response, language.version)
        return _response(language)

    @router.post(
        "/api/v1/account-languages/{language_id}:archive",
        operation_id="archive_account_language",
        response_model=AccountLanguageResponse,
        responses=_ETAG_RESPONSE,
    )
    async def archive_account_language(
        language_id: UUID,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        if_match: IfMatchHeader,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> AccountLanguageResponse:
        account_id = await account_for(request, session_token, csrf_token, origin)
        language = await application_service().archive_language(
            account_id=account_id,
            language_id=language_id,
            expected_version=_expected_version(if_match),
            idempotency_key=idempotency_key,
            context=_context(request),
        )
        _etag(response, language.version)
        return _response(language)

    return router
