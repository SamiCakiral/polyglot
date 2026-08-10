from pathlib import Path

from polyglot.modules.lexicon.core.fixtures import (
    iter_word_bank_entries,
    load_lexicon_fixture,
    load_word_bank_fixture,
)

ROOT = Path(__file__).resolve().parents[4] / "fixtures" / "canonical"


def test_fx_lexicon_covers_identity_ambiguity_and_late_resolution() -> None:
    fixture = load_lexicon_fixture(ROOT / "FX-LEXICON")

    assert fixture.has_homonyms
    assert fixture.has_polysemy
    assert fixture.has_syncretism
    assert fixture.has_multiword_expression
    assert fixture.has_private_unit
    assert fixture.has_late_resolution


def test_fx_word_bank_is_reproducible_bounded_and_cross_user() -> None:
    fixture = load_word_bank_fixture(ROOT / "FX-WB")

    assert fixture.empty_profile_count == 0
    assert fixture.small_profile_count == 10
    assert fixture.synthetic_count == 100_000
    assert fixture.seed == 6006
    assert fixture.cross_user_oracle is True
    assert fixture.private_context_deleted is True
    assert fixture.network_dependencies == ()


def test_fx_word_bank_materializes_100k_distinct_entries() -> None:
    fixture = load_word_bank_fixture(ROOT / "FX-WB")
    entries = tuple(iter_word_bank_entries(fixture))

    assert len(entries) == 100_000
    assert len({entry.sense_id for entry in entries}) == 100_000
    assert entries[0].label == "lemma-000001"
    assert entries[-1].label == "lemma-100000"
