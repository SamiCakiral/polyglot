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

NOW = datetime(2026, 8, 10, 8, tzinfo=UTC)
ACCOUNT_ID = UUID("019feb33-0000-7000-8000-000000000001")
PROFILE_ID = UUID("019feb33-0000-7000-8000-000000000002")


@pytest.fixture
async def migration_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migration_database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.fixture
async def runtime_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url_from_environment())
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def seeded_profile(migration_session: AsyncSession) -> UUID:
    await migration_session.execute(
        text(
            "INSERT INTO identity.accounts "
            "(account_id,status,security_version,session_version,version,created_at,"
            "security_last_activity_at) VALUES (:account,'active',1,1,1,:now,:now) "
            "ON CONFLICT DO NOTHING"
        ),
        {"account": ACCOUNT_ID, "now": NOW},
    )
    await migration_session.execute(
        text("SELECT set_config('app.user_id',:actor,false)"), {"actor": str(ACCOUNT_ID)}
    )
    await migration_session.execute(
        text(
            "INSERT INTO language_profiles.learner_language_profiles "
            "(profile_id,account_id,target_variety_id,native_variety_id,status,current_phase,"
            "goals,interests,excluded_themes,correction_preference,availability_pattern,"
            "version,created_at,updated_at) VALUES "
            "(:profile,:account,:target,:native,'active','module_learning','[]','[]','[]',"
            "'{}','{}',1,:now,:now) ON CONFLICT DO NOTHING"
        ),
        {
            "profile": PROFILE_ID,
            "account": ACCOUNT_ID,
            "target": UUID("019feb33-0000-7000-8000-000000000003"),
            "native": UUID("019feb33-0000-7000-8000-000000000004"),
            "now": NOW,
        },
    )
    await migration_session.commit()
    return PROFILE_ID


@pytest.fixture(autouse=True)
async def clean_assessment_storage() -> AsyncIterator[None]:
    yield
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.begin() as connection:
        if await connection.scalar(text("SELECT to_regnamespace('assessments')")) is not None:
            await connection.execute(
                text(
                    "TRUNCATE assessments.assessment_evidence,assessments.assessment_reviews,"
                    "assessments.assessment_results,assessments.assessment_responses,"
                    "assessments.assessment_section_runs,assessments.form_exposures,"
                    "assessments.assessment_runs CASCADE"
                )
            )
        await connection.execute(text("TRUNCATE platform.command_receipts CASCADE"))
    await engine.dispose()
