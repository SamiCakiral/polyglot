from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import (
    database_url_from_environment,
    migration_database_url_from_environment,
)


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
async def clean_identity_tables(migration_database_url: str) -> AsyncIterator[None]:
    engine = create_async_engine(migration_database_url)
    async with engine.begin() as connection:
        schema_exists = await connection.scalar(text("SELECT to_regnamespace('identity')"))
        if schema_exists is not None:
            table_names = (
                await connection.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'identity' "
                        "AND table_name != 'consent_purposes'"
                    )
                )
            ).scalars()
            for table_name in table_names:
                await connection.execute(
                    text(f'TRUNCATE TABLE identity."{table_name}" CASCADE')
                )
    await engine.dispose()
    yield
