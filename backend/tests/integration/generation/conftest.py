from __future__ import annotations

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

ACCOUNT_ID = UUID("019fec20-0000-7000-8000-000000000001")
NOW = datetime(2026, 8, 10, 12, tzinfo=UTC)


@pytest.fixture
async def migration_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migration_database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.fixture
async def runtime_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url_from_environment())
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def seeded_account(migration_session: AsyncSession) -> UUID:
    await migration_session.execute(
        text(
            "INSERT INTO identity.accounts "
            "(account_id,status,security_version,session_version,version,created_at,"
            "security_last_activity_at) VALUES (:account,'active',1,1,1,:now,:now) "
            "ON CONFLICT DO NOTHING"
        ),
        {"account": ACCOUNT_ID, "now": NOW},
    )
    await migration_session.commit()
    return ACCOUNT_ID


@pytest.fixture(autouse=True)
async def clean_generation_storage() -> AsyncIterator[None]:
    yield
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.begin() as connection:
        if await connection.scalar(text("SELECT to_regnamespace('generation')")) is not None:
            await connection.execute(
                text(
                    "TRUNCATE generation.runner_transcripts,generation.authoring_artifacts,"
                    "generation.tool_invocations,generation.generation_attempts,"
                    "generation.generation_jobs CASCADE"
                )
            )
            await connection.execute(
                text("DELETE FROM platform.jobs WHERE job_type='generation'")
            )
            await connection.execute(
                text(
                    "DELETE FROM platform.command_receipts "
                    "WHERE command_type LIKE 'generation.%'"
                )
            )
    await engine.dispose()
