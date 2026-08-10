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

NOW = datetime(2026, 8, 10, 14, 0, tzinfo=UTC)


def uid(value: int) -> UUID:
    return UUID(f"019feb00-0000-7000-8000-{value:012x}")


ACCOUNT_A = uid(1)
ACCOUNT_B = uid(2)
PROFILE_A = uid(11)
PROFILE_B = uid(12)
TARGET_VARIETY = uid(21)
NATIVE_VARIETY = uid(22)


async def set_actor(session: AsyncSession, account_id: UUID | None) -> None:
    await session.execute(
        text("SELECT set_config('app.user_id', :actor, false)"),
        {"actor": "" if account_id is None else str(account_id)},
    )


async def seed_profiles(session: AsyncSession) -> None:
    for account_id in (ACCOUNT_A, ACCOUNT_B):
        await session.execute(
            text(
                "INSERT INTO identity.accounts "
                "(account_id,status,security_version,session_version,version,created_at,"
                "security_last_activity_at) VALUES "
                "(:account,'active',1,1,1,:now,:now) ON CONFLICT DO NOTHING"
            ),
            {"account": account_id, "now": NOW},
        )
    for profile_id, account_id in ((PROFILE_A, ACCOUNT_A), (PROFILE_B, ACCOUNT_B)):
        await set_actor(session, account_id)
        await session.execute(
            text(
                "INSERT INTO language_profiles.learner_language_profiles "
                "(profile_id,account_id,target_variety_id,native_variety_id,status,current_phase,"
                "goals,interests,excluded_themes,correction_preference,availability_pattern,"
                "version,created_at,updated_at) VALUES "
                "(:profile,:account,:target,:native,'active','module_learning','[]','[]','[]',"
                "'{}','{}',1,:now,:now) ON CONFLICT DO NOTHING"
            ),
            {
                "profile": profile_id,
                "account": account_id,
                "target": TARGET_VARIETY,
                "native": NATIVE_VARIETY,
                "now": NOW,
            },
        )
    await set_actor(session, None)
    await session.commit()


@pytest.fixture(autouse=True)
async def clean_exchange_database() -> AsyncIterator[None]:
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.begin() as connection:
        for schema in ("exchange", "memory", "lexicon"):
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
        await connection.execute(text("TRUNCATE platform.command_receipts CASCADE"))
        await connection.execute(text("TRUNCATE platform.domain_events CASCADE"))
        await connection.execute(text("TRUNCATE platform.outbox_messages CASCADE"))
        await connection.execute(
            text("TRUNCATE language_profiles.learner_language_profiles CASCADE")
        )
        await connection.execute(text("TRUNCATE identity.accounts CASCADE"))
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
async def runtime_factory(migration_session: AsyncSession):
    await seed_profiles(migration_session)
    engine = create_async_engine(database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()
