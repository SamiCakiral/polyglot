from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_0001_platform_creates_the_complete_platform_schema(
    session: AsyncSession,
) -> None:
    expected_tables = {
        "command_receipts",
        "deletion_requests",
        "deletion_tombstones",
        "domain_events",
        "feature_flag_values",
        "feature_flags",
        "inbox_receipts",
        "job_attempts",
        "jobs",
        "outbox_messages",
        "projection_checkpoints",
        "provenance_records",
        "security_audit_entries",
    }

    rows = await session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'platform'"
        )
    )

    assert {row[0] for row in rows} == expected_tables


async def test_0001_platform_uses_postgresql_json_and_expiration_indexes(
    session: AsyncSession,
) -> None:
    payload_type = await session.scalar(
        text(
            "SELECT format_type(attribute.atttypid, attribute.atttypmod) "
            "FROM pg_attribute AS attribute "
            "JOIN pg_class AS relation ON relation.oid = attribute.attrelid "
            "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
            "WHERE namespace.nspname = 'platform' "
            "AND relation.relname = 'domain_events' "
            "AND attribute.attname = 'payload'"
        )
    )
    index_names = set(
        (
            await session.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'platform'")
            )
        ).scalars()
    )

    assert payload_type == "jsonb"
    assert {
        "ix_command_receipts_expires_at",
        "ix_deletion_tombstones_expires_at",
        "ix_feature_flags_expires_at",
        "ix_outbox_messages_available",
        "ix_security_audit_entries_expires_at",
    } <= index_names
