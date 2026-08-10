from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from polyglot.modules.assessments.domain import AssessmentModality


class AssessmentFormUnavailable(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AssessmentFormCandidate:
    form_id: UUID
    modality: AssessmentModality
    item_ids: tuple[UUID, ...]
    current_band_weight: int
    lower_anchor_weight: int
    transfer_weight: int
    calibration_uncertainty: float
    media_cost: int
    coverage_targets: frozenset[str]
    required_capabilities: frozenset[str]
    published: bool

    @property
    def total_weight(self) -> int:
        return self.current_band_weight + self.lower_anchor_weight + self.transfer_weight

    @property
    def quota_deviation(self) -> float:
        if self.total_weight <= 0:
            return float("inf")
        ratios = (
            self.current_band_weight / self.total_weight,
            self.lower_anchor_weight / self.total_weight,
            self.transfer_weight / self.total_weight,
        )
        return sum(
            abs(actual - expected)
            for actual, expected in zip(ratios, (0.6, 0.2, 0.2), strict=True)
        )

    @property
    def meets_quota(self) -> bool:
        return self.quota_deviation <= 0.001


@dataclass(frozen=True, slots=True)
class FormExposure:
    form_id: UUID
    item_ids: frozenset[UUID]
    exposed_at: datetime


def select_assessment_form(
    *,
    candidates: tuple[AssessmentFormCandidate, ...],
    modality: AssessmentModality,
    required_targets: frozenset[str],
    capabilities: frozenset[str],
    exposures: tuple[FormExposure, ...],
    now: datetime,
    seed: str,
) -> AssessmentFormCandidate:
    recent_cutoff = now - timedelta(days=14)
    recent_form_ids = {
        exposure.form_id for exposure in exposures if exposure.exposed_at >= recent_cutoff
    }
    recent_item_ids = {
        item_id
        for exposure in exposures
        if exposure.exposed_at >= recent_cutoff
        for item_id in exposure.item_ids
    }
    exposure_count = {
        candidate.form_id: sum(exposure.form_id == candidate.form_id for exposure in exposures)
        for candidate in candidates
    }

    eligible = [
        candidate
        for candidate in candidates
        if candidate.published
        and candidate.modality is modality
        and candidate.meets_quota
        and required_targets.issubset(candidate.coverage_targets)
        and candidate.required_capabilities.issubset(capabilities)
        and candidate.form_id not in recent_form_ids
        and not recent_item_ids.intersection(candidate.item_ids)
    ]
    if not eligible:
        raise AssessmentFormUnavailable("assessment_form_unavailable")

    def rank(candidate: AssessmentFormCandidate) -> tuple[int, float, float, int, str]:
        tie = hashlib.sha256(f"{seed}:{candidate.form_id}".encode()).hexdigest()
        return (
            exposure_count[candidate.form_id],
            candidate.quota_deviation,
            candidate.calibration_uncertainty,
            candidate.media_cost,
            tie,
        )

    return min(eligible, key=rank)
