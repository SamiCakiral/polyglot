from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from polyglot.modules.identity.application import RequestContext


@dataclass(frozen=True, slots=True)
class PlanBlockView:
    block_id: UUID
    ordinal: int
    family: str
    roles: tuple[str, ...]
    reason_codes: tuple[str, ...]
    modalities: tuple[str, ...]
    p50_seconds: int
    p80_seconds: int
    required: bool
    delayed_recode_id: UUID | None
    exercise_instance_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class SessionPlanView:
    plan_id: UUID
    plan_revision_id: UUID
    snapshot_id: UUID
    profile_id: UUID
    plan_kind: str
    pedagogical_day: date
    budget_minutes: int
    status: str
    failure_code: str | None
    total_p50_seconds: int
    total_p80_seconds: int
    novelty_points: float
    plan_fingerprint: str
    blocks: tuple[PlanBlockView, ...]
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SprintBlockView:
    block_id: UUID
    session_plan_block_id: UUID
    ordinal: int
    family: str
    status: str
    required: bool
    reason: str | None
    exercise_instance_ids: tuple[UUID, ...]
    version: int


@dataclass(frozen=True, slots=True)
class SprintRunView:
    run_id: UUID
    plan_id: UUID
    plan_revision_id: UUID
    profile_id: UUID
    plan_kind: str
    pedagogical_day: date
    status: str
    current_block_id: UUID | None
    blocks: tuple[SprintBlockView, ...]
    started_at: datetime
    interrupted_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime
    stop_reason: str | None
    active_duration_ms: int
    consumes_module_day: bool
    version: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ComposeDailySession:
    plan_id: UUID
    snapshot_id: UUID
    pedagogical_day: date
    budget_minutes: int


@dataclass(frozen=True, slots=True)
class ComposeFreePractice:
    plan_id: UUID
    snapshot_id: UUID
    pedagogical_day: date
    budget_minutes: int
    target_refs: tuple[str, ...]
    primitive_ids: tuple[str, ...]
    modalities: tuple[str, ...]
    challenge: str
    allow_novelty: bool
    vocabulary_list_snapshot_ids: tuple[UUID, ...] = ()
    context_family_ref: str | None = None
    private_context: str | None = None


@dataclass(frozen=True, slots=True)
class StartSprintRun:
    run_id: UUID


@dataclass(frozen=True, slots=True)
class InterruptSprintRun:
    reason: str


@dataclass(frozen=True, slots=True)
class StopSprintRun:
    reason: str


@dataclass(frozen=True, slots=True)
class SkipExerciseBlock:
    reason: str


@dataclass(frozen=True, slots=True)
class AbandonExerciseBlock:
    reason: str


class SprintApplicationService(Protocol):
    async def get_plan(self, actor_id: UUID, plan_id: UUID) -> SessionPlanView: ...

    async def get_run(self, actor_id: UUID, run_id: UUID) -> SprintRunView: ...

    async def compose_daily(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: ComposeDailySession,
        *,
        idempotency_key: str,
        context: RequestContext,
    ) -> SessionPlanView: ...

    async def compose_free(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: ComposeFreePractice,
        *,
        idempotency_key: str,
        context: RequestContext,
    ) -> SessionPlanView: ...

    async def prepare(
        self,
        actor_id: UUID,
        plan_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SessionPlanView: ...

    async def cancel_plan(
        self,
        actor_id: UUID,
        plan_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SessionPlanView: ...

    async def start_run(
        self,
        actor_id: UUID,
        plan_id: UUID,
        command: StartSprintRun,
        *,
        idempotency_key: str,
        context: RequestContext,
    ) -> SprintRunView: ...

    async def interrupt_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        command: InterruptSprintRun,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SprintRunView: ...

    async def resume_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SprintRunView: ...

    async def stop_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        command: StopSprintRun,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SprintRunView: ...

    async def complete_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SprintRunView: ...

    async def skip_block(
        self,
        actor_id: UUID,
        run_id: UUID,
        block_id: UUID,
        command: SkipExerciseBlock,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SprintRunView: ...

    async def abandon_block(
        self,
        actor_id: UUID,
        run_id: UUID,
        block_id: UUID,
        command: AbandonExerciseBlock,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SprintRunView: ...


__all__ = [
    "AbandonExerciseBlock",
    "ComposeDailySession",
    "ComposeFreePractice",
    "InterruptSprintRun",
    "PlanBlockView",
    "SessionPlanView",
    "SkipExerciseBlock",
    "SprintApplicationService",
    "SprintBlockView",
    "SprintRunView",
    "StartSprintRun",
    "StopSprintRun",
]
