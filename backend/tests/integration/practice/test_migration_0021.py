from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

EXPECTED_TABLES = {
    "practice_stacks",
    "practice_stack_members",
    "practice_presets",
    "practice_preset_revisions",
    "practice_runs",
    "practice_run_items",
    "sprint_stack_injections",
}


async def test_practice_schema_enforces_private_immutable_snapshots(
    migration_session: AsyncSession,
) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='practice'"
                )
            )
        ).scalars()
    )
    policies = set(
        (
            await migration_session.execute(
                text(
                    "SELECT tablename FROM pg_policies "
                    "WHERE schemaname='practice'"
                )
            )
        ).scalars()
    )
    forced_rls = set(
        (
            await migration_session.execute(
                text(
                    "SELECT relname FROM pg_class relation "
                    "JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace "
                    "WHERE namespace.nspname='practice' AND relation.relforcerowsecurity"
                )
            )
        ).scalars()
    )
    foreign_keys = set(
        (
            await migration_session.execute(
                text(
                    "SELECT constraint_name FROM information_schema.table_constraints "
                    "WHERE table_schema='practice' AND constraint_type='FOREIGN KEY'"
                )
            )
        ).scalars()
    )
    pending_index = await migration_session.scalar(
        text(
            "SELECT indexdef FROM pg_indexes WHERE schemaname='practice' "
            "AND indexname='uq_sprint_stack_injection_pending'"
        )
    )

    assert EXPECTED_TABLES <= tables
    assert EXPECTED_TABLES <= policies
    assert EXPECTED_TABLES <= forced_rls
    assert {
        "fk_practice_stack_member_sense",
        "fk_practice_stack_member_sense_revision",
    } <= foreign_keys
    assert pending_index is not None
    assert "WHERE" in str(pending_index)
    assert "'pending'::text" in str(pending_index)
