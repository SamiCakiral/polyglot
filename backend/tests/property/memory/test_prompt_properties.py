from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.lexicon.memory.application import (
    CreateMemoryPrompt,
    DeleteMemoryPrompt,
    MemoryLifecycle,
    MergeMemoryPrompts,
    ResetMemoryPrompt,
    ResumeMemoryPrompt,
    SubmitMemoryReview,
)
from polyglot.modules.lexicon.memory.domain import PromptStatus
from polyglot.modules.lexicon.memory.policy import HintLevel, ReviewVerdict, SchedulerPolicy
from polyglot.modules.lexicon.memory.ports import MemoryRating, MemoryState
from polyglot.modules.lexicon.memory.providers.fsrs_v6 import FsrsV6Scheduler
from polyglot.modules.lexicon.memory.rebuild import (
    MemoryReplayBinding,
    StaticMemoryReplayResolver,
    rebuild_schedule,
)
from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 1, 5, 9, tzinfo=UTC)


def uid(value: int) -> UUID:
    return UUID(f"018f0000-0000-7000-8000-{value:012x}")


def create(
    prompt_id: int,
    direction: str,
    protocol_id: str = "certified-recall-v1",
) -> CreateMemoryPrompt:
    return CreateMemoryPrompt(
        prompt_id=uid(prompt_id),
        profile_id=uid(2),
        target_ref=uid(3),
        target_revision_id=uid(4),
        direction=direction,
        modality="written",
        operation="recall",
        protocol_id=protocol_id,
        protocol_revision=1,
        rating_semantics_id="polyglot-recall-v1",
        scheduler_policy_id=uid(5),
        created_at=NOW,
    )


def review(
    index: int,
    rating: MemoryRating,
    at: datetime,
    opportunity_id: int | None = None,
) -> SubmitMemoryReview:
    return SubmitMemoryReview(
        review_id=uid(100 + index),
        opportunity_id=uid(200 + index if opportunity_id is None else opportunity_id),
        attempt_id=None,
        response_ref=None,
        correction_ref=None,
        verdict=(
            ReviewVerdict.INCORRECT if rating is MemoryRating.AGAIN else ReviewVerdict.CORRECT
        ),
        highest_hint=HintLevel.H0,
        rating=rating,
        certified_recall=True,
        certification_ref="certification:recall-v1",
        certified_operation="recall",
        certified_protocol_id="certified-recall-v1",
        certified_protocol_revision=1,
        certified_target_revision_id=uid(4),
        answer_revealed=False,
        exposure_only=False,
        incidental_production=False,
        self_reported=True,
        active_duration_ms=1_000,
        scheduled_at=at,
        reviewed_at=at,
        idempotency_key=f"property-{index}",
    )


def resolver(*policies: SchedulerPolicy) -> StaticMemoryReplayResolver:
    scheduler = FsrsV6Scheduler()
    return StaticMemoryReplayResolver(
        tuple(MemoryReplayBinding(scheduler, policy) for policy in policies)
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

    replay = resolver(policy)
    assert rebuild_schedule(aggregate, replay) == aggregate.schedule
    assert rebuild_schedule(aggregate, replay) == rebuild_schedule(aggregate, replay)


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
    assert rebuild_schedule(reset, resolver(policy)) == reset.schedule


@given(st.integers(min_value=1, max_value=365))
def test_suspension_is_schedule_neutral(days: int) -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    lifecycle = MemoryLifecycle(scheduler)
    aggregate = lifecycle.submit_review(
        lifecycle.create(create(31, "target_to_support"), policy),
        review(31, MemoryRating.GOOD, NOW),
        policy,
    ).aggregate

    suspended = lifecycle.suspend(aggregate, NOW + timedelta(days=days))

    assert suspended.schedule == aggregate.schedule
    assert suspended.reviews == aggregate.reviews


@given(st.integers(min_value=1, max_value=365))
def test_resume_is_replay_equivalent_and_never_adds_a_review(days: int) -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    lifecycle = MemoryLifecycle(scheduler)
    aggregate = lifecycle.submit_review(
        lifecycle.create(create(41, "target_to_support"), policy),
        review(41, MemoryRating.GOOD, NOW),
        policy,
    ).aggregate
    suspended = lifecycle.suspend(aggregate, NOW + timedelta(hours=1))

    resumed = lifecycle.resume(
        suspended,
        ResumeMemoryPrompt(uid(441), NOW + timedelta(days=days)),
        policy,
    )

    assert resumed.reviews == aggregate.reviews
    assert rebuild_schedule(resumed, resolver(policy)) == resumed.schedule


@given(st.sampled_from(tuple(MemoryRating)))
def test_compatible_merge_matches_deduplicated_replay_with_reset(
    rating: MemoryRating,
) -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    replay = resolver(policy)
    lifecycle = MemoryLifecycle(scheduler, replay_resolver=replay)
    first = lifecycle.submit_review(
        lifecycle.create(create(51, "target_to_support"), policy),
        review(51, rating, NOW, opportunity_id=951),
        policy,
    ).aggregate
    first = lifecycle.reset(
        first,
        ResetMemoryPrompt(uid(551), "property merge reset", NOW + timedelta(days=2)),
        policy,
    )
    second = lifecycle.submit_review(
        lifecycle.create(create(52, "target_to_support"), policy),
        review(52, rating, NOW + timedelta(days=1), opportunity_id=951),
        policy,
    ).aggregate

    merged = lifecycle.merge(
        MergeMemoryPrompts(uid(53), (first, second), NOW + timedelta(days=3)),
        policy,
    ).canonical

    assert len(merged.reviews) == 2
    assert merged.schedule.state is MemoryState.NEW
    assert rebuild_schedule(merged, replay) == merged.schedule


@given(
    st.text(
        alphabet=st.characters(whitelist_categories=("Ll",)),
        min_size=1,
        max_size=12,
    ).filter(lambda value: value != "certified-recall-v1")
)
def test_incompatible_merge_never_mutates_sources(protocol_id: str) -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    lifecycle = MemoryLifecycle(scheduler)
    first = lifecycle.create(create(61, "target_to_support"), policy)
    second = lifecycle.create(create(62, "target_to_support", protocol_id), policy)

    with pytest.raises(DomainError) as error:
        lifecycle.merge(MergeMemoryPrompts(uid(63), (first, second), NOW), policy)

    assert error.value.code is ErrorCode.INCOMPATIBLE_PROTOCOLS
    assert first.prompt.status is PromptStatus.ACTIVE
    assert second.prompt.status is PromptStatus.ACTIVE


@given(st.booleans())
def test_terminal_prompts_reject_every_further_transition(use_merge: bool) -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    lifecycle = MemoryLifecycle(scheduler)
    first = lifecycle.create(create(71, "target_to_support"), policy)
    if use_merge:
        second = lifecycle.create(create(72, "target_to_support"), policy)
        terminal = lifecycle.merge(
            MergeMemoryPrompts(uid(73), (first, second), NOW),
            policy,
        ).sources[0]
    else:
        terminal = lifecycle.delete(
            first,
            DeleteMemoryPrompt(NOW, reauthenticated=True),
        )

    with pytest.raises(DomainError) as error:
        lifecycle.suspend(terminal, NOW + timedelta(minutes=1))

    assert error.value.code is ErrorCode.INVALID_TRANSITION


@given(st.integers(min_value=1, max_value=500))
def test_same_instant_order_follows_checkpoint_not_fact_uuid(seed: int) -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    lifecycle = MemoryLifecycle(scheduler)
    aggregate = lifecycle.submit_review(
        lifecycle.create(create(81, "target_to_support"), policy),
        review(1000 + seed, MemoryRating.GOOD, NOW),
        policy,
    ).aggregate
    reset = lifecycle.reset(
        aggregate,
        ResetMemoryPrompt(uid(900 - seed), "same instant", NOW),
        policy,
    )

    rebuilt = rebuild_schedule(reset, resolver(policy))

    assert rebuilt.state is MemoryState.NEW
    assert rebuilt.reps == 0


@given(st.integers(min_value=2, max_value=50))
def test_policy_revision_replay_uses_the_binding_persisted_on_each_fact(
    revision: int,
) -> None:
    scheduler = FsrsV6Scheduler()
    policy_v1 = SchedulerPolicy.default()
    policy_vn = replace(policy_v1, revision=revision)
    replay = resolver(policy_v1, policy_vn)
    lifecycle = MemoryLifecycle(scheduler, replay_resolver=replay)
    first = lifecycle.submit_review(
        lifecycle.create(create(91, "target_to_support"), policy_v1),
        review(91, MemoryRating.GOOD, NOW),
        policy_v1,
    ).aggregate
    second = lifecycle.submit_review(
        lifecycle.create(create(92, "target_to_support"), policy_vn),
        review(92, MemoryRating.HARD, NOW + timedelta(days=1)),
        policy_vn,
    ).aggregate
    merged = lifecycle.merge(
        MergeMemoryPrompts(uid(93), (first, second), NOW + timedelta(days=2)),
        policy_vn,
    ).canonical

    assert rebuild_schedule(merged, replay) == merged.schedule
    with pytest.raises(DomainError) as error:
        rebuild_schedule(merged, resolver(policy_vn))
    assert error.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE


@given(st.sampled_from(tuple(MemoryRating)))
def test_merge_in_one_direction_does_not_change_the_reverse_direction(
    rating: MemoryRating,
) -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    lifecycle = MemoryLifecycle(scheduler)
    first = lifecycle.submit_review(
        lifecycle.create(create(101, "target_to_support"), policy),
        review(101, rating, NOW),
        policy,
    ).aggregate
    second = lifecycle.create(create(102, "target_to_support"), policy)
    reverse = lifecycle.create(create(103, "support_to_target"), policy)
    reverse_before = reverse

    merged = lifecycle.merge(
        MergeMemoryPrompts(uid(104), (first, second), NOW + timedelta(days=1)),
        policy,
    )

    assert merged.canonical.prompt.direction == "target_to_support"
    assert reverse == reverse_before


@given(
    st.sampled_from(tuple(MemoryRating)),
    st.sampled_from(tuple(MemoryRating)),
)
def test_replay_rejects_every_detached_but_self_consistent_transition(
    first_rating: MemoryRating,
    second_rating: MemoryRating,
) -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    lifecycle = MemoryLifecycle(scheduler)
    aggregate = lifecycle.submit_review(
        lifecycle.create(create(111, "target_to_support"), policy),
        review(111, first_rating, NOW),
        policy,
    ).aggregate
    aggregate = lifecycle.submit_review(
        aggregate,
        review(112, second_rating, NOW + timedelta(days=1)),
        policy,
    ).aggregate
    detached_before = aggregate.reviews[0].state_before
    detached_transition = scheduler.review(
        detached_before,
        second_rating,
        NOW + timedelta(days=1),
        policy,
    )
    detached = replace(
        aggregate.reviews[1],
        state_before=detached_transition.before,
        state_after=detached_transition.after,
    )
    corrupt = replace(aggregate, reviews=(aggregate.reviews[0], detached))

    with pytest.raises(DomainError) as error:
        rebuild_schedule(corrupt, resolver(policy))

    assert error.value.code is ErrorCode.VALIDATION_FAILED


@given(st.integers(min_value=1, max_value=365))
def test_merge_rejects_every_source_reset_before_prompt_creation(days: int) -> None:
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    lifecycle = MemoryLifecycle(scheduler)
    first = lifecycle.reset(
        lifecycle.create(create(121, "target_to_support"), policy),
        ResetMemoryPrompt(uid(122), "source reset", NOW + timedelta(days=1)),
        policy,
    )
    backdated = replace(first.resets[0], reset_at=NOW - timedelta(days=days))
    corrupt = replace(first, resets=(backdated,))
    second = lifecycle.create(create(123, "target_to_support"), policy)

    with pytest.raises(DomainError) as error:
        lifecycle.merge(
            MergeMemoryPrompts(uid(124), (corrupt, second), NOW + timedelta(days=2)),
            policy,
        )

    assert error.value.code is ErrorCode.VALIDATION_FAILED
