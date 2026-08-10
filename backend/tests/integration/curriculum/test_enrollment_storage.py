from __future__ import annotations

import pytest

# ruff: noqa: E501
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .conftest import (
    ACCOUNT_ID,
    MODULE_ID,
    MODULE_REVISION_ID,
    NOW,
    OTHER_ACCOUNT_ID,
    PROFILE_ID,
    SUCCESSOR_REVISION_ID,
    insert_module_revision,
    seed_curriculum_dependencies,
    uid,
)


async def insert_enrollment(session: AsyncSession, enrollment_id, *, status: str = "planned"):
    started = None if status == "planned" else NOW.date()
    await session.execute(
        text("SELECT set_config('app.user_id',:actor,true)"),
        {"actor": str(ACCOUNT_ID)},
    )
    await session.execute(
        text(
            "INSERT INTO curriculum.module_enrollments "
            "(enrollment_id,profile_id,module_revision_id,nominal_days,max_days,status,"
            "current_day_ordinal,started_on_pedagogical_day,waiver_refs,version,created_at,updated_at) "
            "VALUES (:id,:profile,:revision,3,3,:status,1,:started,ARRAY[]::varchar[],1,:now,:now)"
        ),
        {
            "id": enrollment_id,
            "profile": PROFILE_ID,
            "revision": MODULE_REVISION_ID,
            "status": status,
            "started": started,
            "now": NOW,
        },
    )


async def test_profile_cannot_hold_two_live_module_enrollments(
    migration_session: AsyncSession,
) -> None:
    await seed_curriculum_dependencies(migration_session)
    await insert_enrollment(migration_session, uid(201))

    with pytest.raises(IntegrityError, match="uq_curriculum_active_enrollment"):
        await insert_enrollment(migration_session, uid(202))


async def test_published_day_cannot_be_rewritten(migration_session: AsyncSession) -> None:
    await seed_curriculum_dependencies(migration_session)

    with pytest.raises(DBAPIError, match="curriculum fact is append-only"):
        await migration_session.execute(
            text(
                "UPDATE curriculum.module_days SET objective_codes=ARRAY['rewritten'] "
                "WHERE module_revision_id=:revision AND ordinal=1"
            ),
            {"revision": MODULE_REVISION_ID},
        )


async def test_runtime_only_sees_its_own_enrollment(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_curriculum_dependencies(migration_session)
    await insert_enrollment(migration_session, uid(203), status="active")
    await migration_session.commit()

    async with runtime_factory() as owner_session:
        await owner_session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"),
            {"actor": str(ACCOUNT_ID)},
        )
        assert (
            await owner_session.scalar(text("SELECT count(*) FROM curriculum.module_enrollments"))
            == 1
        )

    async with runtime_factory() as other_session:
        await other_session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"),
            {"actor": str(OTHER_ACCOUNT_ID)},
        )
        assert (
            await other_session.scalar(text("SELECT count(*) FROM curriculum.module_enrollments"))
            == 0
        )


async def test_successor_publication_does_not_repin_existing_enrollment(
    migration_session: AsyncSession,
) -> None:
    await seed_curriculum_dependencies(migration_session)
    enrollment_id = uid(204)
    await insert_enrollment(migration_session, enrollment_id, status="active")
    await insert_module_revision(
        migration_session,
        SUCCESSOR_REVISION_ID,
        2,
        supersedes_revision_id=MODULE_REVISION_ID,
    )
    await migration_session.execute(
        text(
            "UPDATE curriculum.learning_modules SET current_revision_id=:successor,version=2 "
            "WHERE module_id=:module"
        ),
        {"successor": SUCCESSOR_REVISION_ID, "module": MODULE_ID},
    )

    assert (
        await migration_session.scalar(
            text(
                "SELECT module_revision_id FROM curriculum.module_enrollments "
                "WHERE enrollment_id=:enrollment"
            ),
            {"enrollment": enrollment_id},
        )
        == MODULE_REVISION_ID
    )


async def test_planned_enrollment_can_be_cancelled_before_it_starts(
    migration_session: AsyncSession,
) -> None:
    await seed_curriculum_dependencies(migration_session)
    await migration_session.execute(
        text("SELECT set_config('app.user_id',:actor,true)"),
        {"actor": str(ACCOUNT_ID)},
    )

    await migration_session.execute(
        text(
            "INSERT INTO curriculum.module_enrollments "
            "(enrollment_id,profile_id,module_revision_id,nominal_days,max_days,status,"
            "current_day_ordinal,terminal_at,waiver_refs,version,created_at,updated_at) "
            "VALUES (:id,:profile,:revision,3,3,'cancelled',1,:now,ARRAY[]::varchar[],2,:now,:now)"
        ),
        {
            "id": uid(205),
            "profile": PROFILE_ID,
            "revision": MODULE_REVISION_ID,
            "now": NOW,
        },
    )

    assert (
        await migration_session.scalar(
            text("SELECT status FROM curriculum.module_enrollments WHERE enrollment_id=:id"),
            {"id": uid(205)},
        )
        == "cancelled"
    )
