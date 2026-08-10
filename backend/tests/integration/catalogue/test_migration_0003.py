import asyncio
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from polyglot.modules.catalogue.core.domain import foundation_content_checksum

from .conftest import IDS, NOW, seed_catalogue

DRAFT_IDS = {
    "pack_revision": UUID("019fe900-5000-7000-8003-000000000200"),
    "structure_revision": UUID("019fe900-5000-7000-8014-000000000200"),
    "unit_revision_potere": UUID("019fe900-5000-7000-8021-000000000200"),
    "unit_revision_per_favore": UUID("019fe900-5000-7000-8021-000000000201"),
    "sense_revision_potere": UUID("019fe900-5000-7000-8023-000000000200"),
    "form_potere": UUID("019fe900-5000-7000-8024-000000000200"),
}


async def seed_draft_catalogue_owners(session: AsyncSession) -> None:
    await session.execute(
        text(
            "INSERT INTO catalogue.language_pack_revisions "
            "(pack_revision_id, pack_id, revision_no, target_variety_id, status, "
            "engine_min_version, engine_max_version, capability_manifest, checksum_manifest, "
            "license_refs, provenance_id, published_at) VALUES "
            "(:revision, :pack, 2, :target, 'draft', '2.0.0', '2.0.x', "
            "'{\"schema_version\": 1}'::jsonb, "
            "jsonb_build_object('catalogue.json', repeat('b', 64)), "
            "ARRAY['CC-BY-4.0'], :provenance, NULL)"
        ),
        {
            "revision": DRAFT_IDS["pack_revision"],
            "pack": IDS["pack"],
            "target": IDS["target_variety"],
            "provenance": IDS["provenance"],
        },
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.grammar_structure_revisions "
            "(structure_revision_id, structure_id, pack_revision_id, revision_no, "
            "constraints, contrasts, typical_errors, variants, status, provenance_id) "
            "VALUES (:revision, :structure, :pack_revision, 2, '{}'::jsonb, '[]'::jsonb, "
            "'[]'::jsonb, '[]'::jsonb, 'draft', :provenance)"
        ),
        {
            "revision": DRAFT_IDS["structure_revision"],
            "structure": IDS["structure"],
            "pack_revision": DRAFT_IDS["pack_revision"],
            "provenance": IDS["provenance"],
        },
    )
    for revision, unit, lemma, part_of_speech in (
        (
            DRAFT_IDS["unit_revision_potere"],
            IDS["unit_potere"],
            "potere",
            "verb",
        ),
        (
            DRAFT_IDS["unit_revision_per_favore"],
            IDS["unit_per_favore"],
            "per favore",
            "expression",
        ),
    ):
        await session.execute(
            text(
                "INSERT INTO catalogue.lexical_unit_revisions "
                "(unit_revision_id, lexical_unit_id, pack_revision_id, revision_no, lemma, "
                "part_of_speech, register, status, provenance_id) VALUES "
                "(:revision, :unit, :pack_revision, 2, :lemma, :part_of_speech, NULL, "
                "'draft', :provenance)"
            ),
            {
                "revision": revision,
                "unit": unit,
                "pack_revision": DRAFT_IDS["pack_revision"],
                "lemma": lemma,
                "part_of_speech": part_of_speech,
                "provenance": IDS["provenance"],
            },
        )
    await session.execute(
        text(
            "INSERT INTO catalogue.lexical_sense_revisions "
            "(sense_revision_id, sense_id, pack_revision_id, revision_no, definition, "
            "domains, register, status, provenance_id) VALUES "
            "(:revision, :sense, :pack_revision, 2, 'brouillon', ARRAY[]::varchar[], "
            "NULL, 'draft', :provenance)"
        ),
        {
            "revision": DRAFT_IDS["sense_revision_potere"],
            "sense": IDS["sense_potere"],
            "pack_revision": DRAFT_IDS["pack_revision"],
            "provenance": IDS["provenance"],
        },
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.form_analyses "
            "(form_analysis_id, unit_revision_id, surface, morphological_features, "
            "pronunciation_refs, normalization_key) VALUES "
            "(:form, :unit_revision, 'potrebbe', '{}'::jsonb, ARRAY[]::uuid[], 'potrebbe')"
        ),
        {
            "form": DRAFT_IDS["form_potere"],
            "unit_revision": DRAFT_IDS["unit_revision_potere"],
        },
    )


async def test_0003_creates_versioned_catalogue_tables_constraints_and_read_grants(
    migration_session: AsyncSession,
) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'catalogue'"
                )
            )
        ).scalars()
    )
    constraints = set(
        (
            await migration_session.execute(
                text(
                    "SELECT conname FROM pg_constraint AS item "
                    "JOIN pg_namespace AS namespace ON namespace.oid = item.connamespace "
                    "WHERE namespace.nspname = 'catalogue'"
                )
            )
        ).scalars()
    )
    triggers = set(
        (
            await migration_session.execute(
                text(
                    "SELECT trigger_name FROM information_schema.triggers "
                    "WHERE trigger_schema = 'catalogue'"
                )
            )
        ).scalars()
    )

    assert tables == {
        "expression_components",
        "foundation_block_revisions",
        "foundation_definition_revisions",
        "foundation_definitions",
        "foundation_gate_revisions",
        "foundation_item_revisions",
        "foundation_reference_revisions",
        "form_analyses",
        "form_realizations",
        "grammar_patterns",
        "grammar_structure_revisions",
        "grammar_structures",
        "language_pack_publications",
        "language_pack_revisions",
        "language_pack_support_varieties",
        "language_packs",
        "language_varieties",
        "lexical_sense_revisions",
        "lexical_senses",
        "lexical_unit_revisions",
        "lexical_units",
        "skill_prerequisite_edges",
        "skill_revisions",
        "skills",
    }
    assert {
        "ck_catalogue_pack_revision_status",
        "ck_catalogue_skill_revision_status",
        "ck_catalogue_skill_type_code",
        "ck_catalogue_structure_code",
        "ck_catalogue_pattern_code",
        "ck_catalogue_sense_code",
        "ck_catalogue_edge_type",
        "ck_catalogue_form_surface",
        "uq_catalogue_pack_revision",
        "uq_catalogue_edge",
    } <= constraints
    assert {
        "guard_published_pack_revision",
        "guard_published_skill_revision",
        "guard_required_prerequisite_cycle",
    } <= triggers
    assert await migration_session.scalar(
        text(
            "SELECT has_table_privilege('polyglot_runtime', "
            "'catalogue.language_pack_revisions', 'SELECT')"
        )
    )
    assert not await migration_session.scalar(
        text(
            "SELECT has_table_privilege('polyglot_runtime', "
            "'catalogue.language_pack_revisions', 'INSERT')"
        )
    )
    for table_name in (
        "foundation_definitions",
        "foundation_definition_revisions",
        "foundation_reference_revisions",
        "foundation_block_revisions",
        "foundation_item_revisions",
        "foundation_gate_revisions",
    ):
        assert await migration_session.scalar(
            text("SELECT has_table_privilege('polyglot_runtime', :table_name, 'SELECT')"),
            {"table_name": f"catalogue.{table_name}"},
        )
        for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            assert not await migration_session.scalar(
                text("SELECT has_table_privilege('polyglot_runtime', :table_name, :privilege)"),
                {"table_name": f"catalogue.{table_name}", "privilege": privilege},
            )


async def test_0003_restricts_incoherent_foundations_and_published_child_reparenting(
    migration_session: AsyncSession,
) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'catalogue'"
                )
            )
        ).scalars()
    )
    required_tables = {
        "foundation_definitions",
        "foundation_definition_revisions",
        "foundation_reference_revisions",
        "foundation_block_revisions",
        "foundation_item_revisions",
        "foundation_gate_revisions",
    }
    assert required_tables <= tables, "W04F foundation persistence tables are missing"

    await seed_catalogue(migration_session, include_foundations=True)
    with pytest.raises(DBAPIError, match="published revision is immutable"):
        await migration_session.execute(
            text(
                "UPDATE catalogue.foundation_item_revisions SET item_code = item_code "
                "WHERE item_revision_id = :item"
            ),
            {"item": IDS["foundation_item_f1_01"]},
        )
    await migration_session.rollback()

    with pytest.raises(DBAPIError, match="published revision is immutable"):
        await migration_session.execute(
            text(
                "UPDATE catalogue.foundation_item_revisions "
                "SET block_revision_id = :block WHERE item_revision_id = :item"
            ),
            {
                "block": IDS["foundation_block_f2"],
                "item": IDS["foundation_item_f1_01"],
            },
        )
    await migration_session.rollback()

    with pytest.raises(DBAPIError, match="published revision is immutable"):
        await migration_session.execute(
            text("DELETE FROM catalogue.foundation_item_revisions WHERE item_revision_id = :item"),
            {"item": IDS["foundation_item_f1_01"]},
        )
    await migration_session.rollback()

    with pytest.raises(DBAPIError):
        await migration_session.execute(
            text(
                "INSERT INTO catalogue.foundation_item_revisions "
                "(item_revision_id, block_revision_id, pack_revision_id, item_code, "
                "ordinal, target_refs, response_kind, checker_kind, checker_values, "
                "modalities, status, checksum) "
                "VALUES ('019fe900-5000-7000-8075-000000000099', :block, :pack, "
                "'ITF-F1-03', 3, ARRAY['IT-PHON-001'], 'raw', 'exact_choice', "
                "ARRAY['late_but_valid'], ARRAY['reading'], 'published', repeat('e', 64))"
            ),
            {"block": IDS["foundation_block_f1"], "pack": IDS["pack_revision"]},
        )


async def test_0003_rejects_unresolved_foundation_refs_before_publication(
    migration_session: AsyncSession,
) -> None:
    await seed_catalogue(
        migration_session,
        include_foundations=True,
        include_foundation_gate=False,
    )

    item_revision_id = UUID("019fe900-5000-7000-8075-000000000098")
    checksum = foundation_content_checksum(
        "foundation_item_v1",
        item_revision_id,
        IDS["foundation_block_f1"],
        IDS["pack_revision"],
        "ITF-F1-03",
        3,
        ("IT-MISSING-999",),
        "raw",
        "exact_choice",
        ("well_formed",),
        ("reading",),
        "published",
    )
    with pytest.raises(DBAPIError, match="foundation reference is not published"):
        await migration_session.execute(
            text(
                "INSERT INTO catalogue.foundation_item_revisions "
                "(item_revision_id, block_revision_id, pack_revision_id, item_code, "
                "ordinal, target_refs, response_kind, checker_kind, checker_values, "
                "modalities, status, checksum) "
                "VALUES (:item, :block, :pack, "
                "'ITF-F1-03', 3, ARRAY['IT-MISSING-999'], 'raw', 'exact_choice', "
                "ARRAY['well_formed'], ARRAY['reading'], 'published', :checksum)"
            ),
            {
                "item": item_revision_id,
                "block": IDS["foundation_block_f1"],
                "pack": IDS["pack_revision"],
                "checksum": checksum,
            },
        )


async def test_0003_rejects_a_well_formed_item_with_a_forged_content_checksum(
    migration_session: AsyncSession,
) -> None:
    await seed_catalogue(
        migration_session,
        include_foundations=True,
        include_foundation_gate=False,
    )

    with pytest.raises(DBAPIError, match="foundation checksum does not match content"):
        await migration_session.execute(
            text(
                "INSERT INTO catalogue.foundation_item_revisions "
                "(item_revision_id, block_revision_id, pack_revision_id, item_code, "
                "ordinal, target_refs, response_kind, checker_kind, checker_values, "
                "modalities, status, checksum) "
                "VALUES ('019fe900-5000-7000-8075-000000000097', :block, :pack, "
                "'ITF-F1-03', 3, ARRAY['IT-PHON-001'], 'raw', 'exact_choice', "
                "ARRAY['well_formed'], ARRAY['reading'], 'published', repeat('0', 64))"
            ),
            {"block": IDS["foundation_block_f1"], "pack": IDS["pack_revision"]},
        )


async def test_0003_rejects_a_structurally_valid_late_item_insert(
    migration_session: AsyncSession,
) -> None:
    await seed_catalogue(migration_session, include_foundations=True)

    item_revision_id = UUID("019fe900-5000-7000-8075-000000000096")
    checksum = foundation_content_checksum(
        "foundation_item_v1",
        item_revision_id,
        IDS["foundation_block_f1"],
        IDS["pack_revision"],
        "ITF-F1-03",
        3,
        ("IT-PHON-001",),
        "raw",
        "exact_choice",
        ("late_but_valid",),
        ("reading",),
        "published",
    )
    with pytest.raises(DBAPIError, match="published foundation is immutable"):
        await migration_session.execute(
            text(
                "INSERT INTO catalogue.foundation_item_revisions "
                "(item_revision_id, block_revision_id, pack_revision_id, item_code, "
                "ordinal, target_refs, response_kind, checker_kind, checker_values, "
                "modalities, status, checksum) "
                "VALUES (:item, :block, :pack, "
                "'ITF-F1-03', 3, ARRAY['IT-PHON-001'], 'raw', 'exact_choice', "
                "ARRAY['late_but_valid'], ARRAY['reading'], 'published', :checksum)"
            ),
            {
                "item": item_revision_id,
                "block": IDS["foundation_block_f1"],
                "pack": IDS["pack_revision"],
                "checksum": checksum,
            },
        )


@pytest.mark.parametrize(
    "gate_change",
    (
        {"minimum_distinct_sessions": 3},
        {"delayed_control_hours": 25},
        {"grapheme_minimum": 7},
        {"grapheme_total": 11},
        {"reading_minimum": 7},
        {"reading_total": 11},
        {"survival_minimum": 3},
        {"survival_total": 6},
        {"coverage_threshold": 0.9},
        {"confidence_threshold": 0.7},
        {"facet_minimum_status": "mastered"},
        {"delayed_control_block_code": "F2"},
        {"without_reveal": False},
        {"oral_policy": "self_report_non_blocking"},
        {
            "facets": (
                "controlled_reading",
                "grapheme_sound_discrimination",
                "greeting_recognition",
                "functional_frame_choice",
                "written_guided_repair",
            )
        },
    ),
)
async def test_0003_rejects_validly_shaped_non_contractual_gate_values(
    migration_session: AsyncSession,
    gate_change: dict[str, object],
) -> None:
    await seed_catalogue(
        migration_session,
        include_foundations=True,
        include_foundation_gate=False,
    )
    gate_revision_id = UUID("019fe900-5000-7000-8076-000000000001")
    targets = (
        "IT-PHON-001",
        "IT-PHON-003",
        "IT-PHON-002",
        "IT-PRAG-001",
        "IT-PRAG-002",
        "IT-ID-001",
        "IT-GRAM-002",
        "IT-GRAM-003",
        "IT-GRAM-007",
        "IT-GRAM-027",
        "IT-POLITE-002",
        "IT-REPAIR-001",
    )
    gate_values: dict[str, object] = {
        "facets": (
            "grapheme_sound_discrimination",
            "controlled_reading",
            "greeting_recognition",
            "functional_frame_choice",
            "written_guided_repair",
        ),
        "facet_minimum_status": "reliable",
        "coverage_threshold": 1.0,
        "confidence_threshold": 0.6,
        "minimum_distinct_sessions": 2,
        "delayed_control_block_code": "F1",
        "delayed_control_hours": 24,
        "grapheme_minimum": 8,
        "grapheme_total": 10,
        "reading_minimum": 8,
        "reading_total": 10,
        "survival_minimum": 4,
        "survival_total": 5,
        "without_reveal": True,
        "oral_policy": "not_evaluable_non_blocking",
    }
    gate_values.update(gate_change)
    checksum = foundation_content_checksum(
        "foundation_gate_v1",
        gate_revision_id,
        IDS["foundation_revision"],
        IDS["pack_revision"],
        "FOUNDATIONS_IT_V0",
        targets,
        gate_values["facets"],
        gate_values["facet_minimum_status"],
        gate_values["coverage_threshold"],
        gate_values["confidence_threshold"],
        gate_values["minimum_distinct_sessions"],
        gate_values["delayed_control_block_code"],
        gate_values["delayed_control_hours"],
        gate_values["grapheme_minimum"],
        gate_values["grapheme_total"],
        gate_values["reading_minimum"],
        gate_values["reading_total"],
        gate_values["survival_minimum"],
        gate_values["survival_total"],
        gate_values["without_reveal"],
        gate_values["oral_policy"],
        "published",
    )

    with pytest.raises(DBAPIError):
        await migration_session.execute(
            text(
                "INSERT INTO catalogue.foundation_gate_revisions "
                "(gate_revision_id, foundation_revision_id, pack_revision_id, gate_code, "
                "blocking_target_refs, blocking_facet_refs, blocking_facet_minimum_status, "
                "coverage_threshold, confidence_threshold, minimum_distinct_sessions, "
                "delayed_control_block_code, delayed_control_hours, "
                "grapheme_sound_minimum, grapheme_sound_total, targeted_reading_minimum, "
                "targeted_reading_total, survival_exchange_minimum, survival_exchange_total, "
                "survival_exchange_without_reveal, oral_policy, status, checksum) VALUES "
                "(:gate, :foundation, :pack, 'FOUNDATIONS_IT_V0', :targets, :facets, "
                ":facet_status, :coverage, :confidence, :sessions, :delayed_block, :hours, "
                ":grapheme_minimum, :grapheme_total, :reading_minimum, :reading_total, "
                ":survival_minimum, :survival_total, :without_reveal, :oral_policy, "
                "'published', :checksum)"
            ),
            {
                "gate": gate_revision_id,
                "foundation": IDS["foundation_revision"],
                "pack": IDS["pack_revision"],
                "targets": list(targets),
                **gate_values,
                "facets": list(gate_values["facets"]),
                "facet_status": gate_values["facet_minimum_status"],
                "coverage": gate_values["coverage_threshold"],
                "confidence": gate_values["confidence_threshold"],
                "sessions": gate_values["minimum_distinct_sessions"],
                "delayed_block": gate_values["delayed_control_block_code"],
                "hours": gate_values["delayed_control_hours"],
                "checksum": checksum,
            },
        )


async def test_database_rejects_published_rewrite_duplicate_publication_and_required_cycle(
    migration_session: AsyncSession,
) -> None:
    await seed_catalogue(migration_session, publish_skills=False)

    with pytest.raises(DBAPIError, match="published revision is immutable"):
        await migration_session.execute(
            text(
                "UPDATE catalogue.language_pack_revisions "
                "SET engine_max_version = '2.1.x' WHERE pack_revision_id = :revision"
            ),
            {"revision": IDS["pack_revision"]},
        )
    await migration_session.rollback()

    with pytest.raises(IntegrityError):
        await migration_session.execute(
            text(
                "INSERT INTO catalogue.language_pack_publications "
                "(publication_id, pack_id, pack_revision_id, channel, compatibility_range, "
                "published_at, retired_at) VALUES "
                "(:id, :pack, :revision, 'stable', '>=2.0.0,<2.1.0', :now, NULL)"
            ),
            {
                "id": UUID("019fe900-5000-7000-8004-000000000002"),
                "pack": IDS["pack"],
                "revision": IDS["pack_revision"],
                "now": NOW,
            },
        )
    await migration_session.rollback()

    with pytest.raises(IntegrityError):
        await migration_session.execute(
            text(
                "INSERT INTO catalogue.language_packs (pack_id, pack_code) "
                "VALUES ('019fe900-5000-7000-8002-000000000002', 'pack-é')"
            )
        )
    await migration_session.rollback()

    with pytest.raises(DBAPIError, match="prerequisite_cycle"):
        await migration_session.execute(
            text(
                "INSERT INTO catalogue.skill_prerequisite_edges "
                "(edge_id, from_skill_revision_id, to_skill_revision_id, edge_type, provenance_id) "
                "VALUES (:edge, :source, :target, 'required', :provenance)"
            ),
            {
                "edge": UUID("019fe900-5000-7000-8012-000000000003"),
                "source": IDS["skill_revision_c"],
                "target": IDS["skill_revision_a"],
                "provenance": IDS["provenance"],
            },
        )


async def test_runtime_catalogue_access_is_read_only(
    migration_session: AsyncSession,
    session: AsyncSession,
) -> None:
    await seed_catalogue(migration_session)

    assert await session.scalar(text("SELECT count(*) FROM catalogue.language_packs")) == 1
    with pytest.raises(DBAPIError):
        await session.execute(
            text(
                "INSERT INTO catalogue.language_packs (pack_id, pack_code) "
                "VALUES ('019fe900-5000-7000-8002-000000000002', 'forbidden')"
            )
        )


@pytest.mark.parametrize(
    ("table", "where", "update"),
    (
        (
            "language_pack_support_varieties",
            "pack_revision_id = :pack_revision",
            "variety_id = variety_id",
        ),
        ("grammar_patterns", "pattern_id = :pattern", "template = template"),
        ("form_analyses", "form_analysis_id = :form", "surface = surface"),
        (
            "form_realizations",
            "realization_id = :realization",
            "sense_revision_id = sense_revision_id",
        ),
        (
            "expression_components",
            "expression_unit_revision_id = :expression",
            "position = position",
        ),
    ),
)
async def test_database_rejects_update_and_delete_of_every_child_owned_by_published_revision(
    migration_session: AsyncSession,
    table: str,
    where: str,
    update: str,
) -> None:
    await seed_catalogue(migration_session)
    parameters = {
        "pack_revision": IDS["pack_revision"],
        "pattern": IDS["pattern"],
        "form": IDS["form_puo"],
        "realization": IDS["realization_puo"],
        "expression": IDS["unit_revision_per_favore"],
    }

    with pytest.raises(DBAPIError, match="published revision is immutable"):
        await migration_session.execute(
            text(f"UPDATE catalogue.{table} SET {update} WHERE {where}"), parameters
        )
    await migration_session.rollback()

    with pytest.raises(DBAPIError, match="published revision is immutable"):
        await migration_session.execute(
            text(f"DELETE FROM catalogue.{table} WHERE {where}"), parameters
        )
    await migration_session.rollback()


@pytest.mark.parametrize(
    ("family", "statement"),
    (
        (
            "language_pack_support_varieties",
            "UPDATE catalogue.language_pack_support_varieties "
            "SET pack_revision_id = :draft_pack_revision "
            "WHERE pack_revision_id = :published_pack_revision",
        ),
        (
            "grammar_patterns",
            "UPDATE catalogue.grammar_patterns "
            "SET structure_revision_id = :draft_structure_revision "
            "WHERE pattern_id = :pattern",
        ),
        (
            "form_analyses",
            "UPDATE catalogue.form_analyses SET unit_revision_id = :draft_unit_revision "
            "WHERE form_analysis_id = :form",
        ),
        (
            "form_realizations",
            "UPDATE catalogue.form_realizations "
            "SET form_analysis_id = :draft_form, unit_revision_id = :draft_unit_revision, "
            "sense_revision_id = :draft_sense_revision WHERE realization_id = :realization",
        ),
        (
            "expression_components",
            "UPDATE catalogue.expression_components "
            "SET expression_unit_revision_id = :draft_expression_revision, "
            "component_unit_revision_id = :draft_unit_revision "
            "WHERE expression_unit_revision_id = :published_expression_revision",
        ),
    ),
)
async def test_database_rejects_reparenting_child_from_published_to_draft_revision(
    migration_session: AsyncSession,
    family: str,
    statement: str,
) -> None:
    await seed_catalogue(migration_session)
    await seed_draft_catalogue_owners(migration_session)
    parameters = {
        "published_pack_revision": IDS["pack_revision"],
        "draft_pack_revision": DRAFT_IDS["pack_revision"],
        "draft_structure_revision": DRAFT_IDS["structure_revision"],
        "pattern": IDS["pattern"],
        "draft_unit_revision": DRAFT_IDS["unit_revision_potere"],
        "form": IDS["form_puo"],
        "draft_form": DRAFT_IDS["form_potere"],
        "draft_sense_revision": DRAFT_IDS["sense_revision_potere"],
        "realization": IDS["realization_puo"],
        "draft_expression_revision": DRAFT_IDS["unit_revision_per_favore"],
        "published_expression_revision": IDS["unit_revision_per_favore"],
    }

    with pytest.raises(
        DBAPIError,
        match="published revision is immutable",
        check=lambda error: family in statement and error.orig is not None,
    ):
        await migration_session.execute(text(statement), parameters)


async def test_database_rejects_cross_unit_cross_pack_and_invalid_mwe_component_links(
    migration_session: AsyncSession,
) -> None:
    await seed_catalogue(migration_session, publish_lexical=False)

    with pytest.raises(DBAPIError, match="form realization must match its form analysis unit"):
        await migration_session.execute(
            text(
                "INSERT INTO catalogue.form_realizations "
                "(realization_id, form_analysis_id, unit_revision_id, sense_revision_id) "
                "VALUES ('019fe900-5000-7000-8025-000000000100', :form, :unit, :sense)"
            ),
            {
                "form": IDS["form_puo"],
                "unit": IDS["unit_revision_piano"],
                "sense": IDS["sense_revision_piano_slow"],
            },
        )
    await migration_session.rollback()

    await migration_session.execute(
        text(
            "INSERT INTO catalogue.language_pack_revisions "
            "(pack_revision_id, pack_id, revision_no, target_variety_id, status, "
            "engine_min_version, engine_max_version, capability_manifest, checksum_manifest, "
            "license_refs, provenance_id, published_at) VALUES "
            "('019fe900-5000-7000-8003-000000000100', :pack, 2, :target, 'approved', "
            "'2.0.0', '2.0.x', '{\"schema_version\": 1}'::jsonb, "
            "jsonb_build_object('catalogue.json', repeat('a', 64)), ARRAY['CC-BY-4.0'], "
            ":provenance, NULL)"
        ),
        {
            "pack": IDS["pack"],
            "target": IDS["target_variety"],
            "provenance": IDS["provenance"],
        },
    )
    await migration_session.execute(
        text(
            "INSERT INTO catalogue.lexical_sense_revisions "
            "(sense_revision_id, sense_id, pack_revision_id, revision_no, definition, "
            "domains, register, status, provenance_id) VALUES "
            "('019fe900-5000-7000-8023-000000000100', :sense, "
            "'019fe900-5000-7000-8003-000000000100', 2, 'autre pack', "
            "ARRAY[]::varchar[], NULL, 'approved', :provenance)"
        ),
        {"sense": IDS["sense_potere"], "provenance": IDS["provenance"]},
    )
    with pytest.raises(DBAPIError, match="form realization references a different pack revision"):
        await migration_session.execute(
            text(
                "INSERT INTO catalogue.form_realizations "
                "(realization_id, form_analysis_id, unit_revision_id, sense_revision_id) "
                "VALUES ('019fe900-5000-7000-8025-000000000102', :form, :unit, "
                "'019fe900-5000-7000-8023-000000000100')"
            ),
            {"form": IDS["form_puo"], "unit": IDS["unit_revision_potere"]},
        )
    await migration_session.rollback()

    with pytest.raises(DBAPIError, match="form realization sense must belong to its unit"):
        await migration_session.execute(
            text(
                "INSERT INTO catalogue.form_realizations "
                "(realization_id, form_analysis_id, unit_revision_id, sense_revision_id) "
                "VALUES ('019fe900-5000-7000-8025-000000000101', :form, :unit, :sense)"
            ),
            {
                "form": IDS["form_puo"],
                "unit": IDS["unit_revision_potere"],
                "sense": IDS["sense_revision_piano_slow"],
            },
        )
    await migration_session.rollback()

    with pytest.raises(
        DBAPIError,
        match="expression components require a multiword expression root",
    ):
        await migration_session.execute(
            text(
                "INSERT INTO catalogue.expression_components "
                "(expression_unit_revision_id, component_unit_revision_id, position) "
                "VALUES (:expression, :component, 2)"
            ),
            {
                "expression": IDS["unit_revision_potere"],
                "component": IDS["unit_revision_piano"],
            },
        )
    await migration_session.rollback()

    await migration_session.execute(
        text(
            "UPDATE catalogue.lexical_units SET variety_id = :support WHERE lexical_unit_id = :unit"
        ),
        {"support": IDS["support_variety"], "unit": IDS["unit_piano"]},
    )
    with pytest.raises(DBAPIError, match="expression components must share pack and variety"):
        await migration_session.execute(
            text(
                "INSERT INTO catalogue.expression_components "
                "(expression_unit_revision_id, component_unit_revision_id, position) "
                "VALUES (:expression, :component, 2)"
            ),
            {
                "expression": IDS["unit_revision_per_favore"],
                "component": IDS["unit_revision_piano"],
            },
        )


async def test_required_dag_mutations_are_serialized_across_transactions(
    migration_database_url: str,
    migration_session: AsyncSession,
) -> None:
    await seed_catalogue(migration_session, publish_skills=False)
    await migration_session.execute(text("DELETE FROM catalogue.skill_prerequisite_edges"))
    await migration_session.commit()
    engine = create_async_engine(migration_database_url)
    first = await engine.connect()
    second = await engine.connect()
    first_transaction = await first.begin()
    second_transaction = await second.begin()
    try:
        await first.execute(
            text(
                "INSERT INTO catalogue.skill_prerequisite_edges "
                "(edge_id, from_skill_revision_id, to_skill_revision_id, edge_type, provenance_id) "
                "VALUES ('019fe900-5000-7000-8012-000000000100', :source, :target, "
                "'required', :provenance)"
            ),
            {
                "source": IDS["skill_revision_a"],
                "target": IDS["skill_revision_b"],
                "provenance": IDS["provenance"],
            },
        )
        competing = asyncio.create_task(
            second.execute(
                text(
                    "INSERT INTO catalogue.skill_prerequisite_edges "
                    "(edge_id, from_skill_revision_id, to_skill_revision_id, edge_type, "
                    "provenance_id) "
                    "VALUES ('019fe900-5000-7000-8012-000000000101', :source, :target, "
                    "'required', :provenance)"
                ),
                {
                    "source": IDS["skill_revision_b"],
                    "target": IDS["skill_revision_a"],
                    "provenance": IDS["provenance"],
                },
            )
        )
        await asyncio.sleep(0.1)
        assert not competing.done()
        await first_transaction.commit()
        with pytest.raises(DBAPIError, match="prerequisite_cycle"):
            await asyncio.wait_for(competing, timeout=2)
    finally:
        if first_transaction.is_active:
            await first_transaction.rollback()
        if second_transaction.is_active:
            await second_transaction.rollback()
        await first.close()
        await second.close()
        await engine.dispose()
