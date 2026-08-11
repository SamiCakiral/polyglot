from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.curriculum.application import (
    CompleteEnrollment,
    EnrollInModule,
    PauseEnrollment,
)
from polyglot.modules.curriculum.persistence import SqlCurriculumService
from polyglot.modules.identity.application import RequestContext
from polyglot.platform.clock import FrozenClock
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.ids import Uuid7Generator

from .conftest import (
    ACCOUNT_ID,
    MODULE_REVISION_ID,
    NOW,
    PACK_REVISION_ID,
    PROFILE_ID,
    SUPPORT_VARIETY_ID,
    TARGET_VARIETY_ID,
    seed_curriculum_dependencies,
    uid,
)


def service(factory: async_sessionmaker[AsyncSession]) -> SqlCurriculumService:
    return SqlCurriculumService(
        factory,
        clock=FrozenClock(NOW),
        id_generator=Uuid7Generator(FrozenClock(NOW)),
    )


def new_id():  # type: ignore[no-untyped-def]
    return Uuid7Generator(FrozenClock(NOW)).new()


def context() -> RequestContext:
    return RequestContext(
        request_id=uid(280),
        correlation_id=uid(281),
        truncated_ip="127.0.0",
    )


async def test_lists_published_modules_with_pinned_current_revision(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_curriculum_dependencies(migration_session)
    await migration_session.commit()

    modules = await service(runtime_factory).list_modules(ACCOUNT_ID)

    assert len(modules) == 1
    assert modules[0].module_code == "IT-FIRST-AUTONOMOUS-EXCHANGE"
    assert modules[0].module_revision_id == MODULE_REVISION_ID
    assert modules[0].pack_revision_id == PACK_REVISION_ID
    assert modules[0].nominal_days == 3

    assert (
        await service(runtime_factory).list_modules(
            ACCOUNT_ID,
            pack_revision_id=uid(999),
        )
        == ()
    )


async def test_enrollment_rejects_a_module_for_another_target_language(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_curriculum_dependencies(migration_session)
    await migration_session.execute(
        text(
            "UPDATE language_profiles.learner_language_profiles "
            "SET target_variety_id=:support,native_variety_id=:target "
            "WHERE profile_id=:profile"
        ),
        {
            "profile": PROFILE_ID,
            "support": SUPPORT_VARIETY_ID,
            "target": TARGET_VARIETY_ID,
        },
    )
    await migration_session.commit()

    with pytest.raises(DomainError) as error:
        await service(runtime_factory).enroll(
            ACCOUNT_ID,
            PROFILE_ID,
            EnrollInModule(new_id(), MODULE_REVISION_ID, NOW.date()),
            idempotency_key="wrong-target-language",
            context=context(),
        )

    assert error.value.code is ErrorCode.NOT_FOUND


async def test_enrollment_starts_and_replays_without_duplicate_effects(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_curriculum_dependencies(migration_session)
    await migration_session.commit()
    curriculum = service(runtime_factory)
    command = EnrollInModule(
        enrollment_id=new_id(),
        module_revision_id=MODULE_REVISION_ID,
        pedagogical_day=NOW.date(),
    )
    key = f"enroll-pilot:{command.enrollment_id}"

    created = await curriculum.enroll(
        ACCOUNT_ID,
        PROFILE_ID,
        command,
        idempotency_key=key,
        context=context(),
    )
    replay = await curriculum.enroll(
        ACCOUNT_ID,
        PROFILE_ID,
        command,
        idempotency_key=key,
        context=context(),
    )

    assert replay == created
    assert created.status == "active"
    assert created.started_on_pedagogical_day == NOW.date()
    assert created.version == 2
    assert (
        await migration_session.scalar(
            text(
                "SELECT count(*) FROM platform.domain_events "
                "WHERE event_type='module_enrollment_created' AND aggregate_id=:enrollment"
            ),
            {"enrollment": command.enrollment_id},
        )
        == 1
    )


async def test_pause_requires_current_version_and_completion_requires_exit_evidence(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_curriculum_dependencies(migration_session)
    await migration_session.commit()
    curriculum = service(runtime_factory)
    enrollment_id = new_id()
    created = await curriculum.enroll(
        ACCOUNT_ID,
        PROFILE_ID,
        EnrollInModule(enrollment_id, MODULE_REVISION_ID, NOW.date()),
        idempotency_key=f"enroll-transition:{enrollment_id}",
        context=context(),
    )

    with pytest.raises(DomainError) as stale:
        await curriculum.pause(
            ACCOUNT_ID,
            created.enrollment_id,
            PauseEnrollment(paused_at=NOW),
            expected_version=1,
            idempotency_key=f"pause-stale:{enrollment_id}",
            context=context(),
        )
    assert stale.value.code is ErrorCode.VERSION_CONFLICT

    paused = await curriculum.pause(
        ACCOUNT_ID,
        created.enrollment_id,
        PauseEnrollment(paused_at=NOW),
        expected_version=created.version,
        idempotency_key=f"pause-current:{enrollment_id}",
        context=context(),
    )
    assert paused.status == "paused" and paused.version == 3

    with pytest.raises(DomainError) as incomplete:
        await curriculum.complete(
            ACCOUNT_ID,
            paused.enrollment_id,
            CompleteEnrollment(completed_at=NOW),
            expected_version=paused.version,
            idempotency_key=f"complete-too-early:{enrollment_id}",
            context=context(),
        )
    assert incomplete.value.code is ErrorCode.INVALID_TRANSITION
