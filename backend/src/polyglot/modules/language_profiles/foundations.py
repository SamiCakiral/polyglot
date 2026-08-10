from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode


class FoundationBlock(StrEnum):
    F1 = "f1_graphs_and_sounds"
    F2 = "f2_rhythm_and_stress"
    F3 = "f3_minimal_interaction"
    F4 = "f4_fundamental_frames"
    F5 = "f5_repair_strategies"


class FoundationCriterion(StrEnum):
    GRAPHEME_SOUND_DISCRIMINATION = "grapheme_sound_discrimination"
    TARGETED_READING = "targeted_reading"
    SURVIVAL_EXCHANGE = "survival_exchange"


def _invalid(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


@dataclass(frozen=True, slots=True)
class FoundationMeasurement:
    block: FoundationBlock
    criterion: FoundationCriterion | None
    score: int
    maximum: int
    session_id: UUID
    at: datetime
    revealed: bool
    evaluable: bool

    def __post_init__(self) -> None:
        if self.session_id.version != 7:
            raise _invalid("session_id must be UUIDv7")
        if self.maximum < 1 or self.score < 0 or self.score > self.maximum:
            raise _invalid("measurement score is outside its bounds")
        if self.at.tzinfo is None or self.at.utcoffset() != timedelta(0):
            raise _invalid("measurement timestamp must be UTC")

    @property
    def ratio(self) -> float:
        return self.score / self.maximum


@dataclass(frozen=True, slots=True)
class FoundationGateResult:
    passed: bool
    reasons: tuple[str, ...]
    not_evaluable_blocks: tuple[FoundationBlock, ...]
    implicit_mastery_target_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class FoundationGate:
    gate_code: str
    revision: int
    grapheme_sound_minimum: int
    grapheme_sound_total: int
    targeted_reading_minimum: int
    targeted_reading_total: int
    survival_exchange_minimum: int
    survival_exchange_total: int
    delayed_control_after: timedelta

    @classmethod
    def v0(cls) -> "FoundationGate":
        return cls(
            gate_code="FOUNDATIONS_IT_V0",
            revision=1,
            grapheme_sound_minimum=8,
            grapheme_sound_total=10,
            targeted_reading_minimum=8,
            targeted_reading_total=10,
            survival_exchange_minimum=4,
            survival_exchange_total=5,
            delayed_control_after=timedelta(hours=24),
        )

    def evaluate(
        self,
        measurements: tuple[FoundationMeasurement, ...],
    ) -> FoundationGateResult:
        if not measurements:
            return FoundationGateResult(False, ("measurements_missing",), ())
        not_evaluable = tuple(
            block
            for block in FoundationBlock
            if any(item.block is block and not item.evaluable for item in measurements)
        )
        reasons: list[str] = []
        sessions = {item.session_id for item in measurements if item.evaluable}
        if len(sessions) < 2:
            reasons.append("two_sessions_required")
        if not self._has_criterion_pass(
            FoundationCriterion.GRAPHEME_SOUND_DISCRIMINATION,
            self.grapheme_sound_minimum,
            self.grapheme_sound_total,
            2,
            measurements,
        ):
            reasons.append("grapheme_sound_discrimination_incomplete")
        if not self._has_criterion_pass(
            FoundationCriterion.TARGETED_READING,
            self.targeted_reading_minimum,
            self.targeted_reading_total,
            2,
            measurements,
        ):
            reasons.append("targeted_reading_incomplete")
        for block in (FoundationBlock.F3, FoundationBlock.F4):
            if not self._has_block_pass(block, measurements):
                reasons.append(f"{block.value}_incomplete")
        if not self._has_criterion_pass(
            FoundationCriterion.SURVIVAL_EXCHANGE,
            self.survival_exchange_minimum,
            self.survival_exchange_total,
            1,
            measurements,
        ):
            reasons.append("repair_not_autonomous")
        if not self._has_delayed_f1_control(measurements):
            reasons.append("delayed_control_missing")
        if FoundationBlock.F1 in not_evaluable:
            reasons.append("f1_not_evaluable")
        return FoundationGateResult(
            passed=not reasons,
            reasons=tuple(reasons),
            not_evaluable_blocks=not_evaluable,
        )

    @staticmethod
    def _has_block_pass(
        block: FoundationBlock,
        measurements: tuple[FoundationMeasurement, ...],
    ) -> bool:
        return any(
            item.block is block
            and item.criterion is None
            and item.evaluable
            and not item.revealed
            and item.ratio >= 0.8
            for item in measurements
        )

    @staticmethod
    def _has_criterion_pass(
        criterion: FoundationCriterion,
        minimum: int,
        total: int,
        minimum_sessions: int,
        measurements: tuple[FoundationMeasurement, ...],
    ) -> bool:
        sessions = {
            item.session_id
            for item in measurements
            if item.criterion is criterion
            and item.evaluable
            and not item.revealed
            and item.maximum == total
            and item.score >= minimum
        }
        return len(sessions) >= minimum_sessions

    def _has_delayed_f1_control(
        self,
        measurements: tuple[FoundationMeasurement, ...],
    ) -> bool:
        return all(
            self._has_delayed_criterion_control(criterion, minimum, total, measurements)
            for criterion, minimum, total in (
                (
                    FoundationCriterion.GRAPHEME_SOUND_DISCRIMINATION,
                    self.grapheme_sound_minimum,
                    self.grapheme_sound_total,
                ),
                (
                    FoundationCriterion.TARGETED_READING,
                    self.targeted_reading_minimum,
                    self.targeted_reading_total,
                ),
            )
        )

    def _has_delayed_criterion_control(
        self,
        criterion: FoundationCriterion,
        minimum: int,
        total: int,
        measurements: tuple[FoundationMeasurement, ...],
    ) -> bool:
        eligible = tuple(
            item
            for item in measurements
            if item.criterion is criterion
            and item.evaluable
            and not item.revealed
            and item.maximum == total
            and item.score >= minimum
        )
        return any(
            later.at - earlier.at >= self.delayed_control_after
            and later.session_id != earlier.session_id
            for earlier in eligible
            for later in eligible
        )
