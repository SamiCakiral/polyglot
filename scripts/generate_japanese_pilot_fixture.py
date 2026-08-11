#!/usr/bin/env python3
"""Generate the deterministic French-to-Japanese MVP catalogue fixture."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path
from uuid import UUID

from polyglot.modules.catalogue.core.domain import (
    ContentRevisionStatus,
    FoundationCheckerKind,
    FoundationReferenceKind,
    foundation_content_checksum,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "fixtures/canonical/FX-CATALOGUE-JA"
PACK_REVISION_ID = UUID("019c0000-0000-7000-9000-000000000009")
PROVENANCE_ID = UUID("019c0000-0000-7000-9000-000000000001")
STATUS = ContentRevisionStatus.PUBLISHED


def uid(value: int) -> UUID:
    return UUID(f"019c0000-0000-7000-9000-{value:012d}")


FUNCTIONS = (
    ("ja-foundation-hiragana", "Reconnaître les hiragana", ("あ", "い", "う", "え", "お")),
    ("JA-FUNC-GREET", "Saluer", ("こんにちは", "おはようございます")),
    ("JA-FUNC-IDENTIFY", "S'identifier", ("わたしは…です",)),
    ("JA-FUNC-REQUEST", "Formuler une demande", ("…をください",)),
    ("JA-FUNC-QUESTION", "Poser une question", ("…ですか",)),
    ("JA-FUNC-EXIST", "Exprimer l'existence", ("…があります", "…がいます")),
    ("JA-FUNC-LOCATE", "Situer quelque chose", ("…はどこですか",)),
    ("JA-FUNC-REPAIR", "Demander de répéter", ("もういちどおねがいします",)),
)

GRAMMAR = (
    ("JA-GRAM-001", "ja-foundation-hiragana", "[hiragana]", "かな", "あ・い・う・え・お"),
    ("JA-GRAM-002", "JA-FUNC-GREET", "salutation", "salutation", "こんにちは"),
    ("JA-GRAM-003", "JA-FUNC-IDENTIFY", "X は Y です", "X,Y", "わたしはサミです"),
    ("JA-GRAM-004", "JA-FUNC-REQUEST", "X をください", "X", "みずをください"),
    ("JA-GRAM-005", "JA-FUNC-QUESTION", "X ですか", "X", "だいじょうぶですか"),
    ("JA-GRAM-006", "JA-FUNC-EXIST", "X があります/います", "X", "えきがあります"),
    ("JA-GRAM-007", "JA-FUNC-LOCATE", "X はどこですか", "X", "えきはどこですか"),
    (
        "JA-GRAM-008",
        "JA-FUNC-REPAIR",
        "もういちど + おねがいします",
        "request",
        "もういちどおねがいします",
    ),
)

LEXEMES = (
    ("こんにちは", "interjection", "Bonjour."),
    ("おはよう", "interjection", "Bonjour, le matin."),
    ("こんばんは", "interjection", "Bonsoir."),
    ("ありがとう", "interjection", "Merci."),
    ("すみません", "interjection", "Excusez-moi ou pardon."),
    ("はい", "interjection", "Oui."),
    ("いいえ", "interjection", "Non."),
    ("わたし", "pronoun", "Je ou moi."),
    ("あなた", "pronoun", "Vous ou toi, lorsque le contexte l'exige."),
    ("です", "copula", "Copule polie d'identification."),
    ("ます", "auxiliary", "Marque verbale polie."),
    ("ください", "verb", "Donnez-moi, s'il vous plaît."),
    ("おねがいします", "expression", "S'il vous plaît ou je vous en prie."),
    ("なまえ", "noun", "Nom d'une personne."),
    ("みず", "noun", "Eau."),
    ("ごはん", "noun", "Repas ou riz cuit."),
    ("えき", "noun", "Gare."),
    ("でんしゃ", "noun", "Train."),
    ("ホテル", "noun", "Hôtel."),
    ("トイレ", "noun", "Toilettes."),
    ("ここ", "adverb", "Ici."),
    ("そこ", "adverb", "Là, près de l'interlocuteur."),
    ("どこ", "interrogative", "Où."),
    ("これ", "pronoun", "Ceci."),
    ("それ", "pronoun", "Cela, près de l'interlocuteur."),
    ("いくら", "interrogative", "Combien, pour un prix."),
    ("だいじょうぶ", "adjective", "D'accord, sans problème ou en bon état."),
    ("わかります", "verb", "Comprendre, forme polie."),
    ("わかりません", "verb", "Ne pas comprendre, forme polie."),
    ("もういちど", "adverb", "Encore une fois."),
)


def checksum(kind: str, *parts: object) -> str:
    return foundation_content_checksum(kind, *parts)


def foundation_item(
    index: int,
    block_id: UUID,
    block_code: str,
    ordinal: int,
    targets: tuple[str, ...],
    answer: str,
    modalities: tuple[str, ...],
) -> dict[str, object]:
    item_id = uid(1100 + index)
    checker = FoundationCheckerKind.EXACT_CHOICE
    code = f"JAF-{block_code}-{ordinal:02d}"
    values = (answer,)
    return {
        "item_revision_id": str(item_id),
        "block_revision_id": str(block_id),
        "pack_revision_id": str(PACK_REVISION_ID),
        "item_code": code,
        "ordinal": ordinal,
        "target_refs": list(targets),
        "response_kind": "raw",
        "checker_kind": checker.value,
        "checker_values": list(values),
        "modalities": list(modalities),
        "status": STATUS.value,
        "checksum": checksum(
            "foundation_item_v1",
            item_id,
            block_id,
            PACK_REVISION_ID,
            code,
            ordinal,
            targets,
            "raw",
            checker,
            values,
            modalities,
            STATUS,
        ),
    }


def foundations() -> dict[str, object]:
    foundation_id = uid(900)
    revision_id = uid(901)
    foundation_code = "FOUNDATIONS_JA_V0"
    target_refs = (
        "ja-foundation-hiragana",
        "ja-foundation-sounds",
        "ja-foundation-segmentation",
        "ja-foundation-greeting",
        "ja-foundation-request",
        "ja-foundation-survival",
    )
    facets = (
        "grapheme_sound_discrimination",
        "controlled_reading",
        "greeting_recognition",
        "functional_frame_choice",
        "written_guided_repair",
    )
    waiver = "DIAGNOSTIC_WAIVER_JA_V0"
    references: list[dict[str, object]] = []
    for index, (code, kind) in enumerate(
        (
            *((value, FoundationReferenceKind.TARGET) for value in target_refs),
            *((value, FoundationReferenceKind.FACET) for value in facets),
            (waiver, FoundationReferenceKind.WAIVER_POLICY),
        ),
        start=1,
    ):
        reference_id = uid(950 + index)
        references.append(
            {
                "reference_revision_id": str(reference_id),
                "pack_revision_id": str(PACK_REVISION_ID),
                "reference_code": code,
                "reference_kind": kind.value,
                "status": STATUS.value,
                "checksum": checksum(
                    "foundation_reference_v1",
                    reference_id,
                    PACK_REVISION_ID,
                    code,
                    kind,
                    STATUS,
                ),
            }
        )

    specifications = (
        (
            "F1",
            "script_sound",
            (),
            ("listening", "reading"),
            tuple(
                (
                    ("ja-foundation-hiragana", "ja-foundation-sounds"),
                    value,
                    ("listening", "reading"),
                )
                for value in (
                    "あ=a",
                    "い=i",
                    "う=u",
                    "え=e",
                    "お=o",
                    "か=ka",
                    "き=ki",
                    "く=ku",
                    "け=ke",
                    "こ=ko",
                )
            ),
        ),
        (
            "F2",
            "controlled_reading",
            ("ja-foundation-hiragana",),
            ("reading",),
            tuple(
                (("ja-foundation-segmentation",), value, ("reading",))
                for value in (
                    "こんにちは",
                    "ありがとう",
                    "わたし",
                    "みず",
                    "えき",
                    "ここ",
                    "どこ",
                    "です",
                    "ください",
                    "わかりません",
                )
            ),
        ),
        (
            "F3",
            "greeting_recognition",
            ("ja-foundation-segmentation",),
            ("reading", "listening"),
            (
                (("ja-foundation-greeting",), "こんにちは", ("reading",)),
                (("ja-foundation-greeting",), "おはよう", ("listening",)),
            ),
        ),
        (
            "F4",
            "functional_frames",
            ("ja-foundation-greeting",),
            ("reading", "writing"),
            (
                (("ja-foundation-request",), "みずをください", ("reading",)),
                (("ja-foundation-request",), "えきはどこですか", ("reading",)),
                (("ja-foundation-request",), "わたしはサミです", ("writing",)),
            ),
        ),
        (
            "F5",
            "survival_exchange",
            ("ja-foundation-request",),
            ("reading", "writing", "speaking"),
            tuple(
                (("ja-foundation-survival",), value, ("writing",))
                for value in (
                    "すみません",
                    "もういちどおねがいします",
                    "わかりません",
                    "トイレはどこですか",
                    "ありがとう",
                )
            ),
        ),
    )
    blocks: list[dict[str, object]] = []
    item_index = 0
    for ordinal, (code, component, prerequisites, modalities, raw_items) in enumerate(
        specifications, start=1
    ):
        block_id = uid(910 + ordinal)
        items = []
        for item_ordinal, (targets, answer, item_modalities) in enumerate(raw_items, start=1):
            item_index += 1
            items.append(
                foundation_item(
                    item_index,
                    block_id,
                    code,
                    item_ordinal,
                    targets,
                    answer,
                    item_modalities,
                )
            )
        blocks.append(
            {
                "block_revision_id": str(block_id),
                "foundation_revision_id": str(revision_id),
                "pack_revision_id": str(PACK_REVISION_ID),
                "block_code": code,
                "ordinal": ordinal,
                "component_type": component,
                "prerequisite_refs": list(prerequisites),
                "modalities": list(modalities),
                "backend_criteria": ["deterministic"],
                "waiver_policy_ref": waiver,
                "status": STATUS.value,
                "checksum": checksum(
                    "foundation_block_v1",
                    block_id,
                    revision_id,
                    PACK_REVISION_ID,
                    code,
                    ordinal,
                    component,
                    prerequisites,
                    modalities,
                    ("deterministic",),
                    waiver,
                    STATUS,
                ),
                "items": items,
            }
        )

    gate_id = uid(990)
    gate = {
        "gate_revision_id": str(gate_id),
        "foundation_revision_id": str(revision_id),
        "pack_revision_id": str(PACK_REVISION_ID),
        "gate_code": foundation_code,
        "blocking_target_refs": list(target_refs),
        "blocking_facet_refs": list(facets),
        "blocking_facet_minimum_status": "reliable",
        "coverage_threshold": 1.0,
        "confidence_threshold": 0.6,
        "minimum_distinct_sessions": 2,
        "delayed_control_block_code": "F1",
        "delayed_control_hours": 24,
        "grapheme_sound_minimum": 8,
        "grapheme_sound_total": 10,
        "targeted_reading_minimum": 8,
        "targeted_reading_total": 10,
        "survival_exchange_minimum": 4,
        "survival_exchange_total": 5,
        "survival_exchange_without_reveal": True,
        "oral_policy": "not_evaluable_non_blocking",
        "status": STATUS.value,
    }
    gate["checksum"] = checksum(
        "foundation_gate_v1",
        gate_id,
        revision_id,
        PACK_REVISION_ID,
        foundation_code,
        target_refs,
        facets,
        "reliable",
        1.0,
        0.6,
        2,
        "F1",
        24,
        8,
        10,
        8,
        10,
        4,
        5,
        True,
        "not_evaluable_non_blocking",
        STATUS,
    )
    return {
        "foundation_id": str(foundation_id),
        "foundation_revision_id": str(revision_id),
        "pack_revision_id": str(PACK_REVISION_ID),
        "foundation_code": foundation_code,
        "revision_no": 1,
        "references": references,
        "status": STATUS.value,
        "checksum": checksum(
            "foundation_definition_v1",
            revision_id,
            foundation_id,
            PACK_REVISION_ID,
            foundation_code,
            1,
            STATUS,
        ),
        "blocks": blocks,
        "gate": gate,
    }


def catalogue() -> dict[str, object]:
    functions = []
    for index, (code, label, realizations) in enumerate(FUNCTIONS, start=1):
        functions.append(
            {
                "function_revision_id": str(uid(100 + index * 2)),
                "function_id": str(uid(99 + index * 2)),
                "revision_no": 1,
                "function_code": code,
                "label": label,
                "realizations": list(realizations),
                "status": STATUS.value,
                "provenance_id": str(PROVENANCE_ID),
            }
        )
    grammar = []
    for index, (code, function_code, template, slot, example) in enumerate(GRAMMAR, start=1):
        grammar.append(
            {
                "structure_revision_id": str(uid(300 + index * 3)),
                "structure_id": str(uid(299 + index * 3)),
                "revision_no": 1,
                "structure_code": code,
                "function_code": function_code,
                "constraints": {"activation_day": str(min(3, 1 + (index - 1) // 3))},
                "contrasts": ["L'ordre japonais place généralement le prédicat en fin de phrase."],
                "typical_errors": ["Omettre une particule en calquant le français."],
                "variants": [],
                "patterns": [
                    {
                        "pattern_id": str(uid(301 + index * 3)),
                        "pattern_code": f"{code}-P1",
                        "template": template,
                        "slots": [slot],
                        "instantiation_rules": {"register": "polite"},
                        "examples": [example],
                        "counterexamples": [],
                    }
                ],
                "status": STATUS.value,
                "provenance_id": str(PROVENANCE_ID),
            }
        )
    skills = []
    for index, (code, _, _) in enumerate(FUNCTIONS, start=1):
        skills.append(
            {
                "skill_revision_id": str(uid(500 + index * 2)),
                "skill_id": str(uid(499 + index * 2)),
                "revision_no": 1,
                "skill_code": f"JA-SKILL-FUNC-{index:02d}",
                "skill_type": "communicative_function",
                "modality": "reading" if index == 1 else "speaking",
                "operation": "recognize" if index == 1 else "interact",
                "target_ref": code,
                "scope": ["japanese-pilot"],
                "evidence_protocol_ids": [],
                "load_profile": {"intrinsic": min(5, index)},
                "status": STATUS.value,
                "provenance_id": str(PROVENANCE_ID),
            }
        )
    for index, (code, _, _, _, _) in enumerate(GRAMMAR, start=1):
        skills.append(
            {
                "skill_revision_id": str(uid(550 + index * 2)),
                "skill_id": str(uid(549 + index * 2)),
                "revision_no": 1,
                "skill_code": f"JA-SKILL-GRAM-{index:02d}",
                "skill_type": "grammar_structure",
                "modality": "writing",
                "operation": "transform",
                "target_ref": code,
                "scope": ["japanese-pilot"],
                "evidence_protocol_ids": [],
                "load_profile": {"intrinsic": min(5, index)},
                "status": STATUS.value,
                "provenance_id": str(PROVENANCE_ID),
            }
        )
    prerequisites = [
        {
            "edge_id": str(uid(600 + index)),
            "from_skill_revision_id": skills[index - 1]["skill_revision_id"],
            "to_skill_revision_id": skills[index]["skill_revision_id"],
            "edge_type": "required",
            "provenance_id": str(PROVENANCE_ID),
        }
        for index in range(1, len(skills))
    ]
    lexical_units = []
    for index, (lemma, part_of_speech, definition) in enumerate(LEXEMES, start=1):
        base = 2000 + index * 10
        lexical_units.append(
            {
                "unit_revision_id": str(uid(base + 1)),
                "lexical_unit_id": str(uid(base)),
                "revision_no": 1,
                "lemma": lemma,
                "unit_type": "word",
                "part_of_speech": part_of_speech,
                "register": "polite"
                if lemma in {"です", "ます", "ください", "おねがいします"}
                else None,
                "senses": [
                    {
                        "sense_revision_id": str(uid(base + 3)),
                        "sense_id": str(uid(base + 2)),
                        "revision_no": 1,
                        "sense_code": f"JA-SENSE-{index:03d}",
                        "definition": definition,
                        "domains": ["survival"],
                        "register": None,
                        "status": STATUS.value,
                        "provenance_id": str(PROVENANCE_ID),
                    }
                ],
                "forms": [
                    {
                        "form_analysis_id": str(uid(base + 4)),
                        "surface": lemma,
                        "features": {"script": "mixed" if "ー" in lemma else "hiragana"},
                        "pronunciation_refs": [],
                        "normalization_key": unicodedata.normalize("NFC", lemma).casefold(),
                    }
                ],
                "components": [],
                "status": STATUS.value,
                "provenance_id": str(PROVENANCE_ID),
            }
        )
    return {
        "schema_version": 1,
        "fixture_id": "FX-CATALOGUE-JA",
        "pilot_days": [1, 2, 3],
        "linguistic_review": "pending_human",
        "pack": {
            "pack_id": str(uid(8)),
            "pack_revision_id": str(PACK_REVISION_ID),
            "pack_code": "ja-JP__fr-FR",
            "pack_revision_code": "pilot-1.0.0",
            "revision_no": 1,
            "target": {
                "variety_id": str(uid(2)),
                "language_tag": "ja-JP",
                "region_code": "JP",
                "script_codes": ["Hira", "Kana", "Jpan"],
                "text_direction": "ltr",
                "segmentation_policy_revision_id": str(uid(3)),
                "media_capabilities": ["text", "tts"],
                "normalization_policy_revision_id": str(uid(4)),
            },
            "supports": [
                {
                    "variety_id": "019b0000-0000-7000-8000-000000000005",
                    "language_tag": "fr-FR",
                    "region_code": "FR",
                    "script_codes": ["Latn"],
                    "text_direction": "ltr",
                    "segmentation_policy_revision_id": "019b0000-0000-7000-8000-000000000006",
                    "media_capabilities": ["text"],
                    "normalization_policy_revision_id": "019b0000-0000-7000-8000-000000000007",
                }
            ],
            "status": STATUS.value,
            "engine_min_version": "2.0.0",
            "engine_max_version": "2.0.x",
            "capabilities": ["catalogue", "grammar", "lexicon", "skill_graph", "non_latin_script"],
            "checksum_manifest": {"pilot-content": "b" * 64},
            "license_refs": ["CC-BY-4.0"],
            "provenance_id": str(PROVENANCE_ID),
            "published_at": "2026-08-11T12:00:00+00:00",
        },
        "communicative_functions": functions,
        "grammar_structures": grammar,
        "skills": skills,
        "prerequisites": prerequisites,
        "foundations": foundations(),
        "lexical_units": lexical_units,
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(catalogue(), ensure_ascii=False, indent=2) + "\n"
    (OUTPUT / "catalogue.json").write_text(payload, encoding="utf-8")
    manifest = {"id": "FX-CATALOGUE-JA", "kind": "positive", "expected_status": "accepted"}
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata = {
        "schema_version": 1,
        "synthetic": True,
        "seed": 20260811,
        "clock": "2026-08-11T12:00:00+00:00",
        "payloads": {"catalogue.json": f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"},
        "oracles": [
            "published_revisions_immutable",
            "required_prerequisites_acyclic",
            "unicode_normalization_preserved",
            "non_latin_segmentation_explicit",
            "pilot_scope_only",
        ],
        "network_dependencies": [],
        "linguistic_review": "pending_human",
    }
    (OUTPUT / "fixture-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
