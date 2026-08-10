from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from polyglot.platform.fingerprint import canonical_json_fingerprint

POLICY_REVISION = "MASTERY_V0"
PRIOR_MASS = 2.0
PRIOR_SCORE = 0.5


class Modality(StrEnum):
    READING = "reading"
    LISTENING = "listening"
    WRITING = "writing"
    SPEAKING = "speaking"


class MasteryStatus(StrEnum):
    NON_OBSERVED = "non_observed"
    DISCOVERED = "discovered"
    IN_PROGRESS = "in_progress"
    RELIABLE = "reliable"
    MASTERED = "mastered"
    REVIEW_DUE = "review_due"
    NOT_EVALUABLE = "not_evaluable"


class DelayBand(StrEnum):
    SAME_SESSION = "same_session"
    ONE_TO_SIX_DAYS = "one_to_six_days"
    SEVEN_DAYS_OR_MORE = "seven_days_or_more"


class EvidenceSource(StrEnum):
    VALID_ASSESSMENT = "assessment"
    PLANNED_SPRINT = "daily_sprint"
    GUIDED_FOUNDATION = "foundations"
    FREE_PRACTICE = "free_practice"
    ADAPTIVE_DIAGNOSTIC = "diagnostic"
    DECLARATION_OR_EXPOSURE = "declaration"


SOURCE_WEIGHTS = {
    EvidenceSource.VALID_ASSESSMENT: 1.0,
    EvidenceSource.PLANNED_SPRINT: 0.9,
    EvidenceSource.GUIDED_FOUNDATION: 0.9,
    EvidenceSource.FREE_PRACTICE: 0.75,
    EvidenceSource.ADAPTIVE_DIAGNOSTIC: 0.7,
    EvidenceSource.DECLARATION_OR_EXPOSURE: 0.0,
}


class ObservationRole(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    SUPPORT = "support"
    DISTRACTOR = "distractor"


class ObservationResult(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    INCONCLUSIVE = "inconclusive"


class HelpLevel(StrEnum):
    H0 = "h0"
    H1 = "h1"
    H2 = "h2"
    H3 = "h3"
    H4 = "h4"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class LearningEvidence:
    evidence_id: UUID
    observation_id: UUID
    profile_id: UUID
    target_type: str
    target_id: str
    facet_key: str
    modality: Modality
    operation: str
    evidence_score: float
    evidence_mass: float
    source_weight: float
    independence_weight: float
    opportunity_id: UUID
    pedagogical_session_id: str
    context_family_id: str
    delay_band: DelayBand
    transfer: bool
    policy_revision_id: str
    created_at: datetime
    eligible: bool = True
    direct: bool = True
    invalidated_at: datetime | None = None
    replacement_evidence_id: UUID | None = None

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        if self.invalidated_at is not None:
            _require_aware(self.invalidated_at, "invalidated_at")
        if not self.target_type or not self.target_id or not self.facet_key or not self.operation:
            raise ValueError("evidence target is incomplete")
        if not self.pedagogical_session_id or not self.context_family_id:
            raise ValueError("evidence diversity identifiers are required")
        if not 0 <= self.evidence_score <= 1:
            raise ValueError("evidence_score must be bounded")
        if not 0 <= self.evidence_mass <= 1:
            raise ValueError("evidence_mass must be bounded")
        if not 0 <= self.source_weight <= 1 or not 0 <= self.independence_weight <= 1:
            raise ValueError("evidence weights must be bounded")
        expected_mass = _clamp(self.source_weight * self.independence_weight)
        if not math.isclose(self.evidence_mass, expected_mass, abs_tol=1e-9):
            raise ValueError("evidence_mass must match pinned weights")

    @classmethod
    def from_observation_value(
        cls,
        *,
        evidence_id: UUID,
        observation_id: UUID,
        profile_id: UUID,
        target_type: str,
        target_id: str,
        facet_key: str,
        modality: Modality,
        operation: str,
        observation_value: float,
        source: EvidenceSource,
        independence_weight: float,
        opportunity_id: UUID,
        pedagogical_session_id: str,
        context_family_id: str,
        delay_band: DelayBand,
        transfer: bool,
        policy_revision_id: str,
        created_at: datetime,
        eligible: bool = True,
        direct: bool = True,
        invalidated_at: datetime | None = None,
        replacement_evidence_id: UUID | None = None,
    ) -> LearningEvidence:
        if not -1 <= observation_value <= 1:
            raise ValueError("observation_value must be in [-1, 1]")
        source_weight = SOURCE_WEIGHTS[source]
        if not direct:
            source_weight = min(source_weight, 0.25)
        return cls(
            evidence_id=evidence_id,
            observation_id=observation_id,
            profile_id=profile_id,
            target_type=target_type,
            target_id=target_id,
            facet_key=facet_key,
            modality=modality,
            operation=operation,
            evidence_score=_clamp((observation_value + 1.0) / 2.0),
            evidence_mass=_clamp(source_weight * independence_weight),
            source_weight=source_weight,
            independence_weight=independence_weight,
            opportunity_id=opportunity_id,
            pedagogical_session_id=pedagogical_session_id,
            context_family_id=context_family_id,
            delay_band=delay_band,
            transfer=transfer,
            policy_revision_id=policy_revision_id,
            created_at=created_at,
            eligible=eligible,
            direct=direct,
            invalidated_at=invalidated_at,
            replacement_evidence_id=replacement_evidence_id,
        )


@dataclass(frozen=True, slots=True)
class LearningObservation:
    observation_id: UUID
    profile_id: UUID
    attempt_id: UUID
    correction_id: UUID
    target_type: str
    target_id: str
    facet_key: str
    modality: Modality
    operation: str
    role: ObservationRole
    result: ObservationResult
    observation_value: float
    correction_confidence: float
    target_coverage: float
    help_level: HelpLevel
    opportunity_id: UUID
    pedagogical_session_id: str
    context_family_id: str
    source: EvidenceSource
    delay_band: DelayBand
    policy_revision_id: str
    created_at: datetime
    target_required: bool = True
    target_discriminating: bool = True
    protocol_valid: bool = True
    submitted: bool = True
    correction_available: bool = True
    help_known: bool = True
    contested: bool = False
    target_defective: bool = False
    transfer: bool = False
    direct: bool = True
    independence_weight: float = 1.0
    invalidated_at: datetime | None = None
    replacement_observation_id: UUID | None = None
    invalidation_reason: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        if self.invalidated_at is not None:
            _require_aware(self.invalidated_at, "invalidated_at")
        if not -1 <= self.observation_value <= 1:
            raise ValueError("observation_value must be in [-1, 1]")
        if not 0 <= self.correction_confidence <= 1 or not 0 <= self.target_coverage <= 1:
            raise ValueError("observation confidence and coverage must be bounded")
        if not 0 <= self.independence_weight <= 1:
            raise ValueError("independence_weight must be bounded")
        if not self.target_id or not self.facet_key or not self.pedagogical_session_id:
            raise ValueError("observation target and session are required")
        if (self.invalidated_at is None) != (self.invalidation_reason is None):
            raise ValueError("observation invalidation requires timestamp and reason")


def observation_ineligibility_reasons(observation: LearningObservation) -> tuple[str, ...]:
    reasons: list[str] = []
    if observation.invalidated_at is not None:
        reasons.append("observation_invalidated")
    if not observation.target_required and not observation.target_discriminating:
        reasons.append("target_not_tested")
    if not observation.protocol_valid:
        reasons.append("protocol_invalid")
    if not observation.submitted:
        reasons.append("response_not_submitted")
    if not observation.correction_available:
        reasons.append("correction_unavailable")
    if observation.correction_confidence < 0.8:
        reasons.append("correction_confidence_low")
    if not observation.help_known:
        reasons.append("help_unknown")
    if observation.help_level is HelpLevel.H4 and observation.operation == "recall":
        reasons.append("answer_revealed")
    if observation.result is ObservationResult.INCONCLUSIVE:
        reasons.append("inconclusive")
    if observation.contested:
        reasons.append("correction_contested")
    if observation.target_defective:
        reasons.append("target_defective")
    if SOURCE_WEIGHTS[observation.source] == 0:
        reasons.append("source_has_zero_weight")
    if observation.independence_weight == 0:
        reasons.append("identical_replay")
    return tuple(reasons)


def evidence_from_observation(
    observation: LearningObservation,
    *,
    evidence_id: UUID,
    policy_revision_id: str = POLICY_REVISION,
) -> tuple[LearningEvidence, tuple[str, ...]]:
    reasons = observation_ineligibility_reasons(observation)
    evidence = LearningEvidence.from_observation_value(
        evidence_id=evidence_id,
        observation_id=observation.observation_id,
        profile_id=observation.profile_id,
        target_type=observation.target_type,
        target_id=observation.target_id,
        facet_key=observation.facet_key,
        modality=observation.modality,
        operation=observation.operation,
        observation_value=observation.observation_value,
        source=observation.source,
        independence_weight=0.0 if reasons else observation.independence_weight,
        opportunity_id=observation.opportunity_id,
        pedagogical_session_id=observation.pedagogical_session_id,
        context_family_id=observation.context_family_id,
        delay_band=observation.delay_band,
        transfer=observation.transfer,
        policy_revision_id=policy_revision_id,
        created_at=observation.created_at,
        eligible=not reasons,
        direct=observation.direct,
    )
    return evidence, reasons


def replace_observation(
    original: LearningObservation,
    replacement: LearningObservation,
    *,
    replaced_at: datetime,
    reason: str,
) -> tuple[LearningObservation, LearningObservation]:
    _require_aware(replaced_at, "replaced_at")
    if original.invalidated_at is not None:
        raise ValueError("observation is already invalidated")
    identity = ("profile_id", "target_type", "target_id", "facet_key", "modality")
    if any(getattr(original, field) != getattr(replacement, field) for field in identity):
        raise ValueError("replacement observation must preserve its projection target")
    if replacement.invalidated_at is not None or not reason:
        raise ValueError("replacement must be current and invalidation reason is required")
    return (
        replace(
            original,
            invalidated_at=replaced_at,
            replacement_observation_id=replacement.observation_id,
            invalidation_reason=reason,
        ),
        replacement,
    )


@dataclass(frozen=True, slots=True)
class MasteryProjection:
    status: MasteryStatus
    modality: Modality | None
    mastery_base: float
    mastery_current: float
    confidence: float
    freshness: float
    effective_mass: float
    success_count: int
    failure_count: int
    context_count: int
    session_count: int
    delay_band_count: int
    transfer_count: int
    evidence_ids: tuple[UUID, ...]
    last_evidence_at: datetime | None
    next_verification_at: datetime | None
    policy_revision_id: str


@dataclass(frozen=True, slots=True)
class ModalityProjection:
    modality: Modality
    status: MasteryStatus
    score: float | None
    confidence: float
    freshness: float | None
    coverage: float
    observed_weight: float
    eligible_weight: float
    observed_facet_count: int


def _current_evidence(evidence: tuple[LearningEvidence, ...]) -> tuple[LearningEvidence, ...]:
    by_opportunity: dict[UUID, LearningEvidence] = {}
    for item in evidence:
        if not item.eligible or item.invalidated_at is not None or item.evidence_mass <= 0:
            continue
        previous = by_opportunity.get(item.opportunity_id)
        if previous is None or (
            item.independence_weight,
            item.created_at,
            item.evidence_id.int,
        ) > (
            previous.independence_weight,
            previous.created_at,
            previous.evidence_id.int,
        ):
            by_opportunity[item.opportunity_id] = item
    return tuple(
        sorted(by_opportunity.values(), key=lambda item: (item.created_at, item.evidence_id.int))
    )


def _gate_candidate(
    *,
    mastery_base: float,
    successes: int,
    sessions: int,
    contexts: int,
    delays: set[DelayBand],
    transfers: int,
) -> MasteryStatus:
    delayed_24h = bool(delays & {DelayBand.ONE_TO_SIX_DAYS, DelayBand.SEVEN_DAYS_OR_MORE})
    delayed_7d = DelayBand.SEVEN_DAYS_OR_MORE in delays
    if (
        mastery_base >= 0.85
        and successes >= 5
        and sessions >= 3
        and contexts >= 3
        and transfers >= 1
        and delayed_7d
    ):
        return MasteryStatus.MASTERED
    if mastery_base >= 0.75 and successes >= 3 and sessions >= 2 and contexts >= 2 and delayed_24h:
        return MasteryStatus.RELIABLE
    return MasteryStatus.IN_PROGRESS


def project_mastery(
    evidence: tuple[LearningEvidence, ...],
    *,
    as_of: datetime,
    modality: Modality | None = None,
    previous_status: MasteryStatus | None = None,
    discovered: bool = False,
    attempted_but_not_evaluable: bool = False,
    policy_revision_id: str = POLICY_REVISION,
) -> MasteryProjection:
    _require_aware(as_of, "as_of")
    relevant = tuple(item for item in evidence if modality is None or item.modality is modality)
    current = _current_evidence(relevant)
    if not current:
        status = (
            MasteryStatus.NOT_EVALUABLE
            if attempted_but_not_evaluable
            else MasteryStatus.DISCOVERED
            if discovered
            else MasteryStatus.NON_OBSERVED
        )
        return MasteryProjection(
            status=status,
            modality=modality,
            mastery_base=0.5,
            mastery_current=0.5,
            confidence=0.0,
            freshness=0.0,
            effective_mass=0.0,
            success_count=0,
            failure_count=0,
            context_count=0,
            session_count=0,
            delay_band_count=0,
            transfer_count=0,
            evidence_ids=(),
            last_evidence_at=None,
            next_verification_at=None,
            policy_revision_id=policy_revision_id,
        )

    keys = {
        (item.profile_id, item.target_type, item.target_id, item.facet_key, item.modality)
        for item in current
    }
    if len(keys) != 1:
        raise ValueError("a mastery projection requires one profile, target, facet and modality")
    effective_mass = sum(item.evidence_mass for item in current)
    weighted_score = sum(item.evidence_mass * item.evidence_score for item in current)
    mastery_base = _clamp(
        (PRIOR_MASS * PRIOR_SCORE + weighted_score) / (PRIOR_MASS + effective_mass)
    )
    successes = sum(item.evidence_score > 0.5 for item in current)
    failures = sum(item.evidence_score < 0.5 for item in current)
    sessions = {item.pedagogical_session_id for item in current}
    contexts = {item.context_family_id for item in current}
    delays = {item.delay_band for item in current}
    transfers = sum(item.transfer for item in current)
    candidate = _gate_candidate(
        mastery_base=mastery_base,
        successes=successes,
        sessions=len(sessions),
        contexts=len(contexts),
        delays=delays,
        transfers=transfers,
    )
    horizon_days = {
        MasteryStatus.IN_PROGRESS: 3,
        MasteryStatus.RELIABLE: 21,
        MasteryStatus.MASTERED: 60,
    }[candidate]
    last_at = max(item.created_at for item in current)
    age_days = max(0.0, (as_of - last_at).total_seconds() / 86400)
    freshness = _clamp(2 ** (-age_days / horizon_days))
    projected_modality = next(iter(keys))[4]
    retention_floor = 0.55 if projected_modality in {Modality.READING, Modality.LISTENING} else 0.4
    mastery_current = _clamp(mastery_base * (retention_floor + (1 - retention_floor) * freshness))
    context_diversity = min(len(contexts) / 3, 1.0)
    session_diversity = min(len(sessions) / 3, 1.0)
    delay_diversity = min(len(delays) / 3, 1.0)
    confidence = _clamp(
        (1 - math.exp(-effective_mass / 3))
        * (0.4 + 0.2 * context_diversity + 0.2 * session_diversity + 0.2 * delay_diversity)
        * (0.75 + 0.25 * freshness)
    )
    status = candidate
    if candidate is MasteryStatus.MASTERED and confidence < 0.75:
        status = MasteryStatus.RELIABLE if confidence >= 0.6 else MasteryStatus.IN_PROGRESS
    elif candidate is MasteryStatus.RELIABLE and confidence < 0.6:
        status = MasteryStatus.IN_PROGRESS
    recent_direct_failures = sum(item.direct and item.evidence_score < 0.5 for item in current[-2:])
    was_high = previous_status in {MasteryStatus.RELIABLE, MasteryStatus.MASTERED}
    if (was_high or candidate in {MasteryStatus.RELIABLE, MasteryStatus.MASTERED}) and (
        freshness < 0.5 or recent_direct_failures >= 2
    ):
        status = MasteryStatus.REVIEW_DUE
    return MasteryProjection(
        status=status,
        modality=projected_modality,
        mastery_base=mastery_base,
        mastery_current=mastery_current,
        confidence=confidence,
        freshness=freshness,
        effective_mass=effective_mass,
        success_count=successes,
        failure_count=failures,
        context_count=len(contexts),
        session_count=len(sessions),
        delay_band_count=len(delays),
        transfer_count=transfers,
        evidence_ids=tuple(item.evidence_id for item in current),
        last_evidence_at=last_at,
        next_verification_at=last_at + timedelta(days=horizon_days),
        policy_revision_id=policy_revision_id,
    )


def project_modality(
    modality: Modality,
    weighted_facets: tuple[tuple[MasteryProjection, float], ...],
    *,
    eligible_weight: float,
) -> ModalityProjection:
    if eligible_weight < 0 or any(weight <= 0 for _, weight in weighted_facets):
        raise ValueError("modality weights must be positive")
    if any(item.modality is not modality for item, _ in weighted_facets):
        raise ValueError("modality projection cannot mix modalities")
    observed = tuple((item, weight) for item, weight in weighted_facets if item.effective_mass > 0)
    observed_weight = sum(weight for _, weight in observed)
    denominator = sum(weight * item.confidence for item, weight in observed)
    coverage = _clamp(observed_weight / eligible_weight) if eligible_weight else 0.0
    if not observed or denominator == 0:
        return ModalityProjection(
            modality,
            MasteryStatus.NON_OBSERVED,
            None,
            0.0,
            None,
            coverage,
            observed_weight,
            eligible_weight,
            len(observed),
        )
    score = (
        sum(weight * item.mastery_current * item.confidence for item, weight in observed)
        / denominator
    )
    freshness = (
        sum(weight * item.confidence * item.freshness for item, weight in observed) / denominator
    )
    confidence = _clamp(coverage * denominator / eligible_weight) if eligible_weight else 0.0
    statuses = {item.status for item, _ in observed}
    if MasteryStatus.REVIEW_DUE in statuses or freshness < 0.5:
        status = MasteryStatus.REVIEW_DUE
    elif (
        score >= 0.85
        and confidence >= 0.75
        and coverage >= 0.85
        and all(
            item.status in {MasteryStatus.RELIABLE, MasteryStatus.MASTERED} for item, _ in observed
        )
    ):
        status = MasteryStatus.MASTERED
    elif (
        score >= 0.75
        and confidence >= 0.6
        and coverage >= 0.7
        and all(item.status is not MasteryStatus.NON_OBSERVED for item, _ in observed)
    ):
        status = MasteryStatus.RELIABLE
    else:
        status = MasteryStatus.IN_PROGRESS
    return ModalityProjection(
        modality,
        status,
        score,
        confidence,
        freshness,
        coverage,
        observed_weight,
        eligible_weight,
        len(observed),
    )


def projection_fingerprint(projection: MasteryProjection) -> str:
    return canonical_json_fingerprint(
        {
            "status": projection.status.value,
            "modality": projection.modality.value if projection.modality else None,
            "mastery_base": projection.mastery_base,
            "mastery_current": projection.mastery_current,
            "confidence": projection.confidence,
            "freshness": projection.freshness,
            "effective_mass": projection.effective_mass,
            "success_count": projection.success_count,
            "failure_count": projection.failure_count,
            "context_count": projection.context_count,
            "session_count": projection.session_count,
            "delay_band_count": projection.delay_band_count,
            "transfer_count": projection.transfer_count,
            "evidence_ids": [str(value) for value in projection.evidence_ids],
            "last_evidence_at": (
                projection.last_evidence_at.isoformat() if projection.last_evidence_at else None
            ),
            "next_verification_at": (
                projection.next_verification_at.isoformat()
                if projection.next_verification_at
                else None
            ),
            "policy_revision_id": projection.policy_revision_id,
        }
    )
