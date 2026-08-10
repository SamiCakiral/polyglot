from datetime import UTC, datetime
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from polyglot.platform.clock import FrozenClock

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


@given(st.text(min_size=0, max_size=80))
def test_exact_normalized_is_deterministic_and_never_turns_ambiguous_input_into_success(
    value: str,
) -> None:
    from polyglot.modules.exercises.core.domain import CorrectionStrategy, CorrectionVerdict

    strategy = CorrectionStrategy.exact_normalized("Ciao")

    assert strategy.correct(value) == strategy.correct(value)
    assert CorrectionStrategy.ambiguous().correct(value).verdict is CorrectionVerdict.AMBIGUOUS


@given(st.sampled_from(("h0", "h1", "h2", "h3", "h4")), st.floats(min_value=0.0, max_value=1.0))
def test_credit_is_deterministic_and_h4_never_yields_positive_credit(
    hint_level: str, coverage: float
) -> None:
    from polyglot.modules.exercises.core.domain import CorrectionResult

    result = CorrectionResult.correct(confidence=1.0, target_coverage=coverage)
    credit = result.credit_value(operation_cap=0.75, target_weight=1.0, hint_level=hint_level)

    assert credit == result.credit_value(
        operation_cap=0.75, target_weight=1.0, hint_level=hint_level
    )
    if hint_level == "h4":
        assert credit == 0.0


@given(st.lists(st.text(min_size=0, max_size=20), min_size=1, max_size=8))
def test_same_submission_key_is_idempotent_for_every_answer_value(values: list[str]) -> None:
    from polyglot.modules.exercises.core.domain import (
        Answer,
        AnswerKind,
        Attempt,
        ExerciseDefinition,
        ExerciseInstance,
    )

    definition = ExerciseDefinition.published(
        definition_id=UUID("019fe009-1000-7000-8000-000000000001"),
        revision_id=UUID("019fe009-1000-7000-8000-000000000002"),
        revision_no=1,
        primitive_id="EX-RECALL-03",
        response_kinds=(AnswerKind.SHORT_TEXT,),
        language_certification_ids=(UUID("019fe009-1000-7000-8000-000000000003"),),
        modes=("cued",),
        target_weights=(("skill:recall", 0.55),),
        correction_policy_id="policy:exact:v1",
        hint_policy_id="policy:hints:v1",
        observation_policy_id="policy:observation:v1",
        accessibility_features=("keyboard", "screen_reader", "untimed"),
    )
    instance = ExerciseInstance.create(
        instance_id=UUID("019fe009-1000-7000-8000-000000000004"),
        definition=definition,
        language_pack_revision_id=UUID("019fe009-1000-7000-8000-000000000005"),
        seed=9,
        stimulus_revision_ids=(definition.revision_id,),
    )
    attempt = Attempt.start(
        instance=instance,
        profile_id=UUID("019fe009-1000-7000-8000-000000000006"),
        attempt_no=1,
        clock=FrozenClock(NOW),
        ids=type("Ids", (), {"new": lambda self: UUID("019fe009-1000-7000-8000-000000000007")})(),
    )
    answer = Answer.create(
        kind=AnswerKind.SHORT_TEXT,
        raw_value=values[0],
        input_method="keyboard",
        submitted_at=NOW,
    )

    submitted = attempt.submit(answer=answer, idempotency_key="same-key")
    assert submitted.submit(answer=answer, idempotency_key="same-key") == submitted
