from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from polyglot.interfaces.tools.executor import ToolInvocation, ToolResult
from polyglot.platform.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class RequestGenerationJob:
    task_type: str
    task_input: dict[str, JsonValue]
    tool_allowlist: tuple[str, ...]
    provider_code: str
    model_code: str
    prompt_revision: str
    max_attempts: int
    max_input_tokens: int
    max_output_tokens: int
    max_cost_micros: int


@dataclass(frozen=True, slots=True)
class GenerationJobView:
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


@dataclass(frozen=True, slots=True)
class AuthoringArtifactView:
    artifact_id: UUID
    artifact_type: str
    source_tool_name: str
    status: str
    payload: dict[str, JsonValue]
    checksum: str
    created_at: datetime


class GenerationApplicationService(Protocol):
    async def request_job(
        self,
        actor_id: UUID,
        command: RequestGenerationJob,
        *,
        idempotency_key: str,
    ) -> GenerationJobView: ...

    async def get_job(self, actor_id: UUID, job_id: UUID) -> GenerationJobView: ...

    async def cancel_job(
        self,
        actor_id: UUID,
        job_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> GenerationJobView: ...

    async def invoke_tool(self, invocation: ToolInvocation) -> ToolResult: ...

    async def list_artifacts(
        self, actor_id: UUID, *, limit: int = 100
    ) -> tuple[AuthoringArtifactView, ...]: ...

    async def get_artifact(
        self, actor_id: UUID, artifact_id: UUID
    ) -> AuthoringArtifactView: ...
