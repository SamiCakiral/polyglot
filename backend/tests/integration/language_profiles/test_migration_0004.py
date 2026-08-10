from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

ACCOUNT_A = UUID("019fe903-2000-7000-8000-000000000001")
ACCOUNT_B = UUID("019fe903-2000-7000-8000-000000000002")
PROFILE_A = UUID("019fe903-2000-7000-8000-000000000003")
PROFILE_B = UUID("019fe903-2000-7000-8000-000000000004")
TARGET = UUID("019fe900-5000-7000-8001-000000000001")
NATIVE = UUID("019fe900-5000-7000-8001-000000000002")
NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


async def seed_account(session: AsyncSession, account_id: UUID) -> None:
    await session.execute(
        text(
            "INSERT INTO identity.accounts "
            "(account_id, status, security_version, session_version, version, created_at, "
            "security_last_activity_at, deleted_at) VALUES "
            "(:account_id, 'active', 1, 1, 1, :now, :now, NULL)"
        ),
        {"account_id": account_id, "now": NOW},
    )


async def seed_profile(session: AsyncSession, profile_id: UUID, account_id: UUID) -> None:
    await session.execute(
        text(
            "INSERT INTO language_profiles.learner_language_profiles "
            "(profile_id, account_id, target_variety_id, native_variety_id, status, "
            "current_phase, goals, interests, excluded_themes, correction_preference, "
            "availability_pattern, version, created_at, updated_at, archived_at, deleted_at) "
            "VALUES (:profile_id, :account_id, :target, :native, 'onboarding', 'diagnostic', "
            "'[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, '{}'::jsonb, 1, :now, :now, "
            "NULL, NULL)"
        ),
        {
            "profile_id": profile_id,
            "account_id": account_id,
            "target": TARGET,
            "native": NATIVE,
            "now": NOW,
        },
    )


async def test_0004_creates_profile_tables_constraints_and_rls(
    migration_session: AsyncSession,
) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'language_profiles'"
                )
            )
        ).scalars()
    )

    assert tables == {
        "learner_language_profiles",
        "support_language_authorizations",
        "declared_language_experiences",
        "diagnostic_runs",
        "diagnostic_responses",
        "foundation_runs",
        "foundation_run_blocks",
        "foundation_gate_results",
    }
    assert await migration_session.scalar(
        text(
            "SELECT relrowsecurity FROM pg_class "
            "WHERE oid = 'language_profiles.learner_language_profiles'::regclass"
        )
    )
    assert await migration_session.scalar(
        text(
            "SELECT has_table_privilege('polyglot_runtime', "
            "'language_profiles.learner_language_profiles', 'SELECT, INSERT, UPDATE')"
        )
    )


async def test_profile_pair_is_unique_until_deletion(
    migration_session: AsyncSession,
) -> None:
    await seed_account(migration_session, ACCOUNT_A)
    await seed_profile(migration_session, PROFILE_A, ACCOUNT_A)

    with pytest.raises(IntegrityError):
        await seed_profile(migration_session, PROFILE_B, ACCOUNT_A)
    await migration_session.rollback()


async def test_runtime_rls_cannot_read_another_owner_profile(
    migration_session: AsyncSession,
    session: AsyncSession,
) -> None:
    await seed_account(migration_session, ACCOUNT_A)
    await seed_account(migration_session, ACCOUNT_B)
    await seed_profile(migration_session, PROFILE_A, ACCOUNT_A)
    await seed_profile(migration_session, PROFILE_B, ACCOUNT_B)
    await migration_session.commit()

    await session.execute(
        text("SELECT set_config('app.user_id', :account_id, true)"), {"account_id": str(ACCOUNT_A)}
    )
    visible = (
        (
            await session.execute(
                text(
                    "SELECT profile_id FROM language_profiles.learner_language_profiles "
                    "ORDER BY profile_id"
                )
            )
        )
        .scalars()
        .all()
    )

    assert visible == [PROFILE_A]
