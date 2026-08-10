from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.modules.language_profiles.domain import LearnerLanguageProfile
from polyglot.modules.language_profiles.persistence import SqlLanguageProfileRepository
from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
ACCOUNT_ID = UUID("019fe903-3000-7000-8000-000000000001")
PROFILE_ID = UUID("019fe903-3000-7000-8000-000000000002")
TARGET = UUID("019fe900-5000-7000-8001-000000000001")
NATIVE = UUID("019fe900-5000-7000-8001-000000000002")


async def seed_account(session: AsyncSession) -> None:
    await session.execute(
        text(
            "INSERT INTO identity.accounts "
            "(account_id, status, security_version, session_version, version, created_at, "
            "security_last_activity_at, deleted_at) VALUES "
            "(:account_id, 'active', 1, 1, 1, :now, :now, NULL)"
        ),
        {"account_id": ACCOUNT_ID, "now": NOW},
    )


async def test_repository_creates_and_reloads_owned_profile(
    migration_session: AsyncSession,
    session: AsyncSession,
) -> None:
    await seed_account(migration_session)
    await migration_session.commit()
    await session.execute(
        text("SELECT set_config('app.user_id', :account_id, true)"),
        {"account_id": str(ACCOUNT_ID)},
    )
    repository = SqlLanguageProfileRepository(session)
    profile = LearnerLanguageProfile.create(
        profile_id=PROFILE_ID,
        account_id=ACCOUNT_ID,
        target_variety_id=TARGET,
        native_variety_id=NATIVE,
        now=NOW,
    )

    await repository.add(profile)
    await session.commit()

    loaded = await repository.get_owned(PROFILE_ID, ACCOUNT_ID)
    assert loaded == profile


async def test_repository_rejects_stale_profile_version(
    migration_session: AsyncSession,
    session: AsyncSession,
) -> None:
    await seed_account(migration_session)
    await migration_session.commit()
    await session.execute(
        text("SELECT set_config('app.user_id', :account_id, true)"),
        {"account_id": str(ACCOUNT_ID)},
    )
    repository = SqlLanguageProfileRepository(session)
    profile = LearnerLanguageProfile.create(
        profile_id=PROFILE_ID,
        account_id=ACCOUNT_ID,
        target_variety_id=TARGET,
        native_variety_id=NATIVE,
        now=NOW,
    )
    await repository.add(profile)
    await session.commit()

    with pytest.raises(DomainError) as rejected:
        await repository.update(profile.with_goals(("travel",), expected_version=2, now=NOW))

    assert rejected.value.code is ErrorCode.VERSION_CONFLICT
