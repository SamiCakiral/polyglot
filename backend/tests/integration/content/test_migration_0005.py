from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_content_migration_creates_revision_publication_and_history_tables(
    session: AsyncSession,
) -> None:
    table_names = set(
        (
            await session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'content'"
                )
            )
        ).scalars()
    )

    assert {
        "content_items",
        "content_revisions",
        "validation_reports",
        "validation_findings",
        "content_approval_decisions",
        "publication_manifests",
        "publication_manifest_entries",
        "historical_content_references",
        "editorial_pack_assignments",
        "command_contexts",
    } <= table_names


async def test_content_migration_persists_pack_scope_and_sealed_proof_counts(
    session: AsyncSession,
) -> None:
    columns = set(
        (
            await session.execute(
                text(
                    "SELECT table_name || '.' || column_name "
                    "FROM information_schema.columns WHERE table_schema = 'content'"
                )
            )
        ).scalars()
    )

    assert {
        "content_items.pack_id",
        "validation_reports.finding_count",
        "publication_manifests.entry_count",
        "command_contexts.actor_id",
        "command_contexts.actor_type",
        "command_contexts.session_id",
        "command_contexts.pack_id",
    } <= columns
