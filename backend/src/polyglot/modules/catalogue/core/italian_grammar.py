from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GrammarFamily:
    code: str
    label: str


@dataclass(frozen=True, slots=True)
class GrammarRealizationDefinition:
    realization_code: str
    function_code: str
    family_code: str
    support_template: str
    target_template: str
    examples: tuple[str, ...]
    prerequisite_codes: tuple[str, ...]
    variants: tuple[str, ...]
    pitfalls: tuple[str, ...]
    compatible_primitives: tuple[str, ...]
    transformations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GrammarToolbox:
    target_language_tag: str
    support_language_tag: str
    version: str
    families: tuple[GrammarFamily, ...]
    realizations: tuple[GrammarRealizationDefinition, ...]
    priority_realization_codes: tuple[str, ...]


_FAMILIES = (
    GrammarFamily("existence_identification", "Existence et identification"),
    GrammarFamily("volition_modality", "Volonté, capacité et obligation"),
    GrammarFamily("time_aspect", "Temps et déroulement"),
    GrammarFamily("habit_frequency", "Habitude et fréquence"),
    GrammarFamily("preferences_emotions", "Goûts, préférences et émotions"),
    GrammarFamily("attempt_success", "Essai, réussite et difficulté"),
    GrammarFamily("cause_result_purpose", "Cause, conséquence et but"),
    GrammarFamily("condition_hypothesis", "Condition et hypothèse"),
    GrammarFamily("comparison_degree", "Comparaison et degré"),
    GrammarFamily("manner_simultaneity", "Manière et simultanéité"),
    GrammarFamily("questions", "Questions générales"),
    GrammarFamily("polite_requests", "Demandes polies"),
    GrammarFamily("opinion_certainty", "Opinion, certitude et doute"),
    GrammarFamily("discourse_links", "Relations entre les idées"),
    GrammarFamily("relative_clauses", "Relatives"),
    GrammarFamily("pronouns", "Pronoms utiles"),
    GrammarFamily("directives", "Ordres, conseils et interdictions"),
    GrammarFamily("priority_productive", "Structures productives prioritaires"),
)

_PRIMITIVES = (
    "EX-EXPOSE-01",
    "EX-DISC-01",
    "EX-RECALL-02",
    "EX-RECALL-03",
    "EX-TRANSFORM-01",
    "EX-PROD-01",
)
_TRANSFORMATIONS = (
    "person",
    "tense",
    "polarity",
    "register",
    "modality",
    "pronouns",
    "context",
)


def _item(
    number: int,
    function_code: str,
    family_code: str,
    support_template: str,
    target_template: str,
    example: str,
    *,
    prerequisites: tuple[str, ...] = ("foundation:sentence",),
    variants: tuple[str, ...] = (),
    pitfalls: tuple[str, ...] = (),
) -> GrammarRealizationDefinition:
    return GrammarRealizationDefinition(
        realization_code=f"IT-GRAM-{number:03d}",
        function_code=function_code,
        family_code=family_code,
        support_template=support_template,
        target_template=target_template,
        examples=(example,),
        prerequisite_codes=prerequisites,
        variants=variants,
        pitfalls=pitfalls,
        compatible_primitives=_PRIMITIVES,
        transformations=_TRANSFORMATIONS,
    )


_REALIZATIONS = (
    _item(
        1,
        "express_will",
        "volition_modality",
        "je veux + infinitif",
        "voglio + infinito",
        "Voglio mangiare.",
    ),
    _item(
        2,
        "make_polite_request",
        "polite_requests",
        "je voudrais + nom/infinitif",
        "vorrei + nome/infinito",
        "Vorrei un caffè.",
        pitfalls=("Ne pas calquer une demande polie avec voglio.",),
    ),
    _item(
        3,
        "request_permission",
        "volition_modality",
        "est-ce que je peux + infinitif ?",
        "posso + infinito?",
        "Posso entrare?",
    ),
    _item(
        4,
        "request_formally",
        "polite_requests",
        "pouvez-vous + infinitif ?",
        "può + infinito?",
        "Può ripetere?",
        prerequisites=("foundation:infinitive", "register:formal"),
        pitfalls=("L'accent de può est obligatoire.",),
    ),
    _item(
        5,
        "express_personal_obligation",
        "volition_modality",
        "je dois + infinitif",
        "devo + infinito",
        "Devo partire.",
    ),
    _item(
        6,
        "express_general_obligation",
        "volition_modality",
        "il faut + infinitif",
        "bisogna + infinito",
        "Bisogna prenotare.",
        pitfalls=("Bisogna exprime une nécessité générale, pas une personne précise.",),
    ),
    _item(
        7,
        "express_need",
        "volition_modality",
        "j'ai besoin de + nom",
        "ho bisogno di + nome",
        "Ho bisogno di aiuto.",
    ),
    _item(
        8,
        "express_necessity",
        "volition_modality",
        "il me faut + nom",
        "mi serve/servono + nome",
        "Mi servono due biglietti.",
        prerequisites=("foundation:number",),
        pitfalls=("Serve s'accorde au singulier et servono au pluriel.",),
    ),
    _item(
        9,
        "express_progressive_action",
        "time_aspect",
        "être en train de + infinitif",
        "stare + gerundio",
        "Sto mangiando.",
        prerequisites=("morphology:present", "morphology:gerund"),
    ),
    _item(
        10,
        "express_recent_past",
        "time_aspect",
        "venir de + infinitif",
        "avere appena + participio",
        "Ho appena mangiato.",
        prerequisites=("morphology:compound_past",),
    ),
    _item(
        11,
        "express_continuation",
        "time_aspect",
        "continuer à + infinitif",
        "continuare a + infinito",
        "Continuo a studiare.",
    ),
    _item(
        12,
        "express_beginning",
        "time_aspect",
        "commencer à + infinitif",
        "cominciare a + infinito",
        "Comincio a capire.",
    ),
    _item(
        13,
        "express_stopping",
        "time_aspect",
        "arrêter de + infinitif",
        "smettere di + infinito",
        "Smetto di fumare.",
        pitfalls=("Smettere sélectionne di, pas a.",),
    ),
    _item(
        14,
        "express_attempt",
        "attempt_success",
        "essayer de + infinitif",
        "cercare di + infinito",
        "Cerco di capire.",
    ),
    _item(
        15,
        "express_success",
        "attempt_success",
        "arriver à + infinitif",
        "riuscire a + infinito",
        "Riesco a capirlo.",
    ),
    _item(
        16,
        "express_failure",
        "attempt_success",
        "ne pas arriver à + infinitif",
        "non riuscire a + infinito",
        "Non riesco a dormire.",
    ),
    _item(
        17,
        "express_difficulty",
        "attempt_success",
        "avoir du mal à + infinitif",
        "fare fatica a + infinito",
        "Faccio fatica a parlare.",
    ),
    _item(
        18,
        "express_habit",
        "habit_frequency",
        "avoir l'habitude de + infinitif",
        "essere abituato a + infinito",
        "Sono abituato a correre presto.",
        prerequisites=("morphology:agreement",),
        pitfalls=("Abituato s'accorde avec la personne qui parle.",),
    ),
    _item(
        19,
        "express_desire",
        "preferences_emotions",
        "avoir envie de + infinitif",
        "avere voglia di + infinito",
        "Ho voglia di mangiare.",
    ),
    _item(
        20,
        "express_liking",
        "preferences_emotions",
        "aimer + nom/infinitif",
        "mi piace/piacciono + nome/infinito",
        "Mi piacciono questi libri.",
        prerequisites=("foundation:number",),
        pitfalls=("Piace ou piacciono s'accorde avec ce qui plaît.",),
    ),
    _item(
        21,
        "express_real_condition",
        "condition_hypothesis",
        "si + présent",
        "se + presente",
        "Se piove, resto a casa.",
    ),
    _item(
        22,
        "express_purpose",
        "cause_result_purpose",
        "pour + infinitif",
        "per + infinito",
        "Studio per imparare.",
    ),
    _item(
        23,
        "express_anteriority",
        "manner_simultaneity",
        "avant de + infinitif",
        "prima di + infinito",
        "Mangio prima di partire.",
    ),
    _item(
        24,
        "express_posteriority",
        "manner_simultaneity",
        "après avoir + participe",
        "dopo aver + participio",
        "Dopo aver mangiato, esco.",
        prerequisites=("morphology:past_participle",),
    ),
    _item(
        25,
        "express_absence_of_action",
        "manner_simultaneity",
        "sans + infinitif",
        "senza + infinito",
        "Esce senza parlare.",
    ),
    _item(
        26,
        "express_simultaneity",
        "manner_simultaneity",
        "pendant que + verbe",
        "mentre + verbo",
        "Ascolto musica mentre corro.",
    ),
    _item(
        27,
        "express_existence",
        "existence_identification",
        "il y a + nom",
        "c'è/ci sono + nome",
        "C'è una farmacia. Ci sono due camere.",
        prerequisites=("foundation:number",),
        pitfalls=(
            "C'è prend un singulier; ci sono prend un pluriel.",
            "L'apostrophe de c'è est obligatoire.",
        ),
    ),
    _item(
        28,
        "identify_or_question",
        "existence_identification",
        "c'est/est-ce + nom ou adjectif",
        "è + nome/aggettivo?",
        "È facile?",
        pitfalls=("L'accent distingue è du connecteur e.",),
    ),
    _item(
        29,
        "express_uncertainty",
        "opinion_certainty",
        "je ne sais pas si + proposition",
        "non so se + proposizione",
        "Non so se è aperto.",
    ),
    _item(
        30,
        "express_opinion",
        "opinion_certainty",
        "je pense que + proposition",
        "penso che + proposizione",
        "Penso che sia utile.",
        prerequisites=("foundation:clause",),
        variants=("Penso che + indicatif dans certains usages informels",),
        pitfalls=("Une opinion incertaine appelle souvent le subjonctif.",),
    ),
)

ITALIAN_GRAMMAR_TOOLBOX = GrammarToolbox(
    target_language_tag="it-IT",
    support_language_tag="fr-FR",
    version="it-grammar-1.0.0",
    families=_FAMILIES,
    realizations=_REALIZATIONS,
    priority_realization_codes=tuple(item.realization_code for item in _REALIZATIONS),
)


__all__ = [
    "ITALIAN_GRAMMAR_TOOLBOX",
    "GrammarFamily",
    "GrammarRealizationDefinition",
    "GrammarToolbox",
]
