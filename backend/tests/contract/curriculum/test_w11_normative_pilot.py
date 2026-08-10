from __future__ import annotations

import json
from pathlib import Path

from polyglot.modules.curriculum.fixtures import load_italian_curriculum_fixture


FIXTURE = Path(__file__).parents[4] / "fixtures" / "canonical" / "FX-MODULE-IT"


def test_dialogues_match_the_normative_italian_pack_verbatim() -> None:
    payload = json.loads((FIXTURE / "dialogues.json").read_text(encoding="utf-8"))
    lines = {item["id"]: item["lines"] for item in payload["dialogues"]}
    assert lines == {
        "dialogue:j1-contact": [
            "Buongiorno.",
            "Buongiorno. Sono Luca.",
            "Piacere, sono Camille.",
            "Piacere. Arrivederci.",
            "Arrivederci.",
        ],
        "dialogue:j2-cafe": [
            "Buongiorno. Vorrei un caffè e un'acqua, per favore.",
            "Certo. Ecco il caffè.",
            "Grazie. Posso avere il conto?",
            "Certo.",
        ],
        "dialogue:j3-repair": [
            "Scusi, c'è un autobus diretto per il centro?",
            "Sì, parte da qui.",
            "Può ripetere più lentamente, per favore?",
            "L'autobus parte da qui.",
            "Grazie. Ho bisogno di un biglietto.",
            "Ecco.",
        ],
    }


def test_pilot_contains_normative_lexicon_exercises_mission_and_budget_plans() -> None:
    report = load_italian_curriculum_fixture(FIXTURE)

    assert report.lexicon_set_sizes == (
        ("IT-LEXSET-D1", 8),
        ("IT-LEXSET-D2", 8),
        ("IT-LEXSET-D3", 8),
    )
    assert report.target_lexicon_count == 24
    assert report.exercise_count == 35
    assert report.pinned_exercise_revision_count == 35
    assert report.final_mission_criteria == (
        "closing",
        "existence_or_location_question",
        "express_need",
        "greeting",
        "polite_request",
        "repair_strategy",
    )
    assert report.budget_plan_keys == (
        "D1-15", "D1-30", "D1-60",
        "D2-15", "D2-30", "D2-60",
        "D3-15", "D3-30", "D3-60",
    )
