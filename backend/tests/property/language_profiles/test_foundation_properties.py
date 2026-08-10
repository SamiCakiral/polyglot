from datetime import UTC, datetime, timedelta
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.language_profiles.foundations import (
    FoundationBlock,
    FoundationCriterion,
    FoundationGate,
    FoundationMeasurement,
)

SESSION_1 = UUID("019fe903-0000-7000-8000-000000000101")
SESSION_2 = UUID("019fe903-0000-7000-8000-000000000102")


@given(st.integers(min_value=1, max_value=86_399))
def test_no_scores_can_bypass_the_twenty_four_hour_control(delay_seconds: int) -> None:
    started = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
    measurements = tuple(
        FoundationMeasurement(
            block=block,
            criterion=criterion,
            score=score,
            maximum=maximum,
            session_id=session_id,
            at=at,
            revealed=False,
            evaluable=True,
        )
        for session_id, at in (
            (SESSION_1, started),
            (SESSION_2, started + timedelta(seconds=delay_seconds)),
        )
        for block, criterion, score, maximum in (
            (
                FoundationBlock.F1,
                FoundationCriterion.GRAPHEME_SOUND_DISCRIMINATION,
                10,
                10,
            ),
            (FoundationBlock.F1, FoundationCriterion.TARGETED_READING, 10, 10),
            (FoundationBlock.F3, None, 1, 1),
            (FoundationBlock.F4, None, 1, 1),
            (FoundationBlock.F5, FoundationCriterion.SURVIVAL_EXCHANGE, 5, 5),
        )
    )

    result = FoundationGate.v0().evaluate(measurements)

    assert result.passed is False
    assert "delayed_control_missing" in result.reasons
