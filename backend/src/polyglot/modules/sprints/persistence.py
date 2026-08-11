from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.identity.application import RequestContext
from polyglot.modules.sprints.application import (
    AbandonExerciseBlock,
    ComposeDailySession,
    ComposeFreePractice,
    InterruptSprintRun,
    PlanBlockView,
    SessionPlanView,
    SkipExerciseBlock,
    SprintBlockView,
    SprintRunView,
    StartSprintRun,
    StopSprintRun,
)
from polyglot.modules.sprints.composer import DailySprintComposer
from polyglot.modules.sprints.domain import (
    CORE_ROLES,
    BlockFamily,
    CandidateBlock,
    DelayedRecodeSpec,
    PlanKind,
    PlanningSnapshot,
    SessionPlan,
    SprintDomainError,
)
from polyglot.platform.clock import Clock, SystemClock
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.json_types import JsonValue
from polyglot.platform.persistence.records import CommandReceipt, DomainEvent
from polyglot.platform.persistence.repositories import (
    SqlCommandReceiptStore,
    SqlEventOutboxRepository,
)

RECEIPT_RETENTION = timedelta(hours=24)
EVENT_RETENTION = timedelta(days=3650)
RUN_RETENTION = timedelta(days=7)


def _uuid(value: object) -> UUID:
    return UUID(str(value))


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _family_for(primitive_id: str, target_refs: tuple[str, ...]) -> BlockFamily:
    if primitive_id.startswith("EX-RECALL"):
        return BlockFamily.RECALL_WARMUP
    if primitive_id.startswith("EX-EXPOSE"):
        return (
            BlockFamily.GRAMMAR_TOOLBOX
            if any(value.startswith("grammar:") for value in target_refs)
            else BlockFamily.LEXICAL_ACQUISITION
        )
    if primitive_id.startswith("EX-TRANSFORM"):
        return BlockFamily.TRANSFORMATION_GYM
    if primitive_id.startswith("EX-ORAL"):
        return BlockFamily.SHADOWING
    if primitive_id.startswith("EX-PROD"):
        return BlockFamily.GUIDED_OUTPUT
    if primitive_id.startswith("EX-COMP"):
        return BlockFamily.LISTENING
    if primitive_id.startswith("EX-REPAIR"):
        return BlockFamily.GRAMMAR_TOOLBOX
    return BlockFamily.VERSION_INPUT


def _roles_for(family: BlockFamily) -> frozenset[str]:
    return {
        BlockFamily.RECALL_WARMUP: frozenset({"activation"}),
        BlockFamily.DELAYED_RECODE: frozenset({"activation", "j1_due"}),
        BlockFamily.LEXICAL_ACQUISITION: frozenset({"lexical_preexposure"}),
        BlockFamily.GRAMMAR_TOOLBOX: frozenset({"grammar_explanation"}),
        BlockFamily.TRANSFORMATION_GYM: frozenset({"guided_practice"}),
        BlockFamily.VERSION_INPUT: frozenset({"contextual_encounter", "comprehension"}),
        BlockFamily.LISTENING: frozenset({"contextual_encounter", "comprehension"}),
        BlockFamily.SHADOWING: frozenset({"second_modality"}),
        BlockFamily.GUIDED_OUTPUT: frozenset({"production"}),
        BlockFamily.FREE_WRITING: frozenset({"production"}),
        BlockFamily.REFLECTION_CLOSE: frozenset({"reflection"}),
    }[family]


def _modalities_for(family: BlockFamily) -> frozenset[str]:
    if family in {BlockFamily.LISTENING}:
        return frozenset({"listening"})
    if family is BlockFamily.SHADOWING:
        return frozenset({"speaking"})
    if family in {BlockFamily.GUIDED_OUTPUT, BlockFamily.FREE_WRITING}:
        return frozenset({"writing"})
    if family is BlockFamily.VERSION_INPUT:
        return frozenset({"reading"})
    return frozenset()


class SqlSprintService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
        composer: DailySprintComposer | None = None,
    ) -> None:
        self._sessions = session_factory
        self._clock = clock or SystemClock()
        self._ids = id_generator or Uuid7Generator(self._clock)
        self._composer = composer or DailySprintComposer()

    async def get_plan(self, actor_id: UUID, plan_id: UUID) -> SessionPlanView:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            view = await self._read_plan(session, plan_id)
            if view is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            return view

    async def get_run(self, actor_id: UUID, run_id: UUID) -> SprintRunView:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            view = await self._read_run(session, run_id)
            if view is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            return view

    async def compose_daily(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: ComposeDailySession,
        *,
        idempotency_key: str,
        context: RequestContext,
    ) -> SessionPlanView:
        payload: dict[str, JsonValue] = {
            "profile_id": str(profile_id),
            "plan_id": str(command.plan_id),
            "snapshot_id": str(command.snapshot_id),
            "pedagogical_day": command.pedagogical_day.isoformat(),
            "budget_minutes": command.budget_minutes,
        }
        return await self._compose(
            actor_id=actor_id,
            profile_id=profile_id,
            plan_id=command.plan_id,
            snapshot_id=command.snapshot_id,
            pedagogical_day=command.pedagogical_day,
            budget_minutes=command.budget_minutes,
            plan_kind=PlanKind.DAILY,
            command_type="ComposeDailySession",
            event_type="session_plan_composed",
            idempotency_key=idempotency_key,
            context=context,
            fingerprint_payload=payload,
        )

    async def compose_free(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: ComposeFreePractice,
        *,
        idempotency_key: str,
        context: RequestContext,
    ) -> SessionPlanView:
        if command.challenge not in {"gentler", "matched", "stretch"}:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        if not command.target_refs or not command.primitive_ids:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        payload: dict[str, JsonValue] = {
            "plan_id": str(command.plan_id),
            "snapshot_id": str(command.snapshot_id),
            "pedagogical_day": command.pedagogical_day.isoformat(),
            "budget_minutes": command.budget_minutes,
            "target_refs": list(command.target_refs),
            "primitive_ids": list(command.primitive_ids),
            "modalities": list(command.modalities),
            "challenge": command.challenge,
            "allow_novelty": command.allow_novelty,
            "vocabulary_list_snapshot_ids": [
                str(value) for value in command.vocabulary_list_snapshot_ids
            ],
            "context_family_ref": command.context_family_ref,
            "private_context": command.private_context,
        }
        return await self._compose(
            actor_id=actor_id,
            profile_id=profile_id,
            plan_id=command.plan_id,
            snapshot_id=command.snapshot_id,
            pedagogical_day=command.pedagogical_day,
            budget_minutes=command.budget_minutes,
            plan_kind=PlanKind.FREE,
            command_type="ComposeFreePractice",
            event_type="free_practice_plan_composed",
            idempotency_key=idempotency_key,
            context=context,
            fingerprint_payload=payload,
            free_command=command,
        )

    async def _compose(
        self,
        *,
        actor_id: UUID,
        profile_id: UUID,
        plan_id: UUID,
        snapshot_id: UUID,
        pedagogical_day: date,
        budget_minutes: int,
        plan_kind: PlanKind,
        command_type: str,
        event_type: str,
        idempotency_key: str,
        context: RequestContext,
        fingerprint_payload: dict[str, JsonValue],
        free_command: ComposeFreePractice | None = None,
    ) -> SessionPlanView:
        now = self._clock.now()
        fingerprint = canonical_json_fingerprint(fingerprint_payload)
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            receipt, replay_id = await self._reserve(
                session,
                actor_id=actor_id,
                command_type=command_type,
                aggregate_type="session_plan",
                aggregate_id=plan_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=None,
                now=now,
            )
            if replay_id is not None:
                replay = await self._read_plan(session, replay_id)
                if replay is None:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return replay
            profile = (
                (
                    await session.execute(
                        text(
                            "SELECT profile.profile_id,profile.status,prefs.timezone,"
                            "prefs.accessibility_preferences,prefs.media_preferences "
                            "FROM language_profiles.learner_language_profiles profile "
                            "JOIN identity.user_preferences prefs "
                            "ON prefs.account_id=profile.account_id "
                            "WHERE profile.profile_id=:profile AND profile.account_id=:actor"
                        ),
                        {"profile": profile_id, "actor": actor_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if profile is None or str(profile["status"]) != "active":
                raise DomainError(ErrorCode.NOT_FOUND)
            if plan_kind is PlanKind.DAILY:
                context_row = await self._daily_context(session, profile_id)
                target_refs = tuple(str(item) for item in context_row["primary_target_refs"])
                definition_ids = tuple(
                    _uuid(item) for item in context_row["exercise_definition_revision_ids"]
                )
                content_ids = tuple(_uuid(item) for item in context_row["content_revision_ids"])
                enrollment_id = _uuid(context_row["enrollment_id"])
                module_revision_id = _uuid(context_row["module_revision_id"])
                module_day_id = _uuid(context_row["module_day_id"])
                pack_revision_id = _uuid(context_row["pack_revision_id"])
                grammar_families = tuple(
                    str(item) for item in context_row["new_grammar_family_codes"]
                )
            else:
                assert free_command is not None
                target_refs = free_command.target_refs
                definition_ids = await self._free_definition_ids(
                    session, free_command.primitive_ids
                )
                content_ids = ()
                enrollment_id = None
                module_revision_id = None
                module_day_id = None
                pack_revision_id = await self._profile_pack_revision(session, profile_id)
                grammar_families = ()
            candidates = await self._candidates(
                session,
                snapshot_id=snapshot_id,
                definition_ids=definition_ids,
                target_refs=target_refs,
                content_ids=content_ids,
                grammar_families=grammar_families,
                allow_novelty=True if free_command is None else free_command.allow_novelty,
                reject_prerequisites=free_command is not None,
            )
            due_ids: tuple[UUID, ...] = ()
            if plan_kind is PlanKind.DAILY:
                due_ids = await self._due_recode_ids(session, profile_id, now)
                candidates = self._attach_due_recodes(snapshot_id, candidates, due_ids)
            snapshot = PlanningSnapshot(
                snapshot_id=snapshot_id,
                profile_id=profile_id,
                plan_kind=plan_kind,
                budget_minutes=budget_minutes,
                pedagogical_day=pedagogical_day,
                timezone=str(profile["timezone"]),
                cutoff_at=now,
                seed=hashlib.sha256(
                    f"{profile_id}:{pedagogical_day}:{snapshot_id}".encode()
                ).hexdigest(),
                policy_revision="SPRINT_PRIORITY_V0",
                planner_revision="COMPOSER_V0",
                profile_band="P-ABS",
                mastered_refs=frozenset(),
                candidates=candidates,
                enrollment_id=enrollment_id,
                module_revision_id=module_revision_id,
                module_day_id=module_day_id,
                due_delayed_recode_ids=due_ids,
                word_bank_snapshot_ids=(
                    () if free_command is None else free_command.vocabulary_list_snapshot_ids
                ),
                private_context=None if free_command is None else free_command.private_context,
            )
            try:
                plan = self._composer.compose(plan_id, snapshot)
            except SprintDomainError as error:
                raise DomainError(ErrorCode.NO_VALID_COMPOSITION, detail=str(error)) from error
            await self._persist_plan(
                session,
                plan=plan,
                pack_revision_id=pack_revision_id,
                now=now,
            )
            view = await self._required_plan(session, plan_id)
            await self._record(
                session,
                receipt=receipt,
                actor_id=actor_id,
                profile_id=profile_id,
                context=context,
                event_type=event_type,
                aggregate_type="session_plan",
                aggregate_id=plan_id,
                aggregate_version=view.version,
                now=now,
            )
            await session.commit()
            return view

    async def interrupt_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        command: InterruptSprintRun,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SprintRunView:
        if not command.reason.strip():
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        return await self._transition_run(
            actor_id=actor_id,
            run_id=run_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            context=context,
            command_type="InterruptSprintRun",
            event_type="sprint_run_interrupted",
            allowed_statuses={"in_progress"},
            target_status="interrupted",
            reason=command.reason,
        )

    async def resume_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SprintRunView:
        return await self._transition_run(
            actor_id=actor_id,
            run_id=run_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            context=context,
            command_type="ResumeSprintRun",
            event_type="sprint_run_resumed",
            allowed_statuses={"interrupted"},
            target_status="in_progress",
        )

    async def stop_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        command: StopSprintRun,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SprintRunView:
        if not command.reason.strip():
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        return await self._transition_run(
            actor_id=actor_id,
            run_id=run_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            context=context,
            command_type="StopSprintRun",
            event_type="sprint_run_stopped",
            allowed_statuses={"in_progress", "interrupted"},
            target_status="stopped",
            reason=command.reason,
        )

    async def complete_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SprintRunView:
        now = self._clock.now()
        fingerprint = canonical_json_fingerprint(
            {"run_id": str(run_id), "expected_version": expected_version}
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            receipt, replay_id = await self._reserve(
                session,
                actor_id=actor_id,
                command_type="CompleteSprintRun",
                aggregate_type="sprint_run",
                aggregate_id=run_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
                now=now,
            )
            if replay_id is not None:
                replay = await self._read_run(session, replay_id)
                if replay is None:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return replay
            before = await self._read_run(session, run_id, for_update=True)
            if before is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if before.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if before.status not in {"in_progress", "interrupted"}:
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            await session.execute(
                text(
                    "UPDATE exercises.exercise_block_runs runtime SET status='completed',"
                    "version=version+1,updated_at=:now FROM planning.session_plan_blocks plan "
                    "WHERE runtime.session_plan_block_id=plan.session_plan_block_id "
                    "AND runtime.sprint_run_id=:run AND plan.family='reflection_close' "
                    "AND runtime.status IN ('pending','available')"
                ),
                {"run": run_id, "now": now},
            )
            incomplete = await session.scalar(
                text(
                    "SELECT count(*) FROM exercises.exercise_block_runs "
                    "WHERE sprint_run_id=:run AND required AND status <> 'completed'"
                ),
                {"run": run_id},
            )
            if incomplete:
                raise DomainError(ErrorCode.REQUIRED_BLOCK_INCOMPLETE)
            elapsed_ms = self._active_elapsed_ms(before, now)
            await session.execute(
                text(
                    "UPDATE planning.sprint_runs SET status='completed',current_block_id=NULL,"
                    "interrupted_at=NULL,completed_at=:now,stop_reason=NULL,"
                    "active_duration_ms=active_duration_ms+:elapsed,version=version+1,"
                    "updated_at=:now WHERE sprint_run_id=:run"
                ),
                {"run": run_id, "now": now, "elapsed": elapsed_ms},
            )
            await session.execute(
                text(
                    "UPDATE planning.delayed_recode_tasks task SET status='consumed',"
                    "version=task.version+1,updated_at=:now FROM planning.sprint_runs run "
                    "WHERE run.sprint_run_id=:run AND task.profile_id=run.profile_id "
                    "AND task.consumed_by_plan_revision_id=run.plan_revision_id "
                    "AND task.status='planned'"
                ),
                {"run": run_id, "now": now},
            )
            view = await self._required_run(session, run_id)
            await self._record_run_event(
                session,
                receipt=receipt,
                actor_id=actor_id,
                context=context,
                event_type="sprint_run_completed",
                view=view,
                now=now,
            )
            await session.commit()
            return view

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
    ) -> SprintRunView:
        return await self._transition_block(
            actor_id=actor_id,
            run_id=run_id,
            block_id=block_id,
            reason=command.reason,
            target_status="skipped",
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            context=context,
            command_type="SkipExerciseBlock",
            event_type="exercise_block_skipped",
            reject_required=True,
        )

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
    ) -> SprintRunView:
        return await self._transition_block(
            actor_id=actor_id,
            run_id=run_id,
            block_id=block_id,
            reason=command.reason,
            target_status="abandoned",
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            context=context,
            command_type="AbandonExerciseBlock",
            event_type="exercise_block_abandoned",
            reject_required=False,
        )

    async def _transition_run(
        self,
        *,
        actor_id: UUID,
        run_id: UUID,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
        command_type: str,
        event_type: str,
        allowed_statuses: set[str],
        target_status: str,
        reason: str | None = None,
    ) -> SprintRunView:
        now = self._clock.now()
        fingerprint = canonical_json_fingerprint(
            {
                "run_id": str(run_id),
                "expected_version": expected_version,
                "target_status": target_status,
                "reason": reason,
            }
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            receipt, replay_id = await self._reserve(
                session,
                actor_id=actor_id,
                command_type=command_type,
                aggregate_type="sprint_run",
                aggregate_id=run_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
                now=now,
            )
            if replay_id is not None:
                replay = await self._read_run(session, replay_id)
                if replay is None:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return replay
            before = await self._read_run(session, run_id, for_update=True)
            if before is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if before.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if before.status not in allowed_statuses:
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            if target_status == "in_progress" and now >= before.expires_at:
                raise DomainError(ErrorCode.RUN_EXPIRED)
            terminal = target_status in {"completed", "stopped", "cancelled"}
            interrupted = now if target_status == "interrupted" else None
            elapsed_ms = self._active_elapsed_ms(before, now)
            await session.execute(
                text(
                    "UPDATE planning.sprint_runs SET status=:status,"
                    "interrupted_at=:interrupted,completed_at=:completed,stop_reason=:reason,"
                    "active_duration_ms=active_duration_ms+:elapsed,version=version+1,"
                    "updated_at=:now WHERE sprint_run_id=:run"
                ),
                {
                    "status": target_status,
                    "interrupted": interrupted,
                    "completed": now if terminal else None,
                    "reason": reason if target_status == "stopped" else None,
                    "elapsed": elapsed_ms,
                    "now": now,
                    "run": run_id,
                },
            )
            view = await self._required_run(session, run_id)
            await self._record_run_event(
                session,
                receipt=receipt,
                actor_id=actor_id,
                context=context,
                event_type=event_type,
                view=view,
                now=now,
            )
            await session.commit()
            return view

    async def _transition_block(
        self,
        *,
        actor_id: UUID,
        run_id: UUID,
        block_id: UUID,
        reason: str,
        target_status: str,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
        command_type: str,
        event_type: str,
        reject_required: bool,
    ) -> SprintRunView:
        if not reason.strip():
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        now = self._clock.now()
        fingerprint = canonical_json_fingerprint(
            {
                "run_id": str(run_id),
                "block_id": str(block_id),
                "expected_version": expected_version,
                "target_status": target_status,
                "reason": reason,
            }
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            receipt, replay_id = await self._reserve(
                session,
                actor_id=actor_id,
                command_type=command_type,
                aggregate_type="sprint_run",
                aggregate_id=run_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
                now=now,
            )
            if replay_id is not None:
                replay = await self._read_run(session, replay_id)
                if replay is None:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return replay
            run = await self._read_run(session, run_id, for_update=True)
            if run is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if run.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if run.status != "in_progress":
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            block = next((value for value in run.blocks if value.block_id == block_id), None)
            if block is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if reject_required and block.required:
                raise DomainError(ErrorCode.BLOCK_REQUIRED)
            if block.status not in {"available", "in_progress"}:
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            await session.execute(
                text(
                    "UPDATE exercises.exercise_block_runs SET status=:status,reason=:reason,"
                    "version=version+1,updated_at=:now WHERE block_id=:block"
                ),
                {"status": target_status, "reason": reason, "now": now, "block": block_id},
            )
            await self._unlock_next_block(session, run_id, block.ordinal, now)
            await session.execute(
                text(
                    "UPDATE planning.sprint_runs SET current_block_id=NULL,version=version+1,"
                    "updated_at=:now WHERE sprint_run_id=:run"
                ),
                {"run": run_id, "now": now},
            )
            view = await self._required_run(session, run_id)
            await self._record_run_event(
                session,
                receipt=receipt,
                actor_id=actor_id,
                context=context,
                event_type=event_type,
                view=view,
                now=now,
            )
            await session.commit()
            return view

    @staticmethod
    async def _unlock_next_block(
        session: AsyncSession, run_id: UUID, ordinal: int, now: datetime
    ) -> None:
        await session.execute(
            text(
                "UPDATE exercises.exercise_block_runs runtime SET status='available',"
                "version=version+1,updated_at=:now FROM planning.session_plan_blocks plan "
                "WHERE runtime.session_plan_block_id=plan.session_plan_block_id "
                "AND runtime.sprint_run_id=:run AND plan.ordinal=:ordinal "
                "AND runtime.status='pending'"
            ),
            {"run": run_id, "ordinal": ordinal + 1, "now": now},
        )

    @staticmethod
    def _active_elapsed_ms(run: SprintRunView, now: datetime) -> int:
        if run.status != "in_progress":
            return 0
        return max(0, int((now - run.updated_at).total_seconds() * 1000))

    async def _record_run_event(
        self,
        session: AsyncSession,
        *,
        receipt: CommandReceipt,
        actor_id: UUID,
        context: RequestContext,
        event_type: str,
        view: SprintRunView,
        now: datetime,
    ) -> None:
        await self._record(
            session,
            receipt=receipt,
            actor_id=actor_id,
            profile_id=view.profile_id,
            context=context,
            event_type=event_type,
            aggregate_type="sprint_run",
            aggregate_id=view.run_id,
            aggregate_version=view.version,
            now=now,
        )

    async def _reserve(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        command_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        idempotency_key: str,
        fingerprint: str,
        expected_version: int | None,
        now: datetime,
    ) -> tuple[CommandReceipt, UUID | None]:
        if not idempotency_key or len(idempotency_key) > 255:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        receipt = CommandReceipt(
            command_id=self._ids.new(),
            command_type=command_type,
            actor_id=actor_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            expected_version=expected_version,
            received_at=now,
            result_ref=None,
            result_payload=None,
            status="started",
            expires_at=now + RECEIPT_RETENTION,
        )
        reservation = await SqlCommandReceiptStore(session).reserve(receipt)
        if reservation.created:
            return reservation.receipt, None
        stored = reservation.receipt
        if stored.status != "succeeded" or stored.result_ref is None:
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return stored, stored.result_ref

    async def _record(
        self,
        session: AsyncSession,
        *,
        receipt: CommandReceipt,
        actor_id: UUID,
        profile_id: UUID,
        context: RequestContext,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        aggregate_version: int,
        now: datetime,
    ) -> None:
        await SqlCommandReceiptStore(session).complete(
            command_id=receipt.command_id,
            status="succeeded",
            result_ref=aggregate_id,
            result_payload={"resource_id": str(aggregate_id), "version": aggregate_version},
        )
        await SqlEventOutboxRepository(session, self._ids).add(
            DomainEvent(
                event_id=self._ids.new(),
                event_type=event_type,
                schema_version=1,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                aggregate_version=aggregate_version,
                actor_type="account",
                actor_id=actor_id,
                profile_id=profile_id,
                occurred_at=now,
                recorded_at=now,
                correlation_id=context.correlation_id,
                causation_id=None,
                command_id=receipt.command_id,
                privacy_class="personal",
                policy_versions={"sprint": 1},
                payload={"resource_id": str(aggregate_id)},
                expires_at=now + EVENT_RETENTION,
                subject_type="profile",
                subject_id=profile_id,
            ),
            destinations=("sprints.events",),
        )

    async def _required_run(self, session: AsyncSession, run_id: UUID) -> SprintRunView:
        view = await self._read_run(session, run_id)
        if view is None:
            raise DomainError(ErrorCode.INTERNAL_ERROR)
        return view

    @staticmethod
    async def _set_actor(session: AsyncSession, actor_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"),
            {"actor": str(actor_id)},
        )

    async def _daily_context(self, session: AsyncSession, profile_id: UUID) -> RowMapping:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT enrollment.enrollment_id,enrollment.module_revision_id,"
                        "day.module_day_id,day.primary_target_refs,day.content_revision_ids,"
                        "day.exercise_definition_revision_ids,day.new_grammar_family_codes,"
                        "revision.pack_revision_id "
                        "FROM curriculum.module_enrollments enrollment "
                        "JOIN curriculum.module_revisions revision USING (module_revision_id) "
                        "JOIN curriculum.module_days day "
                        "ON day.module_revision_id=enrollment.module_revision_id "
                        "AND day.ordinal=LEAST(revision.nominal_days,GREATEST("
                        "enrollment.current_day_ordinal,1+(SELECT count(*) "
                        "FROM planning.sprint_runs completed WHERE "
                        "completed.enrollment_id=enrollment.enrollment_id "
                        "AND completed.plan_kind='daily' AND completed.status='completed'))) "
                        "WHERE enrollment.profile_id=:profile AND enrollment.status='active'"
                    ),
                    {"profile": profile_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NO_VALID_COMPOSITION)
        return row

    async def _free_definition_ids(
        self, session: AsyncSession, primitive_ids: tuple[str, ...]
    ) -> tuple[UUID, ...]:
        statement = text(
            "SELECT DISTINCT ON (primitive_id) definition_revision_id "
            "FROM exercises.exercise_definition_revisions "
            "WHERE status='published' AND primitive_id IN :primitives "
            "ORDER BY primitive_id,revision_no DESC,definition_revision_id DESC LIMIT 16"
        ).bindparams(bindparam("primitives", expanding=True))
        values = tuple(
            _uuid(item)
            for item in (await session.execute(statement, {"primitives": primitive_ids})).scalars()
        )
        if not values:
            raise DomainError(ErrorCode.PRIMITIVE_UNKNOWN)
        return values

    @staticmethod
    async def _profile_pack_revision(session: AsyncSession, profile_id: UUID) -> UUID:
        value = await session.scalar(
            text(
                "SELECT revision.pack_revision_id FROM catalogue.language_pack_revisions revision "
                "JOIN catalogue.language_packs pack USING (pack_id) "
                "JOIN language_profiles.learner_language_profiles profile "
                "ON profile.target_variety_id=revision.target_variety_id "
                "WHERE profile.profile_id=:profile AND revision.status='published' "
                "ORDER BY revision.revision_no DESC LIMIT 1"
            ),
            {"profile": profile_id},
        )
        if value is None:
            raise DomainError(ErrorCode.PACK_NOT_PUBLISHED)
        return _uuid(value)

    async def _candidates(
        self,
        session: AsyncSession,
        *,
        snapshot_id: UUID,
        definition_ids: tuple[UUID, ...],
        target_refs: tuple[str, ...],
        content_ids: tuple[UUID, ...],
        grammar_families: tuple[str, ...],
        allow_novelty: bool,
        reject_prerequisites: bool = False,
    ) -> tuple[CandidateBlock, ...]:
        if not definition_ids:
            raise DomainError(ErrorCode.CONTENT_UNAVAILABLE)
        statement = text(
            "SELECT definition_revision_id,primitive_id,p50_duration_ms,p80_duration_ms,"
            "prerequisite_skill_revision_ids,correction_policy_id "
            "FROM exercises.exercise_definition_revisions "
            "WHERE definition_revision_id IN :definitions AND status='published' "
            "ORDER BY primitive_id,definition_revision_id"
        ).bindparams(bindparam("definitions", expanding=True))
        rows = (await session.execute(statement, {"definitions": definition_ids})).mappings().all()
        if len(rows) != len(set(definition_ids)):
            raise DomainError(ErrorCode.CONTENT_UNAVAILABLE)
        if reject_prerequisites and any(row["prerequisite_skill_revision_ids"] for row in rows):
            raise DomainError(ErrorCode.PREREQUISITE_MISSING)
        candidates: list[CandidateBlock] = []
        for row in rows:
            primitive_id = str(row["primitive_id"])
            family = _family_for(primitive_id, target_refs)
            grammar_family = (
                grammar_families[0]
                if grammar_families
                and family in {BlockFamily.GRAMMAR_TOOLBOX, BlockFamily.TRANSFORMATION_GYM}
                else None
            )
            teaches = (
                frozenset(target_refs)
                if family in {BlockFamily.GRAMMAR_TOOLBOX, BlockFamily.LEXICAL_ACQUISITION}
                else frozenset()
            )
            requires = (
                frozenset(target_refs)
                if grammar_family is not None and family is BlockFamily.TRANSFORMATION_GYM
                else frozenset()
            )
            novelty = 0.0
            if allow_novelty and family is BlockFamily.GRAMMAR_TOOLBOX:
                novelty = 3.0
            elif allow_novelty and family is BlockFamily.LEXICAL_ACQUISITION:
                novelty = float(min(len(target_refs), 3))
            candidates.append(
                CandidateBlock(
                    candidate_id=_uuid(row["definition_revision_id"]),
                    family=family,
                    roles=_roles_for(family),
                    p50_seconds=max(30, int(row["p50_duration_ms"]) // 1000),
                    p80_seconds=max(30, int(row["p80_duration_ms"]) // 1000),
                    novelty_points=novelty,
                    grammar_family=grammar_family,
                    modalities=_modalities_for(family),
                    target_refs=frozenset(target_refs),
                    requires_refs=requires,
                    teaches_refs=teaches,
                    exercise_definition_revision_ids=(_uuid(row["definition_revision_id"]),),
                    content_revision_ids=content_ids,
                    memory_due=0.7 if family is BlockFamily.RECALL_WARMUP else 0,
                    module_criticality=(
                        0.9
                        if family
                        in {
                            BlockFamily.GRAMMAR_TOOLBOX,
                            BlockFamily.TRANSFORMATION_GYM,
                            BlockFamily.GUIDED_OUTPUT,
                        }
                        else 0.4
                    ),
                    modality_balance=(
                        0.5
                        if family
                        in {
                            BlockFamily.LISTENING,
                            BlockFamily.SHADOWING,
                            BlockFamily.GUIDED_OUTPUT,
                        }
                        else 0
                    ),
                    information_gain=0.5,
                    corrector_ready=bool(row["correction_policy_id"]),
                )
            )
        candidates = self._assign_core_roles(candidates)
        candidates.append(
            CandidateBlock(
                candidate_id=self._derived_uuid(snapshot_id, "reflection"),
                family=BlockFamily.REFLECTION_CLOSE,
                roles=frozenset({"reflection"}),
                p50_seconds=60,
                p80_seconds=90,
                module_criticality=1,
            )
        )
        return tuple(candidates)

    @staticmethod
    def _assign_core_roles(candidates: list[CandidateBlock]) -> list[CandidateBlock]:
        activation = next(
            (item for item in candidates if item.family is BlockFamily.RECALL_WARMUP),
            next(
                (
                    item
                    for item in candidates
                    if item.family in {BlockFamily.VERSION_INPUT, BlockFamily.LISTENING}
                ),
                None,
            ),
        )
        production = next(
            (
                item
                for item in candidates
                if item.family
                in {
                    BlockFamily.GUIDED_OUTPUT,
                    BlockFamily.FREE_WRITING,
                    BlockFamily.TRANSFORMATION_GYM,
                }
            ),
            None,
        )
        if activation is None or production is None:
            raise DomainError(ErrorCode.NO_VALID_COMPOSITION)
        result: list[CandidateBlock] = []
        for item in candidates:
            roles = set(item.roles)
            if item.candidate_id == activation.candidate_id:
                roles.add("activation")
            if item.candidate_id == production.candidate_id:
                roles.update({"primary_objective", "unsupported_production"})
            result.append(replace(item, roles=frozenset(roles)))
        return result

    @staticmethod
    async def _due_recode_ids(
        session: AsyncSession, profile_id: UUID, cutoff_at: datetime
    ) -> tuple[UUID, ...]:
        rows = (
            await session.execute(
                text(
                    "SELECT delayed_recode_id FROM planning.delayed_recode_tasks "
                    "WHERE profile_id=:profile AND status IN ('pending','due') "
                    "AND due_at <= :cutoff "
                    "ORDER BY due_at,delayed_recode_id LIMIT 3"
                ),
                {"profile": profile_id, "cutoff": cutoff_at},
            )
        ).scalars()
        return tuple(_uuid(value) for value in rows)

    def _attach_due_recodes(
        self,
        snapshot_id: UUID,
        candidates: tuple[CandidateBlock, ...],
        due_ids: tuple[UUID, ...],
    ) -> tuple[CandidateBlock, ...]:
        if not due_ids:
            return candidates
        template = next(
            (item for item in candidates if item.family is BlockFamily.RECALL_WARMUP),
            None,
        )
        if template is None:
            raise DomainError(ErrorCode.CONTENT_UNAVAILABLE)
        without_plain_recall = tuple(
            item for item in candidates if item.candidate_id != template.candidate_id
        )
        recodes = tuple(
            replace(
                template,
                candidate_id=self._derived_uuid(snapshot_id, f"recode:{value}"),
                family=BlockFamily.DELAYED_RECODE,
                roles=frozenset({"activation", "j1_due"}),
                delayed_recode_id=value,
                novelty_points=0,
                memory_due=1,
            )
            for value in due_ids
        )
        return recodes + without_plain_recall

    async def _persist_plan(
        self,
        session: AsyncSession,
        *,
        plan: SessionPlan,
        pack_revision_id: UUID,
        now: datetime,
    ) -> None:
        snapshot = plan.snapshot
        candidate_payload = [self._candidate_payload(value) for value in snapshot.candidates]
        snapshot_fingerprint = canonical_json_fingerprint(
            cast(
                JsonValue,
                {
                    "snapshot_id": str(snapshot.snapshot_id),
                    "profile_id": str(snapshot.profile_id),
                    "plan_kind": snapshot.plan_kind.value,
                    "budget_minutes": snapshot.budget_minutes,
                    "pedagogical_day": snapshot.pedagogical_day.isoformat(),
                    "timezone": snapshot.timezone,
                    "cutoff_at": snapshot.cutoff_at.isoformat(),
                    "seed": snapshot.seed,
                    "policy_revision": snapshot.policy_revision,
                    "planner_revision": snapshot.planner_revision,
                    "candidates": candidate_payload,
                    "pack_revision_id": str(pack_revision_id),
                },
            )
        )
        try:
            await session.execute(
                text(
                    "INSERT INTO planning.planning_snapshots "
                    "(snapshot_id,profile_id,plan_kind,budget_minutes,pedagogical_day,timezone,"
                    "cutoff_at,seed,policy_revision,planner_revision,profile_band,enrollment_id,"
                    "module_revision_id,module_day_id,mastered_refs,prerequisite_refs,"
                    "due_delayed_recode_ids,word_bank_snapshot_ids,candidate_payload,private_context,"
                    "payload_fingerprint,created_at) VALUES "
                    "(:snapshot,:profile,:kind,:budget,:day,:timezone,:cutoff,:seed,:policy,"
                    ":planner,:band,:enrollment,:module_revision,:module_day,:mastered,:prerequisites,"
                    ":due,:word_bank,CAST(:candidates AS jsonb),:private_context,:fingerprint,:now)"
                ),
                {
                    "snapshot": snapshot.snapshot_id,
                    "profile": snapshot.profile_id,
                    "kind": snapshot.plan_kind.value,
                    "budget": snapshot.budget_minutes,
                    "day": snapshot.pedagogical_day,
                    "timezone": snapshot.timezone,
                    "cutoff": snapshot.cutoff_at,
                    "seed": snapshot.seed,
                    "policy": snapshot.policy_revision,
                    "planner": snapshot.planner_revision,
                    "band": snapshot.profile_band,
                    "enrollment": snapshot.enrollment_id,
                    "module_revision": snapshot.module_revision_id,
                    "module_day": snapshot.module_day_id,
                    "mastered": sorted(snapshot.mastered_refs),
                    "prerequisites": sorted(snapshot.prerequisite_refs),
                    "due": list(snapshot.due_delayed_recode_ids),
                    "word_bank": list(snapshot.word_bank_snapshot_ids),
                    "candidates": _json(candidate_payload),
                    "private_context": snapshot.private_context,
                    "fingerprint": snapshot_fingerprint,
                    "now": now,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO planning.session_plans "
                    "(plan_id,profile_id,plan_kind,pedagogical_day,current_revision_id,status,"
                    "failure_code,version,created_at,updated_at) VALUES "
                    "(:plan,:profile,:kind,:day,NULL,'draft',NULL,1,:now,:now)"
                ),
                {
                    "plan": plan.plan_id,
                    "profile": snapshot.profile_id,
                    "kind": snapshot.plan_kind.value,
                    "day": snapshot.pedagogical_day,
                    "now": now,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO planning.session_plan_revisions "
                    "(plan_revision_id,plan_id,profile_id,revision_no,snapshot_id,budget_minutes,"
                    "total_p50_seconds,total_p80_seconds,novelty_points,planner_revision,"
                    "policy_revision,plan_fingerprint,created_at) VALUES "
                    "(:revision,:plan,:profile,1,:snapshot,:budget,:p50,:p80,:novelty,:planner,"
                    ":policy,:fingerprint,:now)"
                ),
                {
                    "revision": plan.revision_id,
                    "plan": plan.plan_id,
                    "profile": snapshot.profile_id,
                    "snapshot": snapshot.snapshot_id,
                    "budget": snapshot.budget_minutes,
                    "p50": plan.total_p50_seconds,
                    "p80": plan.total_p80_seconds,
                    "novelty": plan.novelty_points,
                    "planner": snapshot.planner_revision,
                    "policy": snapshot.policy_revision,
                    "fingerprint": plan.fingerprint,
                    "now": now,
                },
            )
            for block in plan.blocks:
                await session.execute(
                    text(
                        "INSERT INTO planning.session_plan_blocks "
                        "(session_plan_block_id,plan_revision_id,profile_id,ordinal,candidate_id,"
                        "family,roles,reason_codes,modalities,p50_seconds,p80_seconds,novelty_points,"
                        "required,target_refs,delayed_recode_id,exercise_definition_revision_ids,"
                        "content_revision_ids,created_at) VALUES "
                        "(:block,:revision,:profile,:ordinal,:candidate,:family,:roles,:reasons,"
                        ":modalities,:p50,:p80,:novelty,:required,:targets,:recode,:definitions,:content,:now)"
                    ),
                    {
                        "block": block.block_id,
                        "revision": plan.revision_id,
                        "profile": snapshot.profile_id,
                        "ordinal": block.ordinal,
                        "candidate": block.candidate_id,
                        "family": block.family.value,
                        "roles": sorted(block.roles),
                        "reasons": list(block.reason_codes),
                        "modalities": sorted(block.modalities),
                        "p50": block.p50_seconds,
                        "p80": block.p80_seconds,
                        "novelty": block.novelty_points,
                        "required": bool(block.roles & CORE_ROLES),
                        "targets": list(block.target_refs),
                        "recode": block.delayed_recode_id,
                        "definitions": list(block.exercise_definition_revision_ids),
                        "content": list(block.content_revision_ids),
                        "now": now,
                    },
                )
            await session.execute(
                text(
                    "UPDATE planning.session_plans SET current_revision_id=:revision "
                    "WHERE plan_id=:plan"
                ),
                {"revision": plan.revision_id, "plan": plan.plan_id},
            )
            if snapshot.due_delayed_recode_ids:
                statement = text(
                    "UPDATE planning.delayed_recode_tasks SET status='planned',"
                    "consumed_by_plan_revision_id=:revision,version=version+1,updated_at=:now "
                    "WHERE profile_id=:profile AND delayed_recode_id IN :recodes "
                    "AND status IN ('pending','due')"
                ).bindparams(bindparam("recodes", expanding=True))
                await session.execute(
                    statement,
                    {
                        "revision": plan.revision_id,
                        "now": now,
                        "profile": snapshot.profile_id,
                        "recodes": snapshot.due_delayed_recode_ids,
                    },
                )
        except IntegrityError as error:
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT) from error

    @staticmethod
    def _candidate_payload(value: CandidateBlock) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            {
                "candidate_id": str(value.candidate_id),
                "family": value.family.value,
                "roles": sorted(value.roles),
                "p50_seconds": value.p50_seconds,
                "p80_seconds": value.p80_seconds,
                "novelty_points": value.novelty_points,
                "grammar_family": value.grammar_family,
                "modalities": sorted(value.modalities),
                "target_refs": sorted(value.target_refs),
                "requires_refs": sorted(value.requires_refs),
                "teaches_refs": sorted(value.teaches_refs),
                "delayed_recode_id": (
                    None if value.delayed_recode_id is None else str(value.delayed_recode_id)
                ),
                "exercise_definition_revision_ids": [
                    str(item) for item in value.exercise_definition_revision_ids
                ],
                "content_revision_ids": [str(item) for item in value.content_revision_ids],
                "priority": value.priority,
                "ready": value.is_ready,
            },
        )

    @staticmethod
    def _derived_uuid(namespace: UUID, label: str) -> UUID:
        digest = bytearray(hashlib.sha256(f"{namespace}:{label}".encode()).digest()[:16])
        digest[0:6] = namespace.bytes[0:6]
        digest[6] = (digest[6] & 0x0F) | 0x70
        digest[8] = (digest[8] & 0x3F) | 0x80
        return UUID(bytes=bytes(digest))

    async def _required_plan(self, session: AsyncSession, plan_id: UUID) -> SessionPlanView:
        view = await self._read_plan(session, plan_id)
        if view is None:
            raise DomainError(ErrorCode.INTERNAL_ERROR)
        return view

    async def _read_plan(
        self,
        session: AsyncSession,
        plan_id: UUID,
        *,
        for_update: bool = False,
    ) -> SessionPlanView | None:
        suffix = " FOR UPDATE OF plan" if for_update else ""
        row = (
            (
                await session.execute(
                    text(
                        "SELECT plan.*,revision.plan_revision_id,revision.snapshot_id,"
                        "revision.budget_minutes,revision.total_p50_seconds,"
                        "revision.total_p80_seconds,revision.novelty_points,"
                        "revision.plan_fingerprint FROM planning.session_plans plan "
                        "JOIN planning.session_plan_revisions revision "
                        "ON revision.plan_revision_id=plan.current_revision_id "
                        "WHERE plan.plan_id=:plan" + suffix
                    ),
                    {"plan": plan_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        block_rows = (
            (
                await session.execute(
                    text(
                        "SELECT block.*,COALESCE(array_agg(link.instance_id ORDER BY link.ordinal) "
                        "FILTER (WHERE link.instance_id IS NOT NULL),ARRAY[]::uuid[]) instance_ids "
                        "FROM planning.session_plan_blocks block "
                        "LEFT JOIN planning.session_plan_exercise_instances link "
                        "ON link.session_plan_block_id=block.session_plan_block_id "
                        "WHERE block.plan_revision_id=:revision "
                        "GROUP BY block.session_plan_block_id "
                        "ORDER BY block.ordinal"
                    ),
                    {"revision": row["plan_revision_id"]},
                )
            )
            .mappings()
            .all()
        )
        blocks = tuple(
            PlanBlockView(
                block_id=_uuid(block["session_plan_block_id"]),
                ordinal=int(block["ordinal"]),
                family=str(block["family"]),
                roles=tuple(str(item) for item in block["roles"]),
                reason_codes=tuple(str(item) for item in block["reason_codes"]),
                modalities=tuple(str(item) for item in block["modalities"]),
                p50_seconds=int(block["p50_seconds"]),
                p80_seconds=int(block["p80_seconds"]),
                required=bool(block["required"]),
                delayed_recode_id=(
                    None
                    if block["delayed_recode_id"] is None
                    else _uuid(block["delayed_recode_id"])
                ),
                exercise_instance_ids=tuple(_uuid(item) for item in block["instance_ids"]),
            )
            for block in block_rows
        )
        return SessionPlanView(
            plan_id=_uuid(row["plan_id"]),
            plan_revision_id=_uuid(row["plan_revision_id"]),
            snapshot_id=_uuid(row["snapshot_id"]),
            profile_id=_uuid(row["profile_id"]),
            plan_kind=str(row["plan_kind"]),
            pedagogical_day=row["pedagogical_day"],
            budget_minutes=int(row["budget_minutes"]),
            status=str(row["status"]),
            failure_code=None if row["failure_code"] is None else str(row["failure_code"]),
            total_p50_seconds=int(row["total_p50_seconds"]),
            total_p80_seconds=int(row["total_p80_seconds"]),
            novelty_points=float(row["novelty_points"]),
            plan_fingerprint=str(row["plan_fingerprint"]),
            blocks=blocks,
            version=int(row["version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def _read_run(
        self,
        session: AsyncSession,
        run_id: UUID,
        *,
        for_update: bool = False,
    ) -> SprintRunView | None:
        suffix = " FOR UPDATE OF run" if for_update else ""
        row = (
            (
                await session.execute(
                    text(
                        "SELECT run.* FROM planning.sprint_runs run WHERE sprint_run_id=:run"
                        + suffix
                    ),
                    {"run": run_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        blocks = (
            (
                await session.execute(
                    text(
                        "SELECT runtime.block_id,runtime.session_plan_block_id,runtime.status,"
                        "runtime.required,runtime.reason,runtime.version,plan.ordinal,plan.family,"
                        "COALESCE(array_agg(link.instance_id ORDER BY link.ordinal) "
                        "FILTER (WHERE link.instance_id IS NOT NULL),ARRAY[]::uuid[]) instance_ids "
                        "FROM exercises.exercise_block_runs runtime "
                        "JOIN planning.session_plan_blocks plan "
                        "ON plan.session_plan_block_id=runtime.session_plan_block_id "
                        "LEFT JOIN planning.session_plan_exercise_instances link "
                        "ON link.session_plan_block_id=plan.session_plan_block_id "
                        "WHERE runtime.sprint_run_id=:run "
                        "GROUP BY runtime.block_id,plan.session_plan_block_id "
                        "ORDER BY plan.ordinal"
                    ),
                    {"run": run_id},
                )
            )
            .mappings()
            .all()
        )
        block_views = tuple(
            SprintBlockView(
                block_id=_uuid(block["block_id"]),
                session_plan_block_id=_uuid(block["session_plan_block_id"]),
                ordinal=int(block["ordinal"]),
                family=str(block["family"]),
                status=str(block["status"]),
                required=bool(block["required"]),
                reason=None if block["reason"] is None else str(block["reason"]),
                exercise_instance_ids=tuple(_uuid(item) for item in block["instance_ids"]),
                version=int(block["version"]),
            )
            for block in blocks
        )
        return SprintRunView(
            run_id=_uuid(row["sprint_run_id"]),
            plan_id=_uuid(row["plan_id"]),
            plan_revision_id=_uuid(row["plan_revision_id"]),
            profile_id=_uuid(row["profile_id"]),
            plan_kind=str(row["plan_kind"]),
            pedagogical_day=row["pedagogical_day"],
            status=str(row["status"]),
            current_block_id=(
                None if row["current_block_id"] is None else _uuid(row["current_block_id"])
            ),
            blocks=block_views,
            started_at=row["started_at"],
            interrupted_at=row["interrupted_at"],
            completed_at=row["completed_at"],
            expires_at=row["expires_at"],
            stop_reason=None if row["stop_reason"] is None else str(row["stop_reason"]),
            active_duration_ms=int(row["active_duration_ms"]),
            consumes_module_day=(
                str(row["plan_kind"]) == "daily" and str(row["status"]) == "completed"
            ),
            version=int(row["version"]),
            updated_at=row["updated_at"],
        )

    async def prepare(
        self,
        actor_id: UUID,
        plan_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SessionPlanView:
        now = self._clock.now()
        fingerprint = canonical_json_fingerprint(
            {
                "plan_id": str(plan_id),
                "expected_version": expected_version,
            }
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            receipt, replay_id = await self._reserve(
                session,
                actor_id=actor_id,
                command_type="PrepareSessionPlan",
                aggregate_type="session_plan",
                aggregate_id=plan_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
                now=now,
            )
            if replay_id is not None:
                replay = await self._read_plan(session, replay_id)
                if replay is None:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return replay
            before = await self._read_plan(session, plan_id, for_update=True)
            if before is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if before.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if before.status != "draft":
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            await session.execute(
                text(
                    "UPDATE planning.session_plans SET status='preparing',version=version+1,"
                    "updated_at=:now WHERE plan_id=:plan"
                ),
                {"now": now, "plan": plan_id},
            )
            await self._prepare_instances(session, before, now)
            await session.execute(
                text(
                    "UPDATE planning.session_plans SET status='ready',version=version+1,"
                    "updated_at=:now WHERE plan_id=:plan"
                ),
                {"now": now, "plan": plan_id},
            )
            view = await self._required_plan(session, plan_id)
            await self._record(
                session,
                receipt=receipt,
                actor_id=actor_id,
                profile_id=view.profile_id,
                context=context,
                event_type="session_plan_ready",
                aggregate_type="session_plan",
                aggregate_id=plan_id,
                aggregate_version=view.version,
                now=now,
            )
            await session.commit()
            return view

    async def _prepare_instances(
        self,
        session: AsyncSession,
        plan: SessionPlanView,
        now: datetime,
    ) -> None:
        block_rows = (
            (
                await session.execute(
                    text(
                        "SELECT session_plan_block_id,ordinal,exercise_definition_revision_ids,"
                        "content_revision_ids,target_refs FROM planning.session_plan_blocks "
                        "WHERE plan_revision_id=:revision ORDER BY ordinal"
                    ),
                    {"revision": plan.plan_revision_id},
                )
            )
            .mappings()
            .all()
        )
        for block in block_rows:
            definitions = tuple(_uuid(item) for item in block["exercise_definition_revision_ids"])
            for ordinal, definition_id in enumerate(definitions, start=1):
                definition = (
                    (
                        await session.execute(
                            text(
                                "SELECT definition.primitive_id,"
                                "certification.language_pack_revision_id "
                                "FROM exercises.exercise_definition_revisions definition "
                                "LEFT JOIN exercises.exercise_language_certifications "
                                "certification ON certification.definition_revision_id="
                                "definition.definition_revision_id "
                                "AND certification.status='validated' "
                                "WHERE definition.definition_revision_id=:definition "
                                "AND definition.status='published' "
                                "ORDER BY certification.validated_at DESC NULLS LAST LIMIT 1"
                            ),
                            {"definition": definition_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if definition is None:
                    raise DomainError(ErrorCode.CONTENT_UNAVAILABLE)
                pack_revision_id = definition["language_pack_revision_id"]
                if pack_revision_id is None:
                    pack_revision_id = await session.scalar(
                        text(
                            "SELECT revision.pack_revision_id "
                            "FROM planning.planning_snapshots snapshot "
                            "JOIN curriculum.module_revisions revision "
                            "ON revision.module_revision_id=snapshot.module_revision_id "
                            "WHERE snapshot.snapshot_id=:snapshot"
                        ),
                        {"snapshot": plan.snapshot_id},
                    )
                if pack_revision_id is None:
                    pack_revision_id = await self._profile_pack_revision(session, plan.profile_id)
                if pack_revision_id is None:
                    raise DomainError(ErrorCode.CONTENT_UNAVAILABLE)
                instance_id = self._ids.new()
                stimulus_ids = tuple(_uuid(item) for item in block["content_revision_ids"])
                if not stimulus_ids:
                    stimulus_ids = (definition_id,)
                seed = int(
                    hashlib.sha256(
                        f"{plan.plan_fingerprint}:{block['session_plan_block_id']}:{ordinal}".encode()
                    ).hexdigest()[:15],
                    16,
                )
                await session.execute(
                    text(
                        "INSERT INTO exercises.exercise_instances "
                        "(instance_id,standalone_profile_id,definition_revision_id,"
                        "language_pack_revision_id,seed,stimulus_revision_ids,"
                        "session_plan_revision_id,target_bindings,lexical_bindings,grammar_bindings,"
                        "accepted_answer_set_revision_id,rubric_revision_id,available_from,expires_at,"
                        "provenance_id,created_at) VALUES "
                        "(:instance,NULL,:definition,:pack,:seed,"
                        "CAST(:stimulus AS jsonb),:revision,"
                        "CAST(:targets AS jsonb),CAST(:lexical AS jsonb),CAST(:grammar AS jsonb),"
                        "NULL,NULL,:available,:expires,:provenance,:created)"
                    ),
                    {
                        "instance": instance_id,
                        "definition": definition_id,
                        "pack": pack_revision_id,
                        "seed": seed,
                        "stimulus": _json([str(item) for item in stimulus_ids]),
                        "revision": plan.plan_revision_id,
                        "targets": _json(list(block["target_refs"])),
                        "lexical": _json(
                            [
                                value
                                for value in block["target_refs"]
                                if str(value).startswith("lexical:")
                            ]
                        ),
                        "grammar": _json(
                            [
                                value
                                for value in block["target_refs"]
                                if str(value).startswith("grammar:")
                            ]
                        ),
                        "available": now,
                        "expires": now + RUN_RETENTION,
                        "provenance": self._ids.new(),
                        "created": now,
                    },
                )
                await session.execute(
                    text(
                        "INSERT INTO planning.session_plan_exercise_instances "
                        "(plan_instance_link_id,profile_id,plan_revision_id,session_plan_block_id,"
                        "instance_id,ordinal,created_at) VALUES "
                        "(:link,:profile,:revision,:block,:instance,:ordinal,:created)"
                    ),
                    {
                        "link": self._ids.new(),
                        "profile": plan.profile_id,
                        "revision": plan.plan_revision_id,
                        "block": block["session_plan_block_id"],
                        "instance": instance_id,
                        "ordinal": ordinal,
                        "created": now,
                    },
                )

    async def cancel_plan(
        self,
        actor_id: UUID,
        plan_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> SessionPlanView:
        return await self._transition_plan(
            actor_id=actor_id,
            plan_id=plan_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            context=context,
            command_type="CancelSessionPlan",
            event_type="session_plan_cancelled",
            allowed_statuses={"draft", "preparing", "ready"},
            target_status="cancelled",
        )

    async def _transition_plan(
        self,
        *,
        actor_id: UUID,
        plan_id: UUID,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
        command_type: str,
        event_type: str,
        allowed_statuses: set[str],
        target_status: str,
    ) -> SessionPlanView:
        now = self._clock.now()
        fingerprint = canonical_json_fingerprint(
            {
                "plan_id": str(plan_id),
                "expected_version": expected_version,
                "target_status": target_status,
            }
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            receipt, replay_id = await self._reserve(
                session,
                actor_id=actor_id,
                command_type=command_type,
                aggregate_type="session_plan",
                aggregate_id=plan_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
                now=now,
            )
            if replay_id is not None:
                replay = await self._read_plan(session, replay_id)
                if replay is None:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return replay
            before = await self._read_plan(session, plan_id, for_update=True)
            if before is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if before.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if before.status not in allowed_statuses:
                raise DomainError(ErrorCode.RUN_ALREADY_STARTED)
            if target_status == "cancelled":
                run_exists = await session.scalar(
                    text("SELECT EXISTS (SELECT 1 FROM planning.sprint_runs WHERE plan_id=:plan)"),
                    {"plan": plan_id},
                )
                if run_exists:
                    raise DomainError(ErrorCode.RUN_ALREADY_STARTED)
            await session.execute(
                text(
                    "UPDATE planning.session_plans SET status=:status,version=version+1,"
                    "updated_at=:now WHERE plan_id=:plan"
                ),
                {"status": target_status, "now": now, "plan": plan_id},
            )
            view = await self._required_plan(session, plan_id)
            await self._record(
                session,
                receipt=receipt,
                actor_id=actor_id,
                profile_id=view.profile_id,
                context=context,
                event_type=event_type,
                aggregate_type="session_plan",
                aggregate_id=plan_id,
                aggregate_version=view.version,
                now=now,
            )
            await session.commit()
            return view

    async def start_run(
        self,
        actor_id: UUID,
        plan_id: UUID,
        command: StartSprintRun,
        *,
        idempotency_key: str,
        context: RequestContext,
    ) -> SprintRunView:
        now = self._clock.now()
        fingerprint = canonical_json_fingerprint(
            {"plan_id": str(plan_id), "run_id": str(command.run_id)}
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            receipt, replay_id = await self._reserve(
                session,
                actor_id=actor_id,
                command_type="StartSprintRun",
                aggregate_type="sprint_run",
                aggregate_id=command.run_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=None,
                now=now,
            )
            if replay_id is not None:
                replay = await self._read_run(session, replay_id)
                if replay is None:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return replay
            plan = await self._read_plan(session, plan_id, for_update=True)
            if plan is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if plan.status != "ready":
                raise DomainError(ErrorCode.CONTENT_UNAVAILABLE)
            snapshot = (
                (
                    await session.execute(
                        text(
                            "SELECT enrollment_id,module_day_id FROM planning.planning_snapshots "
                            "WHERE snapshot_id=:snapshot"
                        ),
                        {"snapshot": plan.snapshot_id},
                    )
                )
                .mappings()
                .one()
            )
            try:
                await session.execute(
                    text(
                        "INSERT INTO planning.sprint_runs "
                        "(sprint_run_id,profile_id,plan_id,plan_revision_id,plan_kind,"
                        "pedagogical_day,enrollment_id,module_day_id,status,current_block_id,"
                        "started_at,interrupted_at,completed_at,expires_at,stop_reason,"
                        "active_duration_ms,version,updated_at) VALUES "
                        "(:run,:profile,:plan,:revision,:kind,:day,:enrollment,:module_day,"
                        "'in_progress',NULL,:now,NULL,NULL,:expires,NULL,0,1,:now)"
                    ),
                    {
                        "run": command.run_id,
                        "profile": plan.profile_id,
                        "plan": plan.plan_id,
                        "revision": plan.plan_revision_id,
                        "kind": plan.plan_kind,
                        "day": plan.pedagogical_day,
                        "enrollment": snapshot["enrollment_id"],
                        "module_day": snapshot["module_day_id"],
                        "now": now,
                        "expires": now + RUN_RETENTION,
                    },
                )
                for block in plan.blocks:
                    await session.execute(
                        text(
                            "INSERT INTO exercises.exercise_block_runs "
                            "(block_id,profile_id,sprint_run_id,session_plan_block_id,required,"
                            "status,reason,aggregate_payload,version,created_at,updated_at) VALUES "
                            "(:block,:profile,:run,:plan_block,:required,:status,NULL,'{}',1,:now,:now)"
                        ),
                        {
                            "block": block.block_id,
                            "profile": plan.profile_id,
                            "run": command.run_id,
                            "plan_block": block.block_id,
                            "required": block.required,
                            "status": "available" if block.ordinal == 1 else "pending",
                            "now": now,
                        },
                    )
            except IntegrityError as error:
                raise DomainError(ErrorCode.ACTIVE_RUN_EXISTS) from error
            view = await self._required_run(session, command.run_id)
            await self._record(
                session,
                receipt=receipt,
                actor_id=actor_id,
                profile_id=view.profile_id,
                context=context,
                event_type="sprint_run_started",
                aggregate_type="sprint_run",
                aggregate_id=view.run_id,
                aggregate_version=view.version,
                now=now,
            )
            await session.commit()
            return view


class SqlDelayedRecodeRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._sessions = session_factory
        self._clock = clock or SystemClock()
        self._ids = id_generator or Uuid7Generator(self._clock)

    async def schedule(self, actor_id: UUID, spec: DelayedRecodeSpec) -> UUID:
        now = self._clock.now()
        due_policy = "after_24h" if spec.due_after_24h else "next_active_session"
        due_at = max(
            spec.not_before,
            spec.source_corrected_at + timedelta(hours=24)
            if spec.due_after_24h
            else spec.not_before,
        )
        async with self._sessions() as session:
            await SqlSprintService._set_actor(session, actor_id)
            existing = await session.scalar(
                text(
                    "SELECT delayed_recode_id FROM planning.delayed_recode_specs "
                    "WHERE source_attempt_id=:attempt AND source_correction_id=:correction"
                ),
                {
                    "attempt": spec.source_attempt_id,
                    "correction": spec.source_correction_revision_id,
                },
            )
            if existing is not None:
                return _uuid(existing)
            await session.execute(
                text(
                    "INSERT INTO planning.delayed_recode_specs "
                    "(delayed_recode_id,profile_id,source_attempt_id,source_correction_id,"
                    "source_exercise_instance_id,target_stimulus,corrected_support_text,"
                    "accepted_target_answers,target_language_tag,support_language_tag,target_refs,"
                    "correction_policy_revision_id,content_revision_ids,source_corrected_at,"
                    "not_before,due_policy,created_at) VALUES "
                    "(:recode,:profile,:attempt,:correction,:instance,:target,:support,"
                    "CAST(:answers AS jsonb),:target_tag,:support_tag,:target_refs,:policy,"
                    ":content,:corrected,:not_before,:due_policy,:created)"
                ),
                {
                    "recode": spec.delayed_recode_id,
                    "profile": spec.profile_id,
                    "attempt": spec.source_attempt_id,
                    "correction": spec.source_correction_revision_id,
                    "instance": spec.source_exercise_instance_id,
                    "target": spec.target_stimulus,
                    "support": spec.corrected_support_text,
                    "answers": _json(list(spec.accepted_target_answers)),
                    "target_tag": spec.target_language_tag,
                    "support_tag": spec.support_language_tag,
                    "target_refs": list(spec.target_refs),
                    "policy": spec.correction_policy_revision_id,
                    "content": list(spec.content_revision_ids),
                    "corrected": spec.source_corrected_at,
                    "not_before": spec.not_before,
                    "due_policy": due_policy,
                    "created": now,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO planning.delayed_recode_tasks "
                    "(delayed_recode_task_id,delayed_recode_id,profile_id,status,due_at,"
                    "consumed_by_plan_revision_id,cancelled_reason,version,created_at,updated_at) "
                    "VALUES (:task,:recode,:profile,'pending',:due,NULL,NULL,1,:now,:now)"
                ),
                {
                    "task": self._ids.new(),
                    "recode": spec.delayed_recode_id,
                    "profile": spec.profile_id,
                    "due": due_at,
                    "now": now,
                },
            )
            await session.commit()
            return spec.delayed_recode_id


__all__ = ["SqlDelayedRecodeRepository", "SqlSprintService"]
