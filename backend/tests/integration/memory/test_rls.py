from polyglot.modules.lexicon.memory.persistence import SqlMemoryRepository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import (
    ACCOUNT_A,
    ACCOUNT_B,
    PROFILE_A,
    PROFILE_B,
    new_aggregate,
    seed_profiles,
    set_actor,
    uid,
)


async def test_without_actor_memory_tables_are_empty(
    migration_session: AsyncSession,
    runtime_session: AsyncSession,
) -> None:
    await seed_profiles(migration_session)
    await set_actor(migration_session, ACCOUNT_A)
    await SqlMemoryRepository(migration_session).add(new_aggregate(prompt_id=uid(400)))
    await migration_session.commit()
    await set_actor(runtime_session, None)
    assert await runtime_session.scalar(text("SELECT count(*) FROM memory.memory_prompts")) == 0


async def test_cross_user_cannot_read_enumerate_or_mutate_guessed_prompt(
    migration_session: AsyncSession,
    runtime_session: AsyncSession,
) -> None:
    await seed_profiles(migration_session)
    prompt_a = new_aggregate(prompt_id=uid(410), profile_id=PROFILE_A)
    prompt_b = new_aggregate(prompt_id=uid(420), profile_id=PROFILE_B, target_ref=uid(421))
    for actor, aggregate in ((ACCOUNT_A, prompt_a), (ACCOUNT_B, prompt_b)):
        await set_actor(migration_session, actor)
        await SqlMemoryRepository(migration_session).add(aggregate)
        await migration_session.commit()

    await set_actor(runtime_session, ACCOUNT_A)
    repository = SqlMemoryRepository(runtime_session)
    assert await repository.get(PROFILE_A, prompt_a.prompt.prompt_id) == prompt_a
    assert await repository.get(PROFILE_B, prompt_b.prompt.prompt_id) is None
    assert await runtime_session.scalar(text("SELECT count(*) FROM memory.memory_prompts")) == 1
    updated = await runtime_session.execute(
        text("UPDATE memory.memory_prompts SET status='suspended' WHERE prompt_id=:prompt"),
        {"prompt": prompt_b.prompt.prompt_id},
    )
    assert getattr(updated, "rowcount", 0) == 0


async def test_cross_user_cannot_insert_fact_for_foreign_prompt(
    migration_session: AsyncSession,
    runtime_session: AsyncSession,
) -> None:
    await seed_profiles(migration_session)
    foreign = new_aggregate(prompt_id=uid(430), profile_id=PROFILE_B)
    await set_actor(migration_session, ACCOUNT_B)
    await SqlMemoryRepository(migration_session).add(foreign)
    await migration_session.commit()

    await set_actor(runtime_session, ACCOUNT_A)
    assert await runtime_session.scalar(
        text(
            "SELECT EXISTS (SELECT 1 FROM memory.memory_prompts "
            "WHERE prompt_id=:prompt AND profile_id=:profile)"
        ),
        {"prompt": foreign.prompt.prompt_id, "profile": PROFILE_B},
    ) is False

