from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hypothesis import given, strategies as st

from polyglot.modules.lexicon.memory.policy import SchedulerPolicy
from polyglot.modules.lexicon.memory.ports import MemoryRating
from polyglot.modules.lexicon.memory.providers.fsrs_v6 import FsrsV6Scheduler


START = datetime(2026, 1, 5, 9, tzinfo=timezone.utc)


@given(
    st.lists(st.sampled_from(tuple(MemoryRating)), min_size=1, max_size=20),
    st.integers(min_value=0, max_value=2**31 - 1),
)
def test_same_inputs_produce_exactly_the_same_schedule(
    ratings: list[MemoryRating],
    fuzz_seed: int,
) -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default(fuzz_seed=fuzz_seed)

    def replay() -> object:
        state = scheduler.initial_state(policy, START)
        for index, rating in enumerate(ratings):
            state = scheduler.review(
                state,
                rating,
                START + timedelta(days=index, minutes=index),
                policy.with_fuzz_seed(fuzz_seed + index),
            ).after
        return state

    assert replay() == replay()


@given(st.decimals(min_value="0.80", max_value="0.97", places=2))
def test_scheduler_outputs_remain_in_documented_bounds(retention: Decimal) -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default(desired_retention=retention)
    state = scheduler.initial_state(policy, START)

    for index, rating in enumerate(MemoryRating):
        state = scheduler.review(
            state,
            rating,
            START + timedelta(days=index),
            policy,
        ).after
        assert state.difficulty is None or Decimal("1") <= state.difficulty <= Decimal("10")
        assert state.stability is None or state.stability > 0
        assert Decimal("0") <= scheduler.retrievability(state, state.last_review_at, policy) <= 1
