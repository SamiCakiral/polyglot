from dataclasses import replace

import pytest

from polyglot.modules.exercises.core.domain import HintLevel
from polyglot.modules.exercises.gym.correction import TargetRole, correct_transformation
from polyglot.modules.exercises.gym.cycle import GymStage
from polyglot.platform.errors import DomainError, ErrorCode

from .test_g0_g4 import _case, _grants


def _scoped_case():
    return replace(
        _case(),
        secondary_target_ids=("it:grammar:request-function",),
        distractor_target_ids=("it:distractor:voglio",),
    )


def _correct(roles: dict[str, TargetRole]):
    return correct_transformation(
        case=_scoped_case(),
        proposed_output="Vorrei un biglietto",
        grants=_grants(),
        stage=GymStage.G1,
        hint_level=HintLevel.H0,
        target_roles=roles,
    )


@pytest.mark.parametrize(
    "unknown_role",
    (TargetRole.PRINCIPAL, TargetRole.SECONDARY, TargetRole.SUPPORT, TargetRole.DISTRACTOR),
)
def test_correction_rejects_every_role_for_an_unpublished_target(
    unknown_role: TargetRole,
) -> None:
    with pytest.raises(DomainError) as rejected:
        _correct(
            {
                "it:grammar:vorrei": TargetRole.PRINCIPAL,
                "it:grammar:unrelated": unknown_role,
            }
        )

    assert rejected.value.code is ErrorCode.OBSERVATION_TARGET_NOT_DISCRIMINANT


def test_grammar_target_must_keep_its_published_principal_role() -> None:
    with pytest.raises(DomainError) as rejected:
        _correct({"it:grammar:vorrei": TargetRole.SECONDARY})

    assert rejected.value.code is ErrorCode.EVIDENCE_SCOPE_FORBIDDEN


def test_only_published_secondary_support_and_distractor_targets_are_accepted() -> None:
    report = _correct(
        {
            "it:grammar:vorrei": TargetRole.PRINCIPAL,
            "it:grammar:request-function": TargetRole.SECONDARY,
            "it:lexicon:biglietto": TargetRole.SUPPORT,
            "it:distractor:voglio": TargetRole.DISTRACTOR,
        }
    )

    assert report.credit_for("it:grammar:vorrei") == 0.65
    assert report.credit_for("it:grammar:request-function") == 0.65
    assert report.credit_for("it:lexicon:biglietto") == 0.0
    assert report.credit_for("it:distractor:voglio") == 0.0
