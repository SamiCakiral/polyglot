from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

EXPECTED_TABLES = {
    "delayed_recode_specs",
    "delayed_recode_tasks",
    "planning_snapshots",
    "session_plans",
    "session_plan_revisions",
    "session_plan_blocks",
    "session_plan_exercise_instances",
    "sprint_runs",
    "planning_command_receipts",
}
IMMUTABLE_TABLES = {
    "delayed_recode_specs",
    "planning_snapshots",
    "session_plan_revisions",
    "session_plan_blocks",
    "session_plan_exercise_instances",
}


async def test_migration_creates_planning_storage(migration_session: AsyncSession) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='planning'"
                )
            )
        ).scalars()
    )
    assert tables == EXPECTED_TABLES


async def test_snapshots_and_plan_revisions_are_immutable(
    migration_session: AsyncSession,
) -> None:
    triggers = set(
        (
            await migration_session.execute(
                text(
                    "SELECT event_object_table || ':' || event_manipulation "
                    "FROM information_schema.triggers WHERE trigger_schema='planning'"
                )
            )
        ).scalars()
    )
    for table in IMMUTABLE_TABLES:
        assert f"{table}:UPDATE" in triggers
        assert f"{table}:DELETE" in triggers


async def test_all_planning_tables_force_owner_rls(migration_session: AsyncSession) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,count(p.polname) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "LEFT JOIN pg_policy p ON p.polrelid=c.oid "
                "WHERE n.nspname='planning' AND c.relkind='r' "
                "GROUP BY c.relname,c.relrowsecurity,c.relforcerowsecurity"
            )
        )
    ).all()
    assert {row[0] for row in rows} == EXPECTED_TABLES
    assert all(row[1] is True and row[2] is True and row[3] >= 1 for row in rows)


async def test_active_run_and_daily_plan_uniqueness_are_declared(
    migration_session: AsyncSession,
) -> None:
    indexes = set(
        (
            await migration_session.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='planning'")
            )
        ).scalars()
    )
    assert "uq_planning_active_run" in indexes
    assert "uq_planning_daily_plan" in indexes


async def test_exercise_runtime_references_versioned_plan_storage(
    migration_session: AsyncSession,
) -> None:
    constraints = set(
        (
            await migration_session.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conname IN "
                    "('fk_exercise_instance_session_plan_revision',"
                    "'fk_exercise_block_sprint_run','fk_exercise_block_plan_block')"
                )
            )
        ).scalars()
    )
    assert constraints == {
        "fk_exercise_instance_session_plan_revision",
        "fk_exercise_block_sprint_run",
        "fk_exercise_block_plan_block",
    }


async def test_planner_can_insert_only_owned_plan_instances(
    migration_session: AsyncSession,
) -> None:
    policy = await migration_session.scalar(
        text(
            "SELECT polname FROM pg_policy WHERE polrelid="
            "'exercises.exercise_instances'::regclass "
            "AND polname='exercise_instances_planning_write'"
        )
    )
    assert policy == "exercise_instances_planning_write"


async def test_runtime_cannot_delete_planning_rows(migration_session: AsyncSession) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT table_name,has_table_privilege("
                "'polyglot_runtime','planning.' || table_name,'DELETE') "
                "FROM information_schema.tables WHERE table_schema='planning'"
            )
        )
    ).all()
    assert {row[0] for row in rows} == EXPECTED_TABLES
    assert all(row[1] is False for row in rows)
