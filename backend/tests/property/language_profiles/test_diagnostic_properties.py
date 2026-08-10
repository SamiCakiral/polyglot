from datetime import UTC, datetime, timedelta
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.language_profiles.diagnostic import (
    DiagnosticPolicy,
    DiagnosticResponse,
    DiagnosticRun,
    DiagnosticTarget,
)


@given(st.lists(st.floats(min_value=0, max_value=1, allow_nan=False), min_size=2, max_size=10))
def test_same_snapshot_and_responses_produce_the_same_summary(scores: list[float]) -> None:
    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

    def make_run() -> DiagnosticRun:
        run = DiagnosticRun.start(
            diagnostic_run_id=UUID("019fe903-0000-7000-8000-000000000002"),
            profile_id=UUID("019fe903-0000-7000-8000-000000000001"),
            policy=DiagnosticPolicy.v0(),
            seed="replay",
            started_at=now,
        )
        for ordinal, score in enumerate(scores, start=1):
            if run.stop_reason is not None:
                break
            run = run.record(
                DiagnosticResponse(
                    target=DiagnosticTarget.FOUNDATIONS,
                    score=score,
                    confidence=1.0,
                    evaluable=True,
                    difficulty=ordinal,
                    item_revision_id=UUID(
                        f"019fe903-0000-7000-8000-{ordinal:012d}"
                    ),
                ),
                at=now + timedelta(minutes=ordinal),
            )
        return run

    assert make_run().snapshot() == make_run().snapshot()
