from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
