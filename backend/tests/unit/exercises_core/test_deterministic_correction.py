from polyglot.modules.exercises.core.correction import correct_published_answer
from polyglot.modules.exercises.core.domain import AnswerKind, CorrectionVerdict


def test_closed_structured_answers_are_corrected_against_the_published_contract() -> None:
    correct = correct_published_answer(
        primitive_id="EX-DISC-02",
        answer_kind=AnswerKind.PAIRING,
        raw_value={"vorrei": "polite_request", "posso": "permission"},
        response_contract={
            "expected_answer": {"vorrei": "polite_request", "posso": "permission"}
        },
        stimulus_contract={},
    )
    incorrect = correct_published_answer(
        primitive_id="EX-DISC-02",
        answer_kind=AnswerKind.PAIRING,
        raw_value={"vorrei": "permission", "posso": "polite_request"},
        response_contract={
            "expected_answer": {"vorrei": "polite_request", "posso": "permission"}
        },
        stimulus_contract={},
    )

    assert correct.verdict is CorrectionVerdict.CORRECT
    assert correct.strategy == "exact_value"
    assert incorrect.verdict is CorrectionVerdict.INCORRECT


def test_controlled_text_is_normalized_but_open_production_is_not_auto_credited() -> None:
    controlled = correct_published_answer(
        primitive_id="EX-TRANSFORM-01",
        answer_kind=AnswerKind.TEXT,
        raw_value="  VORREI un caffè, per favore. ",
        response_contract={},
        stimulus_contract={
            "accepted_answers": ["Vorrei un caffè, per favore."],
        },
    )
    open_production = correct_published_answer(
        primitive_id="EX-PROD-03",
        answer_kind=AnswerKind.TEXT,
        raw_value="Vorrei visitare Roma domani.",
        response_contract={},
        stimulus_contract={"model_answer": "Domani visiterò Roma."},
    )

    assert controlled.verdict is CorrectionVerdict.CORRECT
    assert controlled.strategy == "accepted_set"
    assert open_production.verdict is CorrectionVerdict.NOT_EVALUABLE
    assert open_production.credit_value(
        operation_cap=0.85, target_weight=1.0, hint_level="h0"
    ) is None


def test_missing_or_self_reported_oral_oracles_never_create_credit() -> None:
    missing = correct_published_answer(
        primitive_id="EX-DISC-04",
        answer_kind=AnswerKind.SINGLE_CHOICE,
        raw_value="natural",
        response_contract={},
        stimulus_contract={},
    )
    oral = correct_published_answer(
        primitive_id="EX-ORAL-01",
        answer_kind=AnswerKind.SELF_ASSESSMENT,
        raw_value={"confidence": 1},
        response_contract={"expected_answer": {"confidence": 1}},
        stimulus_contract={},
    )

    assert missing.verdict is CorrectionVerdict.NOT_EVALUABLE
    assert oral.verdict is CorrectionVerdict.NOT_EVALUABLE
