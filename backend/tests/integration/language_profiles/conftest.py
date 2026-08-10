from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import (
    database_url_from_environment,
    migration_database_url_from_environment,
)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as database_session:
        yield database_session
        await database_session.rollback()
    await engine.dispose()


@pytest.fixture
async def migration_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migration_database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as database_session:
        yield database_session
        await database_session.rollback()
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_language_profiles_database() -> AsyncIterator[None]:
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.begin() as connection:
        schema = await connection.scalar(text("SELECT to_regnamespace('language_profiles')"))
        if schema is not None:
            tables = (
                await connection.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'language_profiles'"
                    )
                )
            ).scalars()
            for table_name in tables:
                await connection.execute(
                    text(f'TRUNCATE TABLE language_profiles."{table_name}" CASCADE')
                )
    await engine.dispose()
    yield
