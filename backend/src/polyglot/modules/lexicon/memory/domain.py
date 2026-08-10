from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from polyglot.modules.lexicon.memory.policy import SchedulerPolicy
from polyglot.modules.lexicon.memory.ports import (
    MemoryRating,
    MemorySchedulerPort,
    MemoryState,
    ScheduledState,
)
from polyglot.platform.errors import DomainError, ErrorCode


def _uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"{field} must be UUIDv7")


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _scheduler_identity(
    scheduler_kind: str,
    scheduler_version: str,
    parameter_set_id: str,
    policy_revision: int,
) -> None:
    if (
        not scheduler_kind.strip()
        or not scheduler_version.strip()
        or not parameter_set_id.strip()
        or policy_revision < 1
    ):
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid scheduler identity")


def _state_counters(state: ScheduledState, field: str) -> None:
    if state.reps < 0 or state.lapses < 0 or state.lapses > state.reps:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"invalid {field} counters")
    _utc(state.due_at, f"{field}.due_at")
    if state.last_review_at is not None:
        _utc(state.last_review_at, f"{field}.last_review_at")


class PromptStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    DELETED = "deleted"


class ResumptionKind(StrEnum):
    RESUME = "resume"
    RESTORE = "restore"


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
        if self.protocol_revision < 1 or self.version < 1:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid prompt version")
        if not all(
            (
                self.direction,
                self.modality,
                self.operation,
                self.protocol_id,
                self.rating_semantics_id,
            )
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="prompt semantics are required")
        _scheduler_identity(
            self.scheduler_kind,
            self.scheduler_version,
            self.parameter_set_id,
            self.policy_revision,
        )
        created_at = _utc(self.created_at, "created_at")
        updated_at = _utc(self.updated_at, "updated_at")
        if updated_at < created_at:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="prompt update predates creation")
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)

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

    @property
    def creation_checkpoint(self) -> str:
        return f"created:{self.prompt_id}"

    def transition(self, status: PromptStatus, at: datetime) -> MemoryPrompt:
        transitioned_at = _utc(at, "at")
        return replace(
            self,
            status=status,
            version=self.version + 1,
            updated_at=transitioned_at,
        )


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
        _scheduler_identity(
            self.scheduler_kind,
            self.scheduler_version,
            self.parameter_set_id,
            self.policy_revision,
        )
        if self.projection_version < 1 or not self.causal_checkpoint:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid projection version")
        if not Decimal("0.80") <= self.desired_retention <= Decimal("0.97"):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid desired retention")
        if self.reps < 0 or self.lapses < 0 or self.lapses > self.reps:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid schedule counters")
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


def schedule_projection(
    *,
    prompt_id: UUID,
    state: ScheduledState,
    policy: SchedulerPolicy,
    scheduler: MemorySchedulerPort,
    projection_version: int,
    computed_at: datetime,
    last_rating: MemoryRating | None,
    last_review_id: UUID | None,
    checkpoint: str,
) -> MemoryScheduleState:
    return MemoryScheduleState(
        prompt_id=prompt_id,
        scheduler_kind=scheduler.identity.kind,
        scheduler_version=scheduler.identity.version,
        parameter_set_id=policy.parameter_set_id,
        policy_revision=policy.revision,
        state=state.state,
        difficulty=state.difficulty,
        stability=state.stability,
        desired_retention=policy.desired_retention,
        last_review_at=state.last_review_at,
        due_at=state.due_at,
        reps=state.reps,
        lapses=state.lapses,
        last_rating=last_rating,
        last_review_id=last_review_id,
        projection_version=projection_version,
        computed_at=_utc(computed_at, "computed_at"),
        causal_checkpoint=checkpoint,
        step=state.step,
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
    previous_checkpoint: str

    def __post_init__(self) -> None:
        for field, value in (
            ("review_id", self.review_id),
            ("prompt_id", self.prompt_id),
            ("opportunity_id", self.opportunity_id),
            ("certified_target_revision_id", self.certified_target_revision_id),
        ):
            _uuid7(value, field)
        if self.attempt_id is not None:
            _uuid7(self.attempt_id, "attempt_id")
        _scheduler_identity(
            self.scheduler_kind,
            self.scheduler_version,
            self.parameter_set_id,
            self.policy_revision,
        )
        if (
            self.active_duration_ms < 0
            or self.certified_protocol_revision < 1
            or not self.idempotency_key
            or not self.certification_ref.strip()
            or not self.certified_operation.strip()
            or not self.certified_protocol_id.strip()
            or not self.previous_checkpoint
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid memory review")
        reviewed_at = _utc(self.reviewed_at, "reviewed_at")
        object.__setattr__(self, "scheduled_at", _utc(self.scheduled_at, "scheduled_at"))
        object.__setattr__(self, "reviewed_at", reviewed_at)
        _state_counters(self.state_before, "state_before")
        _state_counters(self.state_after, "state_after")
        if (
            self.state_after.reps != self.state_before.reps + 1
            or self.state_after.lapses < self.state_before.lapses
            or self.state_after.lapses > self.state_before.lapses + 1
            or self.state_after.last_review_at is None
            or _utc(self.state_after.last_review_at, "state_after.last_review_at")
            != reviewed_at
            or (
                self.state_before.last_review_at is not None
                and _utc(self.state_before.last_review_at, "state_before.last_review_at")
                > reviewed_at
            )
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid review transition")

    @property
    def checkpoint(self) -> str:
        return f"review:{self.review_id}"


@dataclass(frozen=True, slots=True)
class MemoryScheduleReset:
    reset_id: UUID
    prompt_id: UUID
    reason: str
    reset_at: datetime
    previous_checkpoint: str
    scheduler_kind: str
    scheduler_version: str
    parameter_set_id: str
    policy_revision: int

    def __post_init__(self) -> None:
        _uuid7(self.reset_id, "reset_id")
        _uuid7(self.prompt_id, "prompt_id")
        if not self.reason.strip() or not self.previous_checkpoint:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="reset reason is required")
        _scheduler_identity(
            self.scheduler_kind,
            self.scheduler_version,
            self.parameter_set_id,
            self.policy_revision,
        )
        object.__setattr__(self, "reset_at", _utc(self.reset_at, "reset_at"))

    @property
    def checkpoint(self) -> str:
        return f"reset:{self.reset_id}"


@dataclass(frozen=True, slots=True)
class MemoryScheduleResumption:
    resumption_id: UUID
    prompt_id: UUID
    kind: ResumptionKind
    resumed_at: datetime
    previous_checkpoint: str
    scheduler_kind: str
    scheduler_version: str
    parameter_set_id: str
    policy_revision: int
    state_before: ScheduledState
    state_after: ScheduledState

    def __post_init__(self) -> None:
        _uuid7(self.resumption_id, "resumption_id")
        _uuid7(self.prompt_id, "prompt_id")
        if not self.previous_checkpoint:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="resumption checkpoint required")
        _scheduler_identity(
            self.scheduler_kind,
            self.scheduler_version,
            self.parameter_set_id,
            self.policy_revision,
        )
        object.__setattr__(self, "resumed_at", _utc(self.resumed_at, "resumed_at"))
        _state_counters(self.state_before, "state_before")
        _state_counters(self.state_after, "state_after")
        if (
            self.state_after.state is not self.state_before.state
            or self.state_after.difficulty != self.state_before.difficulty
            or self.state_after.stability != self.state_before.stability
            or self.state_after.last_review_at != self.state_before.last_review_at
            or self.state_after.step != self.state_before.step
            or self.state_after.reps != self.state_before.reps
            or self.state_after.lapses != self.state_before.lapses
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="resumption changed memory")

    @property
    def checkpoint(self) -> str:
        return f"{self.kind.value}:{self.resumption_id}"


@dataclass(frozen=True, slots=True)
class MemoryPromptLineage:
    source_prompt_id: UUID
    canonical_prompt_id: UUID
    merged_at: datetime

    def __post_init__(self) -> None:
        _uuid7(self.source_prompt_id, "source_prompt_id")
        _uuid7(self.canonical_prompt_id, "canonical_prompt_id")
        if self.source_prompt_id == self.canonical_prompt_id:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="self lineage is invalid")
        object.__setattr__(self, "merged_at", _utc(self.merged_at, "merged_at"))


@dataclass(frozen=True, slots=True)
class MemoryAggregate:
    prompt: MemoryPrompt
    schedule: MemoryScheduleState
    reviews: tuple[MemoryReview, ...] = ()
    resets: tuple[MemoryScheduleReset, ...] = ()
    resumptions: tuple[MemoryScheduleResumption, ...] = ()
    lineages: tuple[MemoryPromptLineage, ...] = ()

    def __post_init__(self) -> None:
        if self.prompt.prompt_id != self.schedule.prompt_id:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="schedule prompt mismatch")
        allowed_prompt_ids = {self.prompt.prompt_id}
        for lineage in self.lineages:
            if lineage.canonical_prompt_id != self.prompt.prompt_id:
                raise DomainError(ErrorCode.VALIDATION_FAILED, detail="lineage prompt mismatch")
            allowed_prompt_ids.add(lineage.source_prompt_id)
        facts: tuple[
            MemoryReview | MemoryScheduleReset | MemoryScheduleResumption,
            ...,
        ] = (*self.reviews, *self.resets, *self.resumptions)
        if any(fact.prompt_id not in allowed_prompt_ids for fact in facts):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="fact prompt mismatch")
        checkpoints = [fact.checkpoint for fact in facts]
        if len(set(checkpoints)) != len(checkpoints):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="duplicate causal fact")
        if len({lineage.source_prompt_id for lineage in self.lineages}) != len(self.lineages):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="duplicate lineage")
        if (
            self.schedule.last_review_id is not None
            and self.schedule.last_review_id not in {review.review_id for review in self.reviews}
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="last review is not in history")
