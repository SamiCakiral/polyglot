from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal
from enum import IntEnum, StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from polyglot.platform.errors import DomainError, ErrorCode

DEFAULT_PARAMETERS = (
    Decimal("0.212"),
    Decimal("1.2931"),
    Decimal("2.3065"),
    Decimal("8.2956"),
    Decimal("6.4133"),
    Decimal("0.8334"),
    Decimal("3.0194"),
    Decimal("0.001"),
    Decimal("1.8722"),
    Decimal("0.1666"),
    Decimal("0.796"),
    Decimal("1.4835"),
    Decimal("0.0614"),
    Decimal("0.2629"),
    Decimal("1.6483"),
    Decimal("0.6014"),
    Decimal("1.8729"),
    Decimal("0.5425"),
    Decimal("0.0912"),
    Decimal("0.0658"),
    Decimal("0.1542"),
)


class ReviewVerdict(StrEnum):
    INCORRECT = "incorrect"
    FORGOTTEN = "forgotten"
    CORRECT = "correct"
    AMBIGUOUS = "ambiguous"
    NOT_EVALUABLE = "not_evaluable"


class HintLevel(IntEnum):
    H0 = 0
    H1 = 1
    H2 = 2
    H3 = 3
    H4 = 4


def _parameter_set_id(parameters: tuple[Decimal, ...]) -> str:
    canonical = json.dumps([str(value) for value in parameters], separators=(",", ":"))
    return "fsrs-6.3.1-" + hashlib.sha256(canonical.encode("ascii")).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class SchedulerPolicy:
    revision: int
    parameters: tuple[Decimal, ...]
    desired_retention: Decimal
    learning_steps: tuple[timedelta, ...]
    relearning_steps: tuple[timedelta, ...]
    timezone_name: str
    after_24h: bool
    fuzz_seed: int
    maximum_interval_days: int
    parameter_set_id: str

    def __post_init__(self) -> None:
        if self.revision < 1 or len(self.parameters) != 21:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid scheduler policy")
        if not Decimal("0.80") <= self.desired_retention <= Decimal("0.97"):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid desired retention")
        one_day = timedelta(days=1)
        if any(step <= timedelta(0) or step >= one_day for step in self.learning_steps):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid learning steps")
        if any(step <= timedelta(0) or step >= one_day for step in self.relearning_steps):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid relearning steps")
        try:
            ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError as error:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid timezone") from error
        if self.fuzz_seed < 0 or self.maximum_interval_days < 1:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="invalid scheduler bounds")
        if self.parameter_set_id != _parameter_set_id(self.parameters):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="parameter set identity mismatch")

    @classmethod
    def default(
        cls,
        *,
        desired_retention: Decimal = Decimal("0.90"),
        timezone_name: str = "UTC",
        after_24h: bool = False,
        fuzz_seed: int = 4_242,
    ) -> SchedulerPolicy:
        return cls(
            revision=1,
            parameters=DEFAULT_PARAMETERS,
            desired_retention=desired_retention,
            learning_steps=(timedelta(minutes=1), timedelta(minutes=10)),
            relearning_steps=(timedelta(minutes=10),),
            timezone_name=timezone_name,
            after_24h=after_24h,
            fuzz_seed=fuzz_seed,
            maximum_interval_days=36_500,
            parameter_set_id=_parameter_set_id(DEFAULT_PARAMETERS),
        )

    def with_fuzz_seed(self, fuzz_seed: int) -> SchedulerPolicy:
        return replace(self, fuzz_seed=fuzz_seed)


def allowed_ratings(
    verdict: ReviewVerdict,
    highest_hint: HintLevel,
) -> tuple[object, ...]:
    from polyglot.modules.lexicon.memory.ports import MemoryRating

    if verdict in {ReviewVerdict.AMBIGUOUS, ReviewVerdict.NOT_EVALUABLE}:
        return ()
    if verdict in {ReviewVerdict.INCORRECT, ReviewVerdict.FORGOTTEN}:
        return (MemoryRating.AGAIN,)
    if highest_hint >= HintLevel.H3:
        return (MemoryRating.AGAIN, MemoryRating.HARD)
    if highest_hint >= HintLevel.H1:
        return (MemoryRating.HARD, MemoryRating.GOOD)
    return (MemoryRating.HARD, MemoryRating.GOOD, MemoryRating.EASY)
