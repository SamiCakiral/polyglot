from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from polyglot.modules.exercises.core.domain import (
    CorrectionResult,
    CorrectionVerdict,
    HintLevel,
)
from polyglot.platform.errors import DomainError, ErrorCode


class GymStage(StrEnum):
    G0 = "g0"
    G1 = "g1"
    G2 = "g2"
    G3 = "g3"
    G4 = "g4"


_NEXT_STAGE = {
    GymStage.G0: GymStage.G1,
    GymStage.G1: GymStage.G2,
    GymStage.G2: GymStage.G3,
    GymStage.G3: GymStage.G4,
}
_MINIMUM_OFFSETS = {
    GymStage.G0: timedelta(0),
    GymStage.G1: timedelta(0),
    GymStage.G2: timedelta(days=1),
    GymStage.G3: timedelta(days=3),
    GymStage.G4: timedelta(days=7),
}
_OPERATION_CAPS = {
    GymStage.G0: 0.0,
    GymStage.G1: 0.65,
    GymStage.G2: 0.55,
    GymStage.G3: 0.65,
    GymStage.G4: 1.0,
}


@dataclass(frozen=True, slots=True)
class GymCycleRecord:
    stage: GymStage
    verdict: CorrectionVerdict
    hint_level: HintLevel
    context_id: str
    scene_id: str
    structure_cued: bool
    recorded_at: datetime
    credit: float
    is_evidence: bool


@dataclass(frozen=True, slots=True)
class _CycleReceipt:
    idempotency_key: str
    payload: tuple[object, ...]


def _require_uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"{field} must be UUIDv7")


def _correction(verdict: CorrectionVerdict) -> CorrectionResult:
    if verdict is CorrectionVerdict.AMBIGUOUS:
        return CorrectionResult.ambiguous("Gym correction is ambiguous")
    if verdict is CorrectionVerdict.NOT_EVALUABLE:
        return CorrectionResult.not_evaluable("Gym correction is unavailable")
    confidence = 1.0
    coverage = 1.0
    return CorrectionResult(
        verdict=verdict,
        confidence=confidence,
        target_coverage=coverage,
        explanation="controlled Gym correction",
        strategy="gym_controlled",
    )


@dataclass(frozen=True, slots=True)
class GymCycle:
    cycle_id: UUID
    plan_revision_id: UUID
    grammar_target_revision_id: UUID
    started_at: datetime
    stage: GymStage = GymStage.G0
    completed: bool = False
    records: tuple[GymCycleRecord, ...] = ()
    receipts: tuple[_CycleReceipt, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "receipts", tuple(self.receipts))
        _require_uuid7(self.cycle_id, "cycle_id")
        _require_uuid7(self.plan_revision_id, "plan_revision_id")
        _require_uuid7(self.grammar_target_revision_id, "grammar_target_revision_id")
        if self.started_at.tzinfo is None:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Cycle clock must be aware")
        if self.completed and self.stage is not GymStage.G4:
            raise DomainError(ErrorCode.INVALID_TRANSITION)

    @classmethod
    def start(
        cls,
        *,
        cycle_id: UUID,
        plan_revision_id: UUID,
        grammar_target_revision_id: UUID,
        started_at: datetime,
    ) -> GymCycle:
        return cls(
            cycle_id=cycle_id,
            plan_revision_id=plan_revision_id,
            grammar_target_revision_id=grammar_target_revision_id,
            started_at=started_at,
        )

    def record(
        self,
        *,
        verdict: CorrectionVerdict,
        hint_level: HintLevel,
        context_id: str,
        scene_id: str,
        structure_cued: bool,
        recorded_at: datetime,
        idempotency_key: str,
    ) -> GymCycle:
        payload = (
            verdict,
            hint_level,
            context_id,
            scene_id,
            structure_cued,
            recorded_at,
        )
        for receipt in self.receipts:
            if receipt.idempotency_key != idempotency_key:
                continue
            if receipt.payload == payload:
                return self
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        if self.completed:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        if recorded_at.tzinfo is None or recorded_at < self.started_at:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Record clock is invalid")
        if not idempotency_key or not context_id or not scene_id:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Gym record is incomplete")
        if recorded_at < self.started_at + _MINIMUM_OFFSETS[self.stage]:
            raise DomainError(ErrorCode.GATE_NOT_READY)
        if self.stage in {GymStage.G2, GymStage.G3, GymStage.G4}:
            if hint_level in {HintLevel.H1, HintLevel.H2, HintLevel.H3}:
                raise DomainError(ErrorCode.HINT_NOT_AVAILABLE)
        if self.stage is GymStage.G3 and context_id in {
            record.context_id for record in self.records if record.stage is GymStage.G2
        }:
            raise DomainError(ErrorCode.INSUFFICIENT_COVERAGE)
        if self.stage is GymStage.G4:
            if scene_id in {record.scene_id for record in self.records}:
                raise DomainError(ErrorCode.INSUFFICIENT_COVERAGE)
            if structure_cued:
                raise DomainError(ErrorCode.EVIDENCE_SCOPE_FORBIDDEN)

        correction = _correction(verdict)
        raw_credit = correction.credit_value(
            operation_cap=_OPERATION_CAPS[self.stage],
            target_weight=1.0,
            hint_level=hint_level.value,
        )
        credit = 0.0 if raw_credit is None else raw_credit
        is_evidence = self.stage is not GymStage.G0 and raw_credit is not None and credit != 0.0
        record = GymCycleRecord(
            stage=self.stage,
            verdict=verdict,
            hint_level=hint_level,
            context_id=context_id,
            scene_id=scene_id,
            structure_cued=structure_cued,
            recorded_at=recorded_at,
            credit=credit,
            is_evidence=is_evidence,
        )
        qualifies = verdict is CorrectionVerdict.CORRECT and (
            self.stage is GymStage.G0 or credit > 0.0
        )
        next_stage = _NEXT_STAGE.get(self.stage, self.stage) if qualifies else self.stage
        completed = self.stage is GymStage.G4 and qualifies
        return replace(
            self,
            stage=next_stage,
            completed=completed,
            records=(*self.records, record),
            receipts=(*self.receipts, _CycleReceipt(idempotency_key, payload)),
        )

