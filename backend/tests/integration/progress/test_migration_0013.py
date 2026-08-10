from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

EXPECTED_TABLES = {
    "policy_revisions",
    "learning_observations",
    "learning_evidence",
    "fact_invalidations",
    "mastery_projections",
    "personal_sense_facets",
    "learning_needs",
    "learning_need_causes",
    "recommendations",
    "consumer_cursors",
}
IMMUTABLE_TABLES = {
    "policy_revisions",
    "learning_observations",
    "learning_evidence",
    "fact_invalidations",
    "learning_need_causes",
}


async def test_migration_creates_complete_progress_storage(
    migration_session: AsyncSession,
) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema='progress'"
                )
            )
        ).scalars()
    )
    assert tables == EXPECTED_TABLES


async def test_facts_and_policy_revisions_are_immutable(
    migration_session: AsyncSession,
) -> None:
    triggers = set(
        (
            await migration_session.execute(
                text(
                    "SELECT event_object_table || ':' || event_manipulation "
                    "FROM information_schema.triggers WHERE trigger_schema='progress'"
                )
            )
        ).scalars()
    )
    for table in IMMUTABLE_TABLES:
        assert f"{table}:UPDATE" in triggers
        assert f"{table}:DELETE" in triggers


async def test_all_progress_tables_force_rls(migration_session: AsyncSession) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,count(p.polname) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "LEFT JOIN pg_policy p ON p.polrelid=c.oid "
                "WHERE n.nspname='progress' AND c.relkind='r' "
                "GROUP BY c.relname,c.relrowsecurity,c.relforcerowsecurity"
            )
        )
    ).all()
    assert {row[0] for row in rows} == EXPECTED_TABLES
    assert all(row[1] is True and row[2] is True and row[3] >= 1 for row in rows)


async def test_projection_and_debt_uniqueness_are_declared(
    migration_session: AsyncSession,
) -> None:
    indexes = set(
        (
            await migration_session.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='progress'")
            )
        ).scalars()
    )
    assert "uq_progress_mastery_facet" in indexes
    assert "uq_progress_active_need" in indexes
    assert "ix_progress_opportunity" in indexes


async def test_runtime_cannot_rewrite_or_delete_progress_facts(
    migration_session: AsyncSession,
) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT table_name,"
                "has_table_privilege('polyglot_runtime','progress.' || table_name,'UPDATE'),"
                "has_table_privilege('polyglot_runtime','progress.' || table_name,'DELETE') "
                "FROM information_schema.tables WHERE table_schema='progress' "
                "AND table_name IN "
                "('learning_observations','learning_evidence','learning_need_causes')"
            )
        )
    ).all()
    assert len(rows) == 3
    assert all(row[1] is False and row[2] is False for row in rows)


async def test_mastery_v0_policy_is_seeded_and_fingerprinted(
    migration_session: AsyncSession,
) -> None:
    row = (
        await migration_session.execute(
            text(
                "SELECT policy_code,policy_fingerprint,config->>'prior_mass' "
                "FROM progress.policy_revisions WHERE policy_code='MASTERY_V0'"
            )
        )
    ).one()
    assert row == (
        "MASTERY_V0",
        "a093e8e172c0b9dfe8bbbc5ec89b8b4254e91de2d60d3ae9746387a6f479d9bf",
        "2.0",
    )
