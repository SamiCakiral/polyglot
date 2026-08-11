from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

EXPECTED_TABLES = {
    "media_assets",
    "media_rights",
    "media_revisions",
    "media_uploads",
    "media_variants",
    "media_segments",
    "oral_assets",
    "tts_voice_catalog_revisions",
    "tts_voice_capabilities",
    "tts_cache_entries",
    "tts_synthesis_requests",
}


async def test_migration_creates_private_media_and_tts_catalogue(
    migration_session: AsyncSession,
) -> None:
    tables = set(
        (
            await migration_session.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='media'")
            )
        ).scalars()
    )
    assert tables == EXPECTED_TABLES


async def test_every_media_table_forces_rls(migration_session: AsyncSession) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,count(p.polname) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "LEFT JOIN pg_policy p ON p.polrelid=c.oid "
                "WHERE n.nspname='media' AND c.relkind='r' "
                "GROUP BY c.relname,c.relrowsecurity,c.relforcerowsecurity"
            )
        )
    ).all()
    assert {row[0] for row in rows} == EXPECTED_TABLES
    assert all(row[1] is True and row[2] is True and row[3] >= 1 for row in rows)


async def test_media_storage_never_declares_public_object_keys(
    migration_session: AsyncSession,
) -> None:
    columns = set(
        (
            await migration_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='media'"
                )
            )
        ).scalars()
    )
    assert "public_url" not in columns
    assert "signed_url" not in columns
    assert "storage_key" in columns


async def test_latest_local_catalogue_exposes_italian_and_japanese_voices(
    migration_session: AsyncSession,
) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT c.voice_id,c.language_tags,c.availability,"
                "r.provider_code,r.provider_version "
                "FROM media.tts_voice_capabilities c "
                "JOIN media.tts_voice_catalog_revisions r "
                "ON r.catalog_revision_id=c.catalog_revision_id "
                "WHERE r.catalog_revision_id=("
                "SELECT catalog_revision_id FROM media.tts_voice_catalog_revisions "
                "ORDER BY published_at DESC LIMIT 1) ORDER BY c.voice_id"
            )
        )
    ).all()
    assert rows == [
        ("Alice", ["it-IT"], "available", "macos-say", "local-v2"),
        ("Kyoko", ["ja-JP"], "available", "macos-say", "local-v2"),
    ]
