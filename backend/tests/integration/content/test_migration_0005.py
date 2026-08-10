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
    } <= table_names
