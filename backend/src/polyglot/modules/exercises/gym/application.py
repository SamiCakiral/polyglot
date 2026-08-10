from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from polyglot.modules.exercises.core.domain import ExerciseDefinition, ExerciseInstance
from polyglot.modules.exercises.gym.domain import PrerequisiteGrant, TransformationCase
from polyglot.modules.exercises.gym.planning import GymPlan, compose_gym_plan


class GymCataloguePort(Protocol):
    async def require_published_grammar_target(
        self,
        grammar_target_revision_id: UUID,
        language_pack_revision_id: UUID,
    ) -> None: ...


class GymLexiconPort(Protocol):
    async def require_owned_snapshot(
        self, actor_id: UUID, profile_id: UUID, snapshot_id: UUID
    ) -> None: ...


class GymExercisePort(Protocol):
    async def get_published_definition(
        self, definition_revision_id: UUID
    ) -> ExerciseDefinition: ...

    async def persist_gym_instances(
        self,
        actor_id: UUID,
        profile_id: UUID,
        instances: tuple[ExerciseInstance, ...],
    ) -> None: ...


class GymPlanRepository(Protocol):
    async def add(
        self,
        actor_id: UUID,
        plan: GymPlan,
        *,
        provenance_id: UUID,
        created_at: datetime,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class PrepareGymPlan:
    actor_id: UUID
    plan_id: UUID
    revision_id: UUID
    profile_id: UUID
    grammar_target_revision_id: UUID
    policy_revision_id: UUID
    language_pack_revision_id: UUID
    lexical_support_snapshot_id: UUID
    definition_revision_id: UUID
    provenance_id: UUID
    seed: int
    candidates: tuple[TransformationCase, ...]
    grants: tuple[PrerequisiteGrant, ...]
    invariants: tuple[str, ...]
    exit_evidence_spec: str
    created_at: datetime


class GymPlanningService:
    def __init__(
        self,
        *,
        catalogue: GymCataloguePort,
        lexicon: GymLexiconPort,
        exercises: GymExercisePort,
        plans: GymPlanRepository,
    ) -> None:
        self._catalogue = catalogue
        self._lexicon = lexicon
        self._exercises = exercises
        self._plans = plans

    async def prepare(self, command: PrepareGymPlan) -> GymPlan:
        await self._catalogue.require_published_grammar_target(
            command.grammar_target_revision_id,
            command.language_pack_revision_id,
        )
        await self._lexicon.require_owned_snapshot(
            command.actor_id,
            command.profile_id,
            command.lexical_support_snapshot_id,
        )
        definition = await self._exercises.get_published_definition(
            command.definition_revision_id
        )
        plan = compose_gym_plan(
            plan_id=command.plan_id,
            revision_id=command.revision_id,
            profile_id=command.profile_id,
            grammar_target_revision_id=command.grammar_target_revision_id,
            policy_revision_id=command.policy_revision_id,
            language_pack_revision_id=command.language_pack_revision_id,
            lexical_support_snapshot_id=command.lexical_support_snapshot_id,
            seed=command.seed,
            definition=definition,
            candidates=command.candidates,
            grants=command.grants,
            invariants=command.invariants,
            exit_evidence_spec=command.exit_evidence_spec,
        )
        await self._exercises.persist_gym_instances(
            command.actor_id,
            command.profile_id,
            tuple(step.instance for step in plan.steps),
        )
        await self._plans.add(
            command.actor_id,
            plan,
            provenance_id=command.provenance_id,
            created_at=command.created_at,
        )
        return plan


__all__ = [
    "GymCataloguePort",
    "GymExercisePort",
    "GymLexiconPort",
    "GymPlanRepository",
    "GymPlanningService",
    "PrepareGymPlan",
]
