from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import (
    database_url_from_environment,
    migration_database_url_from_environment,
)
from polyglot.modules.identity.domain import FakeOidcProvider, OidcAssertion, SessionSecrets
from polyglot.platform.clock import FrozenClock


@pytest.fixture
async def identity_service() -> AsyncIterator[object]:
    from polyglot.modules.identity.application import IdentityApplicationService

    engine = create_async_engine(database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = IdentityApplicationService(
        factory,
        clock=FrozenClock(datetime(2026, 8, 10, 12, 0, tzinfo=UTC)),
        session_secrets=SessionSecrets.from_key(b"contract-test-session-secret-32b"),
        oidc_provider=FakeOidcProvider(
            {
                "fixture-oidc": OidcAssertion(
                    issuer="https://fixture-oidc.invalid",
                    subject="contract-user",
                )
            }
        ),
    )
    yield service
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_contract_identity_database() -> AsyncIterator[None]:
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE TABLE identity.accounts CASCADE"))
        await connection.execute(text("TRUNCATE TABLE platform.domain_events CASCADE"))
        tables = (
            await connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'platform' AND table_name != 'domain_events'"
                )
            )
        ).scalars()
        for table_name in tables:
            await connection.execute(
                text(f'TRUNCATE TABLE platform."{table_name}" CASCADE')
            )
    await engine.dispose()
    yield
