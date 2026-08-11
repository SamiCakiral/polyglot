import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

EXPECTED_TABLES = {
    "tool_revisions",
    "generation_jobs",
    "generation_attempts",
    "tool_invocations",
    "authoring_artifacts",
    "runner_transcripts",
}
TOOL_CONTRACTS = Path(__file__).resolve().parents[4] / "contracts" / "tools"


async def test_migration_seeds_exactly_eleven_closed_tools(
    migration_session: AsyncSession,
) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='generation'"
                )
            )
        ).scalars()
    )
    count = await migration_session.scalar(text("SELECT count(*) FROM generation.tool_revisions"))
    assert tables == EXPECTED_TABLES
    assert count == 11

    rows = (
        await migration_session.execute(
            text("SELECT tool_name,input_schema,output_schema FROM generation.tool_revisions")
        )
    ).mappings()
    for row in rows:
        name = row["tool_name"]
        assert row["input_schema"] == json.loads(
            (TOOL_CONTRACTS / f"{name}.input.schema.json").read_text()
        )
        assert row["output_schema"] == json.loads(
            (TOOL_CONTRACTS / f"{name}.output.schema.json").read_text()
        )


async def test_generation_tables_force_rls_and_expose_no_publish_switch(
    migration_session: AsyncSession,
) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,count(p.polname) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "LEFT JOIN pg_policy p ON p.polrelid=c.oid "
                "WHERE n.nspname='generation' AND c.relkind='r' "
                "GROUP BY c.relname,c.relrowsecurity,c.relforcerowsecurity"
            )
        )
    ).all()
    columns = set(
        (
            await migration_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='generation'"
                )
            )
        ).scalars()
    )
    assert {row[0] for row in rows} == EXPECTED_TABLES
    assert all(row[1] is True and row[2] is True and row[3] >= 1 for row in rows)
    assert not {"publish_capability", "mastery_status", "mastery_credit"} & columns
