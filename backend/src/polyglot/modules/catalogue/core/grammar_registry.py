from polyglot.modules.catalogue.core.italian_grammar import (
    ITALIAN_GRAMMAR_TOOLBOX,
    GrammarRealizationDefinition,
    GrammarToolbox,
)

_TOOLBOXES = {
    (
        ITALIAN_GRAMMAR_TOOLBOX.target_language_tag,
        ITALIAN_GRAMMAR_TOOLBOX.support_language_tag,
    ): ITALIAN_GRAMMAR_TOOLBOX,
}


def grammar_toolbox_for(
    target_language_tag: str, support_language_tag: str
) -> GrammarToolbox | None:
    return _TOOLBOXES.get((target_language_tag, support_language_tag))


def grammar_realization_for(
    realization_code: str,
) -> GrammarRealizationDefinition | None:
    return next(
        (
            realization
            for toolbox in _TOOLBOXES.values()
            for realization in toolbox.realizations
            if realization.realization_code == realization_code
        ),
        None,
    )


__all__ = ["grammar_realization_for", "grammar_toolbox_for"]
