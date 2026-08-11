"""Generation jobs and the closed authoring tool facade."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response, Security
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
from polyglot.interfaces.tools.executor import ToolInvocation, ToolResult, ToolScope
from polyglot.interfaces.tools.registry import TOOL_DEFINITIONS
from polyglot.modules.generation.application import (
    AuthoringArtifactView,
    GenerationApplicationService,
    RequestGenerationJob,
)
from polyglot.modules.identity.application import CurrentSessionResult, IdentityApplicationService
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue

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


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestGenerationJobRequest(ClosedModel):
    task_type: str = Field(min_length=1, max_length=120)
    task_input: dict[str, JsonValue]
    tool_allowlist: tuple[str, ...] = Field(min_length=1, max_length=11)
    provider_code: Literal["lm_studio"]
    model_code: Literal["qwen/qwen3.6-35b-a3b"]
    prompt_revision: str = Field(min_length=1, max_length=120)
    max_attempts: Literal[1]
    max_input_tokens: int = Field(ge=1, le=1_000_000)
    max_output_tokens: int = Field(ge=1, le=1_000_000)
    max_cost_micros: int = Field(ge=1, le=1_000_000_000)


class ToolScopeRequest(ClosedModel):
    pack_revision_id: UUID | None = None
    profile_id: UUID | None = None
    job_id: UUID | None = None
    mandate_id: UUID | None = None


class ToolTraceRequest(ClosedModel):
    correlation_id: UUID
    causation_id: UUID | None = None
    policy_revisions: dict[str, str] = Field(default_factory=dict)


class InvokeToolRequest(ClosedModel):
    tool_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    invocation_id: UUID
    actor_role: str = Field(min_length=1, max_length=32)
    scope: ToolScopeRequest = Field(default_factory=ToolScopeRequest)
    expected_version: int | None = Field(default=None, ge=1)
    input: dict[str, JsonValue]
    trace: ToolTraceRequest


class GenerationJobResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    job_id: UUID
    requested_by_actor_id: UUID
    task_type: str
    status: str
    provider_code: str
    model_code: str
    prompt_revision: str
    tool_allowlist: tuple[str, ...]
    max_attempts: int
    attempt_count: int
    result_draft_id: UUID | None
    error_code: str | None
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    version: int


class AuthoringArtifactResponse(ClosedModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    artifact_id: UUID
    artifact_type: str
    source_tool_name: str
    status: str
    payload: dict[str, JsonValue]
    checksum: str
    created_at: datetime


class ToolFailureResponse(ClosedModel):
    code: str
    retryable: bool
    field_path: str | None
    details_codes: tuple[str, ...]


class ToolResultResponse(ClosedModel):
    invocation_id: UUID
    tool_version: str
    status: str
    output: dict[str, JsonValue] | None
    error: ToolFailureResponse | None
    output_schema_version: int
    provenance_id: UUID
    started_at: datetime
    finished_at: datetime
    output_fingerprint: str


class ToolDefinitionResponse(ClosedModel):
    name: str
    version: str
    roles: tuple[str, ...]
    effect: str
    timeout_ms: int
    max_input_bytes: int
    max_output_bytes: int
    input_schema: dict[str, JsonValue]
    output_schema: dict[str, JsonValue]


def generation_router(
    service: GenerationApplicationService | None,
    identity_service: IdentityApplicationService | None,
    *,
    allowed_origin: str,
) -> APIRouter:
    router = APIRouter()

    def application_service() -> GenerationApplicationService:
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

    @router.get(
        "/api/v1/tools",
        operation_id="list_authoring_tools",
        response_model=list[ToolDefinitionResponse],
        responses=PROBLEM_RESPONSES,
    )
    async def list_authoring_tools(
        request: Request,
        session_token: SessionCookieToken = None,
    ) -> list[ToolDefinitionResponse]:
        current = await session_for(request, session_token)
        roles = set(current.roles)
        return [
            ToolDefinitionResponse(
                name=definition.name,
                version=definition.version,
                roles=tuple(sorted(definition.roles)),
                effect=definition.effect.value,
                timeout_ms=definition.timeout_ms,
                max_input_bytes=definition.max_input_bytes,
                max_output_bytes=definition.max_output_bytes,
                input_schema=definition.input_schema(),
                output_schema=definition.output_schema(),
            )
            for definition in TOOL_DEFINITIONS
            if roles & definition.roles
        ]

    @router.get(
        "/api/v1/authoring-artifacts",
        operation_id="list_authoring_artifacts",
        response_model=list[AuthoringArtifactResponse],
        responses=PROBLEM_RESPONSES,
    )
    async def list_authoring_artifacts(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        session_token: SessionCookieToken = None,
    ) -> list[AuthoringArtifactResponse]:
        current = await session_for(request, session_token)
        artifacts = await application_service().list_artifacts(
            current.account_id, limit=limit
        )
        return [AuthoringArtifactResponse.model_validate(item) for item in artifacts]

    @router.get(
        "/api/v1/authoring-artifacts/{artifact_id}",
        operation_id="get_authoring_artifact",
        response_model=AuthoringArtifactResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def get_authoring_artifact(
        artifact_id: UUID,
        request: Request,
        session_token: SessionCookieToken = None,
    ) -> AuthoringArtifactResponse:
        current = await session_for(request, session_token)
        artifact: AuthoringArtifactView = await application_service().get_artifact(
            current.account_id, artifact_id
        )
        return AuthoringArtifactResponse.model_validate(artifact)

    @router.post(
        "/api/v1/generation-jobs",
        operation_id="request_generation_job",
        response_model=GenerationJobResponse,
        status_code=201,
        responses=PROBLEM_RESPONSES,
    )
    async def request_generation_job(
        payload: RequestGenerationJobRequest,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> GenerationJobResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        if not {"author", "reviewer", "admin"} & set(current.roles):
            raise DomainError(ErrorCode.FORBIDDEN)
        view = await application_service().request_job(
            current.account_id,
            RequestGenerationJob(**payload.model_dump()),
            idempotency_key=idempotency_key,
        )
        response.headers["ETag"] = f'"{view.version}"'
        return GenerationJobResponse.model_validate(view)

    @router.get(
        "/api/v1/jobs/{id}",
        operation_id="get_generation_job",
        response_model=GenerationJobResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def get_generation_job(
        id: UUID,
        request: Request,
        response: Response,
        session_token: SessionCookieToken = None,
    ) -> GenerationJobResponse:
        current = await session_for(request, session_token)
        view = await application_service().get_job(current.account_id, id)
        response.headers["ETag"] = f'"{view.version}"'
        return GenerationJobResponse.model_validate(view)

    @router.post(
        "/api/v1/generation-jobs/{job_id}:cancel",
        operation_id="cancel_generation_job",
        response_model=GenerationJobResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def cancel_generation_job(
        job_id: UUID,
        request: Request,
        response: Response,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        if_match: IfMatchHeader,
        session_token: SessionCookieToken = None,
    ) -> GenerationJobResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        view = await application_service().cancel_job(
            current.account_id,
            job_id,
            expected_version=_expected_version(if_match),
            idempotency_key=idempotency_key,
        )
        response.headers["ETag"] = f'"{view.version}"'
        return GenerationJobResponse.model_validate(view)

    @router.post(
        "/api/v1/tools/{tool_name}:invoke",
        operation_id="invoke_authoring_tool",
        response_model=ToolResultResponse,
        responses=PROBLEM_RESPONSES,
    )
    async def invoke_authoring_tool(
        tool_name: str,
        payload: InvokeToolRequest,
        request: Request,
        idempotency_key: IdempotencyKey,
        origin: OriginHeader,
        csrf_token: CsrfHeader,
        session_token: SessionCookieToken = None,
    ) -> ToolResultResponse:
        current = await session_for(request, session_token, csrf_token, origin)
        if payload.actor_role not in current.roles:
            raise DomainError(ErrorCode.FORBIDDEN)
        if str(payload.trace.correlation_id) != request.state.correlation_id:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        invocation = ToolInvocation(
            tool_name,
            payload.tool_version,
            payload.invocation_id,
            current.account_id,
            payload.actor_role,
            ToolScope(**payload.scope.model_dump()),
            idempotency_key,
            payload.expected_version,
            payload.input,
            payload.trace.correlation_id,
            payload.trace.causation_id,
            payload.trace.policy_revisions,
        )
        result: ToolResult = await application_service().invoke_tool(invocation)
        return ToolResultResponse.model_validate(result, from_attributes=True)

    return router
