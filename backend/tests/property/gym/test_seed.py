from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.exercises.core.domain import AnswerKind, ExerciseDefinition
from polyglot.modules.exercises.gym.domain import PrerequisiteGrant, TransformationCase
from polyglot.platform.errors import DomainError, ErrorCode


def _definition() -> ExerciseDefinition:
    return ExerciseDefinition.published(
        definition_id=UUID("019fe010-0000-7000-8000-000000000001"),
        revision_id=UUID("019fe010-0000-7000-8000-000000000002"),
        revision_no=1,
        primitive_id="EX-TRANSFORM-01",
        response_kinds=(AnswerKind.TEXT,),
        language_certification_ids=(UUID("019fe010-0000-7000-8000-000000000003"),),
        modes=("gym",),
        target_weights=(("grammar:target", 0.65),),
        correction_policy_id="policy:gym:v1",
        hint_policy_id="policy:hints:v1",
        observation_policy_id="policy:observations:v1",
        accessibility_features=("keyboard", "screen_reader", "untimed"),
    )


def _case(index: int, operation_id: str) -> TransformationCase:
    from polyglot.modules.exercises.gym.domain import OperationSemantics, operation_spec

    values = {
        "GYM-01": (
            "Vorrei un caffe",
            ("un caffe", "un biglietto"),
            "Vorrei un biglietto",
            {"slot_id": "object", "before_form": "un caffe", "after_form": "un biglietto"},
        ),
        "GYM-04": (
            "Ho fame",
            ("Ho", "Non ho"),
            "Non ho fame",
            {"marker": "Non", "before_form": "Ho", "after_form": "Non ho"},
        ),
        "GYM-08": (
            "Posso entrare?",
            ("Posso", "Puo"),
            "Puo entrare?",
            {
                "from_register": "informal",
                "to_register": "formal",
                "before_form": "Posso",
                "after_form": "Puo",
            },
        ),
        "GYM-12": (
            "Vorrei un biglietto",
            ("un biglietto", "un biglietto per Roma"),
            "Vorrei un biglietto per Roma",
            {
                "direction": "expansion",
                "before_form": "un biglietto",
                "after_form": "un biglietto per Roma",
            },
        ),
    }
    source, edit, output, parameters = values[operation_id]
    spec = operation_spec(operation_id)
    return TransformationCase.published(
        case_id=f"case:{index}",
        revision_id=f"revision:case:{index}:v1",
        operation_id=operation_id,
        source_text=source,
        edits=(edit,),
        accepted_outputs=(output,),
        rejected_outputs=(f"wrong {index}",),
        required_prerequisites=(f"prerequisite:{index}",),
        invariants=("intention",),
        grammar_target_id="grammar:target",
        lexical_support_ids=(f"lexicon:{index}",),
        semantics=OperationSemantics.create(
            kind=spec.name,
            prerequisite_kind=spec.prerequisite_kind,
            invariant_kind=spec.primary_invariant,
            parameters=parameters,
        ),
    )


def _inputs():
    cases = [_case(1, "GYM-01"), _case(2, "GYM-04"), _case(3, "GYM-08")]
    grants = [PrerequisiteGrant.acquired(f"prerequisite:{index}") for index in range(1, 4)]
    return cases, grants


def _compose(seed: int, cases=None, grants=None):
    from polyglot.modules.exercises.gym.planning import compose_gym_plan

    default_cases, default_grants = _inputs()
    return compose_gym_plan(
        plan_id=UUID("019fe010-0000-7000-8000-000000000010"),
        revision_id=UUID("019fe010-0000-7000-8000-000000000011"),
        profile_id=UUID("019fe010-0000-7000-8000-000000000012"),
        grammar_target_revision_id=UUID("019fe010-0000-7000-8000-000000000013"),
        policy_revision_id=UUID("019fe010-0000-7000-8000-000000000014"),
        language_pack_revision_id=UUID("019fe010-0000-7000-8000-000000000015"),
        lexical_support_snapshot_id=UUID("019fe010-0000-7000-8000-000000000016"),
        seed=seed,
        definition=_definition(),
        candidates=default_cases if cases is None else cases,
        grants=default_grants if grants is None else grants,
        invariants=("communicative_intention",),
        exit_evidence_spec="guided_transformations_complete",
    )


@given(st.integers(min_value=0, max_value=2**31 - 1))
def test_same_inputs_and_seed_always_produce_the_same_pinned_plan(seed: int) -> None:
    first = _compose(seed)
    second = _compose(seed)

    assert first == second
    assert tuple(step.ordinal for step in first.steps) == (1, 2, 3)
    assert len({step.case_id for step in first.steps}) == 3
    assert all(step.instance.seed == step.instance_seed for step in first.steps)
    assert all(step.instance.definition.primitive_id == "EX-TRANSFORM-01" for step in first.steps)


@given(st.integers(min_value=0, max_value=2**31 - 2))
def test_seed_controls_order_and_instance_seeds_without_global_randomness(seed: int) -> None:
    first = _compose(seed)
    changed = _compose(seed + 1)

    assert first.seed == seed
    assert changed.seed == seed + 1
    assert tuple(step.instance_seed for step in first.steps) != tuple(
        step.instance_seed for step in changed.steps
    )


def test_plan_and_steps_are_deeply_immutable_from_caller_collections() -> None:
    cases, grants = _inputs()
    plan = _compose(101, cases=cases, grants=grants)
    expected_case_ids = tuple(step.case_id for step in plan.steps)

    cases.clear()
    grants.clear()

    assert tuple(step.case_id for step in plan.steps) == expected_case_ids
    assert len(plan.steps) == 3
    with pytest.raises(AttributeError):
        plan.steps.append("corrupted")  # type: ignore[attr-defined]


def test_missing_prerequisite_rejects_the_plan_before_any_instance_exists() -> None:
    cases, grants = _inputs()

    with pytest.raises(DomainError) as rejected:
        _compose(101, cases=cases, grants=grants[:-1])

    assert rejected.value.code is ErrorCode.PREREQUISITE_MISSING
    assert rejected.value.details == {"missing": ["prerequisite:3"]}


def test_composition_rejects_duplicates_and_more_than_three_transformations() -> None:
    cases, grants = _inputs()
    with pytest.raises(DomainError) as duplicate:
        _compose(101, cases=[cases[0], cases[0]], grants=grants)
    with pytest.raises(DomainError) as too_many:
        _compose(
            101,
            cases=[*cases, _case(4, "GYM-12")],
            grants=[*grants, PrerequisiteGrant.acquired("prerequisite:4")],
        )

    assert duplicate.value.code is ErrorCode.DUPLICATE_CANDIDATE
    assert too_many.value.code is ErrorCode.VALIDATION_FAILED
