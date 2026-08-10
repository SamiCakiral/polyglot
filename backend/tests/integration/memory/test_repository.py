from dataclasses import replace

import pytest
from polyglot.modules.lexicon.memory.persistence import SqlMemoryRepository
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.modules.lexicon.memory.application import MemoryLifecycle
from polyglot.modules.lexicon.memory.policy import SchedulerPolicy
from polyglot.modules.lexicon.memory.providers.fsrs_v6 import FsrsV6Scheduler
from polyglot.platform.errors import DomainError, ErrorCode

from .conftest import ACCOUNT_A, PROFILE_A, new_aggregate, seed_profiles, set_actor, uid


async def test_repository_round_trips_complete_aggregate(
    migration_session: AsyncSession,
    runtime_session: AsyncSession,
) -> None:
    await seed_profiles(migration_session)
    aggregate = new_aggregate()
    await set_actor(runtime_session, ACCOUNT_A)
    repository = SqlMemoryRepository(runtime_session)
    await repository.add(aggregate)
    await runtime_session.commit()

    loaded = await repository.get(PROFILE_A, aggregate.prompt.prompt_id)
    assert loaded == aggregate


async def test_compare_and_swap_rejects_stale_prompt_and_projection_versions(
    migration_session: AsyncSession,
    runtime_session: AsyncSession,
) -> None:
    await seed_profiles(migration_session)
    aggregate = new_aggregate(prompt_id=uid(110))
    await set_actor(runtime_session, ACCOUNT_A)
    repository = SqlMemoryRepository(runtime_session)
    await repository.add(aggregate)
    await runtime_session.commit()

    changed = replace(
        aggregate,
        prompt=aggregate.prompt.transition(aggregate.prompt.status, aggregate.prompt.updated_at),
    )
    with pytest.raises(DomainError) as error:
        await repository.save(
            changed,
            expected_prompt_version=99,
            expected_projection_version=aggregate.schedule.projection_version,
        )
    assert error.value.code is ErrorCode.VERSION_CONFLICT
    await runtime_session.rollback()
    assert await repository.get(PROFILE_A, aggregate.prompt.prompt_id) == aggregate


async def test_repository_appends_review_and_replaces_only_projection(
    migration_session: AsyncSession,
    runtime_session: AsyncSession,
    review_command,
) -> None:
    await seed_profiles(migration_session)
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    before = new_aggregate(prompt_id=uid(120))
    after = MemoryLifecycle(scheduler).submit_review(
        before,
        review_command(uid(121)),
        policy,
    ).aggregate
    await set_actor(runtime_session, ACCOUNT_A)
    repository = SqlMemoryRepository(runtime_session)
    await repository.add(before)
    await runtime_session.commit()
    await repository.save(
        after,
        expected_prompt_version=before.prompt.version,
        expected_projection_version=before.schedule.projection_version,
    )
    await runtime_session.commit()

    loaded = await repository.get(PROFILE_A, before.prompt.prompt_id)
    assert loaded == after
    assert len(loaded.reviews) == 1
