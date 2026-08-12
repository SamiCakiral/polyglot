from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

EXPECTED_TABLES = {
    "policy_revisions",
    "item_blueprints",
    "item_blueprint_revisions",
    "variant_revisions",
    "rubric_revisions",
    "runs",
    "item_instances",
    "responses",
    "scoring_interpretations",
    "observations",
    "skill_estimate_revisions",
    "contradictions",
    "decisions",
    "calibration_cycles",
}


async def test_placement_schema_is_private_and_append_only(
    migration_session: AsyncSession,
) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='placement'"
                )
            )
        ).scalars()
    )
    rls = set(
        (
            await migration_session.execute(
                text(
                    "SELECT relname FROM pg_class relation JOIN pg_namespace namespace "
                    "ON namespace.oid=relation.relnamespace WHERE namespace.nspname='placement' "
                    "AND relation.relrowsecurity AND relation.relforcerowsecurity"
                )
            )
        ).scalars()
    )
    assert EXPECTED_TABLES == tables
    assert EXPECTED_TABLES == rls
    assert await migration_session.scalar(
        text(
            "SELECT indexdef LIKE '%WHERE%' FROM pg_indexes WHERE schemaname='placement' "
            "AND indexname='uq_placement_active_run'"
        )
    )
