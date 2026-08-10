from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from polyglot.modules.progress.domain import (
    DelayBand,
    EvidenceSource,
    HelpLevel,
    LearningObservation,
    MasteryStatus,
    Modality,
    ObservationResult,
    ObservationRole,
    evidence_from_observation,
    project_mastery,
    replace_observation,
)
from polyglot.modules.progress.recommendations import (
    LearningNeedStatus,
    RecommendationFactors,
    open_learning_need,
    recommend_for_need,
    resolve_learning_need,
)

NOW = datetime(2026, 8, 10, 12, tzinfo=UTC)


def _uuid(index: int) -> UUID:
    return UUID(f"00000000-0000-7000-8000-{index:012d}")


def _observation(index: int, **changes: object) -> LearningObservation:
    values: dict[str, object] = {
        "observation_id": _uuid(100 + index),
        "profile_id": _uuid(1),
        "attempt_id": _uuid(200 + index),
        "correction_id": _uuid(300 + index),
        "target_type": "grammar_structure",
        "target_id": "it.futuro-prossimo",
        "facet_key": "controlled-production",
        "modality": Modality.WRITING,
        "operation": "transform",
        "role": ObservationRole.PRIMARY,
        "result": ObservationResult.SUCCESS,
        "observation_value": 0.75,
        "correction_confidence": 1.0,
        "target_coverage": 1.0,
        "help_level": HelpLevel.H0,
        "opportunity_id": _uuid(400 + index),
        "pedagogical_session_id": f"session-{index}",
        "context_family_id": f"context-{index}",
        "source": EvidenceSource.PLANNED_SPRINT,
        "delay_band": DelayBand.SAME_SESSION,
        "policy_revision_id": "OBSERVATION_V0",
        "created_at": NOW + timedelta(minutes=index),
    }
    values.update(changes)
    return LearningObservation(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"result": ObservationResult.INCONCLUSIVE}, "inconclusive"),
        ({"help_level": HelpLevel.H4, "operation": "recall"}, "answer_revealed"),
        ({"correction_confidence": 0.79}, "correction_confidence_low"),
        ({"contested": True}, "correction_contested"),
        ({"target_required": False, "target_discriminating": False}, "target_not_tested"),
        ({"source": EvidenceSource.DECLARATION_OR_EXPOSURE}, "source_has_zero_weight"),
    ],
)
def test_ineligible_observations_remain_auditable_without_credit(
    changes: dict[str, object], reason: str
) -> None:
    evidence, reasons = evidence_from_observation(
        _observation(1, **changes),
        evidence_id=_uuid(900),
    )

    assert evidence.eligible is False
    assert evidence.evidence_mass == 0
    assert reason in reasons


def test_correction_replacement_invalidates_old_fact_without_deleting_it() -> None:
    original = _observation(1)
    replacement = _observation(2, correction_id=_uuid(999), observation_value=-0.75)

    invalidated, current = replace_observation(
        original,
        replacement,
        replaced_at=NOW + timedelta(hours=1),
        reason="correction_revised",
    )

    assert invalidated.invalidated_at is not None
    assert invalidated.replacement_observation_id == current.observation_id
    assert current.invalidated_at is None


def test_debt_is_opened_by_taught_direct_failure_and_requires_new_success_to_resolve() -> None:
    failed_evidence, _ = evidence_from_observation(
        _observation(1, result=ObservationResult.FAILURE, observation_value=-0.75),
        evidence_id=_uuid(901),
    )
    need = open_learning_need(
        need_id=_uuid(600),
        cause_id=_uuid(601),
        evidence=failed_evidence,
        opened_at=NOW,
        taught=True,
    )
    assert need is not None
    assert need.status is LearningNeedStatus.OPEN

    weak_success, _ = evidence_from_observation(
        _observation(2, observation_value=0.1),
        evidence_id=_uuid(902),
    )
    assert resolve_learning_need(need, weak_success, resolved_at=NOW) is need

    strong_success, _ = evidence_from_observation(_observation(3), evidence_id=_uuid(903))
    resolved = resolve_learning_need(need, strong_success, resolved_at=strong_success.created_at)
    assert resolved.status is LearningNeedStatus.RESOLVED
    assert resolved.resolution_evidence_id == strong_success.evidence_id


def test_new_untaught_target_failure_does_not_open_automatic_debt() -> None:
    evidence, _ = evidence_from_observation(
        _observation(1, result=ObservationResult.FAILURE, observation_value=-1.0),
        evidence_id=_uuid(901),
    )
    assert (
        open_learning_need(
            need_id=_uuid(600),
            cause_id=_uuid(601),
            evidence=evidence,
            opened_at=NOW,
            taught=False,
        )
        is None
    )


def test_recommendation_has_deterministic_priority_and_explanation() -> None:
    evidence, _ = evidence_from_observation(
        _observation(1, result=ObservationResult.FAILURE, observation_value=-0.75),
        evidence_id=_uuid(901),
    )
    need = open_learning_need(
        need_id=_uuid(600),
        cause_id=_uuid(601),
        evidence=evidence,
        opened_at=NOW,
        taught=True,
    )
    assert need is not None
    projection = project_mastery((evidence,), as_of=NOW)
    assert projection.status is MasteryStatus.IN_PROGRESS

    recommendation = recommend_for_need(
        recommendation_id=_uuid(700),
        need=need,
        projection=projection,
        factors=RecommendationFactors(1.0, 0.8, 1.0, 0.9, 0.5),
        created_at=NOW,
    )

    assert recommendation.priority == pytest.approx(0.885)
    assert recommendation.reason_code == "prerequisite_learning_need"
    assert recommendation.missing_evidence_spec
    assert recommendation.proposed_activity["primitive_id"] == "EX-TRANSFORM-01"
    assert recommendation.expires_at > recommendation.created_at
