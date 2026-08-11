from __future__ import annotations

from datetime import datetime
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
from polyglot.modules.identity.application import CurrentSessionResult, IdentityApplicationService
from polyglot.modules.teacher.application import (
    TeacherActionView,
    TeacherConversationView,
    TeacherService,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateTeacherConversationRequest(ClosedModel):
    conversation_id: UUID
    title: str = Field(min_length=1, max_length=160)


class SendTeacherMessageRequest(ClosedModel):
    message_id: UUID
    content: str = Field(min_length=1, max_length=6000)
    page_context: dict[str, JsonValue] = Field(default_factory=dict)


class TeacherActionResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    action_id: UUID
    action_type: str
    status: str
    payload: dict[str, JsonValue]
    version: int
    applied_at: datetime
    reverted_at: datetime | None


class TeacherMessageResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    message_id: UUID
    role: str
    content: str
    provider_code: str | None
    model_code: str | None
    created_at: datetime
    actions: tuple[TeacherActionResponse, ...]


class TeacherConversationResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    conversation_id: UUID
    profile_id: UUID
    title: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    messages: tuple[TeacherMessageResponse, ...]


class TeacherConversationPageResponse(ClosedModel):
    items: tuple[TeacherConversationResponse, ...]


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {
        "model": ProblemResponse,
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemResponse"}}
        },
    }
    for status in (401, 403, 404, 409, 422, 428, 503)
}


def _conversation(view: TeacherConversationView) -> TeacherConversationResponse:
    return TeacherConversationResponse.model_validate(view, from_attributes=True)


def _action(view: TeacherActionView) -> TeacherActionResponse:
    return TeacherActionResponse.model_validate(view, from_attributes=True)


def teacher_router(
    service: TeacherService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> TeacherService:
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
        "/api/v1/language-profiles/{profile_id}/teacher-conversations",
        operation_id="create_teacher_conversation",
        response_model=TeacherConversationResponse,
        status_code=201,
        responses=PROBLEM_RESPONSES,
    )
    async def create_teacher_conversation(
        profile_id: UUID,
        body: CreateTeacherConversationRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf: CsrfHeader,
        token: SessionCookieToken = None,
    ) -> TeacherConversationResponse:
        current = await current_session(request, token, csrf=csrf, origin=origin)
        view = await application_service().create_conversation(
            current.account_id,
            profile_id,
            body.conversation_id,
            body.title,
            idempotency_key=idempotency_key,
        )
        response.headers["ETag"] = f'"{view.version}"'
        return _conversation(view)

    @router.get(
        "/api/v1/language-profiles/{profile_id}/teacher-conversations",
        operation_id="list_teacher_conversations",
        response_model=TeacherConversationPageResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def list_teacher_conversations(
        profile_id: UUID,
        request: Request,
        token: SessionCookieToken = None,
    ) -> TeacherConversationPageResponse:
        current = await current_session(request, token)
        views = await application_service().list_conversations(current.account_id, profile_id)
        return TeacherConversationPageResponse(items=tuple(_conversation(view) for view in views))

    @router.get(
        "/api/v1/teacher-conversations/{conversation_id}",
        operation_id="get_teacher_conversation",
        response_model=TeacherConversationResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def get_teacher_conversation(
        conversation_id: UUID,
        request: Request,
        response: Response,
        token: SessionCookieToken = None,
    ) -> TeacherConversationResponse:
        current = await current_session(request, token)
        view = await application_service().get_conversation(current.account_id, conversation_id)
        response.headers["ETag"] = f'"{view.version}"'
        return _conversation(view)

    @router.post(
        "/api/v1/teacher-conversations/{conversation_id}/messages",
        operation_id="send_teacher_message",
        response_model=TeacherConversationResponse,
        status_code=201,
        responses=PROBLEM_RESPONSES,
    )
    async def send_teacher_message(
        conversation_id: UUID,
        body: SendTeacherMessageRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        if_match: IfMatchHeader,
        origin: OriginHeader,
        csrf: CsrfHeader,
        token: SessionCookieToken = None,
    ) -> TeacherConversationResponse:
        current = await current_session(request, token, csrf=csrf, origin=origin)
        view = await application_service().send_message(
            current.account_id,
            conversation_id,
            body.message_id,
            body.content,
            body.page_context,
            expected_version=expected(if_match),
            idempotency_key=idempotency_key,
        )
        response.headers["ETag"] = f'"{view.version}"'
        return _conversation(view)

    @router.post(
        "/api/v1/teacher-actions/{action_id}:revert",
        operation_id="revert_teacher_action",
        response_model=TeacherActionResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def revert_teacher_action(
        action_id: UUID,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        if_match: IfMatchHeader,
        origin: OriginHeader,
        csrf: CsrfHeader,
        token: SessionCookieToken = None,
    ) -> TeacherActionResponse:
        current = await current_session(request, token, csrf=csrf, origin=origin)
        view = await application_service().revert_action(
            current.account_id,
            action_id,
            expected_version=expected(if_match),
            idempotency_key=idempotency_key,
        )
        response.headers["ETag"] = f'"{view.version}"'
        return _action(view)

    return router
