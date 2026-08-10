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
