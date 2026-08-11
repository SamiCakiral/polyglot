"""Idempotent publication of the local French to Italian MVP pilot."""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from polyglot.bootstrap.database import migration_database_url_from_environment
from polyglot.modules.catalogue.core.fixtures import CatalogueFixture, load_catalogue_fixture
from polyglot.modules.exercises.core.domain import primitive_spec
from polyglot.platform.errors import DomainError, ErrorCode

PILOT_OWNER_ID = UUID("019b0000-0000-7000-8000-0000000000f0")
PILOT_PUBLICATION_ID = UUID("019b0000-0000-7000-8000-00000000000a")
PILOT_MODULE_ID = UUID("019fe113-0000-7000-8000-000000000001")
PILOT_MODULE_REVISION_ID = UUID("019fe113-0000-7000-8000-000000000002")
PILOT_REFERENCE_SET_ID = UUID("019fe113-0000-7000-8200-000000000001")


@dataclass(frozen=True, slots=True)
class PilotBootstrapResult:
    created: bool
    foundation_items: int
    exercise_definitions: int
    module_days: int


def fixture_root_from_environment() -> Path:
    configured = os.environ.get("POLYGLOT_FIXTURES_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.cwd().parent / "fixtures" / "canonical").resolve()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _definition_id(index: int) -> UUID:
    return UUID(f"019fe113-0000-7000-8101-{index:012d}")


def _day_id(ordinal: int) -> UUID:
    return UUID(f"019fe113-0000-7000-8100-{ordinal:012d}")


def _policy_id(offset: int) -> UUID:
    return UUID(f"019fe113-0000-7000-8700-{offset:012d}")


def _realization_id(unit_index: int, form_index: int, sense_index: int) -> UUID:
    suffix = unit_index * 10_000 + form_index * 100 + sense_index
    return UUID(f"019fe113-0000-7000-8300-{suffix:012d}")


def _preferred_answer_kind(primitive_id: str) -> str:
    available = tuple(value.value for value in primitive_spec(primitive_id).answer_kinds)
    for preferred in ("text", "short_text", "single_choice", "self_grade", "self_assessment", "acknowledgement"):
        if preferred in available:
            return preferred
    return available[0]


async def _seed_lexicon(
    session: AsyncSession,
    fixture: CatalogueFixture,
    now: datetime,
) -> None:
    units_by_lemma = {unit.lemma: unit for unit in fixture.lexical_units}
    for unit_index, unit in enumerate(fixture.lexical_units, start=1):
        await session.execute(
            text(
                "INSERT INTO catalogue.lexical_units "
                "(lexical_unit_id,variety_id,unit_type,visibility,owner_profile_id) "
                "VALUES (:id,:variety,:type,'shared',NULL) ON CONFLICT DO NOTHING"
            ),
            {"id": unit.lexical_unit_id, "variety": fixture.target_variety.variety_id, "type": unit.unit_type.value},
        )
        await session.execute(
            text(
                "INSERT INTO catalogue.lexical_unit_revisions "
                "(unit_revision_id,lexical_unit_id,pack_revision_id,revision_no,lemma,part_of_speech,"
                "register,status,provenance_id) VALUES "
                "(:revision,:unit,:pack,:revision_no,:lemma,:part_of_speech,:register,'approved',:provenance) "
                "ON CONFLICT DO NOTHING"
            ),
            {"revision": unit.unit_revision_id, "unit": unit.lexical_unit_id, "pack": fixture.pack_revision.pack_revision_id, "revision_no": unit.revision_no, "lemma": unit.lemma, "part_of_speech": unit.part_of_speech, "register": unit.register, "provenance": unit.provenance_id},
        )
        for sense in unit.senses:
            await session.execute(
                text(
                    "INSERT INTO catalogue.lexical_senses (sense_id,lexical_unit_id,sense_code) "
                    "VALUES (:sense,:unit,:code) ON CONFLICT DO NOTHING"
                ),
                {"sense": sense.sense_id, "unit": unit.lexical_unit_id, "code": sense.sense_code},
            )
            await session.execute(
                text(
                    "INSERT INTO catalogue.lexical_sense_revisions "
                    "(sense_revision_id,sense_id,pack_revision_id,revision_no,definition,domains,register,status,provenance_id) "
                    "VALUES (:revision,:sense,:pack,:revision_no,:definition,:domains,:register,'approved',:provenance) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"revision": sense.sense_revision_id, "sense": sense.sense_id, "pack": fixture.pack_revision.pack_revision_id, "revision_no": sense.revision_no, "definition": sense.definition, "domains": list(sense.domains), "register": sense.register, "provenance": sense.provenance_id},
            )
        for form_index, form in enumerate(unit.forms, start=1):
            await session.execute(
                text(
                    "INSERT INTO catalogue.form_analyses "
                    "(form_analysis_id,unit_revision_id,surface,morphological_features,pronunciation_refs,normalization_key) "
                    "VALUES (:id,:revision,:surface,CAST(:features AS jsonb),:pronunciation,:key) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"id": form.form_analysis_id, "revision": unit.unit_revision_id, "surface": form.surface, "features": _json(dict(form.features)), "pronunciation": list(form.pronunciation_refs), "key": form.normalization_key},
            )
            for sense_index, sense in enumerate(unit.senses, start=1):
                await session.execute(
                    text(
                        "INSERT INTO catalogue.form_realizations "
                        "(realization_id,form_analysis_id,unit_revision_id,sense_revision_id) "
                        "VALUES (:id,:form,:unit,:sense) ON CONFLICT DO NOTHING"
                    ),
                    {"id": _realization_id(unit_index, form_index, sense_index), "form": form.form_analysis_id, "unit": unit.unit_revision_id, "sense": sense.sense_revision_id},
                )
        for position, component in enumerate(unit.components, start=1):
            await session.execute(
                text(
                    "INSERT INTO catalogue.expression_components "
                    "(expression_unit_revision_id,component_unit_revision_id,position) "
                    "VALUES (:expression,:component,:position) ON CONFLICT DO NOTHING"
                ),
                {"expression": unit.unit_revision_id, "component": units_by_lemma[component].unit_revision_id, "position": position},
            )
    await session.execute(
        text(
            "INSERT INTO lexicon.lexical_reference_sets "
            "(reference_set_id,code,revision,label,created_at) "
            "VALUES (:id,'it-pilot-core','v1','Lexique italien pilote',:now) ON CONFLICT DO NOTHING"
        ),
        {"id": PILOT_REFERENCE_SET_ID, "now": now},
    )
    ordinal = 1
    for unit in fixture.lexical_units:
        for sense in unit.senses:
            await session.execute(
                text(
                    "INSERT INTO lexicon.lexical_reference_entries "
                    "(reference_set_id,sense_id,ordinal,label,definition) "
                    "VALUES (:set,:sense,:ordinal,:label,:definition) ON CONFLICT DO NOTHING"
                ),
                {"set": PILOT_REFERENCE_SET_ID, "sense": sense.sense_id, "ordinal": ordinal, "label": unit.lemma, "definition": sense.definition},
            )
            ordinal += 1
    await session.execute(
        text(
            "UPDATE catalogue.lexical_unit_revisions SET status='published' "
            "WHERE pack_revision_id=:revision AND status='approved'"
        ),
        {"revision": fixture.pack_revision.pack_revision_id},
    )
    await session.execute(
        text(
            "UPDATE catalogue.lexical_sense_revisions SET status='published' "
            "WHERE pack_revision_id=:revision AND status='approved'"
        ),
        {"revision": fixture.pack_revision.pack_revision_id},
    )


async def _seed_catalogue(
    session: AsyncSession, root: Path, now: datetime
) -> tuple[CatalogueFixture, int]:
    fixture = load_catalogue_fixture(root / "FX-CATALOGUE-IT")
    pack = fixture.pack_revision
    await session.execute(
        text(
            "INSERT INTO identity.accounts "
            "(account_id,status,security_version,session_version,version,created_at,security_last_activity_at) "
            "VALUES (:id,'active',1,1,1,:now,:now) ON CONFLICT DO NOTHING"
        ),
        {"id": PILOT_OWNER_ID, "now": now},
    )
    await session.execute(
        text(
            "INSERT INTO platform.provenance_records "
            "(provenance_id,source_type,source_ref,transformation_chain,input_fingerprint,created_at) "
            "VALUES (:id,'project_authored','FX-CATALOGUE-IT','[]'::jsonb,:fingerprint,:now) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": pack.provenance_id, "fingerprint": "a" * 64, "now": now},
    )
    for variety in (fixture.target_variety, *fixture.support_varieties):
        await session.execute(
            text(
                "INSERT INTO catalogue.language_varieties "
                "(variety_id,language_tag,region_code,script_codes,text_direction,"
                "segmentation_policy_revision_id,media_capabilities,normalization_policy_revision_id) "
                "VALUES (:id,:tag,:region,:scripts,:direction,:segmentation,"
                "CAST(:media AS jsonb),:normalization) ON CONFLICT DO NOTHING"
            ),
            {
                "id": variety.variety_id,
                "tag": variety.language_tag,
                "region": variety.region_code,
                "scripts": list(variety.script_codes),
                "direction": variety.text_direction,
                "segmentation": variety.segmentation_policy_revision_id,
                "media": _json({"schema_version": 1, "capabilities": list(variety.media_capabilities)}),
                "normalization": variety.normalization_policy_revision_id,
            },
        )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_packs (pack_id,pack_code) "
            "VALUES (:id,:code) ON CONFLICT DO NOTHING"
        ),
        {"id": fixture.pack.pack_id, "code": fixture.pack.pack_code},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_pack_revisions "
            "(pack_revision_id,pack_id,revision_no,target_variety_id,status,engine_min_version,"
            "engine_max_version,capability_manifest,checksum_manifest,license_refs,provenance_id,published_at) "
            "VALUES (:revision,:pack,:number,:target,'approved',:minimum,:maximum,"
            "CAST(:capabilities AS jsonb),CAST(:checksums AS jsonb),:licenses,:provenance,:published) "
            "ON CONFLICT DO NOTHING"
        ),
        {
            "revision": pack.pack_revision_id,
            "pack": pack.pack_id,
            "number": pack.revision_no,
            "target": pack.target_variety_id,
            "minimum": pack.engine_min_version,
            "maximum": pack.engine_max_version,
            "capabilities": _json({"schema_version": 1, "capabilities": list(pack.capabilities)}),
            "checksums": _json(dict(pack.checksum_manifest)),
            "licenses": list(pack.license_refs),
            "provenance": pack.provenance_id,
            "published": None,
        },
    )
    for variety_id in pack.support_variety_ids:
        await session.execute(
            text(
                "INSERT INTO catalogue.language_pack_support_varieties (pack_revision_id,variety_id) "
                "VALUES (:pack,:variety) ON CONFLICT DO NOTHING"
            ),
            {"pack": pack.pack_revision_id, "variety": variety_id},
        )
    for skill in fixture.skills:
        await session.execute(
            text(
                "INSERT INTO catalogue.skills (skill_id,skill_code) VALUES (:id,:code) "
                "ON CONFLICT DO NOTHING"
            ),
            {"id": skill.skill_id, "code": skill.skill_code},
        )
        await session.execute(
            text(
                "INSERT INTO catalogue.skill_revisions "
                "(skill_revision_id,skill_id,pack_revision_id,revision_no,skill_type,modality,"
                "operation,target_ref,scope,evidence_protocol_ids,load_profile,status,provenance_id) "
                "VALUES (:revision,:skill,:pack,:number,:type,:modality,:operation,:target,"
                "CAST(:scope AS jsonb),:protocols,CAST(:load AS jsonb),'published',:provenance) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "revision": skill.skill_revision_id,
                "skill": skill.skill_id,
                "pack": pack.pack_revision_id,
                "number": skill.revision_no,
                "type": skill.skill_type,
                "modality": skill.modality,
                "operation": skill.operation,
                "target": skill.target_ref,
                "scope": _json({"values": list(skill.scope)}),
                "protocols": list(skill.evidence_protocol_ids),
                "load": _json(dict(skill.load_profile)),
                "provenance": skill.provenance_id,
            },
        )
    foundations = fixture.foundations
    definition = foundations.definition
    await session.execute(
        text(
            "INSERT INTO catalogue.foundation_definitions (foundation_id,foundation_code) "
            "VALUES (:id,:code) ON CONFLICT DO NOTHING"
        ),
        {"id": definition.foundation_id, "code": definition.foundation_code},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.foundation_definition_revisions "
            "(foundation_revision_id,foundation_id,pack_revision_id,revision_no,status,checksum) "
            "VALUES (:revision,:foundation,:pack,:number,'published',:checksum) ON CONFLICT DO NOTHING"
        ),
        {
            "revision": definition.foundation_revision_id,
            "foundation": definition.foundation_id,
            "pack": definition.pack_revision_id,
            "number": definition.revision_no,
            "checksum": definition.checksum,
        },
    )
    for reference in foundations.references:
        await session.execute(
            text(
                "INSERT INTO catalogue.foundation_reference_revisions "
                "(reference_revision_id,pack_revision_id,reference_code,reference_kind,status,checksum) "
                "VALUES (:id,:pack,:code,:kind,'published',:checksum) ON CONFLICT DO NOTHING"
            ),
            {"id": reference.reference_revision_id, "pack": reference.pack_revision_id, "code": reference.reference_code, "kind": reference.reference_kind.value, "checksum": reference.checksum},
        )
    item_count = 0
    for block in definition.blocks:
        await session.execute(
            text(
                "INSERT INTO catalogue.foundation_block_revisions "
                "(block_revision_id,foundation_revision_id,pack_revision_id,block_code,ordinal,"
                "component_type,prerequisite_refs,modalities,backend_criteria,waiver_policy_ref,status,checksum) "
                "VALUES (:id,:foundation,:pack,:code,:ordinal,:component,:prerequisites,:modalities,"
                ":criteria,:waiver,'published',:checksum) ON CONFLICT DO NOTHING"
            ),
            {"id": block.block_revision_id, "foundation": block.foundation_revision_id, "pack": block.pack_revision_id, "code": block.block_code, "ordinal": block.ordinal, "component": block.component_type, "prerequisites": list(block.prerequisite_refs), "modalities": list(block.modalities), "criteria": list(block.backend_criteria), "waiver": block.waiver_policy_ref, "checksum": block.checksum},
        )
        for item in block.items:
            await session.execute(
                text(
                    "INSERT INTO catalogue.foundation_item_revisions "
                    "(item_revision_id,block_revision_id,pack_revision_id,item_code,ordinal,target_refs,"
                    "response_kind,checker_kind,checker_values,modalities,status,checksum) "
                    "VALUES (:id,:block,:pack,:code,:ordinal,:targets,:response,:checker,:values,"
                    ":modalities,'published',:checksum) ON CONFLICT DO NOTHING"
                ),
                {"id": item.item_revision_id, "block": item.block_revision_id, "pack": item.pack_revision_id, "code": item.item_code, "ordinal": item.ordinal, "targets": list(item.target_refs), "response": item.response_kind, "checker": item.checker_kind.value, "values": list(item.checker_values), "modalities": list(item.modalities), "checksum": item.checksum},
            )
            item_count += 1
    gate = definition.gate
    await session.execute(
        text(
            "INSERT INTO catalogue.foundation_gate_revisions "
            "(gate_revision_id,foundation_revision_id,pack_revision_id,gate_code,blocking_target_refs,"
            "blocking_facet_refs,blocking_facet_minimum_status,coverage_threshold,confidence_threshold,"
            "minimum_distinct_sessions,delayed_control_block_code,delayed_control_hours,"
            "grapheme_sound_minimum,grapheme_sound_total,targeted_reading_minimum,targeted_reading_total,"
            "survival_exchange_minimum,survival_exchange_total,survival_exchange_without_reveal,"
            "oral_policy,status,checksum) VALUES (:id,:foundation,:pack,:code,:targets,:facets,"
            ":minimum_status,:coverage,:confidence,:sessions,:delayed_block,:delayed_hours,"
            ":grapheme_min,:grapheme_total,:reading_min,:reading_total,:survival_min,:survival_total,"
            ":without_reveal,:oral,'published',:checksum) ON CONFLICT DO NOTHING"
        ),
        {"id": gate.gate_revision_id, "foundation": gate.foundation_revision_id, "pack": gate.pack_revision_id, "code": gate.gate_code, "targets": list(gate.blocking_target_refs), "facets": list(gate.blocking_facet_refs), "minimum_status": gate.blocking_facet_minimum_status, "coverage": gate.coverage_threshold, "confidence": gate.confidence_threshold, "sessions": gate.minimum_distinct_sessions, "delayed_block": gate.delayed_control_block_code, "delayed_hours": gate.delayed_control_hours, "grapheme_min": gate.grapheme_sound_minimum, "grapheme_total": gate.grapheme_sound_total, "reading_min": gate.targeted_reading_minimum, "reading_total": gate.targeted_reading_total, "survival_min": gate.survival_exchange_minimum, "survival_total": gate.survival_exchange_total, "without_reveal": gate.survival_exchange_without_reveal, "oral": gate.oral_policy, "checksum": gate.checksum},
    )
    await session.execute(
        text(
            "UPDATE catalogue.language_pack_revisions SET status='published',published_at=:now "
            "WHERE pack_revision_id=:revision AND status='approved'"
        ),
        {"revision": pack.pack_revision_id, "now": pack.published_at or now},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_pack_publications "
            "(publication_id,pack_id,pack_revision_id,channel,compatibility_range,published_at,retired_at) "
            "VALUES (:id,:pack,:revision,'stable','>=2.0.0,<2.1.0',:now,NULL) "
            "ON CONFLICT DO NOTHING"
        ),
        {
            "id": PILOT_PUBLICATION_ID,
            "pack": pack.pack_id,
            "revision": pack.pack_revision_id,
            "now": pack.published_at or now,
        },
    )
    return fixture, item_count


async def _seed_exercises_and_module(
    session: AsyncSession,
    root: Path,
    fixture: CatalogueFixture,
    now: datetime,
) -> tuple[int, int]:
    module_payload = json.loads((root / "FX-MODULE-IT" / "module.json").read_text())
    days_payload = json.loads((root / "FX-MODULE-IT" / "days.json").read_text())["days"]
    exercise_payload = json.loads((root / "FX-MODULE-IT" / "exercises.json").read_text())["exercises"]
    selected_ids = {
        1: {"ITP-D1-01", "ITP-D1-03", "ITP-D1-04", "ITP-D1-06", "ITP-D1-07", "ITP-D1-10", "ITP-D1-11"},
        2: {"ITP-D2-02", "ITP-D2-05", "ITP-D2-06", "ITP-D2-07", "ITP-D2-08", "ITP-D2-10", "ITP-D2-11"},
        3: {"ITP-D3-04", "ITP-D3-05", "ITP-D3-07", "ITP-D3-08", "ITP-D3-10", "ITP-D3-11", "ITP-D3-12"},
    }
    selected = [item for item in exercise_payload if item["id"] in selected_ids[int(item["day"])]]
    prompts = {
        "EX-EXPOSE-01": "Découvrez les mots et expressions du jour, puis validez quand vous les avez lus à voix haute.",
        "EX-DISC-04": "Choisissez la formulation italienne qui convient le mieux à la situation.",
        "EX-ORAL-01": "Écoutez le modèle italien, répétez-le trois fois, puis évaluez votre aisance.",
        "EX-TRANSFORM-01": "Transformez la phrase en conservant le sens et en appliquant la structure du jour.",
        "EX-PROD-01": "Rédigez une réponse brève et naturelle en italien dans la situation proposée.",
        "EX-PROD-02": "Poursuivez l'échange en italien avec une intention claire et un registre adapté.",
        "EX-PROD-03": "Menez la mission en italien en reliant les structures déjà rencontrées.",
        "EX-RECALL-01": "Retrouvez les expressions sans regarder, puis indiquez honnêtement votre niveau de rappel.",
        "EX-RECALL-04": "Réécrivez en italien la formulation travaillée lors de la séance précédente.",
        "EX-COMP-03": "Traduisez le passage italien en français sans calquer sa structure.",
        "EX-REPAIR-01": "Corrigez votre formulation pour la rendre plus idiomatique en italien.",
    }
    activity_content = {
        "ITP-D1-01": ("Lisez à voix haute : buongiorno, salve, piacere, grazie, prego, scusi et arrivederci.", "Buongiorno, piacere. Arrivederci!"),
        "ITP-D1-03": ("Le moule « mi chiamo + prénom » sert à se présenter. Reformulez : Sono Sami.", "Mi chiamo Sami."),
        "ITP-D1-04": ("Répétez trois fois : Buongiorno, mi chiamo Sami. Piacere.", "Buongiorno, mi chiamo Sami. Piacere."),
        "ITP-D1-06": ("Remplacez la présentation directe par une présentation avec « mi chiamo » : Sono Sami.", "Mi chiamo Sami."),
        "ITP-D1-07": ("Répondez à une personne qui se présente, puis terminez poliment l'échange.", "Piacere, mi chiamo Sami. Arrivederci!"),
        "ITP-D1-10": ("Sans regarder, restituez au moins quatre salutations ou formules de politesse du jour.", "buongiorno; salve; piacere; grazie; prego; scusi; arrivederci"),
        "ITP-D1-11": ("Traduisez en français : Buongiorno, mi chiamo Luca. Piacere. Arrivederci!", "Bonjour, je m'appelle Luca. Enchanté. Au revoir !"),
        "ITP-D2-02": ("Lisez à voix haute : Vorrei un caffè. Posso pagare? Può ripetere?", "Vorrei un caffè. Posso pagare? Può ripetere?"),
        "ITP-D2-05": ("Transformez l'ordre « Dammi un caffè » en demande polie avec « vorrei ».", "Vorrei un caffè, per favore."),
        "ITP-D2-06": ("Répétez trois fois en soignant c et g : Vorrei un caffè e un bicchiere d'acqua.", "Vorrei un caffè e un bicchiere d'acqua."),
        "ITP-D2-07": ("Au café, commandez une boisson puis demandez si vous pouvez payer par carte.", "Vorrei un caffè. Posso pagare con la carta?"),
        "ITP-D2-08": ("Traduisez en français : Scusi, c'è un bagno qui?", "Excusez-moi, y a-t-il des toilettes ici ?"),
        "ITP-D2-10": ("Le moule « vorrei + nom » adoucit une demande. Reformulez : Voglio il conto.", "Vorrei il conto, per favore."),
        "ITP-D2-11": ("Réécrivez en italien : Bonjour, je m'appelle Luca. Enchanté.", "Buongiorno, mi chiamo Luca. Piacere."),
        "ITP-D3-02": ("Lisez à voix haute : Ho bisogno di aiuto. Può parlare lentamente?", "Ho bisogno di aiuto. Può parlare lentamente?"),
        "ITP-D3-04": ("Répétez trois fois : Scusi, può dirmi dov'è la stazione?", "Scusi, può dirmi dov'è la stazione?"),
        "ITP-D3-05": ("Transformez « Parla lentamente » en demande formelle avec « può ».", "Può parlare lentamente, per favore?"),
        "ITP-D3-07": ("Demandez où se trouve la gare puis demandez à votre interlocuteur de répéter.", "Scusi, dov'è la stazione? Può ripetere, per favore?"),
        "ITP-D3-08": ("Vous êtes perdu près de la gare. Demandez de l'aide, reformulez si nécessaire et confirmez la direction.", "Scusi, ho bisogno di aiuto. Dov'è la stazione? È diretto?"),
        "ITP-D3-10": ("Le moule « può + infinitif » transforme un ordre en demande formelle. Reformulez : Parla lentamente.", "Può parlare lentamente, per favore?"),
        "ITP-D3-11": ("Réécrivez en italien : Je voudrais un café et l'addition, s'il vous plaît.", "Vorrei un caffè e il conto, per favore."),
        "ITP-D3-12": ("Traduisez en français : Scusi, ho bisogno di aiuto. Può parlare lentamente?", "Excusez-moi, j'ai besoin d'aide. Pouvez-vous parler lentement ?"),
    }
    revisions_by_day: dict[int, list[UUID]] = {1: [], 2: [], 3: []}
    for index, item in enumerate(selected, start=1):
        definition_id = _definition_id(index)
        revision_id = UUID(item["definition_revision_id"])
        primitive = str(item["primitive"])
        prompt, model_answer = activity_content.get(
            str(item["id"]),
            (prompts[primitive], "Réponse personnelle à comparer avec la consigne."),
        )
        await session.execute(
            text(
                "INSERT INTO exercises.exercise_definitions "
                "(definition_id,definition_code,status,version,created_at,updated_at) "
                "VALUES (:id,:code,'published',1,:now,:now) ON CONFLICT DO NOTHING"
            ),
            {"id": definition_id, "code": f"it.pilot.{str(item['id']).lower()}", "now": now},
        )
        await session.execute(
            text(
                "INSERT INTO exercises.exercise_definition_revisions "
                "(definition_revision_id,definition_id,revision_no,schema_version,primitive_id,status,"
                "response_kinds,language_certification_ids,modes,target_weights,response_contract,"
                "stimulus_contract,target_contract,difficulty_profile,prerequisite_skill_revision_ids,"
                "correction_policy_id,hint_policy_id,observation_policy_id,accessibility_features,"
                "min_duration_ms,p50_duration_ms,p80_duration_ms,example_revision_ids,provenance_id,created_at) "
                "VALUES (:revision,:definition,1,1,:primitive,'published',CAST(:responses AS jsonb),'[]'::jsonb,"
                "'[\"guided\"]'::jsonb,CAST(:weights AS jsonb),'{}'::jsonb,CAST(:stimulus AS jsonb),"
                "CAST(:targets AS jsonb),'{}'::jsonb,'[]'::jsonb,'correction:pilot-v1','hint:pilot-v1',"
                "'observation:pilot-v1','[\"keyboard\",\"screen_reader\",\"untimed\"]'::jsonb,"
                "30000,60000,90000,'[]'::jsonb,:provenance,:now) ON CONFLICT DO NOTHING"
            ),
            {"revision": revision_id, "definition": definition_id, "primitive": primitive, "responses": _json([_preferred_answer_kind(primitive)]), "weights": _json([[target, 1.0] for target in item["targets"]]), "stimulus": _json({"prompt": prompt, "model_answer": model_answer, "language_tag": "it-IT", "feedback_mode": "compare_then_self_assess"}), "targets": _json(item["targets"]), "provenance": fixture.pack_revision.provenance_id, "now": now},
        )
        await session.execute(
            text("UPDATE exercises.exercise_definitions SET current_revision_id=:revision WHERE definition_id=:definition AND current_revision_id IS NULL"),
            {"revision": revision_id, "definition": definition_id},
        )
        revisions_by_day[int(item["day"])].append(revision_id)
    await session.execute(
        text(
            "INSERT INTO curriculum.learning_modules "
            "(module_id,module_code,pack_id,editorial_owner_id,status,version,created_at,updated_at) "
            "VALUES (:id,:code,:pack,:owner,'published',1,:now,:now) ON CONFLICT DO NOTHING"
        ),
        {"id": PILOT_MODULE_ID, "code": module_payload["module_code"], "pack": fixture.pack.pack_id, "owner": PILOT_OWNER_ID, "now": now},
    )
    skill_ids = [item.skill_revision_id for item in fixture.skills[:3]]
    await session.execute(
        text(
            "INSERT INTO curriculum.module_revisions "
            "(module_revision_id,module_id,revision_no,status,pack_revision_id,target_variety_id,"
            "support_variety_ids,primary_intention,final_mission_revision_id,entry_profile_codes,"
            "nominal_days,max_days,min_minutes,max_minutes,prerequisite_skill_revision_ids,"
            "target_skill_revision_ids,lexicon_set_revision_ids,exit_policy_revision_id,recall_policy_revision_id,"
            "provenance_ref,rights_refs,validator_set_revision_id,schema_version,compatibility_range,"
            "reference_manifest_checksum,supersedes_revision_id,payload_checksum,created_at) VALUES "
            "(:revision,:module,1,'published',:pack,:target,:supports,:intention,:mission,"
            "ARRAY['P-ABS','P-FAUX','P-INT'],3,3,10,60,ARRAY[]::uuid[],:skills,ARRAY[:lexicon_set]::uuid[],"
            ":exit,:recall,:provenance,ARRAY['project-authored'],:validators,1,'>=2.0.0,<2.1.0',"
            ":manifest,NULL,:checksum,:now) ON CONFLICT DO NOTHING"
        ),
        {"revision": PILOT_MODULE_REVISION_ID, "module": PILOT_MODULE_ID, "pack": fixture.pack_revision.pack_revision_id, "target": fixture.target_variety.variety_id, "supports": [item.variety_id for item in fixture.support_varieties], "intention": module_payload["primary_intention"], "mission": UUID(module_payload["mission"]["mission_revision_id"]), "skills": skill_ids, "lexicon_set": PILOT_REFERENCE_SET_ID, "exit": _policy_id(1), "recall": _policy_id(2), "provenance": module_payload["provenance"], "validators": _policy_id(3), "manifest": "sha256:" + "1" * 64, "checksum": "sha256:" + "2" * 64, "now": now},
    )
    lexical_sense_ids = [
        sense.sense_id
        for unit in fixture.lexical_units
        for sense in unit.senses
    ]
    senses_by_day = {
        1: lexical_sense_ids[:3],
        2: lexical_sense_ids[3:5],
        3: lexical_sense_ids[5:],
    }
    for day in days_payload:
        ordinal = int(day["ordinal"])
        target_refs = [
            *(f"lexical:{sense_id}" for sense_id in senses_by_day[ordinal]),
            f"skill:it-pilot-day-{ordinal}",
        ]
        recalled = [] if ordinal == 1 else [ordinal - 1]
        await session.execute(
            text(
                "INSERT INTO curriculum.module_days "
                "(module_day_id,module_revision_id,ordinal,arc_type,objective_codes,modality_objectives,"
                "primary_target_refs,secondary_target_refs,encountered_target_refs,output_target_refs,"
                "content_revision_ids,exercise_definition_revision_ids,context_revision_ids,target_bindings,"
                "recall_specs,recall_source_day_ordinals,minimum_useful_minutes,novelty_budget,required_block_roles,"
                "new_grammar_family_codes,explained_grammar_family_codes,gym_grammar_family_codes,"
                "fallback_revision_ids,final_output_spec,validator_revision_ids,prerequisite_day_ordinals,"
                "payload_checksum,created_at) VALUES (:id,:revision,:ordinal,:arc,:objectives,"
                "CAST(:modalities AS jsonb),:targets,ARRAY[]::varchar[],:targets,:targets,ARRAY[]::uuid[],"
                ":definitions,ARRAY[]::uuid[],CAST(:bindings AS jsonb),'[]'::jsonb,:recalls,10,:novelty,"
                "ARRAY['explanation','practice','production'],:new_grammar,:explained,:gym,ARRAY[]::uuid[],"
                ":output,ARRAY[]::uuid[],:prerequisites,:checksum,:now) ON CONFLICT DO NOTHING"
            ),
            {"id": _day_id(ordinal), "revision": PILOT_MODULE_REVISION_ID, "ordinal": ordinal, "arc": day["arc"], "objectives": [day["code"]], "modalities": _json([["written_production", "produce"], ["oral_comprehension", "recognize"]]), "targets": target_refs, "definitions": revisions_by_day[ordinal], "bindings": _json({"theme": day["dialogue_id"], "grammar": day["explanations"]}), "recalls": recalled, "novelty": 0 if day["arc"] == "transfer" else day["novelty_budget"], "new_grammar": day["new_grammar_families"], "explained": day["explanations"], "gym": [item["family"] for item in day["gym"]], "output": day["objective"], "prerequisites": recalled, "checksum": "sha256:" + f"{ordinal:064x}", "now": now},
        )
    await session.execute(
        text("UPDATE curriculum.learning_modules SET current_revision_id=:revision WHERE module_id=:module AND current_revision_id IS NULL"),
        {"revision": PILOT_MODULE_REVISION_ID, "module": PILOT_MODULE_ID},
    )
    return len(selected), len(days_payload)


async def bootstrap_pilot(database_url: str, fixture_root: Path) -> PilotBootstrapResult:
    engine = create_async_engine(database_url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            existing = await session.scalar(
                text("SELECT count(*) FROM catalogue.language_packs WHERE pack_code='it-IT__fr-FR'")
            )
            if existing:
                counts = (
                    int(await session.scalar(text("SELECT count(*) FROM catalogue.foundation_item_revisions")) or 0),
                    int(await session.scalar(text("SELECT count(*) FROM exercises.exercise_definitions WHERE definition_code LIKE 'it.pilot.%'")) or 0),
                    int(await session.scalar(text("SELECT count(*) FROM curriculum.module_days WHERE module_revision_id=:revision"), {"revision": PILOT_MODULE_REVISION_ID}) or 0),
                )
                if counts != (32, 21, 3):
                    raise DomainError(ErrorCode.CONTENT_UNAVAILABLE, detail="Italian pilot publication is incomplete")
                return PilotBootstrapResult(False, *counts)
            now = datetime.now(UTC)
            fixture, foundation_items = await _seed_catalogue(session, fixture_root, now)
            await _seed_lexicon(session, fixture, now)
            exercise_count, day_count = await _seed_exercises_and_module(session, fixture_root, fixture, now)
            await session.commit()
            return PilotBootstrapResult(True, foundation_items, exercise_count, day_count)
    finally:
        await engine.dispose()


async def _main() -> None:
    result = await bootstrap_pilot(
        migration_database_url_from_environment(), fixture_root_from_environment()
    )
    print(json.dumps({"created": result.created, "foundation_items": result.foundation_items, "exercise_definitions": result.exercise_definitions, "module_days": result.module_days}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_main())
