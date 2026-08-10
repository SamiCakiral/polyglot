from datetime import datetime

from polyglot.modules.lexicon.memory.application import _projection
from polyglot.modules.lexicon.memory.domain import (
    MemoryAggregate,
    MemoryReview,
    MemoryScheduleReset,
    MemoryScheduleState,
)
from polyglot.modules.lexicon.memory.policy import SchedulerPolicy
from polyglot.modules.lexicon.memory.ports import MemorySchedulerPort


def rebuild_schedule(
    aggregate: MemoryAggregate,
    scheduler: MemorySchedulerPort,
    policy: SchedulerPolicy,
) -> MemoryScheduleState:
    state = scheduler.initial_state(policy, aggregate.prompt.created_at)
    last_rating = None
    last_review_id = None
    checkpoint = "created"
    computed_at: datetime = aggregate.prompt.created_at
    events: list[tuple[datetime, int, MemoryReview | MemoryScheduleReset]] = [
        (review.reviewed_at, review.review_id.int, review)
        for review in aggregate.reviews
    ]
    events.extend(
        (reset.reset_at, reset.reset_id.int, reset) for reset in aggregate.resets
    )
    for at, _, event in sorted(events, key=lambda item: (item[0], item[1])):
        if isinstance(event, MemoryScheduleReset):
            state = scheduler.initial_state(policy, at)
            last_rating = None
            last_review_id = None
            checkpoint = f"reset:{event.reset_id}"
        else:
            state = scheduler.review(state, event.rating, at, policy).after
            last_rating = event.rating
            last_review_id = event.review_id
            checkpoint = f"review:{event.review_id}"
        computed_at = at
    return _projection(
        prompt_id=aggregate.prompt.prompt_id,
        state=state,
        policy=policy,
        scheduler=scheduler,
        projection_version=1 + len(events),
        computed_at=computed_at,
        last_rating=last_rating,
        last_review_id=last_review_id,
        checkpoint=checkpoint,
    )
