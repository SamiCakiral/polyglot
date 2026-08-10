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

NOW = datetime(2026, 8, 10, 12, tzinfo=UTC)


def uid(value: int) -> UUID:
    return UUID(f"019fab10-0000-7000-8000-{value:012x}")


ACCOUNT_A = uid(1)
ACCOUNT_B = uid(2)
PROFILE_A = uid(11)
PROFILE_B = uid(12)
TARGET_VARIETY = uid(21)
NATIVE_VARIETY = uid(22)


async def set_actor(session: AsyncSession, account_id: UUID | None) -> None:
    await session.execute(
        text("SELECT set_config('app.user_id',:account,false)"),
        {"account": "" if account_id is None else str(account_id)},
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


async def seed_corrected_attempt(session: AsyncSession) -> tuple[UUID, UUID]:
    await seed_profiles(session)
    definition = uid(30)
    revision = uid(31)
    instance = uid(32)
    attempt = uid(33)
    correction = uid(34)
    await session.execute(
        text(
            "INSERT INTO exercises.exercise_definitions "
            "(definition_id,definition_code,current_revision_id,status,version,"
            "created_at,updated_at) "
            "VALUES (:definition,'progress.transform.01',NULL,'published',1,:now,:now)"
        ),
        {"definition": definition, "now": NOW},
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
            "(:revision,:definition,1,1,'EX-TRANSFORM-01','published','[\"text\"]','[]',"
            "'[\"gym\"]','[[\"grammar\",1.0]]','{}','{}','[]','{}','[]','exact:v1',"
            "'hint:v1','observation:v1','[\"keyboard\"]',1000,2000,3000,'[]',:provenance,:now)"
        ),
        {"revision": revision, "definition": definition, "provenance": uid(35), "now": NOW},
    )
    await session.execute(
        text(
            "UPDATE exercises.exercise_definitions SET current_revision_id=:revision "
            "WHERE definition_id=:definition"
        ),
        {"revision": revision, "definition": definition},
    )
    await set_actor(session, ACCOUNT_A)
    await session.execute(
        text(
            "INSERT INTO exercises.exercise_instances "
            "(instance_id,standalone_profile_id,definition_revision_id,language_pack_revision_id,"
            "seed,stimulus_revision_ids,target_bindings,lexical_bindings,grammar_bindings,"
            "provenance_id,created_at) VALUES "
            "(:instance,:profile,:revision,:pack,42,'[\"019fab10-0000-7000-8000-000000000036\"]',"
            "'[\"grammar:it.futuro-prossimo\"]','[]','[\"grammar:it.futuro-prossimo\"]',"
            ":provenance,:now)"
        ),
        {
            "instance": instance,
            "profile": PROFILE_A,
            "revision": revision,
            "pack": uid(37),
            "provenance": uid(38),
            "now": NOW,
        },
    )
    await session.execute(
        text(
            "INSERT INTO exercises.exercise_attempts "
            "(attempt_id,profile_id,instance_id,attempt_no,status,terminal_reason,answer_kind,"
            "raw_answer,input_method,input_locale,submitted_at,corrected_at,aggregate_payload,"
            "version,started_at,updated_at,idempotency_key,request_fingerprint) VALUES "
            "(:attempt,:profile,:instance,1,'corrected','none','text','\"prendo\"','keyboard',"
            "'it-IT',:now,:now,'{}',3,:now,:now,'submit','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')"
        ),
        {"attempt": attempt, "profile": PROFILE_A, "instance": instance, "now": NOW},
    )
    await session.execute(
        text(
            "INSERT INTO exercises.exercise_corrections "
            "(correction_id,attempt_id,profile_id,revision_no,verdict,confidence,target_coverage,"
            "strategy,alternatives,explanation,error_codes,criterion_scores,provenance_id,"
            "requires_review,is_current,result_payload,created_at) VALUES "
            "(:correction,:attempt,:profile,1,'correct',1,1,'exact','[]','correct','[]','{}',"
            ":provenance,false,true,'{}',:now)"
        ),
        {
            "correction": correction,
            "attempt": attempt,
            "profile": PROFILE_A,
            "provenance": uid(39),
            "now": NOW,
        },
    )
    await session.commit()
    return attempt, correction


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


@pytest.fixture(autouse=True)
async def clean_progress_storage() -> AsyncIterator[None]:
    async def clean() -> None:
        engine = create_async_engine(migration_database_url_from_environment())
        async with engine.begin() as connection:
            if await connection.scalar(text("SELECT to_regnamespace('progress')")) is not None:
                tables = tuple(
                    (
                        await connection.execute(
                            text(
                                "SELECT table_name FROM information_schema.tables "
                                "WHERE table_schema='progress'"
                            )
                        )
                    ).scalars()
                )
                mutable = tuple(name for name in tables if name != "policy_revisions")
                if mutable:
                    qualified = ",".join(f'progress."{name}"' for name in mutable)
                    await connection.execute(text(f"TRUNCATE {qualified} CASCADE"))
            for schema in ("planning", "exercises"):
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
                    qualified = ",".join(f'{schema}."{name}"' for name in tables)
                    await connection.execute(text(f"TRUNCATE {qualified} CASCADE"))
            await connection.execute(text("TRUNCATE platform.inbox_receipts CASCADE"))
            await connection.execute(text("TRUNCATE platform.outbox_messages CASCADE"))
            await connection.execute(text("TRUNCATE platform.domain_events CASCADE"))
            await connection.execute(
                text("TRUNCATE language_profiles.learner_language_profiles CASCADE")
            )
            await connection.execute(text("TRUNCATE identity.accounts CASCADE"))
        await engine.dispose()

    await clean()
    yield
    await clean()
