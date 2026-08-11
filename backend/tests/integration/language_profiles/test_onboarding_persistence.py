from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import database_url_from_environment
from polyglot.modules.identity.application import RequestContext
from polyglot.modules.language_profiles.onboarding import (
    EntryPath,
    PlacementBand,
    PlacementChoice,
    SkillDimension,
    SkillEstimate,
)
from polyglot.modules.language_profiles.onboarding_persistence import OnboardingApplicationService
from polyglot.platform.clock import FrozenClock

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
ACCOUNT_ID = UUID("019f0000-0000-7000-8000-000000000501")
PROFILE_ID = UUID("019f0000-0000-7000-8000-000000000502")
TARGET_ID = UUID("019f0000-0000-7000-8000-000000000503")
NATIVE_ID = UUID("019f0000-0000-7000-8000-000000000504")


async def seed_profile(session: AsyncSession) -> None:
    await session.execute(
        text("DELETE FROM platform.command_receipts WHERE actor_id = :account_id"),
        {"account_id": ACCOUNT_ID},
    )
    await session.execute(
        text(
            "INSERT INTO identity.accounts "
            "(account_id,status,security_version,session_version,version,created_at,"
            "security_last_activity_at,deleted_at) "
            "VALUES (:account_id,'active',1,1,1,:now,:now,NULL)"
        ),
        {"account_id": ACCOUNT_ID, "now": NOW},
    )
    await session.execute(
        text(
            "INSERT INTO language_profiles.learner_language_profiles "
            "(profile_id,account_id,target_variety_id,native_variety_id,status,current_phase,"
            "goals,interests,excluded_themes,correction_preference,availability_pattern,"
            "version,created_at,updated_at,archived_at,deleted_at) VALUES "
            "(:profile_id,:account_id,:target,:native,'onboarding','diagnostic','[]'::jsonb,"
            "'[]'::jsonb,'[]'::jsonb,'{}'::jsonb,'{}'::jsonb,1,:now,:now,NULL,NULL)"
        ),
        {
            "profile_id": PROFILE_ID,
            "account_id": ACCOUNT_ID,
            "target": TARGET_ID,
            "native": NATIVE_ID,
            "now": NOW,
        },
    )
    await session.commit()


async def test_onboarding_state_is_versioned_replayable_and_owner_scoped(
    migration_session: AsyncSession,
) -> None:
    await seed_profile(migration_session)
    engine = create_async_engine(database_url_from_environment())
    service = OnboardingApplicationService(
        async_sessionmaker(engine, expire_on_commit=False),
        clock=FrozenClock(NOW),
    )
    context = RequestContext(
        request_id=UUID("019f0000-0000-7000-8000-000000000505"),
        correlation_id=UUID("019f0000-0000-7000-8000-000000000506"),
        truncated_ip="127.0.0.0/24",
    )

    started = await service.start(
        profile_id=PROFILE_ID,
        account_id=ACCOUNT_ID,
        entry_path=EntryPath.ALREADY_STARTED,
        idempotency_key="start-onboarding",
        context=context,
    )
    replay = await service.start(
        profile_id=PROFILE_ID,
        account_id=ACCOUNT_ID,
        entry_path=EntryPath.ALREADY_STARTED,
        idempotency_key="start-onboarding",
        context=context,
    )
    semantic_replay = await service.start(
        profile_id=PROFILE_ID,
        account_id=ACCOUNT_ID,
        entry_path=EntryPath.ALREADY_STARTED,
        idempotency_key="start-onboarding-again",
        context=context,
    )
    skills = tuple(
        SkillEstimate(item, PlacementBand.FUNCTIONAL, 0.75, 2) for item in SkillDimension
    )
    placed = await service.record_placement(
        profile_id=PROFILE_ID,
        account_id=ACCOUNT_ID,
        detected_band=PlacementBand.FUNCTIONAL,
        confidence=0.75,
        skills=skills,
        expected_version=1,
        idempotency_key="record-placement",
        context=context,
    )
    chosen = await service.choose(
        profile_id=PROFILE_ID,
        account_id=ACCOUNT_ID,
        choice=PlacementChoice.START_EASIER,
        expected_version=2,
        idempotency_key="choose-placement",
        context=context,
    )

    assert replay == started
    assert semantic_replay == started
    assert placed.version == 2
    assert chosen.resolved_band is PlacementBand.EMERGING
    assert await service.get(PROFILE_ID, ACCOUNT_ID) == chosen
    profile_status = await migration_session.scalar(
        text(
            "SELECT status FROM language_profiles.learner_language_profiles "
            "WHERE profile_id = :profile_id"
        ),
        {"profile_id": PROFILE_ID},
    )
    assert profile_status == "active"
    await engine.dispose()
