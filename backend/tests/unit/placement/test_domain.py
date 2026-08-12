from uuid import UUID

import pytest

from polyglot.modules.placement.domain import (
    ObservationStatus,
    PlacementCandidate,
    PlacementObservation,
    ScoringKind,
    SkillEstimate,
)
from polyglot.platform.errors import DomainError

UUID7_A = UUID("0194f7c0-7b00-7000-8000-000000000001")


def test_unobserved_skill_has_no_invented_level() -> None:
    estimate = SkillEstimate.unobserved("listening")

    assert estimate.status is ObservationStatus.NOT_OBSERVED
    assert estimate.probable_level is None
    assert estimate.confidence == 0


def test_observed_bounds_must_be_ordered() -> None:
    with pytest.raises(DomainError):
        SkillEstimate.observed("reading", lower=5, probable=3, upper=4, confidence=0.8)


def test_candidate_rejects_levels_outside_internal_scale() -> None:
    with pytest.raises(DomainError):
        PlacementCandidate(
            variant_revision_id=UUID7_A,
            variant_pool_id="reading-short",
            primitive_ref="multiple_choice",
            primary_skill_ref="reading",
            level=9,
            estimated_seconds=30,
            scoring_kind=ScoringKind.DETERMINISTIC,
        )


def test_observation_requires_an_evaluable_score() -> None:
    with pytest.raises(DomainError):
        PlacementObservation(
            item_instance_id=UUID7_A,
            variant_pool_id="reading-short",
            primitive_ref="multiple_choice",
            skill_ref="reading",
            level=2,
            score=None,
            confidence=0.9,
            elapsed_seconds=20,
            scoring_kind=ScoringKind.DETERMINISTIC,
            evaluable=True,
        )
