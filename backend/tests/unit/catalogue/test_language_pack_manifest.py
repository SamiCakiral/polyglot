from uuid import UUID

import pytest

from polyglot.modules.catalogue.core.domain import (
    ContrastiveBridge,
    FunctionConcept,
    GrammarRealization,
    LanguagePackManifest,
    ScriptDefinition,
)
from polyglot.platform.errors import DomainError


def _uuid(value: str) -> UUID:
    return UUID(value)


def test_language_pack_manifest_keeps_language_specific_rules_out_of_the_engine() -> None:
    script = ScriptDefinition(
        code="Latn",
        direction="ltr",
        segmentation="whitespace",
        requires_foundations=False,
    )
    concept = FunctionConcept(
        code="future.intention",
        family="time_action",
        labels={"fr-FR": "exprimer une intention future"},
    )
    realization = GrammarRealization(
        code="it.future.intention.andare_a",
        function_code=concept.code,
        template="andare<finite> a {infinitive}",
        examples=("Vado a prendere il treno.",),
        prerequisite_codes=("it.present.andare",),
    )
    bridge = ContrastiveBridge(
        support_language_tag="fr-FR",
        target_language_tag="it-IT",
        function_code=concept.code,
        explanation="Le futur proche français se rapproche de andare a + infinitif.",
        warnings=("L'italien emploie souvent aussi le présent.",),
    )

    manifest = LanguagePackManifest(
        pack_revision_id=_uuid("019f0000-0000-7000-8000-000000000001"),
        target_language_tag="it-IT",
        display_names={"fr-FR": "Italien"},
        scripts=(script,),
        tts_locale="it-IT",
        functions=(concept,),
        grammar_realizations=(realization,),
        contrastive_bridges=(bridge,),
        version="2.0.0",
    )

    assert manifest.primary_script.direction == "ltr"
    assert manifest.realizations_for(concept.code) == (realization,)
    assert manifest.bridge_for("fr-FR", concept.code) == bridge


def test_manifest_rejects_realization_for_unknown_function() -> None:
    with pytest.raises(DomainError, match="unknown function"):
        LanguagePackManifest(
            pack_revision_id=_uuid("019f0000-0000-7000-8000-000000000001"),
            target_language_tag="it-IT",
            display_names={"fr-FR": "Italien"},
            scripts=(
                ScriptDefinition(
                    code="Latn",
                    direction="ltr",
                    segmentation="whitespace",
                    requires_foundations=False,
                ),
            ),
            tts_locale="it-IT",
            functions=(),
            grammar_realizations=(
                GrammarRealization(
                    code="it.unknown",
                    function_code="unknown",
                    template="x",
                    examples=("x",),
                    prerequisite_codes=(),
                ),
            ),
            contrastive_bridges=(),
            version="2.0.0",
        )
