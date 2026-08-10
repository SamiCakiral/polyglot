from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from polyglot.bootstrap.database import migration_database_url_from_environment
from polyglot.modules.catalogue.core import persistence as catalogue_persistence
from polyglot.modules.content import persistence as content_persistence
from polyglot.modules.identity import persistence as identity_persistence
from polyglot.modules.language_profiles import persistence as language_profiles_persistence
from polyglot.modules.lexicon.core import persistence as lexicon_persistence
from polyglot.platform.persistence.models import metadata

del catalogue_persistence
del content_persistence
del identity_persistence
del language_profiles_persistence
del lexicon_persistence

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def include_object(
    object_: object,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: object | None,
) -> bool:
    """Audited SQL DDL owns schemas with RLS policies and append-only triggers."""
    del name, type_, reflected, compare_to
    return getattr(object_, "schema", None) not in {
        "language_profiles",
        "lexicon",
        "memory",
        "exchange",
    }


def database_url() -> str:
    return migration_database_url_from_environment()


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_sync_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_schemas=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    engine = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(run_sync_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
