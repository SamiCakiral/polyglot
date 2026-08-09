import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture
def database_url() -> str:
    return os.environ["POLYGLOT_DATABASE_URL"]


@pytest.fixture
def migration_database_url() -> str:
    return os.environ["POLYGLOT_MIGRATION_DATABASE_URL"]


@pytest.fixture
def retention_database_url() -> str:
    return os.environ["POLYGLOT_RETENTION_DATABASE_URL"]


@pytest.fixture
async def session(database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as database_session:
        yield database_session
        await database_session.rollback()
    await engine.dispose()


@pytest.fixture
async def retention_session(retention_database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(retention_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as database_session:
        yield database_session
        await database_session.rollback()
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_platform_tables(migration_database_url: str) -> AsyncIterator[None]:
    engine = create_async_engine(migration_database_url)
    async with engine.begin() as connection:
        schema_exists = await connection.scalar(text("SELECT to_regnamespace('platform')"))
        if schema_exists is not None:
            await connection.execute(text("TRUNCATE TABLE platform.domain_events CASCADE"))
            table_names = (
                await connection.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'platform' AND table_name != 'domain_events'"
                    )
                )
            ).scalars()
            for table_name in table_names:
                await connection.execute(text(f'TRUNCATE TABLE platform."{table_name}" CASCADE'))
    await engine.dispose()
    yield
