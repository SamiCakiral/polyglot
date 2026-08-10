from datetime import timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from polyglot.modules.lexicon.memory.application import MemoryLifecycle
from polyglot.modules.lexicon.memory.policy import SchedulerPolicy
from polyglot.modules.lexicon.memory.ports import MemoryRating
from polyglot.modules.lexicon.memory.providers.fsrs_v6 import FsrsV6Scheduler
from polyglot.modules.lexicon.memory.rebuild import rebuild_schedule

from .test_prompt_properties import NOW, create, resolver, review


@settings(max_examples=100, deadline=None)
@given(st.lists(st.sampled_from(tuple(MemoryRating)), min_size=1, max_size=12))
def test_replay_x100_is_identical_for_same_order_and_versions(
    ratings: list[MemoryRating],
) -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    lifecycle = MemoryLifecycle(scheduler)
    aggregate = lifecycle.create(create(700, "target_to_support"), policy)
    for index, rating in enumerate(ratings):
        aggregate = lifecycle.submit_review(
            aggregate,
            review(index + 700, rating, NOW + timedelta(days=index)),
            policy,
        ).aggregate

    results = tuple(rebuild_schedule(aggregate, resolver(policy)) for _ in range(100))
    assert all(result == results[0] for result in results)
    assert results[0].due_at == aggregate.schedule.due_at
    assert results[0].scheduler_version == scheduler.identity.version
