from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import (
    database_url_from_environment,
    migration_database_url_from_environment,
)

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
IDS = {
    name: UUID(f"019fe003-0000-7000-{namespace:04x}-{number:012x}")
    for name, namespace, number in (
        ("author", 0x8000, 1),
        ("reviewer", 0x8000, 2),
        ("content", 0x8001, 1),
        ("revision", 0x8002, 1),
        ("replacement", 0x8002, 2),
        ("provenance", 0x8003, 1),
        ("event", 0x8004, 1),
        ("command", 0x8005, 1),
        ("correlation", 0x8006, 1),
        ("manifest", 0x8007, 1),
        ("history", 0x8008, 1),
        ("report", 0x8009, 1),
        ("validator_set", 0x800A, 1),
        ("finding", 0x800B, 1),
        ("decision", 0x800C, 1),
        ("catalogue_revision", 0x800D, 1),
        ("publication_provenance", 0x800E, 1),
        ("session", 0x800F, 1),
        ("pack", 0x8010, 1),
        ("pack_revision", 0x8011, 1),
        ("pack_publication", 0x8012, 1),
        ("skill", 0x8013, 1),
    )
}
VARIETY_ID = UUID("019fe900-5000-7000-8001-000000000001")


@pytest.fixture
def database_url() -> str:
    return database_url_from_environment()


@pytest.fixture
def migration_database_url() -> str:
    return migration_database_url_from_environment()


@pytest.fixture
async def session(database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as database_session:
        yield database_session
        await database_session.rollback()
    await engine.dispose()


@pytest.fixture
async def migration_session(migration_database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migration_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as database_session:
        yield database_session
        await database_session.rollback()
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_content_tables(migration_database_url: str) -> AsyncIterator[None]:
    engine = create_async_engine(migration_database_url)
    async with engine.begin() as connection:
        if await connection.scalar(text("SELECT to_regnamespace('content')")) is not None:
            await connection.execute(text("TRUNCATE content.content_items CASCADE"))
        await connection.execute(text("TRUNCATE platform.domain_events CASCADE"))
        await connection.execute(text("TRUNCATE platform.command_receipts CASCADE"))
        await connection.execute(text("TRUNCATE platform.outbox_messages CASCADE"))
        await connection.execute(text("TRUNCATE platform.provenance_records CASCADE"))
    await engine.dispose()
    yield


async def seed_provenance(session: AsyncSession) -> None:
    await session.execute(
        text(
            "INSERT INTO catalogue.language_varieties "
            "(variety_id, language_tag, region_code, script_codes, text_direction, "
            "segmentation_policy_revision_id, media_capabilities, "
            "normalization_policy_revision_id) VALUES "
            "(:id, 'it-IT', 'IT', ARRAY['Latn'], 'ltr', :id, "
            "'{\"schema_version\": 1}'::jsonb, :id) ON CONFLICT (variety_id) DO NOTHING"
        ),
        {"id": VARIETY_ID},
    )
    await session.execute(
        text(
            "INSERT INTO platform.provenance_records "
            "(provenance_id, source_type, source_ref, created_by_actor_id, tool_revision_id, "
            "model_code, prompt_revision_id, transformation_chain, input_fingerprint, created_at) "
            "VALUES (:id, 'fixture', 'FX-CONTENT', :author, NULL, NULL, NULL, "
            "'[]'::jsonb, :fingerprint, :now)"
        ),
        {"id": IDS["provenance"], "author": IDS["author"], "fingerprint": "a" * 64, "now": NOW},
    )
    await session.execute(
        text(
            "INSERT INTO platform.provenance_records "
            "(provenance_id, source_type, source_ref, created_by_actor_id, tool_revision_id, "
            "model_code, prompt_revision_id, transformation_chain, input_fingerprint, created_at) "
            "VALUES (:id, 'human_author', 'W05-publication', :author, NULL, NULL, NULL, "
            "'[]'::jsonb, :fingerprint, :now)"
        ),
        {
            "id": IDS["publication_provenance"],
            "author": IDS["reviewer"],
            "fingerprint": "f" * 64,
            "now": NOW,
        },
    )


async def seed_published_catalogue_reference(session: AsyncSession) -> None:
    await seed_provenance(session)
    await session.execute(
        text(
            "INSERT INTO catalogue.language_packs (pack_id, pack_code) "
            "VALUES (:pack, 'it-IT__fr-FR') ON CONFLICT (pack_id) DO NOTHING"
        ),
        {"pack": IDS["pack"]},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_pack_revisions "
            "(pack_revision_id, pack_id, revision_no, target_variety_id, status, "
            "engine_min_version, engine_max_version, capability_manifest, checksum_manifest, "
            "license_refs, provenance_id, published_at) VALUES "
            "(:revision, :pack, 1, :variety, 'published', '2.0.0', '2.0.x', "
            "'{\"schema_version\": 1}'::jsonb, jsonb_build_object('catalogue', repeat('a', 64)), "
            "ARRAY['CC-BY-4.0'], :provenance, :now)"
        ),
        {
            "revision": IDS["pack_revision"],
            "pack": IDS["pack"],
            "variety": VARIETY_ID,
            "provenance": IDS["provenance"],
            "now": NOW,
        },
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_pack_publications "
            "(publication_id, pack_id, pack_revision_id, channel, compatibility_range, "
            "published_at, retired_at) VALUES "
            "(:publication, :pack, :revision, 'stable', '>=2.0.0,<2.1.0', :now, NULL)"
        ),
        {
            "publication": IDS["pack_publication"],
            "pack": IDS["pack"],
            "revision": IDS["pack_revision"],
            "now": NOW,
        },
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.skills (skill_id, skill_code) "
            "VALUES (:skill, 'IT-GRAM-001') ON CONFLICT (skill_id) DO NOTHING"
        ),
        {"skill": IDS["skill"]},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.skill_revisions "
            "(skill_revision_id, skill_id, pack_revision_id, revision_no, skill_type, "
            "modality, operation, target_ref, scope, evidence_protocol_ids, load_profile, "
            "status, provenance_id) VALUES "
            "(:revision, :skill, :pack_revision, 1, 'grammar', 'writing', 'transform', "
            "'IT-GRAM-001', '{\"language_tag\": \"it-IT\"}'::jsonb, ARRAY[]::uuid[], "
            "'{\"complexity\": 1}'::jsonb, 'published', :provenance)"
        ),
        {
            "revision": IDS["catalogue_revision"],
            "skill": IDS["skill"],
            "pack_revision": IDS["pack_revision"],
            "provenance": IDS["provenance"],
        },
    )
