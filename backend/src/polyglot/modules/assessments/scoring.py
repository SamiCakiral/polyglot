from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

from polyglot.modules.assessments.domain import (
    AssessmentBand,
    AssessmentModality,
    AssessmentResultStatus,
)


@dataclass(frozen=True, slots=True)
class ScoreUnit:
    key: str
    facet: str
    weight: float
    normalized_score: float | None
    correction_confidence: float | None
    evaluable: bool
    answered: bool
    critical: bool = False

    def __post_init__(self) -> None:
        if not self.key or not self.facet or not math.isfinite(self.weight) or self.weight <= 0:
            raise ValueError("invalid_score_unit")
        for value in (self.normalized_score, self.correction_confidence):
            if value is not None and (not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError("invalid_score_unit")


@dataclass(frozen=True, slots=True)
class AssessmentScore:
    modality: AssessmentModality
    status: AssessmentResultStatus
    score: float | None
    band: AssessmentBand | None
    confidence: float
    coverage: float
    integrity_factor: float
    limiting_criteria: tuple[str, ...]
    evaluable_units: int


def normalize_multiple_choice(raw_score: float, *, option_count: int) -> float:
    if option_count < 2 or not 0 <= raw_score <= 1:
        raise ValueError("invalid_multiple_choice_score")
    chance = 1 / option_count
    return min(max((raw_score - chance) / (1 - chance), 0), 1)


def _band(score: float) -> AssessmentBand:
    if score < 0.25:
        return AssessmentBand.ASSESS_B0
    if score < 0.45:
        return AssessmentBand.ASSESS_B1
    if score < 0.65:
        return AssessmentBand.ASSESS_B2
    if score < 0.80:
        return AssessmentBand.ASSESS_B3
    return AssessmentBand.ASSESS_B4


def score_assessment(
    modality: AssessmentModality,
    units: tuple[ScoreUnit, ...],
    *,
    minimum_units: int,
    planned_weight: float,
    integrity_factor: float = 1,
) -> AssessmentScore:
    if minimum_units < 1 or planned_weight <= 0 or not 0 <= integrity_factor <= 1:
        raise ValueError("invalid_scoring_policy")
    evaluable = tuple(
        unit
        for unit in units
        if unit.evaluable and unit.answered and unit.normalized_score is not None
    )
    evaluable_weight = sum(unit.weight for unit in evaluable)
    coverage = min(evaluable_weight / planned_weight, 1)
    if not evaluable or evaluable_weight <= 0:
        return AssessmentScore(
            modality=modality,
            status=AssessmentResultStatus.NOT_EVALUABLE,
            score=None,
            band=None,
            confidence=0,
            coverage=coverage,
            integrity_factor=integrity_factor,
            limiting_criteria=(),
            evaluable_units=0,
        )

    score = sum(
        unit.weight * cast(float, unit.normalized_score) for unit in evaluable
    ) / evaluable_weight
    correction_confidence = sum(
        unit.weight * (unit.correction_confidence or 0) for unit in evaluable
    ) / evaluable_weight
    sample_factor = min(math.sqrt(len(evaluable) / minimum_units), 1)
    confidence = min(max(coverage * correction_confidence * sample_factor * integrity_factor, 0), 1)
    status = (
        AssessmentResultStatus.VALID
        if coverage >= 0.8 and len(evaluable) >= minimum_units and confidence >= 0.6
        else AssessmentResultStatus.INDICATIVE
    )
    band = _band(score)
    limiting = tuple(
        sorted(
            {
                unit.facet
                for unit in evaluable
                if unit.critical and cast(float, unit.normalized_score) < 0.25
            }
        )
    )
    if limiting and band in {
        AssessmentBand.ASSESS_B2,
        AssessmentBand.ASSESS_B3,
        AssessmentBand.ASSESS_B4,
    }:
        band = AssessmentBand.ASSESS_B1
    return AssessmentScore(
        modality=modality,
        status=status,
        score=score,
        band=band,
        confidence=confidence,
        coverage=coverage,
        integrity_factor=integrity_factor,
        limiting_criteria=limiting,
        evaluable_units=len(evaluable),
    )
