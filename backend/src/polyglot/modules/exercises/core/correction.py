from __future__ import annotations

import json
import unicodedata
from typing import Any

from polyglot.modules.exercises.core.domain import (
    AnswerKind,
    CorrectionResult,
    CorrectionStrategy,
    CorrectionVerdict,
)
from polyglot.platform.json_types import JsonValue

_OPEN_PRIMITIVES = frozenset(
    {"EX-COMP-03", "EX-PROD-01", "EX-PROD-02", "EX-PROD-03", "EX-ORAL-01"}
)
_UNORDERED_LIST_KINDS = frozenset({AnswerKind.SELECTION, AnswerKind.SPANS})


def _canonical(value: JsonValue, *, unordered_lists: bool) -> str:
    normalized: Any
    if isinstance(value, str):
        normalized = " ".join(
            unicodedata.normalize("NFKC", value).casefold().split()
        )
    elif isinstance(value, list):
        items = [_canonical(item, unordered_lists=unordered_lists) for item in value]
        normalized = sorted(items) if unordered_lists else items
    elif isinstance(value, dict):
        normalized = {
            str(key): _canonical(item, unordered_lists=True)
            for key, item in sorted(value.items())
        }
    else:
        normalized = value
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _exact_result(
    actual: JsonValue, expected: JsonValue, *, unordered_lists: bool
) -> CorrectionResult:
    matched = _canonical(actual, unordered_lists=unordered_lists) == _canonical(
        expected, unordered_lists=unordered_lists
    )
    return CorrectionResult(
        CorrectionVerdict.CORRECT if matched else CorrectionVerdict.INCORRECT,
        1.0,
        float(matched),
        "published deterministic answer",
        "exact_value",
    )


def correct_published_answer(
    *,
    primitive_id: str,
    answer_kind: AnswerKind,
    raw_value: JsonValue,
    response_contract: dict[str, JsonValue],
    stimulus_contract: dict[str, JsonValue],
) -> CorrectionResult:
    """Evaluate only answers whose published oracle is deterministic.

    Open production, oral work and learner self-reports remain evidence awaiting a
    legitimate reviewer; a model answer is never treated as their only valid answer.
    """
    if primitive_id in _OPEN_PRIMITIVES or answer_kind in {
        AnswerKind.ACKNOWLEDGEMENT,
        AnswerKind.NO_ANSWER,
        AnswerKind.SELF_ASSESSMENT,
        AnswerKind.SELF_GRADE,
        AnswerKind.AUDIO_REF,
    }:
        return CorrectionResult.not_evaluable(
            "this response requires a rubric, teacher, or human review"
        )

    expected = response_contract.get("expected_answer")
    if expected is not None:
        return _exact_result(
            raw_value,
            expected,
            unordered_lists=answer_kind in _UNORDERED_LIST_KINDS,
        )

    accepted = stimulus_contract.get("accepted_answers")
    if isinstance(raw_value, str) and isinstance(accepted, list):
        values = tuple(item for item in accepted if isinstance(item, str))
        if values:
            return CorrectionStrategy.accepted_set(values).correct(raw_value)

    return CorrectionResult.not_evaluable(
        "the published exercise has no deterministic correction oracle"
    )


__all__ = ["correct_published_answer"]
