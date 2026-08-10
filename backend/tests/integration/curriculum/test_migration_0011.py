from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

EXPECTED_TABLES = {
    "learning_modules",
    "module_revisions",
    "module_days",
    "module_revision_mappings",
    "module_revision_mapping_entries",
    "module_enrollments",
    "adaptive_day_instances",
}
IMMUTABLE_TABLES = {
    "module_revisions",
    "module_days",
    "module_revision_mappings",
    "module_revision_mapping_entries",
}


async def test_migration_creates_curriculum_storage(migration_session: AsyncSession) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='curriculum'"
                )
            )
        ).scalars()
    )
    assert tables == EXPECTED_TABLES


async def test_published_curriculum_facts_are_guarded(migration_session: AsyncSession) -> None:
    triggers = set(
        (
            await migration_session.execute(
                text(
                    "SELECT event_object_table || ':' || event_manipulation "
                    "FROM information_schema.triggers WHERE trigger_schema='curriculum'"
                )
            )
        ).scalars()
    )
    for table in IMMUTABLE_TABLES:
        assert f"{table}:UPDATE" in triggers
        assert f"{table}:DELETE" in triggers


async def test_personal_curriculum_tables_force_owner_rls(
    migration_session: AsyncSession,
) -> None:
    personal = {"module_enrollments", "adaptive_day_instances"}
    rows = (
        await migration_session.execute(
            text(
                "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,count(p.polname) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "LEFT JOIN pg_policy p ON p.polrelid=c.oid "
                "WHERE n.nspname='curriculum' AND c.relname=ANY(:tables) "
                "GROUP BY c.relname,c.relrowsecurity,c.relforcerowsecurity"
            ),
            {"tables": sorted(personal)},
        )
    ).all()
    assert {row[0] for row in rows} == personal
    assert all(row[1] is True and row[2] is True and row[3] >= 1 for row in rows)


async def test_enrollment_uniqueness_and_versioned_references_are_declared(
    migration_session: AsyncSession,
) -> None:
    indexes = set(
        (
            await migration_session.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='curriculum'")
            )
        ).scalars()
    )
    assert "uq_curriculum_active_enrollment" in indexes
    assert (
        await migration_session.scalar(
            text(
                "SELECT count(*) FROM information_schema.constraint_column_usage "
                "WHERE table_schema='curriculum' AND table_name='module_revisions' "
                "AND column_name='module_revision_id'"
            )
        )
        >= 1
    )


async def test_runtime_cannot_delete_curriculum_rows(migration_session: AsyncSession) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT table_name,has_table_privilege("
                "'polyglot_runtime','curriculum.' || table_name,'DELETE') "
                "FROM information_schema.tables WHERE table_schema='curriculum'"
            )
        )
    ).all()
    assert {row[0] for row in rows} == EXPECTED_TABLES
    assert all(row[1] is False for row in rows)
