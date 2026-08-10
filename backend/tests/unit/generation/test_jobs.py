from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from polyglot.modules.generation.domain import (
    GenerationAttempt,
    GenerationAttemptStatus,
    GenerationJob,
    GenerationJobStatus,
)
from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 8, 10, 12, tzinfo=UTC)


def job() -> GenerationJob:
    return GenerationJob(
        UUID("019fec00-0000-7000-8000-000000000010"),
        UUID("019fec00-0000-7000-8000-000000000011"),
        "exercise_draft",
        "a" * 64,
        ("exercise.get_blueprint@1.0.0", "exercise.submit_draft@1.0.0"),
        1,
        100,
        100,
        1000,
        NOW,
    )


def attempt(*, cost: int = 10) -> GenerationAttempt:
    return GenerationAttempt(
        UUID("019fec00-0000-7000-8000-000000000012"),
        1,
        "offline",
        "deterministic-v1",
        "PROMPT_V1",
        ("exercise.submit_draft@1.0.0",),
        "b" * 64,
        NOW,
        NOW + timedelta(seconds=1),
        GenerationAttemptStatus.SUCCEEDED,
        input_tokens=10,
        output_tokens=10,
        cost_micros=cost,
    )


def test_job_has_one_explicit_attempt_and_only_returns_a_draft() -> None:
    draft_id = UUID("019fec00-0000-7000-8000-000000000013")
    completed = job().queue().start().finish_attempt(attempt(), result_draft_id=draft_id)

    assert completed.status is GenerationJobStatus.SUCCEEDED
    assert completed.result_draft_id == draft_id
    assert len(completed.attempts) == 1


def test_budget_overrun_fails_closed_without_recording_success() -> None:
    with pytest.raises(DomainError) as caught:
        job().queue().start().finish_attempt(attempt(cost=1001))
    assert caught.value.code is ErrorCode.BUDGET_EXCEEDED


def test_cancellation_never_turns_into_success() -> None:
    cancelled = job().queue().request_cancel()
    assert cancelled.status is GenerationJobStatus.CANCELLED
    with pytest.raises(DomainError):
        cancelled.start()
