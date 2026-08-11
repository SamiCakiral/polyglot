from pathlib import Path

from polyglot.modules.catalogue.core.fixtures import load_catalogue_fixture

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures/canonical/FX-CATALOGUE-JA"


def test_japanese_pack_is_a_non_latin_executable_language_pack() -> None:
    catalogue = load_catalogue_fixture(FIXTURE)

    assert catalogue.pack.pack_code == "ja-JP__fr-FR"
    assert catalogue.target_variety.language_tag == "ja-JP"
    assert set(catalogue.target_variety.script_codes) == {"Hira", "Kana", "Jpan"}
    assert catalogue.target_variety.text_direction == "ltr"
    assert catalogue.pilot_days == (1, 2, 3)
    assert len(catalogue.lexical_units) == 30
    assert len(catalogue.communicative_functions) == 8
    assert len(catalogue.grammar_structures) == 8
    assert len(catalogue.skills) >= 8
    assert any("hiragana" in item.target_ref for item in catalogue.skills)
    assert {item.lemma for item in catalogue.lexical_units} >= {
        "こんにちは",
        "ありがとう",
        "わたし",
        "です",
        "ください",
    }


def test_japanese_foundations_cover_graphemes_sounds_segmentation_and_survival() -> None:
    foundations = load_catalogue_fixture(FIXTURE).foundations.definition

    assert [block.block_code for block in foundations.blocks] == ["F1", "F2", "F3", "F4", "F5"]
    target_refs = {
        target
        for block in foundations.blocks
        for item in block.items
        for target in item.target_refs
    }
    assert {
        "ja-foundation-hiragana",
        "ja-foundation-sounds",
        "ja-foundation-segmentation",
        "ja-foundation-survival",
    } <= target_refs
