from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from polyglot.modules.lexicon.memory.application import (
    ArchiveMemoryPrompt,
    CreateMemoryPrompt,
    DeleteMemoryPrompt,
    MemoryLifecycle,
    MergeMemoryPrompts,
    ResetMemoryPrompt,
    RestoreMemoryPrompt,
    ResumeMemoryPrompt,
    SubmitMemoryReview,
)
from polyglot.modules.lexicon.memory.domain import MemoryAggregate, PromptStatus
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


def create_command(
    *,
    prompt_id: int = 1,
    direction: str = "target_to_support",
    protocol_id: str = "certified-recall-v1",
    target_revision_id: int = 5,
    operation: str = "recall",
) -> CreateMemoryPrompt:
    return CreateMemoryPrompt(
        prompt_id=uid(prompt_id),
        profile_id=uid(2),
        target_ref=uid(3),
        target_revision_id=uid(target_revision_id),
        direction=direction,
        modality="written",
        operation=operation,
        protocol_id=protocol_id,
        protocol_revision=1,
        rating_semantics_id="polyglot-recall-v1",
        scheduler_policy_id=uid(6),
        created_at=NOW,
    )


def review_command(
    *,
    review_id: int = 10,
    opportunity_id: int = 11,
    rating: MemoryRating = MemoryRating.GOOD,
    verdict: ReviewVerdict = ReviewVerdict.CORRECT,
    hint: HintLevel = HintLevel.H0,
    reviewed_at: datetime = NOW,
    certified_recall: bool = True,
    answer_revealed: bool = False,
    exposure_only: bool = False,
    incidental_production: bool = False,
    certified_operation: str = "recall",
    certified_protocol_id: str = "certified-recall-v1",
    certified_protocol_revision: int = 1,
    certified_target_revision_id: int = 5,
) -> SubmitMemoryReview:
    return SubmitMemoryReview(
        review_id=uid(review_id),
        opportunity_id=uid(opportunity_id),
        attempt_id=uid(12),
        response_ref="response:12",
        correction_ref="correction:12",
        verdict=verdict,
        highest_hint=hint,
        rating=rating,
        certified_recall=certified_recall,
        certification_ref="certification:recall-v1",
        certified_operation=certified_operation,
        certified_protocol_id=certified_protocol_id,
        certified_protocol_revision=certified_protocol_revision,
        certified_target_revision_id=uid(certified_target_revision_id),
        answer_revealed=answer_revealed,
        exposure_only=exposure_only,
        incidental_production=incidental_production,
        self_reported=False,
        active_duration_ms=2_500,
        scheduled_at=reviewed_at,
        reviewed_at=reviewed_at,
        idempotency_key=f"review-{review_id}",
    )


@pytest.mark.parametrize(
    ("prompt_changes", "review_changes"),
    [
        ({"operation": "exposure"}, {}),
        ({}, {"certified_operation": "recognition"}),
        ({}, {"certified_protocol_id": "other-protocol"}),
        ({}, {"certified_protocol_revision": 2}),
        ({}, {"certified_target_revision_id": 999}),
    ],
)
def test_certification_must_match_every_pinned_prompt_dimension(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
    prompt_changes: dict[str, object],
    review_changes: dict[str, object],
) -> None:
    aggregate = lifecycle.create(create_command(**prompt_changes), policy)
    command = review_command(**review_changes)

    decision = lifecycle.submit_review(aggregate, command, policy)

    assert decision.review_created is False
    assert decision.reason == "operation_not_certified"
    assert decision.aggregate == aggregate


def test_certification_reference_is_required_for_a_scheduling_review(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    aggregate = lifecycle.create(create_command(), policy)
    command = review_command()
    command = SubmitMemoryReview(**{**command.as_dict(), "certification_ref": ""})

    decision = lifecycle.submit_review(aggregate, command, policy)

    assert decision.review_created is False
    assert decision.reason == "operation_not_certified"
    assert decision.aggregate == aggregate


@pytest.fixture
def lifecycle() -> MemoryLifecycle:
    return MemoryLifecycle(FsrsV6Scheduler())


@pytest.fixture
def policy() -> SchedulerPolicy:
    return SchedulerPolicy.default()


def replay_resolver(
    *policies: SchedulerPolicy,
) -> StaticMemoryReplayResolver:
    scheduler = FsrsV6Scheduler()
    return StaticMemoryReplayResolver(
        tuple(MemoryReplayBinding(scheduler, item) for item in policies)
    )


def test_create_has_active_product_status_and_independent_new_schedule(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    aggregate = lifecycle.create(create_command(), policy)

    assert aggregate.prompt.status is PromptStatus.ACTIVE
    assert aggregate.prompt.version == 1
    assert aggregate.schedule.state is MemoryState.NEW
    assert aggregate.schedule.projection_version == 1
    assert aggregate.schedule.desired_retention == Decimal("0.90")
    assert aggregate.reviews == ()
    assert aggregate.resets == ()


def test_review_adds_one_fact_and_projection_without_pedagogical_mastery(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    aggregate = lifecycle.create(create_command(), policy)

    decision = lifecycle.submit_review(aggregate, review_command(), policy)

    assert decision.review_created is True
    assert len(decision.aggregate.reviews) == 1
    assert decision.aggregate.reviews[0].state_before.state is MemoryState.NEW
    assert decision.aggregate.schedule.reps == 1
    assert decision.aggregate.schedule.last_review_id == uid(10)
    assert decision.aggregate.prompt.version == 2
    assert not hasattr(decision.aggregate, "mastery")
    assert not hasattr(decision.aggregate, "learning_evidence")


def test_self_reported_recognition_updates_schedule_at_low_confidence(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    aggregate = lifecycle.create(
        create_command(
            operation="recognition",
            protocol_id="practice-stack-self-recall",
        ),
        policy,
    )
    command = review_command(
        certified_operation="recognition",
        certified_protocol_id="practice-stack-self-recall",
    )
    command = SubmitMemoryReview(
        **{**command.as_dict(), "self_reported": True}
    )

    decision = lifecycle.submit_review(aggregate, command, policy)

    assert decision.review_created is True
    assert decision.aggregate.prompt.version == 2
    assert decision.aggregate.schedule.reps == 1
    assert decision.aggregate.reviews[0].low_confidence is True
    assert not hasattr(decision.aggregate, "mastery")


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"certified_recall": False}, "operation_not_certified"),
        ({"answer_revealed": True}, "answer_revealed"),
        ({"exposure_only": True}, "exposure_only"),
        ({"incidental_production": True}, "incidental_production"),
        ({"verdict": ReviewVerdict.AMBIGUOUS}, "not_evaluable"),
        ({"verdict": ReviewVerdict.NOT_EVALUABLE}, "not_evaluable"),
    ],
)
def test_ineligible_opportunities_do_not_create_review_or_change_projection(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
    changes: dict[str, object],
    reason: str,
) -> None:
    aggregate = lifecycle.create(create_command(), policy)
    command = review_command()
    command = SubmitMemoryReview(**{**command.as_dict(), **changes})

    decision = lifecycle.submit_review(aggregate, command, policy)

    assert decision.review_created is False
    assert decision.reason == reason
    assert decision.aggregate == aggregate


@pytest.mark.parametrize(
    ("verdict", "hint", "rating"),
    [
        (ReviewVerdict.INCORRECT, HintLevel.H0, MemoryRating.GOOD),
        (ReviewVerdict.CORRECT, HintLevel.H4, MemoryRating.GOOD),
        (ReviewVerdict.CORRECT, HintLevel.H3, MemoryRating.EASY),
        (ReviewVerdict.CORRECT, HintLevel.H2, MemoryRating.EASY),
        (ReviewVerdict.CORRECT, HintLevel.H1, MemoryRating.EASY),
    ],
)
def test_user_cannot_choose_a_more_favorable_rating_than_the_observation(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
    verdict: ReviewVerdict,
    hint: HintLevel,
    rating: MemoryRating,
) -> None:
    aggregate = lifecycle.create(create_command(), policy)

    with pytest.raises(DomainError) as error:
        lifecycle.submit_review(
            aggregate,
            review_command(verdict=verdict, hint=hint, rating=rating),
            policy,
        )

    assert error.value.code is ErrorCode.RATING_NOT_ALLOWED
    assert aggregate.reviews == ()


def test_review_rejects_a_policy_other_than_the_prompt_policy(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    aggregate = lifecycle.create(create_command(), policy)
    other_revision = replace(policy, revision=2)

    with pytest.raises(DomainError) as error:
        lifecycle.submit_review(aggregate, review_command(), other_revision)

    assert error.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    assert aggregate.reviews == ()


def test_backdated_review_is_rejected_without_mutating_the_history(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    aggregate = lifecycle.create(create_command(), policy)
    aggregate = lifecycle.submit_review(
        aggregate,
        review_command(reviewed_at=NOW + timedelta(days=2)),
        policy,
    ).aggregate

    with pytest.raises(DomainError) as error:
        lifecycle.submit_review(
            aggregate,
            review_command(
                review_id=20,
                opportunity_id=21,
                reviewed_at=NOW + timedelta(days=1),
            ),
            policy,
        )

    assert error.value.code is ErrorCode.REVIEW_CONFLICT
    assert len(aggregate.reviews) == 1


def test_review_transition_counters_must_be_internally_consistent(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    aggregate = lifecycle.submit_review(
        lifecycle.create(create_command(), policy),
        review_command(),
        policy,
    ).aggregate
    review = aggregate.reviews[0]
    invalid_after = replace(review.state_after, reps=review.state_before.reps)

    with pytest.raises(DomainError) as error:
        replace(review, state_after=invalid_after)

    assert error.value.code is ErrorCode.VALIDATION_FAILED


def test_aggregate_rejects_facts_owned_by_an_unrelated_prompt(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    aggregate = lifecycle.submit_review(
        lifecycle.create(create_command(), policy),
        review_command(),
        policy,
    ).aggregate
    foreign = replace(aggregate.reviews[0], prompt_id=uid(999))

    with pytest.raises(DomainError) as error:
        MemoryAggregate(
            prompt=aggregate.prompt,
            schedule=aggregate.schedule,
            reviews=(foreign,),
        )

    assert error.value.code is ErrorCode.VALIDATION_FAILED


def test_suspend_resume_preserves_memory_and_never_invents_again(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    reviewed = lifecycle.submit_review(
        lifecycle.create(create_command(), policy),
        review_command(),
        policy,
    ).aggregate
    suspended = lifecycle.suspend(reviewed, NOW + timedelta(hours=1))
    resumed = lifecycle.resume(
        suspended,
        ResumeMemoryPrompt(uid(90), NOW + timedelta(days=30)),
        policy,
    )

    assert suspended.prompt.status is PromptStatus.SUSPENDED
    assert suspended.schedule == reviewed.schedule
    assert resumed.prompt.status is PromptStatus.ACTIVE
    assert resumed.schedule.state is reviewed.schedule.state
    assert resumed.schedule.stability == reviewed.schedule.stability
    assert resumed.schedule.lapses == reviewed.schedule.lapses
    assert resumed.schedule.last_rating is MemoryRating.GOOD
    assert len(resumed.reviews) == 1
    assert len(resumed.resumptions) == 1
    assert rebuild_schedule(resumed, replay_resolver(policy)) == resumed.schedule


def test_reset_is_append_only_and_rebuilds_a_new_lineage(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    reviewed = lifecycle.submit_review(
        lifecycle.create(create_command(), policy),
        review_command(),
        policy,
    ).aggregate
    reset = lifecycle.reset(
        reviewed,
        ResetMemoryPrompt(uid(20), "learner requested restart", NOW + timedelta(days=1)),
        policy,
    )

    assert len(reset.reviews) == 1
    assert len(reset.resets) == 1
    assert reset.schedule.state is MemoryState.NEW
    assert reset.schedule.reps == 0
    assert reset.schedule.projection_version == reviewed.schedule.projection_version + 1
    assert rebuild_schedule(reset, replay_resolver(policy)) == reset.schedule


def test_archive_restore_requires_available_revision_and_delete_requires_reauth(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    aggregate = lifecycle.create(create_command(), policy)
    archived = lifecycle.archive(
        aggregate,
        ArchiveMemoryPrompt(NOW + timedelta(hours=1)),
    )
    assert archived.prompt.status is PromptStatus.ARCHIVED

    with pytest.raises(DomainError) as missing:
        lifecycle.restore(
            archived,
            RestoreMemoryPrompt(
                uid(91),
                NOW + timedelta(hours=2),
                target_revision_available=False,
            ),
            policy,
        )
    assert missing.value.code is ErrorCode.TARGET_REVISION_UNAVAILABLE
    assert archived.prompt.status is PromptStatus.ARCHIVED

    restored = lifecycle.restore(
        archived,
        RestoreMemoryPrompt(
            uid(92),
            NOW + timedelta(hours=2),
            target_revision_available=True,
        ),
        policy,
    )
    assert restored.prompt.status is PromptStatus.ACTIVE
    assert len(restored.resumptions) == 1
    assert rebuild_schedule(restored, replay_resolver(policy)) == restored.schedule

    with pytest.raises(DomainError) as forbidden:
        lifecycle.delete(restored, DeleteMemoryPrompt(NOW, reauthenticated=False))
    assert forbidden.value.code is ErrorCode.FORBIDDEN

    deleted = lifecycle.delete(restored, DeleteMemoryPrompt(NOW, reauthenticated=True))
    assert deleted.prompt.status is PromptStatus.DELETED
    with pytest.raises(DomainError) as terminal:
        lifecycle.suspend(deleted, NOW)
    assert terminal.value.code is ErrorCode.INVALID_TRANSITION


def test_merge_deduplicates_causally_and_supersedes_sources_without_erasing_facts(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    first = lifecycle.create(create_command(prompt_id=31), policy)
    second = lifecycle.create(create_command(prompt_id=32), policy)
    first = lifecycle.submit_review(
        first,
        review_command(review_id=41, opportunity_id=51),
        policy,
    ).aggregate
    second = lifecycle.submit_review(
        second,
        review_command(
            review_id=42,
            opportunity_id=52,
            reviewed_at=NOW + timedelta(days=1),
        ),
        policy,
    ).aggregate

    result = lifecycle.merge(
        MergeMemoryPrompts(uid(40), (first, second), NOW + timedelta(days=2)),
        policy,
    )

    assert result.canonical.prompt.prompt_id == uid(40)
    assert [review.review_id for review in result.canonical.reviews] == [uid(41), uid(42)]
    assert len(result.canonical.lineages) == 2
    assert all(source.prompt.status is PromptStatus.SUPERSEDED for source in result.sources)
    assert all(len(source.reviews) == 1 for source in result.sources)
    assert (
        rebuild_schedule(result.canonical, replay_resolver(policy))
        == result.canonical.schedule
    )


def test_incompatible_merge_has_no_partial_effect(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    first = lifecycle.create(create_command(prompt_id=61), policy)
    second = lifecycle.create(
        create_command(prompt_id=62, protocol_id="incompatible-protocol"),
        policy,
    )

    with pytest.raises(DomainError) as error:
        lifecycle.merge(MergeMemoryPrompts(uid(63), (first, second), NOW), policy)

    assert error.value.code is ErrorCode.INCOMPATIBLE_PROTOCOLS
    assert first.prompt.status is PromptStatus.ACTIVE
    assert second.prompt.status is PromptStatus.ACTIVE


def test_rebuild_resolves_every_persisted_scheduler_policy_and_fails_closed(
    policy: SchedulerPolicy,
) -> None:
    scheduler = FsrsV6Scheduler()
    policy_v2 = replace(policy, revision=2)
    resolver = replay_resolver(policy, policy_v2)
    lifecycle = MemoryLifecycle(scheduler, replay_resolver=resolver)
    first = lifecycle.submit_review(
        lifecycle.create(create_command(prompt_id=71), policy),
        review_command(review_id=72, opportunity_id=73),
        policy,
    ).aggregate
    second = lifecycle.submit_review(
        lifecycle.create(create_command(prompt_id=74), policy_v2),
        review_command(
            review_id=75,
            opportunity_id=76,
            reviewed_at=NOW + timedelta(days=1),
        ),
        policy_v2,
    ).aggregate
    merged = lifecycle.merge(
        MergeMemoryPrompts(uid(77), (first, second), NOW + timedelta(days=2)),
        policy_v2,
    ).canonical

    assert rebuild_schedule(merged, resolver) == merged.schedule
    with pytest.raises(DomainError) as unavailable:
        rebuild_schedule(merged, replay_resolver(policy_v2))
    assert unavailable.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE


def test_merge_replays_resets_reviews_and_duplicate_facts_causally(
    policy: SchedulerPolicy,
) -> None:
    resolver = replay_resolver(policy)
    lifecycle = MemoryLifecycle(FsrsV6Scheduler(), replay_resolver=resolver)
    first = lifecycle.submit_review(
        lifecycle.create(create_command(prompt_id=101), policy),
        review_command(review_id=111, opportunity_id=121),
        policy,
    ).aggregate
    first = lifecycle.reset(
        first,
        ResetMemoryPrompt(uid(112), "merge reset", NOW + timedelta(days=2)),
        policy,
    )
    second = lifecycle.submit_review(
        lifecycle.create(create_command(prompt_id=102), policy),
        review_command(
            review_id=113,
            opportunity_id=121,
            reviewed_at=NOW + timedelta(days=1),
        ),
        policy,
    ).aggregate

    canonical = lifecycle.merge(
        MergeMemoryPrompts(uid(103), (first, second), NOW + timedelta(days=3)),
        policy,
    ).canonical

    assert len(canonical.reviews) == 2
    assert len(canonical.resets) == 1
    assert canonical.schedule.state is MemoryState.NEW
    assert canonical.schedule.reps == 0
    assert rebuild_schedule(canonical, resolver) == canonical.schedule


def test_checkpoint_controls_same_instant_review_then_reset_order(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    aggregate = lifecycle.create(create_command(prompt_id=131), policy)
    aggregate = lifecycle.submit_review(
        aggregate,
        review_command(review_id=199, opportunity_id=132),
        policy,
    ).aggregate
    aggregate = lifecycle.reset(
        aggregate,
        ResetMemoryPrompt(uid(133), "same instant", NOW),
        policy,
    )

    rebuilt = rebuild_schedule(aggregate, replay_resolver(policy))

    assert rebuilt.state is MemoryState.NEW
    assert rebuilt.reps == 0
    assert rebuilt.causal_checkpoint == f"reset:{uid(133)}"


def test_rebuild_rejects_broken_checkpoint_and_corrupt_provider_transition(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    aggregate = lifecycle.submit_review(
        lifecycle.create(create_command(prompt_id=141), policy),
        review_command(review_id=142, opportunity_id=143),
        policy,
    ).aggregate
    reset = lifecycle.reset(
        aggregate,
        ResetMemoryPrompt(uid(144), "causal check", NOW + timedelta(days=1)),
        policy,
    )
    broken_reset = replace(reset.resets[0], previous_checkpoint="review:missing")
    broken_history = replace(reset, resets=(broken_reset,))

    with pytest.raises(DomainError) as causal:
        rebuild_schedule(broken_history, replay_resolver(policy))
    assert causal.value.code is ErrorCode.VALIDATION_FAILED

    review = aggregate.reviews[0]
    corrupt_after = replace(review.state_after, difficulty=Decimal("9.999"))
    corrupt_review = replace(review, state_after=corrupt_after)
    corrupt_history = replace(aggregate, reviews=(corrupt_review,))

    with pytest.raises(DomainError) as transition:
        rebuild_schedule(corrupt_history, replay_resolver(policy))
    assert transition.value.code is ErrorCode.VALIDATION_FAILED


def test_rebuild_rejects_a_self_consistent_transition_detached_from_causal_state(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    aggregate = lifecycle.submit_review(
        lifecycle.create(create_command(prompt_id=151), policy),
        review_command(review_id=152, opportunity_id=153),
        policy,
    ).aggregate
    aggregate = lifecycle.submit_review(
        aggregate,
        review_command(
            review_id=154,
            opportunity_id=155,
            rating=MemoryRating.HARD,
            reviewed_at=NOW + timedelta(days=1),
        ),
        policy,
    ).aggregate
    detached_before = aggregate.reviews[0].state_before
    detached_transition = FsrsV6Scheduler().review(
        detached_before,
        MemoryRating.HARD,
        NOW + timedelta(days=1),
        policy,
    )
    detached = replace(
        aggregate.reviews[1],
        state_before=detached_transition.before,
        state_after=detached_transition.after,
    )
    corrupt_history = replace(
        aggregate,
        reviews=(aggregate.reviews[0], detached),
    )

    with pytest.raises(DomainError) as error:
        rebuild_schedule(corrupt_history, replay_resolver(policy))

    assert error.value.code is ErrorCode.VALIDATION_FAILED


def test_merge_rejects_a_source_fact_before_its_prompt_creation(
    lifecycle: MemoryLifecycle,
    policy: SchedulerPolicy,
) -> None:
    first = lifecycle.reset(
        lifecycle.create(create_command(prompt_id=161), policy),
        ResetMemoryPrompt(uid(162), "source reset", NOW + timedelta(days=1)),
        policy,
    )
    backdated_reset = replace(first.resets[0], reset_at=NOW - timedelta(days=1))
    corrupt_source = replace(first, resets=(backdated_reset,))
    second = lifecycle.create(create_command(prompt_id=163), policy)

    with pytest.raises(DomainError) as error:
        lifecycle.merge(
            MergeMemoryPrompts(uid(164), (corrupt_source, second), NOW + timedelta(days=2)),
            policy,
        )

    assert error.value.code is ErrorCode.VALIDATION_FAILED
