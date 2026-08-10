import pytest
from polyglot.modules.lexicon.memory.persistence import SqlMemoryRepository
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.modules.lexicon.memory.application import MemoryLifecycle, ResetMemoryPrompt
from polyglot.modules.lexicon.memory.policy import SchedulerPolicy
from polyglot.modules.lexicon.memory.providers.fsrs_v6 import FsrsV6Scheduler
from polyglot.modules.lexicon.memory.rebuild import rebuild_schedule
from polyglot.platform.errors import DomainError, ErrorCode

from .conftest import (
    ACCOUNT_A,
    NOW,
    PROFILE_A,
    new_aggregate,
    replay_resolver,
    seed_profiles,
    set_actor,
    uid,
)


async def test_loaded_history_rebuilds_to_identical_projection(
    migration_session: AsyncSession,
    runtime_session: AsyncSession,
    review_command,
) -> None:
    await seed_profiles(migration_session)
    scheduler = FsrsV6Scheduler()
    policy = SchedulerPolicy.default()
    lifecycle = MemoryLifecycle(scheduler)
    aggregate = new_aggregate(prompt_id=uid(500))
    aggregate = lifecycle.submit_review(aggregate, review_command(uid(501)), policy).aggregate
    aggregate = lifecycle.reset(
        aggregate,
        ResetMemoryPrompt(uid(502), "integration rebuild", NOW),
        policy,
    )
    await set_actor(runtime_session, ACCOUNT_A)
    repository = SqlMemoryRepository(runtime_session)
    await repository.add(aggregate)
    await runtime_session.commit()

    loaded = await repository.get(PROFILE_A, aggregate.prompt.prompt_id)
    assert loaded is not None
    assert rebuild_schedule(loaded, replay_resolver(policy)) == loaded.schedule


async def test_rebuild_compare_and_swap_is_atomic_and_rejects_stale_projection(
    migration_session: AsyncSession,
    runtime_session: AsyncSession,
) -> None:
    await seed_profiles(migration_session)
    policy = SchedulerPolicy.default()
    aggregate = new_aggregate(prompt_id=uid(510))
    await set_actor(runtime_session, ACCOUNT_A)
    repository = SqlMemoryRepository(runtime_session)
    await repository.add(aggregate)
    await runtime_session.commit()

    rebuilt = await repository.rebuild_projection(
        PROFILE_A,
        aggregate.prompt.prompt_id,
        replay_resolver(policy),
        expected_projection_version=aggregate.schedule.projection_version,
    )
    await runtime_session.commit()
    assert rebuilt == aggregate.schedule

    with pytest.raises(DomainError) as error:
        await repository.rebuild_projection(
            PROFILE_A,
            aggregate.prompt.prompt_id,
            replay_resolver(policy),
            expected_projection_version=99,
        )
    assert error.value.code is ErrorCode.VERSION_CONFLICT
