from polyglot.modules.catalogue.core.italian_grammar import (
    GrammarFamily,
    GrammarRealizationDefinition,
    GrammarToolbox,
)

_PRIMITIVES = (
    "EX-EXPOSE-01",
    "EX-DISC-01",
    "EX-RECALL-02",
    "EX-RECALL-03",
    "EX-TRANSFORM-01",
    "EX-PROD-01",
)
_TRANSFORMATIONS = ("topic", "polarity", "register", "particle", "context")


def _realization(
    number: int,
    function_code: str,
    family_code: str,
    support_template: str,
    target_template: str,
    example: str,
    *,
    prerequisites: tuple[str, ...] = ("foundation:hiragana",),
    pitfalls: tuple[str, ...] = (),
) -> GrammarRealizationDefinition:
    return GrammarRealizationDefinition(
        realization_code=f"JA-GRAM-{number:03d}",
        function_code=function_code,
        family_code=family_code,
        support_template=support_template,
        target_template=target_template,
        examples=(example,),
        prerequisite_codes=prerequisites,
        variants=(),
        pitfalls=pitfalls,
        compatible_primitives=_PRIMITIVES,
        transformations=_TRANSFORMATIONS,
    )


_FAMILIES = (
    GrammarFamily("script_reading", "Écriture et segmentation"),
    GrammarFamily("greetings", "Salutations"),
    GrammarFamily("identification", "Identification polie"),
    GrammarFamily("requests", "Demandes polies"),
    GrammarFamily("questions", "Questions"),
    GrammarFamily("existence", "Existence"),
    GrammarFamily("location", "Localisation"),
    GrammarFamily("repair", "Réparation de l'échange"),
)

_REALIZATIONS = (
    _realization(1, "decode_hiragana", "script_reading", "syllabe", "かな", "あ・い・う・え・お"),
    _realization(2, "greet", "greetings", "bonjour", "こんにちは", "こんにちは。"),
    _realization(
        3,
        "identify_politely",
        "identification",
        "je suis + nom",
        "X は Y です",
        "わたしはサミです。",
        pitfalls=("La particule は se lit wa dans ce rôle.",),
    ),
    _realization(
        4,
        "request_object",
        "requests",
        "nom + s'il vous plaît",
        "X をください",
        "みずをください。",
    ),
    _realization(
        5, "ask_politely", "questions", "est-ce que X ?", "X ですか", "だいじょうぶですか。"
    ),
    _realization(
        6,
        "express_existence",
        "existence",
        "il y a X",
        "X があります/います",
        "えきがあります。",
        prerequisites=("foundation:hiragana", "grammar:particles"),
    ),
    _realization(
        7, "ask_location", "location", "où est X ?", "X はどこですか", "えきはどこですか。"
    ),
    _realization(
        8,
        "request_repetition",
        "repair",
        "encore une fois, s'il vous plaît",
        "もういちどおねがいします",
        "もういちどおねがいします。",
    ),
)

JAPANESE_GRAMMAR_TOOLBOX = GrammarToolbox(
    target_language_tag="ja-JP",
    support_language_tag="fr-FR",
    version="ja-grammar-1.0.0",
    families=_FAMILIES,
    realizations=_REALIZATIONS,
    priority_realization_codes=tuple(item.realization_code for item in _REALIZATIONS),
)


__all__ = ["JAPANESE_GRAMMAR_TOOLBOX"]
