from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from polyglot.modules.progress.domain import (
    DelayBand,
    EvidenceSource,
    LearningEvidence,
    MasteryStatus,
    Modality,
    project_mastery,
    project_modality,
)

NOW = datetime(2026, 8, 10, 12, tzinfo=UTC)


def _uuid(index: int) -> UUID:
    return UUID(f"00000000-0000-7000-8000-{index:012d}")


def _evidence(
    index: int,
    *,
    value: float = 0.75,
    source: EvidenceSource = EvidenceSource.PLANNED_SPRINT,
    modality: Modality = Modality.WRITING,
    age_days: int = 0,
    context: str | None = None,
    session: str | None = None,
    delay: DelayBand = DelayBand.SAME_SESSION,
    transfer: bool = False,
    independence: float = 1.0,
    invalidated: bool = False,
    opportunity: int | None = None,
) -> LearningEvidence:
    created_at = NOW - timedelta(days=age_days)
    return LearningEvidence.from_observation_value(
        evidence_id=_uuid(1000 + index),
        observation_id=_uuid(2000 + index),
        profile_id=_uuid(1),
        target_type="skill",
        target_id=f"skill-{modality.value}",
        facet_key="controlled-production",
        modality=modality,
        operation="produce",
        observation_value=value,
        source=source,
        independence_weight=independence,
        opportunity_id=_uuid(3000 + (opportunity if opportunity is not None else index)),
        pedagogical_session_id=session or f"session-{index}",
        context_family_id=context or f"context-{index}",
        delay_band=delay,
        transfer=transfer,
        policy_revision_id="MASTERY_V0",
        created_at=created_at,
        invalidated_at=created_at if invalidated else None,
    )


def test_one_isolated_success_remains_in_progress() -> None:
    projection = project_mastery((_evidence(1),), as_of=NOW)

    assert projection.mastery_base == pytest.approx(0.616379, abs=1e-6)
    assert projection.effective_mass == pytest.approx(0.9)
    assert projection.status is MasteryStatus.IN_PROGRESS
    assert projection.success_count == 1


def test_three_successes_do_not_cross_reliable_threshold() -> None:
    projection = project_mastery(tuple(_evidence(i) for i in range(1, 4)), as_of=NOW)

    assert projection.mastery_base == pytest.approx(0.715426, abs=1e-6)
    assert projection.status is MasteryStatus.IN_PROGRESS


def test_delayed_transfer_can_make_projection_reliable_but_not_mastered() -> None:
    evidence = (
        _evidence(1, age_days=8, delay=DelayBand.SEVEN_DAYS_OR_MORE),
        _evidence(2, age_days=3, delay=DelayBand.ONE_TO_SIX_DAYS),
        _evidence(3, age_days=1, delay=DelayBand.ONE_TO_SIX_DAYS),
        _evidence(4, value=1.0, transfer=True),
    )

    projection = project_mastery(evidence, as_of=NOW)

    assert projection.mastery_base == pytest.approx(0.761161, abs=1e-6)
    assert projection.status is MasteryStatus.RELIABLE
    assert projection.transfer_count == 1
    assert projection.delay_band_count == 3


def test_same_opportunity_and_invalidated_evidence_never_multiply_credit() -> None:
    original = _evidence(1, opportunity=9, invalidated=True)
    replacement = _evidence(2, opportunity=9, value=-0.75)
    correlated_duplicate = _evidence(3, opportunity=9, independence=0.5)

    projection = project_mastery(
        (correlated_duplicate, original, replacement),
        as_of=NOW,
    )

    assert projection.effective_mass == pytest.approx(0.9)
    assert projection.failure_count == 1
    assert projection.success_count == 0


def test_modalities_are_isolated() -> None:
    delayed = (DelayBand.SAME_SESSION, DelayBand.ONE_TO_SIX_DAYS, DelayBand.SEVEN_DAYS_OR_MORE)
    reading = project_mastery(
        tuple(
            _evidence(
                i,
                modality=Modality.READING,
                value=1.0,
                delay=delayed[i % len(delayed)],
                transfer=i == 8,
            )
            for i in range(1, 9)
        ),
        as_of=NOW,
    )
    listening = project_mastery((), as_of=NOW, modality=Modality.LISTENING)

    assert reading.status in {MasteryStatus.RELIABLE, MasteryStatus.MASTERED}
    assert listening.status is MasteryStatus.NON_OBSERVED
    assert listening.effective_mass == 0


def test_old_reliable_projection_becomes_review_due_without_mutating_facts() -> None:
    old = tuple(
        _evidence(
            i,
            value=1.0,
            age_days=100 + i,
            delay=DelayBand.SEVEN_DAYS_OR_MORE,
            transfer=i == 8,
        )
        for i in range(1, 9)
    )

    projection = project_mastery(
        old,
        as_of=NOW,
        previous_status=MasteryStatus.MASTERED,
    )

    assert projection.status is MasteryStatus.REVIEW_DUE
    assert projection.mastery_base > 0.85
    assert projection.freshness < 0.5
    assert all(item.invalidated_at is None for item in old)


def test_modality_projection_keeps_unknown_axes_unknown_and_reports_coverage() -> None:
    reading_facet = project_mastery(
        tuple(
            _evidence(
                i,
                modality=Modality.READING,
                value=1,
                delay=tuple(DelayBand)[i % 3],
                transfer=i == 8,
            )
            for i in range(1, 9)
        ),
        as_of=NOW,
    )

    reading = project_modality(
        Modality.READING,
        ((reading_facet, 1.0),),
        eligible_weight=2.0,
    )
    listening = project_modality(Modality.LISTENING, (), eligible_weight=2.0)

    assert reading.coverage == pytest.approx(0.5)
    assert reading.score is not None
    assert listening.status is MasteryStatus.NON_OBSERVED
    assert listening.score is None
    assert listening.confidence == 0
