from datetime import UTC, datetime
from uuid import UUID

import pytest

from polyglot.modules.lexicon.core.domain import (
    CandidateSense,
    LexicalForm,
    LexicalMention,
    LexicalRelation,
    LexicalRelationType,
    LexicalSense,
    LexicalUnit,
    LexicalUnitType,
    MentionResolution,
)
from polyglot.platform.errors import DomainError


def uid(number: int) -> UUID:
    return UUID(f"019feb10-0000-7000-8000-{number:012x}")


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def test_homonyms_and_polysemy_never_collapse_to_a_normalized_string() -> None:
    adverb = LexicalSense(uid(11), uid(1), "piano.adverb.slowly", "lentement")
    noun = LexicalSense(uid(12), uid(2), "piano.noun.instrument", "instrument")
    floor = LexicalSense(uid(13), uid(2), "piano.noun.floor", "etage")

    assert len({adverb.identity_key, noun.identity_key, floor.identity_key}) == 3
    assert adverb.normalized_label == noun.normalized_label == floor.normalized_label == "piano"


def test_inflected_and_syncretic_forms_keep_distinct_candidate_analyses() -> None:
    form = LexicalForm(
        form_id=uid(20),
        surface="sono",
        normalization_key="sono",
        analysis_keys=("essere.ind.pres.1s", "essere.ind.pres.3p"),
    )
    mention = LexicalMention(
        mention_id=uid(21),
        encounter_id=uid(22),
        exact_surface="sono",
        form_id=form.form_id,
        candidates=(
            CandidateSense(uid(23), uid(31), 0.52, "morphology"),
            CandidateSense(uid(24), uid(31), 0.48, "morphology"),
        ),
        created_at=NOW,
    )

    assert len(form.analysis_keys) == 2
    assert mention.is_ambiguous
    with pytest.raises(DomainError):
        MentionResolution(
            resolution_id=uid(25),
            mention_id=mention.mention_id,
            sense_id=uid(99),
            candidate_id=uid(99),
            resolver_type="user",
            confidence=1.0,
            created_at=NOW,
        ).validate_against(mention)


def test_multiword_expression_has_ordered_components_and_stable_identity() -> None:
    unit = LexicalUnit(
        lexical_unit_id=uid(40),
        variety_id=uid(41),
        unit_type=LexicalUnitType.MULTIWORD_EXPRESSION,
        lemma="avere bisogno di",
        components=(uid(42), uid(43), uid(44)),
        visibility="shared",
    )

    assert unit.components == (uid(42), uid(43), uid(44))
    assert unit.identity_key != unit.normalization_key


def test_relations_are_typed_directional_and_provenanced() -> None:
    relation = LexicalRelation(
        relation_id=uid(50),
        source_sense_id=uid(51),
        target_sense_id=uid(52),
        relation_type=LexicalRelationType.CONFUSABLE,
        direction="directed",
        provenance_ref="FX-LEXICON:piano",
        confidence=0.9,
    )

    assert relation.source_sense_id != relation.target_sense_id
    assert relation.relation_type is LexicalRelationType.CONFUSABLE

