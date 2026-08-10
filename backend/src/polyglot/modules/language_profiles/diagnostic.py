from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from math import isfinite
from typing import Literal
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode


class DiagnosticClassification(StrEnum):
    BEGINNER = "beginner"
    FALSE_BEGINNER = "false_beginner"
    INTERMEDIATE = "intermediate"
    UNDETERMINED = "undetermined"


class DiagnosticTarget(StrEnum):
    FOUNDATIONS = "foundations"
    READING = "reading"
    LISTENING = "listening"
    WRITING = "writing"
    SPEAKING = "speaking"


class DiagnosticStopReason(StrEnum):
    COVERAGE_REACHED = "coverage_reached"
    CONSECUTIVE_FAILURES = "consecutive_failures"
    TIME_LIMIT = "time_limit"


def _invalid(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


@dataclass(frozen=True, slots=True)
class DiagnosticPolicy:
    policy_code: str
    revision: int
    minimum_opportunities: int
    maximum_duration: timedelta
    resume_window: timedelta
    consecutive_failure_limit: int
    beginner_foundations_maximum: float
    beginner_reception_maximum: float
    intermediate_foundations_minimum: float
    intermediate_reading_minimum: float
    intermediate_writing_minimum: float
    intermediate_confidence_minimum: float

    @classmethod
    def v0(cls) -> "DiagnosticPolicy":
        return cls(
            policy_code="DIAGNOSTIC_V0",
            revision=1,
            minimum_opportunities=2,
            maximum_duration=timedelta(minutes=25),
            resume_window=timedelta(hours=24),
            consecutive_failure_limit=3,
            beginner_foundations_maximum=0.40,
            beginner_reception_maximum=0.45,
            intermediate_foundations_minimum=0.80,
            intermediate_reading_minimum=0.65,
            intermediate_writing_minimum=0.55,
            intermediate_confidence_minimum=0.55,
        )


@dataclass(frozen=True, slots=True)
class DiagnosticResponse:
    target: DiagnosticTarget
    score: float
    confidence: float
    evaluable: bool
    difficulty: int
    item_revision_id: UUID

    def __post_init__(self) -> None:
        if self.item_revision_id.version != 7:
            raise _invalid("item_revision_id must be UUIDv7")
        if self.difficulty < 1:
            raise _invalid("difficulty must be positive")
        for field, value in (("score", self.score), ("confidence", self.confidence)):
            if not isfinite(value) or not 0 <= value <= 1:
                raise _invalid(f"{field} must be between zero and one")


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    classification: DiagnosticClassification
    next_profile_status: str
    stop_reason: DiagnosticStopReason
    target_scores: tuple[tuple[DiagnosticTarget, float | None], ...]
    target_confidences: tuple[tuple[DiagnosticTarget, float | None], ...]
    not_evaluable_targets: tuple[DiagnosticTarget, ...]
    implicit_mastery_target_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class DiagnosticRun:
    diagnostic_run_id: UUID
    profile_id: UUID
    policy: DiagnosticPolicy
    seed: str
    started_at: datetime
    expires_at: datetime
    responses: tuple[DiagnosticResponse, ...]
    response_times: tuple[datetime, ...]
    stop_reason: DiagnosticStopReason | None

    @classmethod
    def start(
        cls,
        *,
        diagnostic_run_id: UUID,
        profile_id: UUID,
        policy: DiagnosticPolicy,
        seed: str,
        started_at: datetime,
    ) -> "DiagnosticRun":
        if diagnostic_run_id.version != 7 or profile_id.version != 7:
            raise _invalid("diagnostic and profile identifiers must be UUIDv7")
        if not seed:
            raise _invalid("seed is required")
        _require_utc(started_at, "started_at")
        return cls(
            diagnostic_run_id=diagnostic_run_id,
            profile_id=profile_id,
            policy=policy,
            seed=seed,
            started_at=started_at,
            expires_at=started_at + policy.resume_window,
            responses=(),
            response_times=(),
            stop_reason=None,
        )

    def record(self, response: DiagnosticResponse, *, at: datetime) -> "DiagnosticRun":
        _require_utc(at, "at")
        if at >= self.expires_at:
            raise DomainError(ErrorCode.RUN_EXPIRED)
        if self.stop_reason is not None:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        if response.item_revision_id in {
            item.item_revision_id for item in self.responses
        }:
            raise DomainError(ErrorCode.RESPONSE_CONFLICT)
        responses = (*self.responses, response)
        times = (*self.response_times, at)
        stop_reason = self._stop_reason(responses, at)
        return replace(self, responses=responses, response_times=times, stop_reason=stop_reason)

    def complete(self, *, at: datetime) -> DiagnosticResult:
        _require_utc(at, "at")
        if at >= self.expires_at:
            raise DomainError(ErrorCode.RUN_EXPIRED)
        if not self._has_required_coverage():
            raise DomainError(ErrorCode.INSUFFICIENT_COVERAGE)
        scores = tuple((target, self._mean(target, "score")) for target in DiagnosticTarget)
        confidences = tuple(
            (target, self._mean(target, "confidence")) for target in DiagnosticTarget
        )
        values = dict(scores)
        confidence_values = dict(confidences)
        not_evaluable = tuple(
            target
            for target in DiagnosticTarget
            if self._has_observation(target) and self._mean(target, "score") is None
        )
        classification = self._classify(values, confidence_values)
        stop_reason = self.stop_reason or DiagnosticStopReason.COVERAGE_REACHED
        return DiagnosticResult(
            classification=classification,
            next_profile_status=(
                "active"
                if classification is DiagnosticClassification.INTERMEDIATE
                else "foundations"
            ),
            stop_reason=stop_reason,
            target_scores=scores,
            target_confidences=confidences,
            not_evaluable_targets=not_evaluable,
        )

    def snapshot(self) -> tuple[object, ...]:
        return (
            self.diagnostic_run_id,
            self.profile_id,
            self.policy,
            self.seed,
            self.started_at,
            self.expires_at,
            self.responses,
            self.response_times,
            self.stop_reason,
        )

    def _has_required_coverage(self) -> bool:
        return all(
            sum(item.target is target for item in self.responses)
            >= self.policy.minimum_opportunities
            for target in (
                DiagnosticTarget.FOUNDATIONS,
                DiagnosticTarget.READING,
                DiagnosticTarget.WRITING,
            )
        )

    def _has_observation(self, target: DiagnosticTarget) -> bool:
        return any(item.target is target for item in self.responses)

    def _mean(
        self,
        target: DiagnosticTarget,
        field: Literal["score", "confidence"],
    ) -> float | None:
        eligible = (
            item
            for item in self.responses
            if item.target is target and item.evaluable
        )
        values = [item.score if field == "score" else item.confidence for item in eligible]
        if not values:
            return None
        return sum(values) / len(values)

    def _classify(
        self,
        scores: dict[DiagnosticTarget, float | None],
        confidences: dict[DiagnosticTarget, float | None],
    ) -> DiagnosticClassification:
        foundations = scores[DiagnosticTarget.FOUNDATIONS]
        reading = scores[DiagnosticTarget.READING]
        writing = scores[DiagnosticTarget.WRITING]
        if foundations is None or reading is None or writing is None:
            return DiagnosticClassification.UNDETERMINED
        reception = reading
        if (
            foundations < self.policy.beginner_foundations_maximum
            and reception < self.policy.beginner_reception_maximum
            and writing == 0
        ):
            return DiagnosticClassification.BEGINNER
        required_confidences = tuple(
            confidences[target]
            for target in (
                DiagnosticTarget.FOUNDATIONS,
                DiagnosticTarget.READING,
                DiagnosticTarget.WRITING,
            )
        )
        if (
            foundations >= self.policy.intermediate_foundations_minimum
            and reading >= self.policy.intermediate_reading_minimum
            and writing >= self.policy.intermediate_writing_minimum
            and all(
                value is not None
                and value >= self.policy.intermediate_confidence_minimum
                for value in required_confidences
            )
        ):
            return DiagnosticClassification.INTERMEDIATE
        return DiagnosticClassification.FALSE_BEGINNER

    def _stop_reason(
        self,
        responses: tuple[DiagnosticResponse, ...],
        at: datetime,
    ) -> DiagnosticStopReason | None:
        if at - self.started_at >= self.policy.maximum_duration:
            return DiagnosticStopReason.TIME_LIMIT
        evaluable = [item for item in responses if item.evaluable]
        if len(evaluable) >= self.policy.consecutive_failure_limit and all(
            item.score == 0
            for item in evaluable[-self.policy.consecutive_failure_limit :]
        ):
            return DiagnosticStopReason.CONSECUTIVE_FAILURES
        return None


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise _invalid(f"{field} must be UTC")
