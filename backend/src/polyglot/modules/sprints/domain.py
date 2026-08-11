from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import StrEnum
from uuid import UUID


class SprintDomainError(ValueError):
    pass


def _require_uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise SprintDomainError(f"{field}_must_be_uuid7")


class PlanKind(StrEnum):
    DAILY = "daily"
    FREE = "free"
    FOUNDATION = "foundation"
    ASSESSMENT_PREP = "assessment_prep"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    PREPARING = "preparing"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class SprintRunStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"


class BlockStatus(StrEnum):
    PENDING = "pending"
    AVAILABLE = "available"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    ABANDONED = "abandoned"
    UNAVAILABLE = "unavailable"


class BlockFamily(StrEnum):
    RECALL_WARMUP = "recall_warmup"
    LEXICAL_ACQUISITION = "lexical_acquisition"
    VERSION_INPUT = "version_input"
    GRAMMAR_TOOLBOX = "grammar_toolbox"
    TRANSFORMATION_GYM = "transformation_gym"
    LISTENING = "listening"
    SHADOWING = "shadowing"
    GUIDED_OUTPUT = "guided_output"
    FREE_WRITING = "free_writing"
    DELAYED_RECODE = "delayed_recode"
    REFLECTION_CLOSE = "reflection_close"


_MAX_BLOCKS = {10: 4, 15: 4, 20: 4, 25: 5, 30: 5, 35: 6, 40: 6, 45: 7, 50: 7, 55: 7, 60: 7}
_P_ABS_NOVELTY = {
    10: 3,
    15: 5,
    20: 6,
    25: 8,
    30: 10,
    35: 11,
    40: 12,
    45: 13,
    50: 14,
    55: 15,
    60: 16,
}
CORE_ROLES = frozenset({"activation", "primary_objective", "unsupported_production", "reflection"})
MODALITIES = frozenset({"reading", "listening", "writing", "speaking"})


@dataclass(frozen=True, slots=True)
class CandidateBlock:
    candidate_id: UUID
    family: BlockFamily
    roles: frozenset[str]
    p50_seconds: int
    p80_seconds: int
    novelty_points: float = 0
    grammar_family: str | None = None
    modalities: frozenset[str] = frozenset()
    target_refs: frozenset[str] = frozenset()
    requires_refs: frozenset[str] = frozenset()
    teaches_refs: frozenset[str] = frozenset()
    delayed_recode_id: UUID | None = None
    exercise_definition_revision_ids: tuple[UUID, ...] = ()
    content_revision_ids: tuple[UUID, ...] = ()
    debt_urgency: float = 0
    memory_due: float = 0
    module_criticality: float = 0
    prerequisite_block: float = 0
    modality_balance: float = 0
    information_gain: float = 0
    instance_ready: bool = True
    corrector_ready: bool = True
    media_ready: bool = True
    fallback_ready: bool = False
    accessibility_ready: bool = True

    def __post_init__(self) -> None:
        _require_uuid7(self.candidate_id, "candidate_id")
        if self.delayed_recode_id is not None:
            _require_uuid7(self.delayed_recode_id, "delayed_recode_id")
        if not self.roles or self.p50_seconds < 30 or self.p80_seconds < self.p50_seconds:
            raise SprintDomainError("invalid_candidate_block")
        if not math.isfinite(self.novelty_points) or self.novelty_points < 0:
            raise SprintDomainError("novelty_limit_exceeded")
        if not self.modalities.issubset(MODALITIES):
            raise SprintDomainError("invalid_candidate_modality")
        priorities = (
            self.debt_urgency,
            self.memory_due,
            self.module_criticality,
            self.prerequisite_block,
            self.modality_balance,
            self.information_gain,
        )
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in priorities):
            raise SprintDomainError("invalid_candidate_priority")
        for value in self.exercise_definition_revision_ids + self.content_revision_ids:
            _require_uuid7(value, "candidate_revision_id")

    @property
    def is_ready(self) -> bool:
        return (
            self.instance_ready
            and self.corrector_ready
            and (self.media_ready or self.fallback_ready)
            and self.accessibility_ready
        )

    @property
    def priority(self) -> float:
        return (
            0.30 * self.debt_urgency
            + 0.25 * self.memory_due
            + 0.20 * self.module_criticality
            + 0.10 * self.prerequisite_block
            + 0.10 * self.modality_balance
            + 0.05 * self.information_gain
        )


@dataclass(frozen=True, slots=True)
class PlanningSnapshot:
    snapshot_id: UUID
    profile_id: UUID
    plan_kind: PlanKind
    budget_minutes: int
    pedagogical_day: date
    timezone: str
    cutoff_at: datetime
    seed: str
    policy_revision: str
    planner_revision: str
    profile_band: str
    mastered_refs: frozenset[str]
    candidates: tuple[CandidateBlock, ...]
    enrollment_id: UUID | None = None
    module_revision_id: UUID | None = None
    module_day_id: UUID | None = None
    due_delayed_recode_ids: tuple[UUID, ...] = ()
    word_bank_snapshot_ids: tuple[UUID, ...] = ()
    private_context: str | None = None
    prerequisite_refs: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _require_uuid7(self.snapshot_id, "snapshot_id")
        _require_uuid7(self.profile_id, "profile_id")
        for field in ("enrollment_id", "module_revision_id", "module_day_id"):
            value = getattr(self, field)
            if value is not None:
                _require_uuid7(value, field)
        for value in self.due_delayed_recode_ids + self.word_bank_snapshot_ids:
            _require_uuid7(value, "snapshot_reference_id")
        if self.budget_minutes not in _MAX_BLOCKS:
            raise SprintDomainError("budget_infeasible")
        if self.cutoff_at.tzinfo is None or not self.timezone or not self.seed:
            raise SprintDomainError("invalid_planning_snapshot")
        if not self.policy_revision or not self.planner_revision:
            raise SprintDomainError("invalid_planning_snapshot")
        if self.profile_band not in {"P-ABS", "P-FAUX", "P-INT"}:
            raise SprintDomainError("invalid_profile_band")
        if len(self.candidates) > 18 or len({item.candidate_id for item in self.candidates}) != len(
            self.candidates
        ):
            raise SprintDomainError("duplicate_candidate")
        if not all(item.is_ready for item in self.candidates):
            raise SprintDomainError("content_unavailable")
        due = set(self.due_delayed_recode_ids)
        represented = {item.delayed_recode_id for item in self.candidates}
        if due - represented:
            raise SprintDomainError("content_unavailable")
        if self.plan_kind is PlanKind.DAILY and (
            self.enrollment_id is None
            or self.module_revision_id is None
            or self.module_day_id is None
        ):
            raise SprintDomainError("day_revision_invalid")
        if self.plan_kind is PlanKind.FREE and self.enrollment_id is not None:
            raise SprintDomainError("free_practice_cannot_bind_enrollment")

    @property
    def max_blocks(self) -> int:
        return _MAX_BLOCKS[self.budget_minutes]

    @property
    def content_budget_seconds(self) -> int:
        return int(self.budget_minutes * 60 * 0.9)

    @property
    def novelty_limit(self) -> float:
        adjustment = {"P-ABS": 0, "P-FAUX": 2, "P-INT": 4}[self.profile_band]
        return float(_P_ABS_NOVELTY[self.budget_minutes] + adjustment)


@dataclass(frozen=True, slots=True)
class PlannedBlock:
    block_id: UUID
    candidate_id: UUID
    ordinal: int
    family: BlockFamily
    roles: frozenset[str]
    p50_seconds: int
    p80_seconds: int
    novelty_points: float
    modalities: frozenset[str]
    reason_codes: tuple[str, ...]
    target_refs: tuple[str, ...] = ()
    delayed_recode_id: UUID | None = None
    exercise_definition_revision_ids: tuple[UUID, ...] = ()
    content_revision_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class SessionPlan:
    plan_id: UUID
    revision_id: UUID
    snapshot: PlanningSnapshot
    blocks: tuple[PlannedBlock, ...]
    status: PlanStatus
    fingerprint: str = ""

    def __post_init__(self) -> None:
        _require_uuid7(self.plan_id, "plan_id")
        _require_uuid7(self.revision_id, "revision_id")
        if tuple(item.ordinal for item in self.blocks) != tuple(range(1, len(self.blocks) + 1)):
            raise SprintDomainError("invalid_block_order")
        if not CORE_ROLES.issubset(self.covered_roles):
            raise SprintDomainError("no_valid_composition")
        if self.total_p50_seconds > self.snapshot.content_budget_seconds:
            raise SprintDomainError("budget_infeasible")
        if self.total_p80_seconds > self.snapshot.budget_minutes * 60:
            raise SprintDomainError("budget_infeasible")
        if len(self.blocks) > self.snapshot.max_blocks:
            raise SprintDomainError("budget_infeasible")
        if self.novelty_points > self.snapshot.novelty_limit:
            raise SprintDomainError("novelty_limit_exceeded")
        payload = {
            "plan_id": str(self.plan_id),
            "revision_id": str(self.revision_id),
            "snapshot_id": str(self.snapshot.snapshot_id),
            "seed": self.snapshot.seed,
            "status": self.status.value,
            "blocks": [
                {
                    "candidate_id": str(item.candidate_id),
                    "ordinal": item.ordinal,
                    "reasons": item.reason_codes,
                }
                for item in self.blocks
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        object.__setattr__(self, "fingerprint", f"sha256:{hashlib.sha256(encoded).hexdigest()}")

    @property
    def total_p50_seconds(self) -> int:
        return sum(item.p50_seconds for item in self.blocks)

    @property
    def total_p80_seconds(self) -> int:
        return sum(item.p80_seconds for item in self.blocks)

    @property
    def novelty_points(self) -> float:
        return sum(item.novelty_points for item in self.blocks)

    @property
    def covered_roles(self) -> frozenset[str]:
        return frozenset(role for item in self.blocks for role in item.roles)

    def begin_preparation(self) -> SessionPlan:
        if self.status is not PlanStatus.DRAFT:
            raise SprintDomainError("invalid_transition")
        return replace(self, status=PlanStatus.PREPARING)

    def mark_ready(self) -> SessionPlan:
        if self.status is not PlanStatus.PREPARING:
            raise SprintDomainError("invalid_transition")
        return replace(self, status=PlanStatus.READY)

    def fail(self) -> SessionPlan:
        if self.status is not PlanStatus.PREPARING:
            raise SprintDomainError("invalid_transition")
        return replace(self, status=PlanStatus.FAILED)

    def cancel(self) -> SessionPlan:
        if self.status not in {PlanStatus.DRAFT, PlanStatus.PREPARING, PlanStatus.READY}:
            raise SprintDomainError("run_already_started")
        return replace(self, status=PlanStatus.CANCELLED)


@dataclass(frozen=True, slots=True)
class DelayedRecodeSpec:
    delayed_recode_id: UUID
    profile_id: UUID
    source_attempt_id: UUID
    source_correction_revision_id: UUID
    source_exercise_instance_id: UUID
    target_stimulus: str
    corrected_support_text: str
    accepted_target_answers: tuple[str, ...]
    target_language_tag: str
    support_language_tag: str
    target_refs: tuple[str, ...]
    correction_policy_revision_id: UUID
    content_revision_ids: tuple[UUID, ...]
    source_corrected_at: datetime
    not_before: datetime
    due_on_next_active_session: bool = True
    due_after_24h: bool = False
    source_evaluable: bool = True
    source_contested: bool = False
    source_invalidated: bool = False

    def __post_init__(self) -> None:
        for field in (
            "delayed_recode_id",
            "profile_id",
            "source_attempt_id",
            "source_correction_revision_id",
            "source_exercise_instance_id",
            "correction_policy_revision_id",
        ):
            _require_uuid7(getattr(self, field), field)
        for value in self.content_revision_ids:
            _require_uuid7(value, "content_revision_id")
        if (
            not self.source_evaluable
            or self.source_contested
            or self.source_invalidated
            or not self.target_stimulus
            or not self.corrected_support_text
            or not self.accepted_target_answers
            or self.not_before < self.source_corrected_at
        ):
            raise SprintDomainError("delayed_source_invalid")

    def is_due(self, now: datetime, *, next_active_session: bool) -> bool:
        if now < self.not_before:
            return False
        if self.due_after_24h and now < self.source_corrected_at + timedelta(hours=24):
            return False
        return next_active_session if self.due_on_next_active_session else True


@dataclass(frozen=True, slots=True)
class BlockRun:
    block_id: UUID
    status: BlockStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SprintRun:
    run_id: UUID
    plan_id: UUID
    profile_id: UUID
    plan_kind: PlanKind
    pedagogical_day: date
    status: SprintRunStatus
    blocks: tuple[BlockRun, ...]
    required_block_ids: frozenset[UUID]
    started_at: datetime
    expires_at: datetime
    current_block_id: UUID | None = None
    interrupted_at: datetime | None = None
    completed_at: datetime | None = None
    stop_reason: str | None = None
    version: int = 1

    @classmethod
    def start(
        cls,
        *,
        run_id: UUID,
        plan_id: UUID,
        profile_id: UUID,
        plan_kind: PlanKind,
        pedagogical_day: date,
        block_ids: tuple[UUID, ...],
        required_block_ids: tuple[UUID, ...],
        started_at: datetime,
        expires_at: datetime,
    ) -> SprintRun:
        if not block_ids or not set(required_block_ids).issubset(block_ids):
            raise SprintDomainError("invalid_sprint_blocks")
        blocks = tuple(
            BlockRun(
                block_id=value, status=BlockStatus.AVAILABLE if index == 0 else BlockStatus.PENDING
            )
            for index, value in enumerate(block_ids)
        )
        return cls(
            run_id=run_id,
            plan_id=plan_id,
            profile_id=profile_id,
            plan_kind=plan_kind,
            pedagogical_day=pedagogical_day,
            status=SprintRunStatus.IN_PROGRESS,
            blocks=blocks,
            required_block_ids=frozenset(required_block_ids),
            started_at=started_at,
            expires_at=expires_at,
        )

    def __post_init__(self) -> None:
        for field in ("run_id", "plan_id", "profile_id"):
            _require_uuid7(getattr(self, field), field)
        if self.expires_at <= self.started_at:
            raise SprintDomainError("run_expired")
        ids = tuple(item.block_id for item in self.blocks)
        if len(set(ids)) != len(ids) or not self.required_block_ids.issubset(ids):
            raise SprintDomainError("invalid_sprint_blocks")

    @property
    def consumes_module_day(self) -> bool:
        return self.plan_kind is PlanKind.DAILY and self.status is SprintRunStatus.COMPLETED

    def block_status(self, block_id: UUID) -> BlockStatus:
        return next(item.status for item in self.blocks if item.block_id == block_id)

    def _replace_block(self, block_id: UUID, replacement: BlockRun) -> tuple[BlockRun, ...]:
        if block_id not in {item.block_id for item in self.blocks}:
            raise SprintDomainError("not_found")
        return tuple(replacement if item.block_id == block_id else item for item in self.blocks)

    def start_block(self, block_id: UUID, at: datetime) -> SprintRun:
        if (
            self.status is not SprintRunStatus.IN_PROGRESS
            or self.block_status(block_id) is not BlockStatus.AVAILABLE
        ):
            raise SprintDomainError("invalid_transition")
        block = BlockRun(block_id=block_id, status=BlockStatus.IN_PROGRESS, started_at=at)
        return replace(
            self,
            blocks=self._replace_block(block_id, block),
            current_block_id=block_id,
            version=self.version + 1,
        )

    def complete_block(self, block_id: UUID, at: datetime) -> SprintRun:
        existing = next(item for item in self.blocks if item.block_id == block_id)
        if (
            self.status is not SprintRunStatus.IN_PROGRESS
            or existing.status is not BlockStatus.IN_PROGRESS
        ):
            raise SprintDomainError("invalid_transition")
        blocks = list(
            self._replace_block(
                block_id,
                BlockRun(
                    block_id=block_id,
                    status=BlockStatus.COMPLETED,
                    started_at=existing.started_at,
                    completed_at=at,
                ),
            )
        )
        index = next(index for index, item in enumerate(blocks) if item.block_id == block_id)
        if index + 1 < len(blocks) and blocks[index + 1].status is BlockStatus.PENDING:
            blocks[index + 1] = replace(blocks[index + 1], status=BlockStatus.AVAILABLE)
        return replace(
            self,
            blocks=tuple(blocks),
            current_block_id=None,
            version=self.version + 1,
        )

    def interrupt(self, at: datetime, reason: str) -> SprintRun:
        if self.status is not SprintRunStatus.IN_PROGRESS or not reason:
            raise SprintDomainError("invalid_transition")
        return replace(
            self,
            status=SprintRunStatus.INTERRUPTED,
            interrupted_at=at,
            stop_reason=reason,
            version=self.version + 1,
        )

    def resume(self, at: datetime) -> SprintRun:
        if self.status is not SprintRunStatus.INTERRUPTED:
            raise SprintDomainError("invalid_transition")
        if at >= self.expires_at:
            raise SprintDomainError("run_expired")
        return replace(
            self,
            status=SprintRunStatus.IN_PROGRESS,
            interrupted_at=None,
            stop_reason=None,
            version=self.version + 1,
        )

    def stop(self, at: datetime, reason: str) -> SprintRun:
        if (
            self.status not in {SprintRunStatus.IN_PROGRESS, SprintRunStatus.INTERRUPTED}
            or not reason
        ):
            raise SprintDomainError("invalid_transition")
        return replace(
            self,
            status=SprintRunStatus.STOPPED,
            completed_at=at,
            stop_reason=reason,
            version=self.version + 1,
        )

    def complete(self, at: datetime) -> SprintRun:
        if self.status is not SprintRunStatus.IN_PROGRESS:
            raise SprintDomainError("invalid_transition")
        states = {item.block_id: item.status for item in self.blocks}
        if any(states[value] is not BlockStatus.COMPLETED for value in self.required_block_ids):
            raise SprintDomainError("required_block_incomplete")
        return replace(
            self,
            status=SprintRunStatus.COMPLETED,
            completed_at=at,
            current_block_id=None,
            version=self.version + 1,
        )


__all__ = [
    "CORE_ROLES",
    "BlockFamily",
    "BlockRun",
    "BlockStatus",
    "CandidateBlock",
    "DelayedRecodeSpec",
    "PlanKind",
    "PlanStatus",
    "PlannedBlock",
    "PlanningSnapshot",
    "SessionPlan",
    "SprintDomainError",
    "SprintRun",
    "SprintRunStatus",
]
