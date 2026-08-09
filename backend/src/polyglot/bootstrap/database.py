import os
from collections.abc import Mapping
from typing import Literal

from sqlalchemy import URL, make_url, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DatabaseWorkload = Literal["migration", "runtime", "retention"]

_EXPLICIT_URL_VARIABLES: dict[DatabaseWorkload, str] = {
    "migration": "POLYGLOT_MIGRATION_DATABASE_URL",
    "runtime": "POLYGLOT_DATABASE_URL",
    "retention": "POLYGLOT_RETENTION_DATABASE_URL",
}


def workload_database_url_from_environment(
    workload: DatabaseWorkload,
    environment: Mapping[str, str] | None = None,
) -> str:
    values = os.environ if environment is None else environment
    explicit_url = values.get(_EXPLICIT_URL_VARIABLES[workload])
    if explicit_url is not None:
        return make_url(explicit_url).render_as_string(hide_password=False)

    workload_prefix = f"POLYGLOT_{workload.upper()}_DATABASE_"
    url = URL.create(
        drivername=values["POLYGLOT_DATABASE_DRIVERNAME"],
        username=values[f"{workload_prefix}USERNAME"],
        password=values[f"{workload_prefix}PASSWORD"],
        host=values["POLYGLOT_DATABASE_HOST"],
        port=int(values["POLYGLOT_DATABASE_PORT"]),
        database=values["POLYGLOT_DATABASE_NAME"],
    )
    return url.render_as_string(hide_password=False)


def migration_database_url_from_environment() -> str:
    return workload_database_url_from_environment("migration")


def database_url_from_environment() -> str:
    return workload_database_url_from_environment("runtime")


def retention_database_url_from_environment() -> str:
    return workload_database_url_from_environment("retention")


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
