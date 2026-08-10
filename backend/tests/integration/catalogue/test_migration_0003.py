import asyncio
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from .conftest import IDS, NOW, seed_catalogue


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
            "UPDATE catalogue.lexical_units SET variety_id = :support "
            "WHERE lexical_unit_id = :unit"
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
