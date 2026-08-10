from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from polyglot.modules.exercises.core.domain import AnswerKind, ExerciseDefinition
from polyglot.modules.exercises.gym.domain import (
    OperationSemantics,
    PrerequisiteGrant,
    TransformationCase,
    operation_spec,
)
from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 8, 10, 17, 0, tzinfo=UTC)


def uid(value: int) -> UUID:
    return UUID(f"019fee00-0000-7000-8000-{value:012x}")


def definition() -> ExerciseDefinition:
    return ExerciseDefinition.published(
        definition_id=uid(1),
        revision_id=uid(2),
        revision_no=1,
        primitive_id="EX-TRANSFORM-01",
        response_kinds=(AnswerKind.TEXT,),
        language_certification_ids=(uid(3),),
        modes=("gym",),
        target_weights=(("grammar:vorrei", 0.65),),
        correction_policy_id="gym-correction:v1",
        hint_policy_id="gym-hints:v1",
        observation_policy_id="gym-observation:v1",
        accessibility_features=("keyboard", "screen_reader", "untimed"),
    )


def candidate() -> TransformationCase:
    spec = operation_spec("GYM-01")
    return TransformationCase.published(
        case_id="it:vorrei:substitution",
        revision_id="it:vorrei:substitution:v1",
        operation_id="GYM-01",
        source_text="Vorrei un caffe",
        edits=(("un caffe", "un biglietto"),),
        accepted_outputs=("Vorrei un biglietto",),
        rejected_outputs=("Voglio un biglietto",),
        required_prerequisites=("it:frame:vorrei",),
        invariants=("polite_request",),
        grammar_target_id="grammar:vorrei",
        lexical_support_ids=("lexicon:biglietto",),
        semantics=OperationSemantics.create(
            kind=spec.name,
            prerequisite_kind=spec.prerequisite_kind,
            invariant_kind=spec.primary_invariant,
            parameters={
                "slot_id": "object",
                "before_form": "un caffe",
                "after_form": "un biglietto",
            },
        ),
    )


class FakeCatalogue:
    def __init__(self, calls: list[str], *, available: bool = True) -> None:
        self.calls = calls
        self.available = available

    async def require_published_grammar_target(
        self, grammar_target_revision_id: UUID, language_pack_revision_id: UUID
    ) -> None:
        self.calls.append("catalogue")
        if not self.available:
            raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)


class FakeLexicon:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def require_owned_snapshot(
        self, actor_id: UUID, profile_id: UUID, snapshot_id: UUID
    ) -> None:
        self.calls.append("lexicon")


class FakeExercises:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.instances = ()

    async def get_published_definition(self, definition_revision_id: UUID) -> ExerciseDefinition:
        self.calls.append("exercise-read")
        return definition()

    async def persist_gym_instances(
        self, actor_id: UUID, profile_id: UUID, instances: tuple
    ) -> None:
        self.calls.append("exercise-write")
        self.instances = instances


class FakePlans:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.plan = None

    async def add(
        self, actor_id: UUID, plan, *, provenance_id: UUID, created_at: datetime
    ) -> None:
        self.calls.append("gym-write")
        self.plan = plan


def command():
    from polyglot.modules.exercises.gym.application import PrepareGymPlan

    return PrepareGymPlan(
        actor_id=uid(9),
        plan_id=uid(10),
        revision_id=uid(11),
        profile_id=uid(12),
        grammar_target_revision_id=uid(13),
        policy_revision_id=uid(14),
        language_pack_revision_id=uid(15),
        lexical_support_snapshot_id=uid(16),
        definition_revision_id=uid(2),
        provenance_id=uid(17),
        seed=42,
        candidates=(candidate(),),
        grants=(PrerequisiteGrant.acquired("it:frame:vorrei"),),
        invariants=("polite_request",),
        exit_evidence_spec="g1_complete",
        created_at=NOW,
    )


async def test_application_resolves_ports_before_persisting_the_plan() -> None:
    from polyglot.modules.exercises.gym.application import GymPlanningService

    calls: list[str] = []
    exercises = FakeExercises(calls)
    plans = FakePlans(calls)
    service = GymPlanningService(
        catalogue=FakeCatalogue(calls),
        lexicon=FakeLexicon(calls),
        exercises=exercises,
        plans=plans,
    )

    plan = await service.prepare(command())

    assert calls == ["catalogue", "lexicon", "exercise-read", "exercise-write", "gym-write"]
    assert plans.plan == plan
    assert exercises.instances == tuple(step.instance for step in plan.steps)


async def test_missing_catalogue_reference_blocks_all_writes() -> None:
    from polyglot.modules.exercises.gym.application import GymPlanningService

    calls: list[str] = []
    exercises = FakeExercises(calls)
    plans = FakePlans(calls)
    service = GymPlanningService(
        catalogue=FakeCatalogue(calls, available=False),
        lexicon=FakeLexicon(calls),
        exercises=exercises,
        plans=plans,
    )

    with pytest.raises(DomainError) as rejected:
        await service.prepare(command())

    assert rejected.value.code is ErrorCode.REFERENCE_NOT_FOUND
    assert calls == ["catalogue"]
    assert plans.plan is None
