from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import (
    database_url_from_environment,
    migration_database_url_from_environment,
)

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
IDS = {
    name: UUID(f"019fe900-5000-7000-{namespace:04x}-{number:012x}")
    for name, namespace, number in (
        ("provenance", 0x8000, 1),
        ("target_variety", 0x8001, 1),
        ("support_variety", 0x8001, 2),
        ("pack", 0x8002, 1),
        ("pack_revision", 0x8003, 1),
        ("publication", 0x8004, 1),
        ("skill_a", 0x8010, 1),
        ("skill_b", 0x8010, 2),
        ("skill_c", 0x8010, 3),
        ("skill_revision_a", 0x8011, 1),
        ("skill_revision_b", 0x8011, 2),
        ("skill_revision_c", 0x8011, 3),
        ("edge_a", 0x8012, 1),
        ("edge_b", 0x8012, 2),
        ("structure", 0x8013, 1),
        ("structure_revision", 0x8014, 1),
        ("pattern", 0x8015, 1),
        ("unit_potere", 0x8020, 1),
        ("unit_piano", 0x8020, 2),
        ("unit_per_favore", 0x8020, 3),
        ("unit_revision_potere", 0x8021, 1),
        ("unit_revision_piano", 0x8021, 2),
        ("unit_revision_per_favore", 0x8021, 3),
        ("sense_potere", 0x8022, 1),
        ("sense_piano_slow", 0x8022, 2),
        ("sense_piano_floor", 0x8022, 3),
        ("sense_per_favore", 0x8022, 4),
        ("sense_revision_potere", 0x8023, 1),
        ("sense_revision_piano_slow", 0x8023, 2),
        ("sense_revision_piano_floor", 0x8023, 3),
        ("sense_revision_per_favore", 0x8023, 4),
        ("form_puo", 0x8024, 1),
        ("form_puo_accented", 0x8024, 2),
        ("form_piano", 0x8024, 3),
        ("form_per_favore", 0x8024, 4),
        ("realization_puo", 0x8025, 1),
        ("realization_puo_accented", 0x8025, 2),
        ("realization_piano_slow", 0x8025, 3),
        ("realization_piano_floor", 0x8025, 4),
        ("realization_per_favore", 0x8025, 5),
    )
}


@pytest.fixture
def database_url() -> str:
    return database_url_from_environment()


@pytest.fixture
def migration_database_url() -> str:
    return migration_database_url_from_environment()


@pytest.fixture
async def session(database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as database_session:
        yield database_session
        await database_session.rollback()
    await engine.dispose()


@pytest.fixture
async def migration_session(migration_database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migration_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as database_session:
        yield database_session
        await database_session.rollback()
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_catalogue_tables(migration_database_url: str) -> AsyncIterator[None]:
    engine = create_async_engine(migration_database_url)
    async with engine.begin() as connection:
        schema_exists = await connection.scalar(text("SELECT to_regnamespace('catalogue')"))
        if schema_exists is not None:
            tables = list(
                (
                    await connection.execute(
                        text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = 'catalogue'"
                        )
                    )
                ).scalars()
            )
            if tables:
                quoted = ", ".join(f'catalogue."{table}"' for table in tables)
                await connection.execute(text(f"TRUNCATE {quoted} CASCADE"))
        platform_exists = await connection.scalar(text("SELECT to_regnamespace('platform')"))
        if platform_exists is not None:
            await connection.execute(text("TRUNCATE platform.provenance_records CASCADE"))
    await engine.dispose()
    yield


async def seed_catalogue(session: AsyncSession, *, publish_skills: bool = True) -> None:
    await session.execute(
        text(
            "INSERT INTO platform.provenance_records "
            "(provenance_id, source_type, source_ref, created_by_actor_id, tool_revision_id, "
            "model_code, prompt_revision_id, transformation_chain, input_fingerprint, created_at) "
            "VALUES (:provenance, 'fixture', 'FX-CATALOGUE-IT', NULL, NULL, NULL, NULL, "
            "'[]'::jsonb, :fingerprint, :now)"
        ),
        {"provenance": IDS["provenance"], "fingerprint": "a" * 64, "now": NOW},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_varieties "
            "(variety_id, language_tag, region_code, script_codes, text_direction, "
            "segmentation_policy_revision_id, media_capabilities, "
            "normalization_policy_revision_id) VALUES "
            "(:target, 'it-IT', 'IT', ARRAY['Latn'], 'ltr', :target, "
            "'{\"schema_version\": 1}'::jsonb, :target), "
            "(:support, 'fr-FR', 'FR', ARRAY['Latn'], 'ltr', :support, "
            "'{\"schema_version\": 1}'::jsonb, :support)"
        ),
        {"target": IDS["target_variety"], "support": IDS["support_variety"]},
    )
    await session.execute(
        text("INSERT INTO catalogue.language_packs (pack_id, pack_code) VALUES (:id, :code)"),
        {"id": IDS["pack"], "code": "it-IT__fr-FR"},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_pack_revisions "
            "(pack_revision_id, pack_id, revision_no, target_variety_id, status, "
            "engine_min_version, engine_max_version, capability_manifest, checksum_manifest, "
            "license_refs, provenance_id, published_at) VALUES "
            "(:revision, :pack, 1, :target, 'approved', '2.0.0', '2.0.x', "
            "'{\"schema_version\": 1, \"capabilities\": [\"catalogue\", \"lexicon\"]}'::jsonb, "
            "jsonb_build_object('catalogue.json', repeat('a', 64)), "
            "ARRAY['CC-BY-4.0'], :provenance, NULL)"
        ),
        {
            "revision": IDS["pack_revision"],
            "pack": IDS["pack"],
            "target": IDS["target_variety"],
            "provenance": IDS["provenance"],
        },
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_pack_support_varieties "
            "(pack_revision_id, variety_id) VALUES (:revision, :support)"
        ),
        {"revision": IDS["pack_revision"], "support": IDS["support_variety"]},
    )
    for index, (skill_name, revision_name, code, operation) in enumerate(
        (
            ("skill_a", "skill_revision_a", "IT-PRAG-001", "interact"),
            ("skill_b", "skill_revision_b", "IT-GRAM-002", "produce"),
            ("skill_c", "skill_revision_c", "IT-GRAM-004", "produce"),
        ),
        start=1,
    ):
        await session.execute(
            text("INSERT INTO catalogue.skills (skill_id, skill_code) VALUES (:id, :code)"),
            {"id": IDS[skill_name], "code": code},
        )
        await session.execute(
            text(
                "INSERT INTO catalogue.skill_revisions "
                "(skill_revision_id, skill_id, pack_revision_id, revision_no, skill_type, "
                "modality, operation, target_ref, scope, evidence_protocol_ids, load_profile, "
                "status, provenance_id) VALUES (:revision, :skill, :pack_revision, 1, "
                "'communicative_function', 'speaking', :operation, :target_ref, "
                "'{\"language_tag\": \"it-IT\"}'::jsonb, ARRAY[]::uuid[], "
                "jsonb_build_object('complexity', CAST(:complexity AS integer)), "
                "'approved', :provenance)"
            ),
            {
                "revision": IDS[revision_name],
                "skill": IDS[skill_name],
                "pack_revision": IDS["pack_revision"],
                "operation": operation,
                "target_ref": code,
                "complexity": index,
                "provenance": IDS["provenance"],
            },
        )
    for edge_name, source_name, target_name in (
        ("edge_a", "skill_revision_a", "skill_revision_b"),
        ("edge_b", "skill_revision_b", "skill_revision_c"),
    ):
        await session.execute(
            text(
                "INSERT INTO catalogue.skill_prerequisite_edges "
                "(edge_id, from_skill_revision_id, to_skill_revision_id, edge_type, provenance_id) "
                "VALUES (:edge, :source, :target, 'required', :provenance)"
            ),
            {
                "edge": IDS[edge_name],
                "source": IDS[source_name],
                "target": IDS[target_name],
                "provenance": IDS["provenance"],
            },
        )
    await session.execute(
        text(
            "INSERT INTO catalogue.grammar_structures "
            "(structure_id, structure_code, function_skill_id) "
            "VALUES (:id, 'IT-GRAM-002', :skill)"
        ),
        {"id": IDS["structure"], "skill": IDS["skill_a"]},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.grammar_structure_revisions "
            "(structure_revision_id, structure_id, pack_revision_id, revision_no, "
            "constraints, contrasts, typical_errors, variants, status, provenance_id) "
            "VALUES (:id, :structure, :pack_revision, 1, '{}'::jsonb, '[]'::jsonb, "
            "'[]'::jsonb, '[]'::jsonb, 'approved', :provenance)"
        ),
        {
            "id": IDS["structure_revision"],
            "structure": IDS["structure"],
            "pack_revision": IDS["pack_revision"],
            "provenance": IDS["provenance"],
        },
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.grammar_patterns "
            "(pattern_id, structure_revision_id, pattern_code, template, slots, "
            "instantiation_rules, examples, counterexamples) "
            "VALUES (:id, :revision, 'IT-GRAM-002-P1', 'vorrei + infinito', "
            "'[]'::jsonb, '{}'::jsonb, ARRAY['Vorrei partire'], ARRAY[]::text[])"
        ),
        {"id": IDS["pattern"], "revision": IDS["structure_revision"]},
    )
    lexical_records = (
        ("potere", "word", "potere", "verb"),
        ("piano", "word", "piano", "adverb"),
        ("per_favore", "multiword_expression", "per favore", "expression"),
    )
    for key, unit_type, lemma, part_of_speech in lexical_records:
        await session.execute(
            text(
                "INSERT INTO catalogue.lexical_units "
                "(lexical_unit_id, variety_id, unit_type, visibility, owner_profile_id) "
                "VALUES (:unit, :variety, :unit_type, 'shared', NULL)"
            ),
            {
                "unit": IDS[f"unit_{key}"],
                "variety": IDS["target_variety"],
                "unit_type": unit_type,
            },
        )
        await session.execute(
            text(
                "INSERT INTO catalogue.lexical_unit_revisions "
                "(unit_revision_id, lexical_unit_id, pack_revision_id, revision_no, lemma, "
                "part_of_speech, register, status, provenance_id) VALUES "
                "(:revision, :unit, :pack_revision, 1, :lemma, :part_of_speech, NULL, "
                "'approved', :provenance)"
            ),
            {
                "revision": IDS[f"unit_revision_{key}"],
                "unit": IDS[f"unit_{key}"],
                "pack_revision": IDS["pack_revision"],
                "lemma": lemma,
                "part_of_speech": part_of_speech,
                "provenance": IDS["provenance"],
            },
        )
    sense_records = (
        ("potere", "potere", "ability", "pouvoir ou permission"),
        ("piano_slow", "piano", "slowly", "lentement"),
        ("piano_floor", "piano", "floor", "étage"),
        ("per_favore", "per_favore", "please", "formule de politesse"),
    )
    for key, unit_key, sense_code, definition in sense_records:
        await session.execute(
            text(
                "INSERT INTO catalogue.lexical_senses (sense_id, lexical_unit_id, sense_code) "
                "VALUES (:sense, :unit, :code)"
            ),
            {
                "sense": IDS[f"sense_{key}"],
                "unit": IDS[f"unit_{unit_key}"],
                "code": sense_code,
            },
        )
        await session.execute(
            text(
                "INSERT INTO catalogue.lexical_sense_revisions "
                "(sense_revision_id, sense_id, pack_revision_id, revision_no, definition, "
                "domains, register, status, provenance_id) VALUES "
                "(:revision, :sense, :pack_revision, 1, :definition, ARRAY[]::varchar[], "
                "NULL, 'approved', :provenance)"
            ),
            {
                "revision": IDS[f"sense_revision_{key}"],
                "sense": IDS[f"sense_{key}"],
                "pack_revision": IDS["pack_revision"],
                "definition": definition,
                "provenance": IDS["provenance"],
            },
        )
    form_records = (
        ("puo", "potere", "puo", "puo", False),
        ("puo_accented", "potere", "può", "può", True),
        ("piano", "piano", "piano", "piano", True),
        ("per_favore", "per_favore", "per favore", "per favore", True),
    )
    for key, unit_key, surface, normalization_key, accepted in form_records:
        await session.execute(
            text(
                "INSERT INTO catalogue.form_analyses "
                "(form_analysis_id, unit_revision_id, surface, morphological_features, "
                "pronunciation_refs, normalization_key) VALUES "
                "(:analysis, :unit_revision, :surface, "
                "jsonb_build_object('accepted_reference', CAST(:accepted AS boolean)), "
                "ARRAY[]::uuid[], :key)"
            ),
            {
                "analysis": IDS[f"form_{key}"],
                "unit_revision": IDS[f"unit_revision_{unit_key}"],
                "surface": surface,
                "accepted": accepted,
                "key": normalization_key,
            },
        )
    realization_records = (
        ("puo", "puo", "potere", "potere"),
        ("puo_accented", "puo_accented", "potere", "potere"),
        ("piano_slow", "piano", "piano", "piano_slow"),
        ("piano_floor", "piano", "piano", "piano_floor"),
        ("per_favore", "per_favore", "per_favore", "per_favore"),
    )
    for key, form_key, unit_key, sense_key in realization_records:
        await session.execute(
            text(
                "INSERT INTO catalogue.form_realizations "
                "(realization_id, form_analysis_id, unit_revision_id, sense_revision_id) "
                "VALUES (:id, :analysis, :unit_revision, :sense_revision)"
            ),
            {
                "id": IDS[f"realization_{key}"],
                "analysis": IDS[f"form_{form_key}"],
                "unit_revision": IDS[f"unit_revision_{unit_key}"],
                "sense_revision": IDS[f"sense_revision_{sense_key}"],
            },
        )
    await session.execute(
        text(
            "INSERT INTO catalogue.expression_components "
            "(expression_unit_revision_id, component_unit_revision_id, position) "
            "VALUES (:expression, :component, 1)"
        ),
        {
            "expression": IDS["unit_revision_per_favore"],
            "component": IDS["unit_revision_potere"],
        },
    )
    if publish_skills:
        await session.execute(text("UPDATE catalogue.skill_revisions SET status = 'published'"))
    await session.execute(
        text("UPDATE catalogue.grammar_structure_revisions SET status = 'published'")
    )
    await session.execute(text("UPDATE catalogue.lexical_unit_revisions SET status = 'published'"))
    await session.execute(text("UPDATE catalogue.lexical_sense_revisions SET status = 'published'"))
    await session.execute(
        text(
            "UPDATE catalogue.language_pack_revisions "
            "SET status = 'published', published_at = :now"
        ),
        {"now": NOW},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_pack_publications "
            "(publication_id, pack_id, pack_revision_id, channel, compatibility_range, "
            "published_at, retired_at) VALUES "
            "(:publication, :pack, :revision, 'stable', '>=2.0.0,<2.1.0', :now, NULL)"
        ),
        {
            "publication": IDS["publication"],
            "pack": IDS["pack"],
            "revision": IDS["pack_revision"],
            "now": NOW,
        },
    )
    await session.commit()
