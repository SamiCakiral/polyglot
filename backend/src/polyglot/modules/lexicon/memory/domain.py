from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from polyglot.modules.lexicon.memory.ports import MemoryRating, MemoryState, ScheduledState
from polyglot.platform.errors import DomainError, ErrorCode


def _uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"{field} must be UUIDv7")


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"{field} must be timezone-aware")
    return value.astimezone(UTC)


class PromptStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass(frozen=True, slots=True)
class MemoryPrompt:
    prompt_id: UUID
    profile_id: UUID
    target_ref: UUID
    target_revision_id: UUID
    direction: str
    modality: str
    operation: str
    protocol_id: str
    protocol_revision: int
    rating_semantics_id: str
    scheduler_policy_id: UUID
    scheduler_kind: str
    scheduler_version: str
    parameter_set_id: str
    policy_revision: int
    status: PromptStatus
    version: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for field, value in (
            ("prompt_id", self.prompt_id),
            ("profile_id", self.profile_id),
            ("target_ref", self.target_ref),
            ("target_revision_id", self.target_revision_id),
            ("scheduler_policy_id", self.scheduler_policy_id),
        ):
            _uuid7(value, field)
        if self.protocol_revision < 1 or self.policy_revision < 1 or self.version < 1:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid prompt version")
        if not all(
            (
                self.direction,
                self.modality,
                self.operation,
                self.protocol_id,
                self.rating_semantics_id,
                self.scheduler_kind,
                self.scheduler_version,
                self.parameter_set_id,
            )
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="prompt semantics are required")
        object.__setattr__(self, "created_at", _utc(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _utc(self.updated_at, "updated_at"))

    @property
    def compatibility_key(self) -> tuple[object, ...]:
        return (
            self.profile_id,
            self.target_ref,
            self.target_revision_id,
            self.direction,
            self.modality,
            self.operation,
            self.protocol_id,
            self.protocol_revision,
            self.rating_semantics_id,
        )

    def transition(self, status: PromptStatus, at: datetime) -> MemoryPrompt:
        return replace(self, status=status, version=self.version + 1, updated_at=_utc(at, "at"))


@dataclass(frozen=True, slots=True)
class MemoryScheduleState:
    prompt_id: UUID
    scheduler_kind: str
    scheduler_version: str
    parameter_set_id: str
    policy_revision: int
    state: MemoryState
    difficulty: Decimal | None
    stability: Decimal | None
    desired_retention: Decimal
    last_review_at: datetime | None
    due_at: datetime
    reps: int
    lapses: int
    last_rating: MemoryRating | None
    last_review_id: UUID | None
    projection_version: int
    computed_at: datetime
    causal_checkpoint: str
    step: int | None

    def __post_init__(self) -> None:
        _uuid7(self.prompt_id, "prompt_id")
        if self.last_review_id is not None:
            _uuid7(self.last_review_id, "last_review_id")
        if self.policy_revision < 1 or self.projection_version < 1:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid projection version")
        if self.reps < 0 or self.lapses < 0 or self.lapses > self.reps:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid schedule counters")
        if not all((self.scheduler_kind, self.scheduler_version, self.parameter_set_id)):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="scheduler identity is required")
        if not Decimal("0.80") <= self.desired_retention <= Decimal("0.97"):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid desired retention")
        object.__setattr__(self, "due_at", _utc(self.due_at, "due_at"))
        object.__setattr__(self, "computed_at", _utc(self.computed_at, "computed_at"))
        if self.last_review_at is not None:
            object.__setattr__(
                self,
                "last_review_at",
                _utc(self.last_review_at, "last_review_at"),
            )

    def scheduled_state(self) -> ScheduledState:
        return ScheduledState(
            state=self.state,
            difficulty=self.difficulty,
            stability=self.stability,
            due_at=self.due_at,
            last_review_at=self.last_review_at,
            step=self.step,
            reps=self.reps,
            lapses=self.lapses,
        )


@dataclass(frozen=True, slots=True)
class MemoryReview:
    review_id: UUID
    prompt_id: UUID
    opportunity_id: UUID
    attempt_id: UUID | None
    response_ref: str | None
    correction_ref: str | None
    highest_hint: int
    active_duration_ms: int
    scheduled_at: datetime
    reviewed_at: datetime
    rating: MemoryRating
    state_before: ScheduledState
    state_after: ScheduledState
    scheduler_kind: str
    scheduler_version: str
    parameter_set_id: str
    policy_revision: int
    idempotency_key: str
    low_confidence: bool
    certification_ref: str
    certified_operation: str
    certified_protocol_id: str
    certified_protocol_revision: int
    certified_target_revision_id: UUID

    def __post_init__(self) -> None:
        for field, value in (
            ("review_id", self.review_id),
            ("prompt_id", self.prompt_id),
            ("opportunity_id", self.opportunity_id),
        ):
            _uuid7(value, field)
        if self.attempt_id is not None:
            _uuid7(self.attempt_id, "attempt_id")
        _uuid7(self.certified_target_revision_id, "certified_target_revision_id")
        if (
            self.active_duration_ms < 0
            or self.policy_revision < 1
            or self.certified_protocol_revision < 1
            or not self.idempotency_key
            or not self.certification_ref.strip()
            or not self.certified_operation.strip()
            or not self.certified_protocol_id.strip()
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid memory review")
        object.__setattr__(self, "scheduled_at", _utc(self.scheduled_at, "scheduled_at"))
        object.__setattr__(self, "reviewed_at", _utc(self.reviewed_at, "reviewed_at"))
        before = self.state_before
        after = self.state_after
        if (
            before.reps < 0
            or before.lapses < 0
            or before.lapses > before.reps
            or after.reps != before.reps + 1
            or after.lapses < before.lapses
            or after.lapses > before.lapses + 1
            or after.lapses > after.reps
            or after.last_review_at is None
            or _utc(after.last_review_at, "state_after.last_review_at") != self.reviewed_at
            or (
                before.last_review_at is not None
                and _utc(before.last_review_at, "state_before.last_review_at")
                > self.reviewed_at
            )
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid review transition")


@dataclass(frozen=True, slots=True)
class MemoryScheduleReset:
    reset_id: UUID
    prompt_id: UUID
    reason: str
    reset_at: datetime
    previous_checkpoint: str

    def __post_init__(self) -> None:
        _uuid7(self.reset_id, "reset_id")
        _uuid7(self.prompt_id, "prompt_id")
        if not self.reason.strip():
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="reset reason is required")
        object.__setattr__(self, "reset_at", _utc(self.reset_at, "reset_at"))


@dataclass(frozen=True, slots=True)
class MemoryPromptLineage:
    source_prompt_id: UUID
    canonical_prompt_id: UUID
    merged_at: datetime

    def __post_init__(self) -> None:
        _uuid7(self.source_prompt_id, "source_prompt_id")
        _uuid7(self.canonical_prompt_id, "canonical_prompt_id")
        object.__setattr__(self, "merged_at", _utc(self.merged_at, "merged_at"))


@dataclass(frozen=True, slots=True)
class MemoryAggregate:
    prompt: MemoryPrompt
    schedule: MemoryScheduleState
    reviews: tuple[MemoryReview, ...] = ()
    resets: tuple[MemoryScheduleReset, ...] = ()
    lineages: tuple[MemoryPromptLineage, ...] = ()

    def __post_init__(self) -> None:
        if self.prompt.prompt_id != self.schedule.prompt_id:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="schedule prompt mismatch")
        allowed_prompt_ids = {self.prompt.prompt_id}
        for lineage in self.lineages:
            if lineage.canonical_prompt_id != self.prompt.prompt_id:
                raise DomainError(ErrorCode.VALIDATION_FAILED, detail="lineage prompt mismatch")
            allowed_prompt_ids.add(lineage.source_prompt_id)
        if any(review.prompt_id not in allowed_prompt_ids for review in self.reviews):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="review prompt mismatch")
        if any(reset.prompt_id not in allowed_prompt_ids for reset in self.resets):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="reset prompt mismatch")
        if len({review.review_id for review in self.reviews}) != len(self.reviews):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="duplicate review fact")
        if len({reset.reset_id for reset in self.resets}) != len(self.resets):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="duplicate reset fact")
        if (
            self.schedule.last_review_id is not None
            and self.schedule.last_review_id not in {review.review_id for review in self.reviews}
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="last review is not in history")
