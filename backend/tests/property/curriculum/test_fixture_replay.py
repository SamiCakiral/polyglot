from __future__ import annotations

from pathlib import Path

from hypothesis import given, strategies as st

from polyglot.modules.curriculum.fixtures import fixture_fingerprint_from_file_order


FIXTURE = Path(__file__).parents[4] / "fixtures" / "canonical" / "FX-MODULE-IT"


@given(st.permutations(("module.json", "days.json", "bindings.json", "dialogues.json", "exercises.json", "oracles.json", "revision-cases.json")))
def test_fixture_fingerprint_ignores_file_enumeration_order(order: list[str]) -> None:
    assert fixture_fingerprint_from_file_order(FIXTURE, tuple(order)) == fixture_fingerprint_from_file_order(FIXTURE, tuple(reversed(order)))
