from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from polyglot.modules.assessments.domain import AssessmentModality
from polyglot.modules.assessments.selection import (
    AssessmentFormCandidate,
    AssessmentFormUnavailable,
    FormExposure,
    select_assessment_form,
)


def uid(value: int) -> UUID:
    return UUID(f"019feb31-0000-7000-8000-{value:012x}")


NOW = datetime(2026, 8, 10, 8, tzinfo=UTC)


def candidate(
    value: int,
    *,
    current: int = 6,
    anchor: int = 2,
    transfer: int = 2,
    media_cost: int = 0,
) -> AssessmentFormCandidate:
    return AssessmentFormCandidate(
        form_id=uid(value),
        modality=AssessmentModality.READING,
        item_ids=tuple(uid(value * 100 + index) for index in range(10)),
        current_band_weight=current,
        lower_anchor_weight=anchor,
        transfer_weight=transfer,
        calibration_uncertainty=0.1,
        media_cost=media_cost,
        coverage_targets=frozenset({"literal", "inference", "register"}),
        required_capabilities=frozenset(),
        published=True,
    )


def test_selection_respects_60_20_20_and_avoids_recent_forms_and_items() -> None:
    recent = candidate(1)
    exposed_item = candidate(2)
    eligible = candidate(3)
    selected = select_assessment_form(
        candidates=(recent, exposed_item, eligible),
        modality=AssessmentModality.READING,
        required_targets=frozenset({"literal", "inference"}),
        capabilities=frozenset(),
        exposures=(
            FormExposure(recent.form_id, frozenset(), NOW - timedelta(days=2)),
            FormExposure(uid(99), frozenset({exposed_item.item_ids[0]}), NOW - timedelta(days=3)),
        ),
        now=NOW,
        seed="learner-seed",
    )

    assert selected.form_id == eligible.form_id


def test_selection_is_deterministic_and_uses_cost_as_a_tiebreaker() -> None:
    expensive = candidate(10, media_cost=3)
    cheap = candidate(11, media_cost=1)

    first = select_assessment_form(
        candidates=(expensive, cheap),
        modality=AssessmentModality.READING,
        required_targets=frozenset({"literal"}),
        capabilities=frozenset(),
        exposures=(),
        now=NOW,
        seed="same-seed",
    )
    second = select_assessment_form(
        candidates=(cheap, expensive),
        modality=AssessmentModality.READING,
        required_targets=frozenset({"literal"}),
        capabilities=frozenset(),
        exposures=(),
        now=NOW,
        seed="same-seed",
    )

    assert first.form_id == second.form_id == cheap.form_id


def test_selection_refuses_to_improvise_when_no_form_meets_quota() -> None:
    with pytest.raises(AssessmentFormUnavailable):
        select_assessment_form(
            candidates=(candidate(20, current=8, anchor=1, transfer=1),),
            modality=AssessmentModality.READING,
            required_targets=frozenset({"literal"}),
            capabilities=frozenset(),
            exposures=(),
            now=NOW,
            seed="seed",
        )
