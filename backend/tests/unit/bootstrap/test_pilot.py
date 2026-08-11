from pathlib import Path

from polyglot.bootstrap.pilot import (
    JAPANESE_DAY_ACTIVITIES,
    _library_interaction,
    _preferred_answer_kind,
    fixture_root_from_environment,
)
from polyglot.modules.exercises.core.domain import CORE_PRIMITIVE_IDS


def test_fixture_root_can_be_pinned_for_reproducible_publication(monkeypatch) -> None:
    monkeypatch.setenv("POLYGLOT_FIXTURES_PATH", "/tmp/polyglot-fixtures")

    assert fixture_root_from_environment() == Path("/tmp/polyglot-fixtures").resolve()


def test_pilot_publishes_an_executable_reader_contract_for_every_core_primitive() -> None:
    structured_keys = {
        "single_choice": "choices",
        "graded_choice": "choices",
        "selection": "choices",
        "pairing": "items",
        "grouping": "groups",
        "ordered_items": "items",
        "cells": "cells",
        "spans": "segments",
        "tokens": "slots",
    }

    for primitive_id in CORE_PRIMITIVE_IDS:
        answer_kind = _preferred_answer_kind(primitive_id)
        response, stimulus = _library_interaction(primitive_id, answer_kind)
        assert stimulus["prompt"]
        assert stimulus["model_answer"]
        if answer_kind in structured_keys:
            assert response[structured_keys[answer_kind]]
            assert "expected_answer" in response


def test_japanese_days_cover_the_complete_daily_sprint_chain() -> None:
    expected_families = {
        "EX-REPAIR-01",
        "EX-EXPOSE-01",
        "EX-COMP-03",
        "EX-TRANSFORM-01",
        "EX-ORAL-01",
        "EX-PROD-01",
        "EX-RECALL-04",
    }

    assert set(JAPANESE_DAY_ACTIVITIES) == {1, 2, 3}
    for activities in JAPANESE_DAY_ACTIVITIES.values():
        assert {activity.primitive_id for activity in activities} == expected_families
        assert all(activity.prompt and activity.model_answer for activity in activities)


def test_japanese_reader_contracts_never_fall_back_to_italian_content() -> None:
    for primitive_id in CORE_PRIMITIVE_IDS:
        answer_kind = _preferred_answer_kind(primitive_id)
        response, stimulus = _library_interaction(
            primitive_id, answer_kind, language_tag="ja-JP"
        )
        serialized = str((response, stimulus))
        assert stimulus["language_tag"] == "ja-JP"
        assert "Buongiorno" not in serialized
        assert "vorrei" not in serialized.casefold()
