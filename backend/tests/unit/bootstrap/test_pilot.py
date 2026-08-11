from pathlib import Path

from polyglot.bootstrap.pilot import (
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
