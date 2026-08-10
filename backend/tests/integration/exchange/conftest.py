from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import migration_database_url_from_environment


@pytest.fixture
async def migration_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migration_database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()

