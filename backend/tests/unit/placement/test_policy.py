from dataclasses import replace
from uuid import UUID

from polyglot.modules.language_profiles.onboarding import EntryPath
from polyglot.modules.placement.domain import (
    PlacementCandidate,
    PlacementObservation,
    PlacementStatus,
    ScoringKind,
)
from polyglot.modules.placement.policy import PlacementPolicyV1


def _uuid7(suffix: int) -> UUID:
    return UUID(f"0194f7c0-7b00-7000-8000-{suffix:012d}")


def _observation(*, score: float, level: int = 3, independent: bool = True) -> PlacementObservation:
    return PlacementObservation(
        item_instance_id=_uuid7(level + int(score * 10) + 10),
        variant_pool_id=f"reading-{level}-{score}",
        primitive_ref="multiple_choice",
        skill_ref="reading",
        level=level,
        score=score,
        confidence=0.9,
        elapsed_seconds=30,
        scoring_kind=ScoringKind.DETERMINISTIC,
        evaluable=True,
        independent=independent,
    )


def _candidate(suffix: int, *, seconds: int = 30, level: int = 3) -> PlacementCandidate:
    return PlacementCandidate(
        variant_revision_id=_uuid7(suffix),
        variant_pool_id=f"pool-{suffix}",
        primitive_ref="multiple_choice",
        primary_skill_ref="reading",
        level=level,
        estimated_seconds=seconds,
        scoring_kind=ScoringKind.DETERMINISTIC,
    )


def test_beginner_prior_starts_at_level_one() -> None:
    state = PlacementPolicyV1().initial_state(EntryPath.COMPLETE_BEGINNER, ("reading",))
    assert state.estimate_for("reading").probable_level == 1
    assert state.estimate_for("reading").status.value == "prior_only"


def test_advanced_prior_starts_at_level_six() -> None:
    state = PlacementPolicyV1().initial_state(EntryPath.ADVANCED, ("reading",))
    assert state.estimate_for("reading").probable_level == 6


def test_strong_success_raises_lower_bound_only() -> None:
    policy = PlacementPolicyV1()
    state = policy.initial_state(EntryPath.ALREADY_STARTED, ("reading",))
    updated = policy.update(state, _observation(score=1.0, level=4))
    estimate = updated.estimate_for("reading")
    assert estimate.lower_bound == 4
    assert estimate.upper_bound == 8


def test_open_response_cannot_close_bound_without_corroboration() -> None:
    policy = PlacementPolicyV1()
    state = policy.initial_state(EntryPath.ALREADY_STARTED, ("reading",))
    observation = replace(
        _observation(score=1.0, level=5),
        scoring_kind=ScoringKind.STRUCTURED_LM,
    )
    updated = policy.update(state, observation)
    assert updated.estimate_for("reading").upper_bound == 8


def test_twenty_minutes_forces_partial_completion() -> None:
    policy = PlacementPolicyV1()
    state = policy.initial_state(EntryPath.ALREADY_STARTED, ("reading",))
    decision = policy.should_stop(state, elapsed_seconds=1200)
    assert decision.should_stop
    assert decision.status is PlacementStatus.PARTIAL


def test_two_provider_failures_stop_without_penalising_the_learner() -> None:
    policy = PlacementPolicyV1()
    state = policy.initial_state(EntryPath.ALREADY_STARTED, ("reading", "writing"))
    decision = policy.should_stop(
        state,
        elapsed_seconds=90,
        provider_failure_count=2,
    )
    assert decision.should_stop
    assert decision.status is PlacementStatus.PARTIAL
    assert decision.reason == "provider_unavailable"


def test_confirmed_beginner_can_stop_before_eight_minutes() -> None:
    policy = PlacementPolicyV1()
    state = policy.initial_state(EntryPath.COMPLETE_BEGINNER, ("reading", "listening"))
    for index, skill in enumerate(("reading", "listening"), start=1):
        for level in (0, 1):
            state = policy.update(
                state,
                PlacementObservation(
                    item_instance_id=_uuid7(100 + index * 10 + level),
                    variant_pool_id=f"{skill}-{level}",
                    primitive_ref="multiple_choice",
                    skill_ref=skill,
                    level=level,
                    score=0.0,
                    confidence=1.0,
                    elapsed_seconds=30,
                    scoring_kind=ScoringKind.DETERMINISTIC,
                    evaluable=True,
                    independent=True,
                ),
            )
    assert policy.should_stop(state, elapsed_seconds=240).should_stop


def test_same_seed_and_history_select_same_candidate() -> None:
    policy = PlacementPolicyV1()
    state = policy.initial_state(EntryPath.ALREADY_STARTED, ("reading",))
    candidates = (_candidate(1), _candidate(2))
    first = policy.select(state, candidates, seconds_remaining=60, seed="stable")
    second = policy.select(state, candidates, seconds_remaining=60, seed="stable")
    assert first.candidate == second.candidate
