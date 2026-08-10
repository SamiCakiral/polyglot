"""Golden W03 fixtures are complete, offline, hashed, and semantically closed."""

from pathlib import Path

from polyglot.modules.catalogue.core.fixtures import load_catalogue_fixture
from polyglot.modules.language_profiles.fixtures import load_w03_fixture

ROOT = Path(__file__).resolve().parents[4] / "fixtures/canonical"


def test_persona_fixture_covers_all_diagnostic_oracles_without_implicit_credit() -> None:
    fixture = load_w03_fixture(ROOT / "FX-PERSONAS")

    assert fixture.fixture_id == "FX-PERSONAS"
    assert fixture.network_dependencies == ()
    assert fixture.scenario_ids == ("P-ABS", "P-FAUX", "P-INT", "P-RETOUR")
    assert fixture.oracles["P-ABS"]["classification"] == "beginner"
    assert fixture.oracles["P-FAUX"]["classification"] == "false_beginner"
    assert fixture.oracles["P-INT"]["classification"] == "intermediate"
    assert fixture.oracles["P-RETOUR"]["expired_run_status"] == "expired"
    assert all(item["implicit_mastery_credit"] is False for item in fixture.oracles.values())


def test_italian_foundation_fixture_pins_w04f_and_gate_boundary_oracles() -> None:
    fixture = load_w03_fixture(ROOT / "FX-IT-FOUND")

    assert fixture.fixture_id == "FX-IT-FOUND"
    assert fixture.network_dependencies == ()
    assert fixture.scenario_ids == (
        "F1-F5",
        "audio-absent",
        "gate-24h",
        "revelation",
    )
    assert fixture.oracles["F1-F5"]["published_item_count"] == 32
    assert fixture.oracles["F1-F5"]["distinct_normative_stimuli"] == {
        "grapheme_sound_discrimination": 10,
        "survival_exchange": 5,
        "targeted_reading": 10,
    }
    assert fixture.oracles["gate-24h"]["at_23_59_59"] == "gate_not_ready"
    assert fixture.oracles["gate-24h"]["at_24_00_00"] == "eligible"
    assert fixture.oracles["audio-absent"]["result"] == "not_evaluable"
    assert fixture.oracles["revelation"]["autonomous_credit"] is False


def test_italian_catalogue_publishes_distinct_stimulus_revisions_and_oracles() -> None:
    catalogue = load_catalogue_fixture(ROOT / "FX-CATALOGUE-IT").foundations
    items = tuple(item for block in catalogue.definition.blocks for item in block.items)
    expected = {
        "ITF-F1-01": 10,
        "ITF-F1-02": 10,
        "ITF-F5-02": 5,
    }

    assert len(items) == 32
    for prefix, total in expected.items():
        stimuli = tuple(item for item in items if item.item_code.startswith(prefix))
        assert len(stimuli) == total
        assert len({item.item_revision_id for item in stimuli}) == total
        assert len({item.checker_values for item in stimuli}) == total
