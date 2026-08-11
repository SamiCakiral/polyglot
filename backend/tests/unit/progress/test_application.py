from __future__ import annotations

from datetime import UTC, datetime

from polyglot.modules.progress.application import SqlProgressQueryService
from polyglot.modules.progress.domain import MasteryStatus, Modality, ModalityProjection


def _projection() -> ModalityProjection:
    return ModalityProjection(
        modality=Modality.READING,
        status=MasteryStatus.IN_PROGRESS,
        score=0.61,
        confidence=0.42,
        freshness=0.9,
        coverage=0.75,
        observed_weight=3,
        eligible_weight=4,
        observed_facet_count=3,
    )


def test_modality_view_exposes_latest_independent_assessment() -> None:
    completed_at = datetime(2026, 8, 11, 12, tzinfo=UTC)

    view = SqlProgressQueryService._modality_view(
        _projection(),
        expected_count=4,
        assessment={
            "result_status": "valid",
            "score": "0.88",
            "band": "assess_b3",
            "confidence": "0.91",
            "created_at": completed_at,
        },
    )

    assert view.assessment_status == "valid"
    assert view.assessment_score == 0.88
    assert view.assessment_band == "assess_b3"
    assert view.assessment_confidence == 0.91
    assert view.assessment_completed_at == completed_at


def test_modality_view_keeps_assessment_fields_empty_without_result() -> None:
    view = SqlProgressQueryService._modality_view(
        _projection(), expected_count=4
    )

    assert view.assessment_status is None
    assert view.assessment_score is None
    assert view.assessment_band is None
    assert view.assessment_confidence is None
    assert view.assessment_completed_at is None
