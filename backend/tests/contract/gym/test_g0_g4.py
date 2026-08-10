import socket
from pathlib import Path

import pytest

from polyglot.modules.exercises.core.domain import CorrectionVerdict, HintLevel
from polyglot.modules.exercises.gym.cycle import GymStage
from polyglot.modules.exercises.gym.domain import PrerequisiteGrant, TransformationCase

FIXTURE = Path(__file__).resolve().parents[4] / "fixtures/canonical/FX-GYM-IT"


def _case() -> TransformationCase:
    from polyglot.modules.exercises.gym.domain import OperationSemantics, operation_spec

    spec = operation_spec("GYM-01")
    return TransformationCase.published(
        case_id="it:vorrei:substitution",
        revision_id="it:vorrei:substitution:v1",
        operation_id="GYM-01",
        source_text="Vorrei un caffe",
        edits=(("un caffe", "un biglietto"),),
        accepted_outputs=("Vorrei un biglietto",),
        rejected_outputs=("Voglio un biglietto",),
        required_prerequisites=("it:frame:vorrei", "it:lexicon:biglietto"),
        invariants=("polite_request",),
        grammar_target_id="it:grammar:vorrei",
        lexical_support_ids=("it:lexicon:biglietto",),
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


def _grants() -> tuple[PrerequisiteGrant, ...]:
    return (
        PrerequisiteGrant.acquired("it:frame:vorrei"),
        PrerequisiteGrant.support("it:lexicon:biglietto"),
    )


def test_controlled_correction_credits_grammar_but_never_lexical_support() -> None:
    from polyglot.modules.exercises.gym.correction import TargetRole, correct_transformation

    result = correct_transformation(
        case=_case(),
        proposed_output="Vorrei un biglietto",
        grants=_grants(),
        stage=GymStage.G1,
        hint_level=HintLevel.H0,
        target_roles={
            "it:grammar:vorrei": TargetRole.PRINCIPAL,
            "it:lexicon:biglietto": TargetRole.SUPPORT,
        },
    )

    assert result.verdict is CorrectionVerdict.CORRECT
    assert result.credit_for("it:grammar:vorrei") == 0.65
    assert result.credit_for("it:lexicon:biglietto") == 0.0


def test_g0_h4_ambiguity_and_unavailability_never_create_credit() -> None:
    from polyglot.modules.exercises.gym.correction import TargetRole, correct_transformation

    roles = {
        "it:grammar:vorrei": TargetRole.PRINCIPAL,
        "it:lexicon:biglietto": TargetRole.SUPPORT,
    }
    g0 = correct_transformation(
        case=_case(),
        proposed_output="Vorrei un biglietto",
        grants=_grants(),
        stage=GymStage.G0,
        hint_level=HintLevel.H0,
        target_roles=roles,
    )
    revealed = correct_transformation(
        case=_case(),
        proposed_output="Vorrei un biglietto",
        grants=_grants(),
        stage=GymStage.G1,
        hint_level=HintLevel.H4,
        target_roles=roles,
    )
    ambiguous = correct_transformation(
        case=_case(),
        proposed_output="Vorrei un biglietto",
        grants=_grants(),
        stage=GymStage.G1,
        hint_level=HintLevel.H0,
        target_roles=roles,
        ambiguous=True,
    )
    unavailable = correct_transformation(
        case=_case(),
        proposed_output="Vorrei un biglietto",
        grants=_grants(),
        stage=GymStage.G1,
        hint_level=HintLevel.H0,
        target_roles=roles,
        correction_available=False,
    )

    assert g0.total_credit == 0.0
    assert revealed.total_credit == 0.0
    assert ambiguous.verdict is CorrectionVerdict.AMBIGUOUS
    assert ambiguous.total_credit == 0.0
    assert unavailable.verdict is CorrectionVerdict.NOT_EVALUABLE
    assert unavailable.total_credit == 0.0


def test_incorrect_controlled_output_is_negative_only_for_evaluable_targets() -> None:
    from polyglot.modules.exercises.gym.correction import TargetRole, correct_transformation

    result = correct_transformation(
        case=_case(),
        proposed_output="Voglio un biglietto",
        grants=_grants(),
        stage=GymStage.G1,
        hint_level=HintLevel.H0,
        target_roles={
            "it:grammar:vorrei": TargetRole.PRINCIPAL,
            "it:lexicon:biglietto": TargetRole.SUPPORT,
        },
    )

    assert result.verdict is CorrectionVerdict.INCORRECT
    assert result.credit_for("it:grammar:vorrei") == -0.65
    assert result.credit_for("it:lexicon:biglietto") == 0.0


def test_fx_gym_it_executes_all_operations_and_cycle_oracles_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from polyglot.modules.exercises.gym.fixtures import validate_gym_fixture

    def deny_network(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"network access attempted: {args!r} {kwargs!r}")

    monkeypatch.setattr(socket, "socket", deny_network)
    report = validate_gym_fixture(FIXTURE)

    assert report.operation_ids == tuple(f"GYM-{index:02d}" for index in range(1, 16))
    assert report.executed_positive == report.operation_ids
    assert report.executed_negative == report.operation_ids
    assert report.executed_missing_prerequisite == report.operation_ids
    assert report.executed_semantic_negative == report.operation_ids
    assert report.executed_semantic_constraints == report.operation_ids
    assert report.cycle_stages == ("g0", "g1", "g2", "g3", "g4")
    assert report.cycle_credits == (0.0, 0.65, 0.65, 0.65, 0.65, 0.55, 0.65, 1.0)
    assert report.completed_g1_requirement_ids == (
        "g1:guided",
        "g1:transform:substitution",
        "g1:transform:person",
        "g1:transform:negation",
    )
    assert report.network_dependencies == ()
    assert {
        "sono_ecco",
        "vorrei",
        "ce_ci_sono",
        "puo_posso",
        "andare_infinitive_calque",
        "j_plus_one",
        "transfer",
        "missing_prerequisite",
    }.issubset(report.scenarios)
