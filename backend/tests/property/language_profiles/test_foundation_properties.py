from datetime import UTC, datetime, timedelta
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.language_profiles.foundations import (
    FoundationBlock,
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
            score=10,
            maximum=10,
            session_id=session_id,
            at=at,
            revealed=False,
            evaluable=True,
        )
        for session_id, at in (
            (SESSION_1, started),
            (SESSION_2, started + timedelta(seconds=delay_seconds)),
        )
        for block in FoundationBlock
    )

    result = FoundationGate.v0().evaluate(measurements)

    assert result.passed is False
    assert "delayed_control_missing" in result.reasons
