from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import (
    database_url_from_environment,
    migration_database_url_from_environment,
)


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


@pytest.fixture(autouse=True)
async def clean_sprint_storage() -> AsyncIterator[None]:
    async def clean() -> None:
        engine = create_async_engine(migration_database_url_from_environment())
        async with engine.begin() as connection:
            for schema in ("planning", "curriculum", "exercises"):
                tables = tuple(
                    (
                        await connection.execute(
                            text(
                                "SELECT table_name FROM information_schema.tables "
                                "WHERE table_schema=:schema"
                            ),
                            {"schema": schema},
                        )
                    ).scalars()
                )
                if tables:
                    qualified = ",".join(f'{schema}."{table}"' for table in tables)
                    await connection.execute(text(f"TRUNCATE {qualified} CASCADE"))
            await connection.execute(text("TRUNCATE platform.outbox_messages CASCADE"))
            await connection.execute(text("TRUNCATE platform.domain_events CASCADE"))
            await connection.execute(text("TRUNCATE platform.command_receipts CASCADE"))
            await connection.execute(
                text("TRUNCATE language_profiles.learner_language_profiles CASCADE")
            )
            await connection.execute(text("TRUNCATE identity.accounts CASCADE"))
        await engine.dispose()

    await clean()
    yield
    await clean()
