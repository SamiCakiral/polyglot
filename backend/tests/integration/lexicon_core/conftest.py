from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import (
    database_url_from_environment,
    migration_database_url_from_environment,
)


@pytest.fixture(autouse=True)
async def clean_lexicon_database() -> AsyncIterator[None]:
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.begin() as connection:
        if await connection.scalar(text("SELECT to_regnamespace('lexicon')")) is not None:
            await connection.execute(text("TRUNCATE TABLE lexicon.lexical_encounters CASCADE"))
            await connection.execute(text("TRUNCATE TABLE lexicon.private_lexical_units CASCADE"))
            await connection.execute(text("TRUNCATE TABLE lexicon.lexical_preferences CASCADE"))
            await connection.execute(text("TRUNCATE TABLE lexicon.lexical_annotations CASCADE"))
            await connection.execute(
                text("TRUNCATE TABLE lexicon.lexicon_command_receipts CASCADE")
            )
        await connection.execute(text("TRUNCATE TABLE platform.domain_events CASCADE"))
        await connection.execute(text("TRUNCATE TABLE platform.command_receipts CASCADE"))
        await connection.execute(text("TRUNCATE TABLE platform.outbox_messages CASCADE"))
        await connection.execute(
            text("TRUNCATE TABLE language_profiles.learner_language_profiles CASCADE")
        )
        await connection.execute(text("TRUNCATE TABLE identity.accounts CASCADE"))
    await engine.dispose()
    yield


@pytest.fixture
async def migration_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migration_database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.fixture
async def runtime_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()
