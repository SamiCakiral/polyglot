import os

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def database_url_from_environment() -> str:
    return os.environ["POLYGLOT_DATABASE_URL"]


def retention_database_url_from_environment() -> str:
    return os.environ["POLYGLOT_RETENTION_DATABASE_URL"]


def create_database_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def database_is_ready(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as connection:
            value = await connection.scalar(text("SELECT 1"))
            return value is not None and int(value) == 1
    except (OSError, SQLAlchemyError):
        return False
