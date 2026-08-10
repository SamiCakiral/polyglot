from dataclasses import replace
from uuid import UUID

import pytest
from test_contracts import (
    ATTEMPT_ID,
    CORRECTION_ID,
    NOW,
    PROFILE_ID,
    FixedIds,
    instance,
)

from polyglot.platform.clock import FrozenClock
from polyglot.platform.errors import DomainError, ErrorCode


def choice_answer(value: str = "choice-a"):
    from polyglot.modules.exercises.core.domain import Answer, AnswerKind

    return Answer.create(
        kind=AnswerKind.SINGLE_CHOICE,
        raw_value=value,
        input_method="keyboard",
        submitted_at=NOW,
    )


def draft_attempt():
    from polyglot.modules.exercises.core.domain import Attempt

    return Attempt.start(
        instance=instance(),
        profile_id=PROFILE_ID,
        attempt_no=1,
        clock=FrozenClock(NOW),
        ids=FixedIds(ATTEMPT_ID),
    )


def test_definition_and_instance_detach_all_nested_collections_from_callers() -> None:
    from polyglot.modules.exercises.core.domain import (
        AnswerKind,
        ExerciseDefinition,
        ExerciseInstance,
    )

    response_kinds = [AnswerKind.SINGLE_CHOICE]
    certification_ids = [UUID("019fe009-0000-7000-8000-000000000006")]
    modes = ["functional_contrast"]
    target = ["skill:contrast", 0.35]
    target_weights = [target]
    accessibility = ["keyboard", "screen_reader", "untimed"]
    stimuli = [UUID("019fe009-0000-7000-8000-000000000002")]

    definition = ExerciseDefinition.published(
        definition_id=UUID("019fe009-0000-7000-8000-000000000001"),
        revision_id=UUID("019fe009-0000-7000-8000-000000000002"),
        revision_no=1,
        primitive_id="EX-DISC-04",
        response_kinds=response_kinds,
        language_certification_ids=certification_ids,
        modes=modes,
        target_weights=target_weights,
        correction_policy_id="policy:exact-choice:v1",
        hint_policy_id="policy:hints:v1",
        observation_policy_id="policy:observation:v1",
        accessibility_features=accessibility,
    )
    exercise = ExerciseInstance.create(
        instance_id=UUID("019fe009-0000-7000-8000-000000000003"),
        definition=definition,
        language_pack_revision_id=UUID("019fe009-0000-7000-8000-000000000005"),
        seed=9009,
        stimulus_revision_ids=stimuli,
    )

    response_kinds.append(AnswerKind.SHORT_TEXT)
    certification_ids.clear()
    modes.append("mutated")
    target[0] = "skill:mutated"
    target_weights.append(["skill:other", 1.0])
    accessibility.clear()
    stimuli.append(UUID("019fe009-0000-7000-8000-000000000099"))

    assert definition.response_kinds == (AnswerKind.SINGLE_CHOICE,)
    assert definition.language_certification_ids == (UUID("019fe009-0000-7000-8000-000000000006"),)
    assert definition.modes == ("functional_contrast",)
    assert definition.target_weights == (("skill:contrast", 0.35),)
    assert definition.accessibility_features == ("keyboard", "screen_reader", "untimed")
    assert exercise.stimulus_revision_ids == (UUID("019fe009-0000-7000-8000-000000000002"),)


def test_attempt_and_correction_result_detach_nested_collections_from_callers() -> None:
    from polyglot.modules.exercises.core.domain import (
        CorrectionResult,
        CorrectionVerdict,
        HintLevel,
        HintUse,
    )

    criteria = [["meaning", 1.0]]
    alternatives = ["ciao", "salve"]
    errors = ["register"]
    result = CorrectionResult(
        verdict=CorrectionVerdict.CORRECT,
        confidence=1.0,
        target_coverage=1.0,
        explanation="accepted",
        criteria_scores=criteria,
        alternatives=alternatives,
        errors=errors,
    )
    hints = [HintUse(HintLevel.H1, "orientation", NOW)]
    corrections = [[CORRECTION_ID, result]]
    attempt = replace(draft_attempt(), hint_uses=hints, corrections=corrections)

    criteria[0][1] = 0.0
    alternatives.clear()
    errors.append("meaning")
    hints.clear()
    corrections.clear()

    assert result.criteria_scores == (("meaning", 1.0),)
    assert result.alternatives == ("ciao", "salve")
    assert result.errors == ("register",)
    assert len(attempt.hint_uses) == 1
    assert attempt.corrections == ((CORRECTION_ID, result),)


def test_submission_and_correction_replay_stay_stable_after_terminal_transition() -> None:
    from polyglot.modules.exercises.core.domain import CorrectionResult

    answer = choice_answer()
    submitted = draft_attempt().submit(answer=answer, idempotency_key="submit-stable")
    corrected = submitted.start_correction().complete_correction(
        correction_id=CORRECTION_ID,
        result=CorrectionResult.correct(confidence=1.0),
        clock=FrozenClock(NOW),
        idempotency_key="correction-stable",
    )

    assert corrected.submit(answer=answer, idempotency_key="submit-stable") == corrected
    assert (
        corrected.complete_correction(
            correction_id=CORRECTION_ID,
            result=CorrectionResult.correct(confidence=1.0),
            clock=FrozenClock(NOW),
            idempotency_key="correction-stable",
        )
        == corrected
    )
    assert len(corrected.corrections) == 1

    with pytest.raises(DomainError) as changed_body:
        corrected.submit(answer=choice_answer("choice-b"), idempotency_key="submit-stable")
    with pytest.raises(DomainError) as changed_key:
        corrected.complete_correction(
            correction_id=CORRECTION_ID,
            result=CorrectionResult.correct(confidence=1.0),
            clock=FrozenClock(NOW),
            idempotency_key="correction-other-key",
        )

    assert changed_body.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert changed_key.value.code is ErrorCode.IDEMPOTENCY_CONFLICT


def test_hint_force_skip_and_abandon_replay_are_stable_and_conflicts_explicit() -> None:
    from polyglot.modules.exercises.core.domain import (
        ExerciseBlockRun,
        HintLevel,
        TerminalReason,
    )

    hinted = draft_attempt().use_hint(
        HintLevel.H2,
        reason="partial clue",
        clock=FrozenClock(NOW),
        idempotency_key="hint-stable",
    )
    submitted = hinted.submit(answer=choice_answer(), idempotency_key="submit-after-hint")
    forced = draft_attempt().force_submit(
        reason=TerminalReason.ANSWER_INVALID,
        idempotency_key="force-stable",
    )
    available = ExerciseBlockRun.create(
        block_id=UUID("019fe009-0000-7000-8000-000000000011")
    ).make_available()
    skipped = available.skip(reason="learner_choice", idempotency_key="skip-stable")
    abandoned = available.start().abandon(idempotency_key="abandon-stable")

    assert (
        submitted.use_hint(
            HintLevel.H2,
            reason="partial clue",
            clock=FrozenClock(NOW),
            idempotency_key="hint-stable",
        )
        == submitted
    )
    assert (
        forced.force_submit(
            reason=TerminalReason.ANSWER_INVALID,
            idempotency_key="force-stable",
        )
        == forced
    )
    assert skipped.skip(reason="learner_choice", idempotency_key="skip-stable") == skipped
    assert abandoned.abandon(idempotency_key="abandon-stable") == abandoned

    with pytest.raises(DomainError) as hint_conflict:
        submitted.use_hint(
            HintLevel.H3,
            reason="different clue",
            clock=FrozenClock(NOW),
            idempotency_key="hint-stable",
        )
    with pytest.raises(DomainError) as force_conflict:
        forced.force_submit(
            reason=TerminalReason.USER_CANCELLED,
            idempotency_key="force-stable",
        )
    with pytest.raises(DomainError) as skip_conflict:
        skipped.skip(reason="different", idempotency_key="skip-stable")

    assert hint_conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert force_conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert skip_conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
