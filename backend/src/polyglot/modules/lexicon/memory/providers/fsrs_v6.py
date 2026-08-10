from __future__ import annotations

import random
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Lock
from typing import Protocol, cast

import fsrs

from polyglot.modules.lexicon.memory.policy import SchedulerPolicy
from polyglot.modules.lexicon.memory.ports import (
    MemoryRating,
    MemoryState,
    ScheduledState,
    SchedulerIdentity,
    ScheduleTransition,
)
from polyglot.platform.errors import DomainError, ErrorCode


class _SchedulerLike(Protocol):
    def review_card(
        self,
        card: fsrs.Card,
        rating: fsrs.Rating,
        review_datetime: datetime,
    ) -> tuple[fsrs.Card, fsrs.ReviewLog]: ...

    def get_card_retrievability(
        self,
        card: fsrs.Card,
        current_datetime: datetime,
    ) -> float: ...


SchedulerFactory = Callable[[SchedulerPolicy], _SchedulerLike]
_RANDOM_LOCK = Lock()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="datetime must be timezone-aware")
    return value.astimezone(UTC)


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


@contextmanager
def _deterministic_random(seed: int) -> Iterator[None]:
    with _RANDOM_LOCK:
        previous = random.getstate()
        random.seed(seed)
        try:
            yield
        finally:
            random.setstate(previous)


def _default_scheduler(policy: SchedulerPolicy) -> _SchedulerLike:
    return fsrs.Scheduler(
        parameters=tuple(float(value) for value in policy.parameters),
        desired_retention=float(policy.desired_retention),
        learning_steps=policy.learning_steps,
        relearning_steps=policy.relearning_steps,
        maximum_interval=policy.maximum_interval_days,
        enable_fuzzing=True,
    )


_RATING_TO_FSRS = {
    MemoryRating.AGAIN: fsrs.Rating.Again,
    MemoryRating.HARD: fsrs.Rating.Hard,
    MemoryRating.GOOD: fsrs.Rating.Good,
    MemoryRating.EASY: fsrs.Rating.Easy,
}
_STATE_TO_FSRS = {
    MemoryState.NEW: fsrs.State.Learning,
    MemoryState.LEARNING: fsrs.State.Learning,
    MemoryState.REVIEW: fsrs.State.Review,
    MemoryState.RELEARNING: fsrs.State.Relearning,
}
_STATE_FROM_FSRS = {
    fsrs.State.Learning: MemoryState.LEARNING,
    fsrs.State.Review: MemoryState.REVIEW,
    fsrs.State.Relearning: MemoryState.RELEARNING,
}


class FsrsV6Scheduler:
    def __init__(
        self,
        scheduler_factory: Callable[[SchedulerPolicy], object] | None = None,
    ) -> None:
        self._scheduler_factory = cast(SchedulerFactory, scheduler_factory or _default_scheduler)

    @property
    def identity(self) -> SchedulerIdentity:
        policy = SchedulerPolicy.default()
        return SchedulerIdentity("fsrs", "6.3.1", policy.parameter_set_id)

    def _scheduler(self, policy: SchedulerPolicy) -> _SchedulerLike:
        try:
            return self._scheduler_factory(policy)
        except Exception as error:
            raise DomainError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                detail="FSRS 6.3.1 is unavailable",
            ) from error

    def initial_state(self, policy: SchedulerPolicy, created_at: datetime) -> ScheduledState:
        return ScheduledState(
            state=MemoryState.NEW,
            difficulty=None,
            stability=None,
            due_at=_utc(created_at),
            last_review_at=None,
            step=0,
            reps=0,
            lapses=0,
        )

    def review(
        self,
        previous_state: ScheduledState,
        rating: MemoryRating,
        reviewed_at: datetime,
        policy: SchedulerPolicy,
    ) -> ScheduleTransition:
        reviewed_at_utc = _utc(reviewed_at)
        try:
            provider_rating = _RATING_TO_FSRS[rating]
        except (KeyError, TypeError) as error:
            raise DomainError(ErrorCode.RATING_NOT_ALLOWED) from error
        scheduler = self._scheduler(policy)
        card = fsrs.Card(
            card_id=1,
            state=_STATE_TO_FSRS[previous_state.state],
            step=previous_state.step,
            stability=None if previous_state.stability is None else float(previous_state.stability),
            difficulty=(
                None if previous_state.difficulty is None else float(previous_state.difficulty)
            ),
            due=_utc(previous_state.due_at),
            last_review=(
                None
                if previous_state.last_review_at is None
                else _utc(previous_state.last_review_at)
            ),
        )
        try:
            with _deterministic_random(policy.fuzz_seed):
                updated, _ = scheduler.review_card(card, provider_rating, reviewed_at_utc)
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                detail="FSRS 6.3.1 failed without fallback",
            ) from error
        due_at = _utc(updated.due)
        if policy.after_24h:
            due_at = max(due_at, reviewed_at_utc + timedelta(hours=24))
        after = ScheduledState(
            state=_STATE_FROM_FSRS[updated.state],
            difficulty=_decimal(updated.difficulty),
            stability=_decimal(updated.stability),
            due_at=due_at,
            last_review_at=reviewed_at_utc,
            step=updated.step,
            reps=previous_state.reps + 1,
            lapses=(
                previous_state.lapses + 1
                if rating is MemoryRating.AGAIN and previous_state.state is MemoryState.REVIEW
                else previous_state.lapses
            ),
        )
        self._validate(after)
        return ScheduleTransition(previous_state, after, rating, reviewed_at_utc)

    def resume(
        self,
        previous_state: ScheduledState,
        resumed_at: datetime,
        policy: SchedulerPolicy,
    ) -> ScheduledState:
        resumed_at_utc = _utc(resumed_at)
        return ScheduledState(
            state=previous_state.state,
            difficulty=previous_state.difficulty,
            stability=previous_state.stability,
            due_at=max(_utc(previous_state.due_at), resumed_at_utc),
            last_review_at=previous_state.last_review_at,
            step=previous_state.step,
            reps=previous_state.reps,
            lapses=previous_state.lapses,
        )

    def retrievability(
        self,
        state: ScheduledState,
        at: datetime | None,
        policy: SchedulerPolicy,
    ) -> Decimal:
        if state.state in {MemoryState.NEW, MemoryState.LEARNING} or state.stability is None:
            return Decimal("1")
        current = _utc(at or state.due_at)
        card = fsrs.Card(
            card_id=1,
            state=_STATE_TO_FSRS[state.state],
            step=state.step,
            stability=float(state.stability),
            difficulty=None if state.difficulty is None else float(state.difficulty),
            due=_utc(state.due_at),
            last_review=None if state.last_review_at is None else _utc(state.last_review_at),
        )
        try:
            value = self._scheduler(policy).get_card_retrievability(card, current)
        except DomainError:
            raise
        except Exception as error:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE) from error
        return Decimal(str(value))

    @staticmethod
    def _validate(state: ScheduledState) -> None:
        if state.due_at.tzinfo is not UTC:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE, detail="FSRS returned non-UTC due")
        if state.difficulty is not None and not Decimal("1") <= state.difficulty <= Decimal("10"):
            raise DomainError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                detail="FSRS difficulty out of bounds",
            )
        if state.stability is not None and state.stability <= 0:
            raise DomainError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                detail="FSRS stability out of bounds",
            )
