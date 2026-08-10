import pytest

from polyglot.modules.assessments.domain import (
    AssessmentBand,
    AssessmentModality,
    AssessmentResultStatus,
)
from polyglot.modules.assessments.scoring import (
    ScoreUnit,
    normalize_multiple_choice,
    score_assessment,
)


def test_multiple_choice_score_corrects_for_random_guessing() -> None:
    assert normalize_multiple_choice(1, option_count=4) == 1
    assert normalize_multiple_choice(0.25, option_count=4) == 0
    assert normalize_multiple_choice(0, option_count=4) == 0


def test_reading_score_computes_coverage_confidence_and_band() -> None:
    units = tuple(
        ScoreUnit(
            key=f"item-{index}",
            facet="literal" if index < 6 else "inference",
            weight=1 / 12,
            normalized_score=0.75,
            correction_confidence=1,
            evaluable=True,
            answered=True,
        )
        for index in range(12)
    )
    result = score_assessment(
        AssessmentModality.READING,
        units,
        minimum_units=12,
        planned_weight=1,
    )

    assert result.status is AssessmentResultStatus.VALID
    assert result.score == pytest.approx(0.75)
    assert result.coverage == pytest.approx(1)
    assert result.confidence == pytest.approx(1)
    assert result.band is AssessmentBand.ASSESS_B3


def test_incomplete_writing_is_indicative_and_oral_without_review_is_not_evaluable() -> None:
    writing = score_assessment(
        AssessmentModality.WRITING,
        (
            ScoreUnit("task-1", "task_achievement", 0.4, 0.75, 1, True, True),
            ScoreUnit("task-2", "task_achievement", 0.6, None, None, False, False),
        ),
        minimum_units=2,
        planned_weight=1,
    )
    oral = score_assessment(
        AssessmentModality.SPEAKING,
        (ScoreUnit("self", "self_assessment", 1, None, None, False, True),),
        minimum_units=1,
        planned_weight=1,
    )

    assert writing.status is AssessmentResultStatus.INDICATIVE
    assert writing.coverage == pytest.approx(0.4)
    assert oral.status is AssessmentResultStatus.NOT_EVALUABLE
    assert oral.score is None
    assert oral.band is None


def test_critical_rubric_score_caps_band_at_b1() -> None:
    result = score_assessment(
        AssessmentModality.WRITING,
        (
            ScoreUnit("critical", "task_achievement", 0.25, 0.2, 1, True, True, True),
            ScoreUnit("other", "coherence", 0.75, 1, 1, True, True),
        ),
        minimum_units=2,
        planned_weight=1,
    )

    assert result.band is AssessmentBand.ASSESS_B1
    assert result.limiting_criteria == ("task_achievement",)
