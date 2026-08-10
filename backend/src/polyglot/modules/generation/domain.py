from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode


class GenerationJobStatus(StrEnum):
    REQUESTED = "requested"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"


class GenerationAttemptStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class GenerationAttempt:
    attempt_id: UUID
    attempt_no: int
    provider_code: str
    model_code: str
    prompt_revision: str
    tool_versions: tuple[str, ...]
    input_fingerprint: str
    started_at: datetime
    finished_at: datetime
    status: GenerationAttemptStatus
    error_code: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_micros: int = 0

    def __post_init__(self) -> None:
        if self.attempt_no < 1 or self.finished_at < self.started_at:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        if min(self.input_tokens, self.output_tokens, self.cost_micros) < 0:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        if self.status is GenerationAttemptStatus.SUCCEEDED and self.error_code is not None:
            raise DomainError(ErrorCode.VALIDATION_FAILED)


@dataclass(frozen=True, slots=True)
class GenerationJob:
    job_id: UUID
    requested_by_actor_id: UUID
    task_type: str
    input_fingerprint: str
    tool_allowlist: tuple[str, ...]
    max_attempts: int
    max_input_tokens: int
    max_output_tokens: int
    max_cost_micros: int
    requested_at: datetime
    status: GenerationJobStatus = GenerationJobStatus.REQUESTED
    attempts: tuple[GenerationAttempt, ...] = ()
    result_draft_id: UUID | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if not self.task_type or not self.tool_allowlist:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        if min(
            self.max_attempts,
            self.max_input_tokens,
            self.max_output_tokens,
            self.max_cost_micros,
        ) < 1:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        if len(self.attempts) > self.max_attempts or self.version < 1:
            raise DomainError(ErrorCode.VALIDATION_FAILED)

    def queue(self) -> GenerationJob:
        if self.status is not GenerationJobStatus.REQUESTED:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return replace(self, status=GenerationJobStatus.QUEUED, version=self.version + 1)

    def start(self) -> GenerationJob:
        if self.status is not GenerationJobStatus.QUEUED:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        if len(self.attempts) >= self.max_attempts:
            raise DomainError(ErrorCode.BUDGET_EXCEEDED)
        return replace(self, status=GenerationJobStatus.RUNNING, version=self.version + 1)

    def finish_attempt(
        self, attempt: GenerationAttempt, *, result_draft_id: UUID | None = None
    ) -> GenerationJob:
        if self.status is not GenerationJobStatus.RUNNING:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        if attempt.attempt_no != len(self.attempts) + 1:
            raise DomainError(ErrorCode.VERSION_CONFLICT)
        totals = (
            sum(item.input_tokens for item in self.attempts) + attempt.input_tokens,
            sum(item.output_tokens for item in self.attempts) + attempt.output_tokens,
            sum(item.cost_micros for item in self.attempts) + attempt.cost_micros,
        )
        if totals[0] > self.max_input_tokens or totals[1] > self.max_output_tokens:
            raise DomainError(ErrorCode.BUDGET_EXCEEDED)
        if totals[2] > self.max_cost_micros:
            raise DomainError(ErrorCode.BUDGET_EXCEEDED)
        succeeded = attempt.status is GenerationAttemptStatus.SUCCEEDED
        return replace(
            self,
            status=(GenerationJobStatus.SUCCEEDED if succeeded else GenerationJobStatus.FAILED),
            attempts=(*self.attempts, attempt),
            result_draft_id=result_draft_id if succeeded else None,
            version=self.version + 1,
        )

    def request_cancel(self) -> GenerationJob:
        if self.status in {GenerationJobStatus.REQUESTED, GenerationJobStatus.QUEUED}:
            return replace(self, status=GenerationJobStatus.CANCELLED, version=self.version + 1)
        if self.status is GenerationJobStatus.RUNNING:
            return replace(
                self, status=GenerationJobStatus.CANCEL_REQUESTED, version=self.version + 1
            )
        raise DomainError(ErrorCode.JOB_NOT_CANCELLABLE)

    def cancel(self) -> GenerationJob:
        if self.status is not GenerationJobStatus.CANCEL_REQUESTED:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return replace(self, status=GenerationJobStatus.CANCELLED, version=self.version + 1)
