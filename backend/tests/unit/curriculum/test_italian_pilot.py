from __future__ import annotations

from pathlib import Path

from polyglot.modules.curriculum.fixtures import load_italian_curriculum_fixture

FIXTURE = Path(__file__).parents[4] / "fixtures" / "canonical" / "FX-MODULE-IT"


def test_pilot_orders_explanation_before_gym_and_j1_recall() -> None:
    report = load_italian_curriculum_fixture(FIXTURE)
    assert report.grammar_families == ("existence", "identity", "polite-request")
    assert report.gym_operations == ("GYM-01", "GYM-03", "GYM-08")
    assert report.recall_edges == ((1, 2), (2, 3))


def test_pilot_executes_distinct_morphology_and_pronunciation_oracles() -> None:
    report = load_italian_curriculum_fixture(FIXTURE)
    assert report.morphology_surfaces == (
        "c'è",
        "ci sono",
        "ha",
        "hai",
        "ho",
        "posso",
        "può",
        "sei",
        "sono",
        "vorrei",
    )
    assert report.not_evaluable_pronunciation_refs == ("pron:shadowing-dialogue-j2",)
    assert "pron:e-vs-e-accent" in report.credit_eligible_refs
