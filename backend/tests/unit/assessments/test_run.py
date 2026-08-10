from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from polyglot.modules.assessments.domain import (
    AssessmentDomainError,
    AssessmentModality,
    AssessmentRun,
    AssessmentRunStatus,
)


def uid(value: int) -> UUID:
    return UUID(f"019feb31-0000-7000-8000-{value:012x}")


NOW = datetime(2026, 8, 10, 8, tzinfo=UTC)


def prepared(*, pause_allowed: bool = True) -> AssessmentRun:
    return AssessmentRun.prepare(
        run_id=uid(1),
        profile_id=uid(2),
        assessment_revision_id=uid(3),
        form_id=uid(4),
        modality=AssessmentModality.READING,
        item_ids=(uid(5), uid(6)),
        time_limit_ms=25 * 60 * 1000,
        pause_allowed=pause_allowed,
        resume_window_ms=24 * 60 * 60 * 1000,
        prepared_at=NOW,
    )


def test_pause_and_resume_preserve_server_time_remaining() -> None:
    run = prepared().start(NOW + timedelta(minutes=1))
    paused = run.pause(NOW + timedelta(minutes=6))
    resumed = paused.resume(NOW + timedelta(hours=2))

    assert paused.remaining_time_ms == 20 * 60 * 1000
    assert resumed.deadline_at == NOW + timedelta(hours=2, minutes=20)
    assert resumed.status is AssessmentRunStatus.IN_PROGRESS


def test_pause_forbidden_and_resume_window_expired_are_explicit() -> None:
    running = prepared(pause_allowed=False).start(NOW)
    with pytest.raises(AssessmentDomainError, match="pause_not_allowed"):
        running.pause(NOW + timedelta(minutes=1))

    paused = prepared().start(NOW).pause(NOW + timedelta(minutes=1))
    with pytest.raises(AssessmentDomainError, match="assessment_expired"):
        paused.resume(NOW + timedelta(hours=25))


def test_submission_is_idempotent_and_divergent_save_is_rejected() -> None:
    run = prepared().start(NOW)
    answered = run.save_response(uid(5), {"kind": "short_text", "value": "Roma"}, 0, NOW)
    submitted = answered.submit(NOW + timedelta(minutes=2))

    assert submitted.submit(NOW + timedelta(minutes=3)) == submitted
    with pytest.raises(AssessmentDomainError, match="response_conflict"):
        submitted.save_response(
            uid(5), {"kind": "short_text", "value": "Milano"}, 1, NOW
        )


def test_server_deadline_expires_and_freezes_partial_responses() -> None:
    run = prepared().start(NOW)
    expired = run.expire_if_due(NOW + timedelta(minutes=26))

    assert expired.status is AssessmentRunStatus.EXPIRED
    assert expired.submitted_at == expired.deadline_at
