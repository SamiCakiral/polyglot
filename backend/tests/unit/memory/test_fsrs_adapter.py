from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from polyglot.modules.lexicon.memory.policy import (
    HintLevel,
    ReviewVerdict,
    SchedulerPolicy,
    allowed_ratings,
)
from polyglot.modules.lexicon.memory.ports import MemoryRating, MemoryState
from polyglot.modules.lexicon.memory.providers.fsrs_v6 import FsrsV6Scheduler
from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 1, 5, 9, tzinfo=UTC)


def test_adapter_exposes_only_the_pinned_scheduler_identity() -> None:
    scheduler = FsrsV6Scheduler()

    assert scheduler.identity.kind == "fsrs"
    assert scheduler.identity.version == "6.3.1"
    assert scheduler.identity.parameter_set_id == SchedulerPolicy.default().parameter_set_id


def test_adapter_matches_the_spike_golden_history() -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default(fuzz_seed=4_242)
    state = scheduler.initial_state(policy, NOW)
    assert state.state is MemoryState.NEW

    for index, (rating, at) in enumerate(
        (
            (MemoryRating.AGAIN, NOW),
            (MemoryRating.GOOD, NOW + timedelta(minutes=10)),
            (MemoryRating.GOOD, NOW + timedelta(days=1)),
            (MemoryRating.EASY, NOW + timedelta(days=8)),
        )
    ):
        state = scheduler.review(
            state,
            rating,
            at,
            policy.with_fuzz_seed(4_242 + index),
        ).after

    assert state.state is MemoryState.REVIEW
    assert state.due_at == datetime(2026, 1, 20, 9, tzinfo=UTC)
    assert state.difficulty == Decimal("5.170190465277389")
    assert state.stability == Decimal("7.48411760536693")
    assert state.reps == 4


@pytest.mark.parametrize(
    ("verdict", "hint", "expected"),
    [
        (ReviewVerdict.INCORRECT, HintLevel.H0, (MemoryRating.AGAIN,)),
        (ReviewVerdict.CORRECT, HintLevel.H4, (MemoryRating.AGAIN, MemoryRating.HARD)),
        (ReviewVerdict.CORRECT, HintLevel.H3, (MemoryRating.AGAIN, MemoryRating.HARD)),
        (ReviewVerdict.CORRECT, HintLevel.H2, (MemoryRating.HARD, MemoryRating.GOOD)),
        (ReviewVerdict.CORRECT, HintLevel.H1, (MemoryRating.HARD, MemoryRating.GOOD)),
        (
            ReviewVerdict.CORRECT,
            HintLevel.H0,
            (MemoryRating.HARD, MemoryRating.GOOD, MemoryRating.EASY),
        ),
        (ReviewVerdict.AMBIGUOUS, HintLevel.H0, ()),
        (ReviewVerdict.NOT_EVALUABLE, HintLevel.H0, ()),
    ],
)
def test_rating_ceiling_is_bounded_by_verdict_and_hint(
    verdict: ReviewVerdict,
    hint: HintLevel,
    expected: tuple[MemoryRating, ...],
) -> None:
    assert allowed_ratings(verdict, hint) == expected


def test_after_24h_policy_never_advances_a_due_below_one_day() -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default(after_24h=True)
    initial = scheduler.initial_state(policy, NOW)

    state = scheduler.review(initial, MemoryRating.AGAIN, NOW, policy).after

    assert state.due_at >= NOW + timedelta(hours=24)


def test_timezone_input_is_normalized_to_utc_without_rewriting_history() -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default(timezone_name="Europe/Rome")
    rome_now = datetime(2026, 3, 29, 9, tzinfo=ZoneInfo("Europe/Rome"))

    state = scheduler.review(
        scheduler.initial_state(policy, rome_now),
        MemoryRating.GOOD,
        rome_now,
        policy,
    ).after

    assert state.last_review_at == datetime(2026, 3, 29, 7, tzinfo=UTC)
    assert state.due_at is not None and state.due_at.tzinfo is UTC


def test_provider_failure_is_visible_and_does_not_return_a_transition() -> None:
    def unavailable(_: SchedulerPolicy) -> object:
        raise RuntimeError("provider unavailable")

    scheduler = FsrsV6Scheduler(scheduler_factory=unavailable)
    policy = SchedulerPolicy.default()
    before = scheduler.initial_state(policy, NOW)

    with pytest.raises(DomainError) as error:
        scheduler.review(before, MemoryRating.GOOD, NOW, policy)

    assert error.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    assert before.state is MemoryState.NEW
    assert before.reps == 0


def test_provider_retrievability_outside_probability_bounds_fails_closed() -> None:
    class InvalidRetrievabilityScheduler:
        def get_card_retrievability(self, card: object, current_datetime: datetime) -> float:
            return 1.5

    scheduler = FsrsV6Scheduler(scheduler_factory=lambda _: InvalidRetrievabilityScheduler())
    policy = SchedulerPolicy.default()
    valid_scheduler = FsrsV6Scheduler()
    state = valid_scheduler.initial_state(policy, NOW)
    state = valid_scheduler.review(state, MemoryRating.GOOD, NOW, policy).after
    state = valid_scheduler.review(
        state,
        MemoryRating.GOOD,
        NOW + timedelta(minutes=10),
        policy,
    ).after
    before = state

    with pytest.raises(DomainError) as error:
        scheduler.retrievability(state, NOW + timedelta(days=1), policy)

    assert error.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    assert state == before
