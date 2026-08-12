import pytest

from polyglot.modules.placement.domain import ScoringKind
from polyglot.modules.placement.scoring import (
    FrozenPlacementItem,
    PlacementAnswer,
    scorer_for,
)
from polyglot.platform.errors import DomainError


def test_single_choice_scores_exact_key() -> None:
    item = FrozenPlacementItem("single_choice", ("reading",), {"value": "b"})
    result = scorer_for(ScoringKind.DETERMINISTIC).score(item, PlacementAnswer({"value": "b"}))
    assert result.score == 1


def test_text_alternatives_are_unicode_and_case_normalized() -> None:
    item = FrozenPlacementItem("text", ("writing",), {"alternatives": ["Per favore"]})
    result = scorer_for(ScoringKind.STRUCTURED).score(
        item, PlacementAnswer({"value": "  PER FAVORE  "})
    )
    assert result.score == 1


def test_invalid_answer_shape_fails_closed() -> None:
    item = FrozenPlacementItem("single_choice", ("reading",), {"value": "a"})
    with pytest.raises(DomainError):
        scorer_for(ScoringKind.DETERMINISTIC).score(item, PlacementAnswer({"other": "a"}))


def test_speaking_without_qualified_path_is_not_evaluable() -> None:
    item = FrozenPlacementItem("speaking", ("speaking",), {})
    result = scorer_for(ScoringKind.NOT_EVALUABLE).score(item, PlacementAnswer({"value": ""}))
    assert not result.evaluable
    assert result.score is None
