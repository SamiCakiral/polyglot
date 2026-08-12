from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.language_profiles.onboarding import EntryPath
from polyglot.modules.placement.domain import PlacementObservation, ScoringKind
from polyglot.modules.placement.policy import PlacementPolicyV1


@given(level=st.integers(0, 8), score=st.floats(0, 1, allow_nan=False))
def test_estimate_bounds_remain_ordered_and_bounded(level: int, score: float) -> None:
    policy = PlacementPolicyV1()
    state = policy.initial_state(EntryPath.ALREADY_STARTED, ("reading",))
    observation = PlacementObservation(
        item_instance_id=UUID(f"0194f7c0-7b00-7000-8000-{level + 1:012d}"),
        variant_pool_id=f"pool-{level}",
        primitive_ref="multiple_choice",
        skill_ref="reading",
        level=level,
        score=score,
        confidence=0.8,
        elapsed_seconds=20,
        scoring_kind=ScoringKind.DETERMINISTIC,
        evaluable=True,
    )

    estimate = policy.update(state, observation).estimate_for("reading")

    assert estimate.lower_bound is not None
    assert estimate.upper_bound is not None
    assert 0 <= estimate.lower_bound <= estimate.upper_bound <= 8
