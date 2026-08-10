from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from polyglot.modules.language_profiles.diagnostic import (
    DiagnosticClassification,
    DiagnosticPolicy,
    DiagnosticResponse,
    DiagnosticRun,
    DiagnosticStopReason,
    DiagnosticTarget,
)
from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
PROFILE_ID = UUID("019fe903-0000-7000-8000-000000000001")
RUN_ID = UUID("019fe903-0000-7000-8000-000000000002")


def response(
    target: DiagnosticTarget,
    *,
    score: float,
    confidence: float = 1.0,
    evaluable: bool = True,
    difficulty: int = 1,
) -> DiagnosticResponse:
    return DiagnosticResponse(
        target=target,
        score=score,
        confidence=confidence,
        evaluable=evaluable,
        difficulty=difficulty,
        item_revision_id=UUID(
            "019fe903-0000-7000-8000-"
            f"{((tuple(DiagnosticTarget).index(target) + 1) * 10 + difficulty):012d}"
        ),
    )


def complete_run(*responses: DiagnosticResponse) -> DiagnosticRun:
    run = DiagnosticRun.start(
        diagnostic_run_id=RUN_ID,
        profile_id=PROFILE_ID,
        policy=DiagnosticPolicy.v0(),
        seed="fx-personas",
        started_at=NOW,
    )
    for item in responses:
        run = run.record(item, at=NOW + timedelta(minutes=1))
    return run


def test_beginner_routes_to_foundations_without_implicit_credit() -> None:
    run = complete_run(
        response(DiagnosticTarget.FOUNDATIONS, score=0.2, difficulty=1),
        response(DiagnosticTarget.FOUNDATIONS, score=0.3, difficulty=2),
        response(DiagnosticTarget.READING, score=0.4, difficulty=1),
        response(DiagnosticTarget.READING, score=0.2, difficulty=2),
        response(DiagnosticTarget.WRITING, score=0.0, difficulty=1),
        response(DiagnosticTarget.WRITING, score=0.0, difficulty=2),
    )

    result = run.complete(at=NOW + timedelta(minutes=2))

    assert result.classification is DiagnosticClassification.BEGINNER
    assert result.next_profile_status == "foundations"
    assert result.implicit_mastery_target_ids == ()


def test_false_beginner_keeps_declarations_out_of_the_score() -> None:
    run = complete_run(
        response(DiagnosticTarget.FOUNDATIONS, score=0.55, difficulty=1),
        response(DiagnosticTarget.FOUNDATIONS, score=0.45, difficulty=2),
        response(DiagnosticTarget.READING, score=0.60, difficulty=1),
        response(DiagnosticTarget.READING, score=0.50, difficulty=2),
        response(DiagnosticTarget.WRITING, score=0.30, difficulty=1),
        response(DiagnosticTarget.WRITING, score=0.20, difficulty=2),
    )

    result = run.complete(at=NOW + timedelta(minutes=2))

    assert result.classification is DiagnosticClassification.FALSE_BEGINNER
    assert result.next_profile_status == "foundations"
    assert result.implicit_mastery_target_ids == ()


def test_intermediate_allows_non_evaluable_listening_and_speaking() -> None:
    run = complete_run(
        response(DiagnosticTarget.FOUNDATIONS, score=0.9, confidence=0.7, difficulty=1),
        response(DiagnosticTarget.FOUNDATIONS, score=0.9, confidence=0.7, difficulty=2),
        response(DiagnosticTarget.READING, score=0.8, confidence=0.7, difficulty=1),
        response(DiagnosticTarget.READING, score=0.8, confidence=0.7, difficulty=2),
        response(DiagnosticTarget.WRITING, score=0.7, confidence=0.7, difficulty=1),
        response(DiagnosticTarget.WRITING, score=0.7, confidence=0.7, difficulty=2),
        response(DiagnosticTarget.LISTENING, score=0.0, evaluable=False, difficulty=1),
        response(DiagnosticTarget.SPEAKING, score=0.0, evaluable=False, difficulty=1),
    )

    result = run.complete(at=NOW + timedelta(minutes=2))

    assert result.classification is DiagnosticClassification.INTERMEDIATE
    assert result.next_profile_status == "active"
    assert result.not_evaluable_targets == (
        DiagnosticTarget.LISTENING,
        DiagnosticTarget.SPEAKING,
    )
    assert result.implicit_mastery_target_ids == ()


def test_insufficient_coverage_cannot_force_a_placement() -> None:
    run = complete_run(response(DiagnosticTarget.FOUNDATIONS, score=1.0, difficulty=1))

    with pytest.raises(DomainError) as rejected:
        run.complete(at=NOW + timedelta(minutes=2))

    assert rejected.value.code is ErrorCode.INSUFFICIENT_COVERAGE


def test_run_expires_after_twenty_four_hours_and_cannot_accept_a_response() -> None:
    run = DiagnosticRun.start(
        diagnostic_run_id=RUN_ID,
        profile_id=PROFILE_ID,
        policy=DiagnosticPolicy.v0(),
        seed="fx-retour",
        started_at=NOW,
    )

    with pytest.raises(DomainError) as rejected:
        run.record(
            response(DiagnosticTarget.FOUNDATIONS, score=0.5),
            at=NOW + timedelta(hours=24),
        )

    assert rejected.value.code is ErrorCode.RUN_EXPIRED


def test_three_consecutive_failures_stop_the_diagnostic() -> None:
    run = DiagnosticRun.start(
        diagnostic_run_id=RUN_ID,
        profile_id=PROFILE_ID,
        policy=DiagnosticPolicy.v0(),
        seed="fx-stop",
        started_at=NOW,
    )
    for difficulty in (1, 2, 3):
        run = run.record(
            response(DiagnosticTarget.READING, score=0.0, difficulty=difficulty),
            at=NOW + timedelta(minutes=difficulty),
        )

    assert run.stop_reason is DiagnosticStopReason.CONSECUTIVE_FAILURES
