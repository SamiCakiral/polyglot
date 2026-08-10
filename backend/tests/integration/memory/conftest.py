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
from polyglot.modules.lexicon.memory.application import (
    CreateMemoryPrompt,
    MemoryLifecycle,
    SubmitMemoryReview,
)
from polyglot.modules.lexicon.memory.domain import MemoryAggregate
from polyglot.modules.lexicon.memory.policy import HintLevel, ReviewVerdict, SchedulerPolicy
from polyglot.modules.lexicon.memory.ports import MemoryRating
from polyglot.modules.lexicon.memory.providers.fsrs_v6 import FsrsV6Scheduler
from polyglot.modules.lexicon.memory.rebuild import (
    MemoryReplayBinding,
    StaticMemoryReplayResolver,
)

NOW = datetime(2026, 8, 10, 13, 0, tzinfo=UTC)


def uid(value: int) -> UUID:
    return UUID(f"019fea00-0000-7000-8000-{value:012x}")


ACCOUNT_A = uid(1)
ACCOUNT_B = uid(2)
PROFILE_A = uid(11)
PROFILE_B = uid(12)
TARGET_VARIETY = uid(21)
NATIVE_VARIETY = uid(22)


async def set_actor(session: AsyncSession, account_id: UUID | None) -> None:
    await session.execute(
        text("SELECT set_config('app.user_id', :account_id, true)"),
        {"account_id": "" if account_id is None else str(account_id)},
    )


async def seed_profiles(session: AsyncSession) -> None:
    for account_id in (ACCOUNT_A, ACCOUNT_B):
        await session.execute(
            text(
                "INSERT INTO identity.accounts "
                "(account_id,status,security_version,session_version,version,created_at,"
                "security_last_activity_at) VALUES "
                "(:account,'active',1,1,1,:now,:now) ON CONFLICT (account_id) DO NOTHING"
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
                "'{}','{}',1,:now,:now) ON CONFLICT (profile_id) DO NOTHING"
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


def replay_resolver(
    policy: SchedulerPolicy,
) -> StaticMemoryReplayResolver:
    scheduler = FsrsV6Scheduler()
    return StaticMemoryReplayResolver(
        (
            MemoryReplayBinding(
                scheduler=scheduler,
                policy=policy,
            ),
        )
    )


def new_aggregate(
    *,
    prompt_id: UUID | None = None,
    profile_id: UUID = PROFILE_A,
    target_ref: UUID | None = None,
) -> MemoryAggregate:
    prompt_id = prompt_id or uid(100)
    target_ref = target_ref or uid(200)
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    return MemoryLifecycle(scheduler).create(
        CreateMemoryPrompt(
            prompt_id=prompt_id,
            profile_id=profile_id,
            target_ref=target_ref,
            target_revision_id=uid(201),
            direction="target_to_support",
            modality="written",
            operation="recall",
            protocol_id="certified-recall-v1",
            protocol_revision=1,
            rating_semantics_id="polyglot-recall-v1",
            scheduler_policy_id=uid(202),
            created_at=NOW,
        ),
        policy,
    )


@pytest.fixture
def review_command():
    def build(
        review_id: UUID,
        *,
        opportunity_id: UUID | None = None,
    ) -> SubmitMemoryReview:
        return SubmitMemoryReview(
            review_id=review_id,
            opportunity_id=opportunity_id or uid(900),
            attempt_id=uid(901),
            response_ref="response:integration",
            correction_ref="correction:integration",
            verdict=ReviewVerdict.CORRECT,
            highest_hint=HintLevel.H0,
            rating=MemoryRating.GOOD,
            certified_recall=True,
            answer_revealed=False,
            exposure_only=False,
            incidental_production=False,
            self_reported=False,
            active_duration_ms=2_000,
            scheduled_at=NOW,
            reviewed_at=NOW,
            idempotency_key=f"review-{review_id}",
            certification_ref="certification:integration",
            certified_operation="recall",
            certified_protocol_id="certified-recall-v1",
            certified_protocol_revision=1,
            certified_target_revision_id=uid(201),
        )

    return build


@pytest.fixture(autouse=True)
async def clean_memory_database() -> AsyncIterator[None]:
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.begin() as connection:
        if await connection.scalar(text("SELECT to_regnamespace('memory')")) is not None:
            tables = tuple(
                (
                    await connection.execute(
                        text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema='memory'"
                        )
                    )
                ).scalars()
            )
            if tables:
                qualified = ", ".join(f'memory."{name}"' for name in tables)
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
async def runtime_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(database_url_from_environment())
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
