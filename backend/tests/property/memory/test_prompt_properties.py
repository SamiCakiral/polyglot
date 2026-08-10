from datetime import UTC, datetime, timedelta
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.lexicon.memory.application import (
    CreateMemoryPrompt,
    MemoryLifecycle,
    ResetMemoryPrompt,
    SubmitMemoryReview,
)
from polyglot.modules.lexicon.memory.policy import HintLevel, ReviewVerdict, SchedulerPolicy
from polyglot.modules.lexicon.memory.ports import MemoryRating, MemoryState
from polyglot.modules.lexicon.memory.providers.fsrs_v6 import FsrsV6Scheduler
from polyglot.modules.lexicon.memory.rebuild import rebuild_schedule


NOW = datetime(2026, 1, 5, 9, tzinfo=UTC)


def uid(value: int) -> UUID:
    return UUID(f"018f0000-0000-7000-8000-{value:012x}")


def create(prompt_id: int, direction: str) -> CreateMemoryPrompt:
    return CreateMemoryPrompt(
        prompt_id=uid(prompt_id),
        profile_id=uid(2),
        target_ref=uid(3),
        target_revision_id=uid(4),
        direction=direction,
        modality="written",
        operation="recall",
        protocol_id="certified-recall-v1",
        protocol_revision=1,
        rating_semantics_id="polyglot-recall-v1",
        scheduler_policy_id=uid(5),
        created_at=NOW,
    )


def review(index: int, rating: MemoryRating, at: datetime) -> SubmitMemoryReview:
    return SubmitMemoryReview(
        review_id=uid(100 + index),
        opportunity_id=uid(200 + index),
        attempt_id=None,
        response_ref=None,
        correction_ref=None,
        verdict=(
            ReviewVerdict.INCORRECT if rating is MemoryRating.AGAIN else ReviewVerdict.CORRECT
        ),
        highest_hint=HintLevel.H0,
        rating=rating,
        certified_recall=True,
        answer_revealed=False,
        exposure_only=False,
        incidental_production=False,
        self_reported=True,
        active_duration_ms=1_000,
        scheduled_at=at,
        reviewed_at=at,
        idempotency_key=f"property-{index}",
    )


@given(st.lists(st.sampled_from(tuple(MemoryRating)), min_size=1, max_size=12))
def test_causal_rebuild_is_stable_for_every_rating_history(
    ratings: list[MemoryRating],
) -> None:
    scheduler = FsrsV6Scheduler()
    lifecycle = MemoryLifecycle(scheduler)
    policy = SchedulerPolicy.default()
    aggregate = lifecycle.create(create(1, "target_to_support"), policy)

    for index, rating in enumerate(ratings):
        at = NOW + timedelta(days=index, minutes=index)
        aggregate = lifecycle.submit_review(aggregate, review(index, rating, at), policy).aggregate

    assert rebuild_schedule(aggregate, scheduler, policy) == aggregate.schedule
    assert rebuild_schedule(aggregate, scheduler, policy) == rebuild_schedule(
        aggregate,
        scheduler,
        policy,
    )


@given(st.lists(st.sampled_from(tuple(MemoryRating)), min_size=1, max_size=8))
def test_directions_remain_strictly_independent(ratings: list[MemoryRating]) -> None:
    scheduler = FsrsV6Scheduler()
    lifecycle = MemoryLifecycle(scheduler)
    policy = SchedulerPolicy.default()
    forward = lifecycle.create(create(11, "target_to_support"), policy)
    reverse = lifecycle.create(create(12, "support_to_target"), policy)
    reverse_before = reverse

    for index, rating in enumerate(ratings):
        forward = lifecycle.submit_review(
            forward,
            review(index, rating, NOW + timedelta(days=index)),
            policy,
        ).aggregate

    assert reverse == reverse_before
    assert forward.prompt.direction != reverse.prompt.direction


@given(st.lists(st.sampled_from(tuple(MemoryRating)), min_size=1, max_size=8))
def test_reset_keeps_facts_but_restarts_only_the_projection(ratings: list[MemoryRating]) -> None:
    scheduler = FsrsV6Scheduler()
    lifecycle = MemoryLifecycle(scheduler)
    policy = SchedulerPolicy.default()
    aggregate = lifecycle.create(create(21, "target_to_support"), policy)

    for index, rating in enumerate(ratings):
        aggregate = lifecycle.submit_review(
            aggregate,
            review(index, rating, NOW + timedelta(days=index)),
            policy,
        ).aggregate
    reset = lifecycle.reset(
        aggregate,
        ResetMemoryPrompt(uid(999), "property reset", NOW + timedelta(days=20)),
        policy,
    )

    assert len(reset.reviews) == len(ratings)
    assert reset.schedule.state is MemoryState.NEW
    assert reset.schedule.reps == 0
    assert rebuild_schedule(reset, scheduler, policy) == reset.schedule
