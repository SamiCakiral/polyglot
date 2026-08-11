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

NOW = datetime(2026, 8, 10, 15, 0, tzinfo=UTC)


def uid(value: int) -> UUID:
    return UUID(f"019fec00-0000-7000-8000-{value:012x}")


ACCOUNT_ID = uid(1)
PROFILE_ID = uid(2)
DEFINITION_ID = uid(3)
DEFINITION_REVISION_ID = uid(4)
INSTANCE_ID = uid(5)
ATTEMPT_ID = uid(6)


async def seed_attempt(
    session: AsyncSession,
    *,
    primitive_id: str = "EX-RECALL-01",
    response_kinds: str = '["self_grade"]',
) -> None:
    await session.execute(
        text(
            "INSERT INTO identity.accounts "
            "(account_id,status,security_version,session_version,version,created_at,"
            "security_last_activity_at) VALUES "
            "(:account,'active',1,1,1,:now,:now) ON CONFLICT DO NOTHING"
        ),
        {"account": ACCOUNT_ID, "now": NOW},
    )
    await session.execute(
        text("SELECT set_config('app.user_id',:actor,false)"),
        {"actor": str(ACCOUNT_ID)},
    )
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
            "profile": PROFILE_ID,
            "account": ACCOUNT_ID,
            "target": uid(20),
            "native": uid(21),
            "now": NOW,
        },
    )
    await session.execute(
        text(
            "INSERT INTO exercises.exercise_definitions "
            "(definition_id,definition_code,status,version,created_at,updated_at) VALUES "
            "(:definition,'core.recall.01','published',1,:now,:now)"
        ),
        {"definition": DEFINITION_ID, "now": NOW},
    )
    await session.execute(
        text(
            "INSERT INTO exercises.exercise_definition_revisions "
            "(definition_revision_id,definition_id,revision_no,schema_version,primitive_id,"
            "status,response_kinds,language_certification_ids,modes,target_weights,"
            "response_contract,stimulus_contract,target_contract,difficulty_profile,"
            "prerequisite_skill_revision_ids,correction_policy_id,hint_policy_id,"
            "observation_policy_id,accessibility_features,min_duration_ms,p50_duration_ms,"
            "p80_duration_ms,example_revision_ids,provenance_id,created_at) VALUES "
            "(:revision,:definition,1,1,:primitive,'published',CAST(:response_kinds AS jsonb),"
            "'[]','[\"cards\"]','[[\"lexical\",0.55]]','{}','{}','[]','{}','[]',"
            "'correction:v1','hint:v1','observation:v1',"
            "'[\"keyboard\",\"screen_reader\",\"untimed\"]',1000,2000,3000,'[]',"
            ":provenance,:now)"
        ),
        {
            "revision": DEFINITION_REVISION_ID,
            "definition": DEFINITION_ID,
            "primitive": primitive_id,
            "response_kinds": response_kinds,
            "provenance": uid(22),
            "now": NOW,
        },
    )
    await session.execute(
        text(
            "UPDATE exercises.exercise_definitions SET current_revision_id=:revision "
            "WHERE definition_id=:definition"
        ),
        {"revision": DEFINITION_REVISION_ID, "definition": DEFINITION_ID},
    )
    await session.execute(
        text(
            "INSERT INTO exercises.exercise_instances "
            "(instance_id,standalone_profile_id,definition_revision_id,"
            "language_pack_revision_id,seed,stimulus_revision_ids,target_bindings,"
            "lexical_bindings,grammar_bindings,provenance_id,created_at) VALUES "
            "(:instance,:profile,:revision,:pack,42,'[\"019fec00-0000-7000-8000-000000000019\"]',"
            "'[]','[]','[]',:provenance,:now)"
        ),
        {
            "instance": INSTANCE_ID,
            "profile": PROFILE_ID,
            "revision": DEFINITION_REVISION_ID,
            "pack": uid(23),
            "provenance": uid(24),
            "now": NOW,
        },
    )
    await session.execute(
        text(
            "INSERT INTO exercises.exercise_attempts "
            "(attempt_id,profile_id,instance_id,attempt_no,status,terminal_reason,"
            "aggregate_payload,version,started_at,updated_at) VALUES "
            "(:attempt,:profile,:instance,1,'draft','none','{}',1,:now,:now)"
        ),
        {
            "attempt": ATTEMPT_ID,
            "profile": PROFILE_ID,
            "instance": INSTANCE_ID,
            "now": NOW,
        },
    )


@pytest.fixture(autouse=True)
async def clean_exercise_database() -> AsyncIterator[None]:
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.begin() as connection:
        tables = tuple(
            (
                await connection.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema='exercises'"
                    )
                )
            ).scalars()
        )
        if tables:
            qualified = ",".join(f'exercises."{table}"' for table in tables)
            await connection.execute(text(f"TRUNCATE {qualified} CASCADE"))
        await connection.execute(text("TRUNCATE platform.outbox_messages CASCADE"))
        await connection.execute(text("TRUNCATE platform.domain_events CASCADE"))
        await connection.execute(text("TRUNCATE platform.command_receipts CASCADE"))
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
async def runtime_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()
