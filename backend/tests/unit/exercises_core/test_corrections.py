from datetime import UTC, datetime
from uuid import UUID

import pytest

from polyglot.platform.clock import FrozenClock
from polyglot.platform.errors import DomainError, ErrorCode

from test_contracts import (
    ATTEMPT_ID,
    CASE_ID,
    CORRECTION_ID,
    NOW,
    PROFILE_ID,
    FixedIds,
    instance,
)


def test_closed_correction_strategies_do_not_promote_ambiguous_or_unavailable_answers() -> None:
    from polyglot.modules.exercises.core.domain import (
        CorrectionResult,
        CorrectionStrategy,
        CorrectionVerdict,
    )

    exact = CorrectionStrategy.exact_normalized("Ciao!").correct("  ciao ")
    accepted = CorrectionStrategy.accepted_set(("ciao", "salve")).correct("salve")
    morphology = CorrectionStrategy.morphological(
        expected="sono", expected_traits={"person": "first", "number": "singular"}
    ).correct("sono", observed_traits={"person": "first", "number": "singular"})
    constraints = CorrectionStrategy.structural_constraints(
        required_tokens=("io", "sono"), ordered=True
    ).correct("io sono")
    grid = CorrectionStrategy.rubric(
        required_criteria=("meaning", "register"), passing_score=0.8
    ).correct({"meaning": 1.0, "register": 0.8})
    ambiguous = CorrectionResult.ambiguous("two published readings")
    unavailable = CorrectionResult.not_evaluable("checker unavailable")

    assert [result.verdict for result in (exact, accepted, morphology, constraints, grid)] == [
        CorrectionVerdict.CORRECT,
        CorrectionVerdict.CORRECT,
        CorrectionVerdict.CORRECT,
        CorrectionVerdict.CORRECT,
        CorrectionVerdict.CORRECT,
    ]
    assert ambiguous.credit_value(operation_cap=0.75, target_weight=1.0, hint_level="h0") is None
    assert unavailable.credit_value(operation_cap=0.75, target_weight=1.0, hint_level="h0") is None


def test_h4_revelation_ambiguity_and_unavailability_never_create_success_or_credit() -> None:
    from polyglot.modules.exercises.core.domain import (
        Answer,
        AnswerKind,
        Attempt,
        AttemptStatus,
        CorrectionResult,
        TerminalReason,
    )

    answer = Answer.create(
        kind=AnswerKind.SINGLE_CHOICE,
        raw_value="choice-a",
        input_method="keyboard",
        submitted_at=NOW,
    )
    attempt = Attempt.start(
        instance=instance(),
        profile_id=PROFILE_ID,
        attempt_no=1,
        clock=FrozenClock(NOW),
        ids=FixedIds(ATTEMPT_ID),
    ).reveal(reason="user_requested")
    corrected = attempt.submit(answer=answer, idempotency_key="submit-1").start_correction().complete_correction(
        correction_id=CORRECTION_ID,
        result=CorrectionResult.correct(confidence=1.0),
        clock=FrozenClock(NOW),
    )
    ambiguous = attempt.submit(answer=answer, idempotency_key="submit-2").start_correction().complete_correction(
        correction_id=CORRECTION_ID,
        result=CorrectionResult.ambiguous("multiple readings"),
        clock=FrozenClock(NOW),
    )
    unavailable = attempt.submit(answer=answer, idempotency_key="submit-3").start_correction().complete_correction(
        correction_id=CORRECTION_ID,
        result=CorrectionResult.not_evaluable("timeout"),
        clock=FrozenClock(NOW),
    )

    assert corrected.status is AttemptStatus.CORRECTED
    assert corrected.current_credit(operation_cap=0.35, target_weight=1.0) == 0.0
    assert ambiguous.status is AttemptStatus.NOT_EVALUABLE
    assert ambiguous.terminal_reason is TerminalReason.CORRECTION_AMBIGUOUS
    assert ambiguous.current_credit(operation_cap=0.35, target_weight=1.0) is None
    assert unavailable.status is AttemptStatus.NOT_EVALUABLE
    assert unavailable.terminal_reason is TerminalReason.CORRECTION_UNAVAILABLE
    assert unavailable.current_credit(operation_cap=0.35, target_weight=1.0) is None


def test_correction_case_is_append_only_and_never_mutates_the_raw_answer() -> None:
    from polyglot.modules.exercises.core.domain import CorrectionCase, CorrectionCaseStatus

    closed = CorrectionCase.closed(case_id=CASE_ID, attempt_id=ATTEMPT_ID, correction_id=CORRECTION_ID)
    contested = closed.contest(reason="published alternative missing", at=NOW)
    queued = contested.queue_review(at=NOW)
    resolved = queued.resolve(correction_id=UUID("019fe009-0000-7000-8000-000000000010"), at=NOW)

    assert closed.status is CorrectionCaseStatus.CLOSED
    assert contested.status is CorrectionCaseStatus.CONTESTED
    assert queued.status is CorrectionCaseStatus.REVIEW_PENDING
    assert resolved.status is CorrectionCaseStatus.RESOLVED
    assert resolved.correction_history == (
        CORRECTION_ID,
        UUID("019fe009-0000-7000-8000-000000000010"),
    )


def test_block_lifecycle_models_skip_abandon_unavailability_and_forced_submission_explicitly() -> None:
    from polyglot.modules.exercises.core.domain import (
        Attempt,
        AttemptStatus,
        BlockStatus,
        ExerciseBlockRun,
        TerminalReason,
    )

    available = ExerciseBlockRun.create(block_id=UUID("019fe009-0000-7000-8000-000000000011")).make_available()
    skipped = available.skip(reason="learner_choice")
    abandoned = available.start().abandon()
    unavailable = available.mark_unavailable(reason="media_missing")
    forced = Attempt.start(
        instance=instance(),
        profile_id=PROFILE_ID,
        attempt_no=1,
        clock=FrozenClock(NOW),
        ids=FixedIds(ATTEMPT_ID),
    ).force_submit(reason=TerminalReason.ANSWER_INVALID, idempotency_key="forced-1")

    assert skipped.status is BlockStatus.SKIPPED
    assert abandoned.status is BlockStatus.ABANDONED
    assert unavailable.status is BlockStatus.UNAVAILABLE
    assert forced.status is AttemptStatus.NOT_EVALUABLE
    assert forced.terminal_reason is TerminalReason.ANSWER_INVALID

    with pytest.raises(DomainError) as invalid:
        skipped.start()

    assert invalid.value.code is ErrorCode.INVALID_TRANSITION
