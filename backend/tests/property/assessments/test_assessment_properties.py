from datetime import UTC, datetime, timedelta
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.assessments.domain import AssessmentModality
from polyglot.modules.assessments.scoring import ScoreUnit, score_assessment


def uid(value: int) -> UUID:
    return UUID(f"019feb36-0000-7000-8000-{value:012x}")


@given(st.lists(st.floats(min_value=0, max_value=1, allow_nan=False), min_size=1, max_size=40))
def test_scores_confidence_and_coverage_are_always_bounded(values: list[float]) -> None:
    weight = 1 / len(values)
    units = tuple(
        ScoreUnit(str(index), "facet", weight, value, 1, True, True)
        for index, value in enumerate(values)
    )

    result = score_assessment(
        AssessmentModality.READING,
        units,
        minimum_units=min(12, len(units)),
        planned_weight=1,
    )

    assert result.score is not None and 0 <= result.score <= 1
    assert 0 <= result.confidence <= 1
    assert 0 <= result.coverage <= 1


@given(st.integers(min_value=0, max_value=25 * 60 * 1000 - 1))
def test_server_timer_never_returns_negative_remaining_time(elapsed_ms: int) -> None:
    from polyglot.modules.assessments.domain import AssessmentRun

    start = datetime(2026, 8, 10, tzinfo=UTC)
    run = AssessmentRun.prepare(
        run_id=uid(1),
        profile_id=uid(2),
        assessment_revision_id=uid(3),
        form_id=uid(4),
        modality=AssessmentModality.READING,
        item_ids=(uid(5),),
        time_limit_ms=25 * 60 * 1000,
        pause_allowed=True,
        resume_window_ms=24 * 60 * 60 * 1000,
        prepared_at=start,
    ).start(start)

    paused = run.pause(start + timedelta(milliseconds=elapsed_ms))

    assert paused.remaining_time_ms is not None and paused.remaining_time_ms >= 0
