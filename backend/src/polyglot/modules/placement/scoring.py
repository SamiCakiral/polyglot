import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from polyglot.modules.placement.domain import ScoringKind
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue


def normalize_answer(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", normalized)


@dataclass(frozen=True, slots=True)
class FrozenPlacementItem:
    response_kind: str
    allowed_skill_refs: tuple[str, ...]
    answer_key: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class PlacementAnswer:
    payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ScoringInterpretationDraft:
    evaluable: bool
    score: float | None
    confidence: float
    criterion_scores: tuple[tuple[str, float], ...] = ()
    error_codes: tuple[str, ...] = ()


class PlacementScorer(Protocol):
    def score(
        self, instance: FrozenPlacementItem, answer: PlacementAnswer
    ) -> ScoringInterpretationDraft: ...


def _value(payload: dict[str, JsonValue]) -> JsonValue:
    if set(payload) != {"value"}:
        raise DomainError(ErrorCode.ANSWER_SHAPE_INVALID)
    return payload["value"]


class ClosedTaskScorer:
    def score(
        self, instance: FrozenPlacementItem, answer: PlacementAnswer
    ) -> ScoringInterpretationDraft:
        actual = _value(answer.payload)
        if instance.response_kind in {"multi_choice", "ordering", "pairing"}:
            expected = instance.answer_key.get("values")
            if not isinstance(actual, list) or not isinstance(expected, list):
                raise DomainError(ErrorCode.ANSWER_SHAPE_INVALID)
            score = float(actual == expected)
        else:
            if not isinstance(actual, str):
                raise DomainError(ErrorCode.ANSWER_SHAPE_INVALID)
            expected_value = instance.answer_key.get("value")
            alternatives = instance.answer_key.get("alternatives", [])
            accepted = ([expected_value] if isinstance(expected_value, str) else []) + (
                alternatives if isinstance(alternatives, list) else []
            )
            if not accepted or not all(isinstance(item, str) for item in accepted):
                raise DomainError(ErrorCode.RUBRIC_MISMATCH)
            string_alternatives = [item for item in accepted if isinstance(item, str)]
            score = float(
                normalize_answer(actual) in {normalize_answer(item) for item in string_alternatives}
            )
        return ScoringInterpretationDraft(True, score, 1.0)


class NotEvaluableScorer:
    def score(
        self, instance: FrozenPlacementItem, answer: PlacementAnswer
    ) -> ScoringInterpretationDraft:
        return ScoringInterpretationDraft(False, None, 0, error_codes=("qualified_path_missing",))


def scorer_for(kind: ScoringKind) -> PlacementScorer:
    if kind is ScoringKind.NOT_EVALUABLE:
        return NotEvaluableScorer()
    if kind in {ScoringKind.DETERMINISTIC, ScoringKind.STRUCTURED}:
        return ClosedTaskScorer()
    raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE, detail="structured evaluator required")
