from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from polyglot.modules.progress.domain import LearningEvidence, MasteryProjection


class LearningNeedStatus(StrEnum):
    OPEN = "open"
    PLANNED = "planned"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class LearningNeedCause:
    cause_id: UUID
    cause_type: str
    source_fact_id: UUID
    opened_at: datetime


@dataclass(frozen=True, slots=True)
class LearningNeed:
    need_id: UUID
    profile_id: UUID
    target_type: str
    target_id: str
    facet_key: str
    status: LearningNeedStatus
    urgency: float
    causes: tuple[LearningNeedCause, ...]
    opened_at: datetime
    planned_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution_policy_revision_id: str | None = None
    resolution_evidence_id: UUID | None = None
    superseded_by_need_id: UUID | None = None
    version: int = 1


@dataclass(frozen=True, slots=True)
class RecommendationFactors:
    prerequisite_block: float
    forgetting_risk: float
    active_goal: float
    observed_weakness: float
    information_gain: float

    def __post_init__(self) -> None:
        if any(not 0 <= value <= 1 for value in self.values()):
            raise ValueError("recommendation factors must be bounded")

    def values(self) -> tuple[float, ...]:
        return (
            self.prerequisite_block,
            self.forgetting_risk,
            self.active_goal,
            self.observed_weakness,
            self.information_gain,
        )

    @property
    def priority(self) -> float:
        return (
            0.30 * self.prerequisite_block
            + 0.25 * self.forgetting_risk
            + 0.20 * self.active_goal
            + 0.15 * self.observed_weakness
            + 0.10 * self.information_gain
        )


@dataclass(frozen=True, slots=True)
class Recommendation:
    recommendation_id: UUID
    profile_id: UUID
    target_type: str
    target_id: str
    facet_key: str
    need_id: UUID
    reason_code: str
    reason_params: Mapping[str, str]
    missing_evidence_spec: Mapping[str, str]
    proposed_activity: Mapping[str, str]
    priority: float
    urgency: float
    estimated_duration_ms: int
    policy_revision_id: str
    created_at: datetime
    expires_at: datetime


def open_learning_need(
    *,
    need_id: UUID,
    cause_id: UUID,
    evidence: LearningEvidence,
    opened_at: datetime,
    taught: bool,
) -> LearningNeed | None:
    if not taught or not evidence.eligible or not evidence.direct or evidence.evidence_score >= 0.5:
        return None
    cause = LearningNeedCause(cause_id, "direct_failure", evidence.evidence_id, opened_at)
    return LearningNeed(
        need_id=need_id,
        profile_id=evidence.profile_id,
        target_type=evidence.target_type,
        target_id=evidence.target_id,
        facet_key=evidence.facet_key,
        status=LearningNeedStatus.OPEN,
        urgency=max(0.0, min(1.0, 1.0 - evidence.evidence_score)),
        causes=(cause,),
        opened_at=opened_at,
    )


def resolve_learning_need(
    need: LearningNeed,
    evidence: LearningEvidence,
    *,
    resolved_at: datetime,
    policy_revision_id: str = "LEARNING_NEED_V0",
) -> LearningNeed:
    matching = (
        need.profile_id == evidence.profile_id
        and need.target_type == evidence.target_type
        and need.target_id == evidence.target_id
        and need.facet_key == evidence.facet_key
    )
    if (
        need.status not in {LearningNeedStatus.OPEN, LearningNeedStatus.PLANNED}
        or not matching
        or not evidence.eligible
        or not evidence.direct
        or evidence.evidence_score < 0.75
        or evidence.created_at <= need.opened_at
    ):
        return need
    if resolved_at < evidence.created_at:
        raise ValueError("resolution cannot predate its evidence")
    return replace(
        need,
        status=LearningNeedStatus.RESOLVED,
        resolved_at=resolved_at,
        resolution_policy_revision_id=policy_revision_id,
        resolution_evidence_id=evidence.evidence_id,
        version=need.version + 1,
    )


def recommend_for_need(
    *,
    recommendation_id: UUID,
    need: LearningNeed,
    projection: MasteryProjection,
    factors: RecommendationFactors,
    created_at: datetime,
) -> Recommendation:
    if need.status not in {LearningNeedStatus.OPEN, LearningNeedStatus.PLANNED}:
        raise ValueError("only active learning needs can be recommended")
    return Recommendation(
        recommendation_id=recommendation_id,
        profile_id=need.profile_id,
        target_type=need.target_type,
        target_id=need.target_id,
        facet_key=need.facet_key,
        need_id=need.need_id,
        reason_code="prerequisite_learning_need",
        reason_params=MappingProxyType(
            {"status": projection.status.value, "cause_count": str(len(need.causes))}
        ),
        missing_evidence_spec=MappingProxyType(
            {"minimum_score": "0.75", "independent": "true", "direct": "true"}
        ),
        proposed_activity=MappingProxyType(
            {"primitive_id": "EX-TRANSFORM-01", "mode": "controlled"}
        ),
        priority=factors.priority,
        urgency=need.urgency,
        estimated_duration_ms=180_000,
        policy_revision_id="RECOMMENDATION_V0",
        created_at=created_at,
        expires_at=created_at + timedelta(days=7),
    )
