from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from polyglot.modules.lexicon.memory.policy import SchedulerPolicy


class MemoryRating(StrEnum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class MemoryState(StrEnum):
    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"


@dataclass(frozen=True, slots=True)
class SchedulerIdentity:
    kind: str
    version: str
    parameter_set_id: str


@dataclass(frozen=True, slots=True)
class ScheduledState:
    state: MemoryState
    difficulty: Decimal | None
    stability: Decimal | None
    due_at: datetime
    last_review_at: datetime | None
    step: int | None
    reps: int
    lapses: int


@dataclass(frozen=True, slots=True)
class ScheduleTransition:
    before: ScheduledState
    after: ScheduledState
    rating: MemoryRating
    reviewed_at: datetime


class MemorySchedulerPort(Protocol):
    @property
    def identity(self) -> SchedulerIdentity: ...

    def initial_state(self, policy: SchedulerPolicy, created_at: datetime) -> ScheduledState: ...

    def review(
        self,
        previous_state: ScheduledState,
        rating: MemoryRating,
        reviewed_at: datetime,
        policy: SchedulerPolicy,
    ) -> ScheduleTransition: ...

    def resume(
        self,
        previous_state: ScheduledState,
        resumed_at: datetime,
        policy: SchedulerPolicy,
    ) -> ScheduledState: ...

    def retrievability(
        self,
        state: ScheduledState,
        at: datetime | None,
        policy: SchedulerPolicy,
    ) -> Decimal: ...
