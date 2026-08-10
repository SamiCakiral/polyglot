from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

LEXICON_TABLES = {
    "vocabulary_lists",
    "vocabulary_list_revisions",
    "list_memberships",
    "list_snapshots",
    "list_snapshot_members",
    "list_associations",
}
EXCHANGE_TABLES = {
    "import_runs",
    "import_lines",
    "import_conflicts",
    "import_manifests",
    "shared_list_publications",
    "export_runs",
    "export_artifacts",
}


async def _tables(session: AsyncSession, schema: str) -> set[str]:
    return set(
        (
            await session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema=:schema"
                ),
                {"schema": schema},
            )
        ).scalars()
    )


async def test_migration_creates_list_and_exchange_storage(
    migration_session: AsyncSession,
) -> None:
    assert LEXICON_TABLES <= await _tables(migration_session, "lexicon")
    assert await _tables(migration_session, "exchange") == EXCHANGE_TABLES


async def test_personal_exchange_tables_force_owner_rls(
    migration_session: AsyncSession,
) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,count(p.polname) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "LEFT JOIN pg_policy p ON p.polrelid=c.oid "
                "WHERE n.nspname IN ('lexicon','exchange') AND c.relkind='r' "
                "AND c.relname = ANY(:tables) "
                "GROUP BY c.relname,c.relrowsecurity,c.relforcerowsecurity"
            ),
            {"tables": sorted(LEXICON_TABLES | EXCHANGE_TABLES)},
        )
    ).all()
    assert {name for name, *_ in rows} == LEXICON_TABLES | EXCHANGE_TABLES
    assert all((rls, forced, policies) == (True, True, 1) for _, rls, forced, policies in rows)


async def test_immutable_list_and_import_artifacts_have_guards(
    migration_session: AsyncSession,
) -> None:
    guarded = set(
        (
            await migration_session.execute(
                text(
                    "SELECT event_object_schema || '.' || event_object_table "
                    "|| ':' || event_manipulation "
                    "FROM information_schema.triggers "
                    "WHERE trigger_schema IN ('lexicon','exchange')"
                )
            )
        ).scalars()
    )
    for table in (
        "lexicon.vocabulary_list_revisions",
        "lexicon.list_memberships",
        "lexicon.list_snapshots",
        "lexicon.list_snapshot_members",
        "exchange.import_manifests",
    ):
        assert f"{table}:UPDATE" in guarded
        assert f"{table}:DELETE" in guarded


async def test_runtime_cannot_delete_import_audit_or_update_snapshots(
    migration_session: AsyncSession,
) -> None:
    assert await migration_session.scalar(
        text(
            "SELECT has_table_privilege('polyglot_runtime',"
            "'exchange.import_manifests','DELETE')"
        )
    ) is False
    assert await migration_session.scalar(
        text(
            "SELECT has_table_privilege('polyglot_runtime',"
            "'lexicon.list_snapshots','UPDATE')"
        )
    ) is False
    assert await migration_session.scalar(
        text(
            "SELECT has_table_privilege('polyglot_runtime',"
            "'exchange.import_conflicts','UPDATE')"
        )
    ) is True
