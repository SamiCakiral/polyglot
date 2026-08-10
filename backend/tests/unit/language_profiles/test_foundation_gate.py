from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from polyglot.modules.language_profiles.foundations import (
    FoundationBlock,
    FoundationCriterion,
    FoundationGate,
    FoundationMeasurement,
)
from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
SESSION_ONE = UUID("019fe903-1000-7000-8000-000000000001")
SESSION_TWO = UUID("019fe903-1000-7000-8000-000000000002")


def measurement(
    block: FoundationBlock,
    *,
    criterion: FoundationCriterion | None = None,
    score: int,
    maximum: int,
    session_id: UUID,
    at: datetime,
    revealed: bool = False,
    evaluable: bool = True,
) -> FoundationMeasurement:
    return FoundationMeasurement(
        block=block,
        criterion=criterion,
        score=score,
        maximum=maximum,
        session_id=session_id,
        at=at,
        revealed=revealed,
        evaluable=evaluable,
    )


def passing_measurements(*, delayed_at: datetime) -> tuple[FoundationMeasurement, ...]:
    return (
        measurement(
            FoundationBlock.F1,
            criterion=FoundationCriterion.GRAPHEME_SOUND_DISCRIMINATION,
            score=8,
            maximum=10,
            session_id=SESSION_ONE,
            at=NOW,
        ),
        measurement(
            FoundationBlock.F1,
            criterion=FoundationCriterion.GRAPHEME_SOUND_DISCRIMINATION,
            score=8,
            maximum=10,
            session_id=SESSION_TWO,
            at=delayed_at,
        ),
        measurement(
            FoundationBlock.F1,
            criterion=FoundationCriterion.TARGETED_READING,
            score=8,
            maximum=10,
            session_id=SESSION_ONE,
            at=NOW,
        ),
        measurement(
            FoundationBlock.F1,
            criterion=FoundationCriterion.TARGETED_READING,
            score=8,
            maximum=10,
            session_id=SESSION_TWO,
            at=delayed_at,
        ),
        measurement(FoundationBlock.F2, score=1, maximum=1, session_id=SESSION_ONE, at=NOW),
        measurement(FoundationBlock.F3, score=4, maximum=5, session_id=SESSION_ONE, at=NOW),
        measurement(FoundationBlock.F4, score=1, maximum=1, session_id=SESSION_TWO, at=delayed_at),
        measurement(
            FoundationBlock.F5,
            criterion=FoundationCriterion.SURVIVAL_EXCHANGE,
            score=4,
            maximum=5,
            session_id=SESSION_TWO,
            at=delayed_at,
        ),
    )


def test_gate_passes_only_after_two_sessions_and_the_twenty_four_hour_control() -> None:
    result = FoundationGate.v0().evaluate(
        passing_measurements(delayed_at=NOW + timedelta(hours=24))
    )

    assert result.passed is True
    assert result.implicit_mastery_target_ids == ()


def test_gate_rejects_control_before_twenty_four_hours() -> None:
    result = FoundationGate.v0().evaluate(
        passing_measurements(delayed_at=NOW + timedelta(hours=24) - timedelta(seconds=1))
    )

    assert result.passed is False
    assert "delayed_control_missing" in result.reasons


def test_revealed_survival_exchange_cannot_satisfy_the_gate() -> None:
    measures = list(passing_measurements(delayed_at=NOW + timedelta(hours=24)))
    measures[-1] = measurement(
        FoundationBlock.F5,
        criterion=FoundationCriterion.SURVIVAL_EXCHANGE,
        score=4,
        maximum=5,
        session_id=SESSION_TWO,
        at=NOW + timedelta(hours=24),
        revealed=True,
    )

    result = FoundationGate.v0().evaluate(tuple(measures))

    assert result.passed is False
    assert "repair_not_autonomous" in result.reasons


def test_two_correct_template_items_cannot_stand_in_for_ten_distinct_trials() -> None:
    measures = list(passing_measurements(delayed_at=NOW + timedelta(hours=24)))
    measures[0] = measurement(
        FoundationBlock.F1,
        criterion=FoundationCriterion.GRAPHEME_SOUND_DISCRIMINATION,
        score=2,
        maximum=2,
        session_id=SESSION_ONE,
        at=NOW,
    )

    result = FoundationGate.v0().evaluate(tuple(measures))

    assert result.passed is False
    assert "grapheme_sound_discrimination_incomplete" in result.reasons


def test_gate_applies_each_published_absolute_threshold_independently() -> None:
    measures = list(passing_measurements(delayed_at=NOW + timedelta(hours=24)))
    measures[3] = measurement(
        FoundationBlock.F1,
        criterion=FoundationCriterion.TARGETED_READING,
        score=7,
        maximum=10,
        session_id=SESSION_TWO,
        at=NOW + timedelta(hours=24),
    )

    reading = FoundationGate.v0().evaluate(tuple(measures))
    assert reading.passed is False
    assert "targeted_reading_incomplete" in reading.reasons

    measures = list(passing_measurements(delayed_at=NOW + timedelta(hours=24)))
    measures[-1] = measurement(
        FoundationBlock.F5,
        criterion=FoundationCriterion.SURVIVAL_EXCHANGE,
        score=3,
        maximum=5,
        session_id=SESSION_TWO,
        at=NOW + timedelta(hours=24),
    )

    survival = FoundationGate.v0().evaluate(tuple(measures))
    assert survival.passed is False
    assert "repair_not_autonomous" in survival.reasons


def test_audio_absent_is_not_evaluable_and_never_a_success() -> None:
    result = FoundationGate.v0().evaluate(
        (
            measurement(
                FoundationBlock.F1,
                score=0,
                maximum=10,
                session_id=SESSION_ONE,
                at=NOW,
                evaluable=False,
            ),
        )
    )

    assert result.passed is False
    assert result.not_evaluable_blocks == (FoundationBlock.F1,)
    assert result.implicit_mastery_target_ids == ()


def test_measurements_require_distinct_uuid7_sessions() -> None:
    with pytest.raises(DomainError) as rejected:
        measurement(
            FoundationBlock.F1,
            score=8,
            maximum=10,
            session_id=UUID("00000000-0000-4000-8000-000000000001"),
            at=NOW,
        )

    assert rejected.value.code is ErrorCode.VALIDATION_FAILED
