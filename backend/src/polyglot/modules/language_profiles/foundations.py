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


def _invalid(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


@dataclass(frozen=True, slots=True)
class FoundationMeasurement:
    block: FoundationBlock
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
    minimum_ratio: float
    delayed_control_after: timedelta

    @classmethod
    def v0(cls) -> "FoundationGate":
        return cls(
            gate_code="FOUNDATIONS_IT_V0",
            revision=1,
            minimum_ratio=0.8,
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
        for block in (FoundationBlock.F1, FoundationBlock.F3, FoundationBlock.F4):
            if not self._has_autonomous_pass(block, measurements):
                reasons.append(f"{block.value}_incomplete")
        if not self._has_autonomous_pass(FoundationBlock.F5, measurements):
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

    def _has_autonomous_pass(
        self,
        block: FoundationBlock,
        measurements: tuple[FoundationMeasurement, ...],
    ) -> bool:
        return any(
            item.block is block
            and item.evaluable
            and not item.revealed
            and item.ratio >= self.minimum_ratio
            for item in measurements
        )

    def _has_delayed_f1_control(
        self,
        measurements: tuple[FoundationMeasurement, ...],
    ) -> bool:
        f1 = tuple(
            item
            for item in measurements
            if item.block is FoundationBlock.F1
            and item.evaluable
            and not item.revealed
            and item.ratio >= self.minimum_ratio
        )
        return any(
            later.at - earlier.at >= self.delayed_control_after
            and later.session_id != earlier.session_id
            for earlier in f1
            for later in f1
        )
