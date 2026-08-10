import asyncio
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.modules.lexicon.memory.application import CreateMemoryPrompt
from polyglot.modules.lexicon.memory.persistence import SqlMemoryService
from polyglot.modules.lexicon.memory.policy import SchedulerPolicy
from polyglot.modules.lexicon.memory.providers.fsrs_v6 import FsrsV6Scheduler
from polyglot.platform.errors import DomainError, ErrorCode

from .conftest import ACCOUNT_A, NOW, PROFILE_A, uid


def create_command(prompt_id: UUID | None = None) -> CreateMemoryPrompt:
    prompt_id = prompt_id or uid(300)
    return CreateMemoryPrompt(
        prompt_id=prompt_id,
        profile_id=PROFILE_A,
        target_ref=uid(301),
        target_revision_id=uid(302),
        direction="target_to_support",
        modality="written",
        operation="recall",
        protocol_id="certified-recall-v1",
        protocol_revision=1,
        rating_semantics_id="polyglot-recall-v1",
        scheduler_policy_id=uid(303),
        created_at=NOW,
    )


async def counts(session: AsyncSession, prompt_id) -> tuple[int, int, int, int]:
    await session.execute(
        text("SELECT set_config('app.user_id', :account_id, false)"),
        {"account_id": str(ACCOUNT_A)},
    )
    return tuple(
        int(value)
        for value in (
            await session.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM memory.memory_prompts WHERE prompt_id=:prompt),"
                    "(SELECT count(*) FROM memory.memory_command_receipts "
                    "WHERE result_prompt_id=:prompt),"
                    "(SELECT count(*) FROM platform.domain_events WHERE aggregate_id=:prompt),"
                    "(SELECT count(*) FROM platform.outbox_messages outbox "
                    "JOIN platform.domain_events "
                    "event ON event.event_id=outbox.event_id WHERE event.aggregate_id=:prompt)"
                ),
                {"prompt": prompt_id},
            )
        ).one()
    )


async def test_same_create_command_replayed_x100_has_one_atomic_effect(
    runtime_factory,
    migration_session: AsyncSession,
) -> None:
    service = SqlMemoryService(runtime_factory, FsrsV6Scheduler())
    command = create_command()
    policy = SchedulerPolicy.default()
    results = [
        await service.create(ACCOUNT_A, command, policy, idempotency_key="create-x100")
        for _ in range(100)
    ]
    assert all(result == results[0] for result in results)
    assert await counts(migration_session, command.prompt_id) == (1, 1, 1, 1)


async def test_same_key_with_divergent_body_is_idempotency_conflict(runtime_factory) -> None:
    service = SqlMemoryService(runtime_factory, FsrsV6Scheduler())
    policy = SchedulerPolicy.default()
    await service.create(ACCOUNT_A, create_command(uid(310)), policy, idempotency_key="conflict")
    with pytest.raises(DomainError) as error:
        await service.create(
            ACCOUNT_A,
            create_command(uid(311)),
            policy,
            idempotency_key="conflict",
        )
    assert error.value.code is ErrorCode.IDEMPOTENCY_CONFLICT


async def test_two_reviews_on_same_version_yield_one_success_and_one_conflict(
    runtime_factory,
    review_command,
) -> None:
    service = SqlMemoryService(runtime_factory, FsrsV6Scheduler())
    policy = SchedulerPolicy.default()
    prompt = await service.create(
        ACCOUNT_A,
        create_command(uid(320)),
        policy,
        idempotency_key="concurrent-create",
    )

    async def invoke(index: int):
        try:
            return await service.submit_review(
                ACCOUNT_A,
                prompt.prompt.prompt_id,
                review_command(
                    uid(321 + index),
                    opportunity_id=uid(331 + index),
                    target_revision_id=uid(302),
                ),
                policy,
                expected_version=prompt.prompt.version,
                idempotency_key=f"concurrent-review-{index}",
            )
        except DomainError as error:
            return error.code

    outcomes = await asyncio.gather(invoke(0), invoke(1))
    assert sum(not isinstance(outcome, ErrorCode) for outcome in outcomes) == 1
    assert ErrorCode.VERSION_CONFLICT in outcomes


async def test_uncertified_review_is_idempotent_without_learning_event(
    runtime_factory,
    migration_session: AsyncSession,
    review_command,
) -> None:
    service = SqlMemoryService(runtime_factory, FsrsV6Scheduler())
    policy = SchedulerPolicy.default()
    prompt = await service.create(
        ACCOUNT_A,
        create_command(uid(335)),
        policy,
        idempotency_key="uncertified-create",
    )

    unchanged = await service.submit_review(
        ACCOUNT_A,
        prompt.prompt.prompt_id,
        review_command(uid(336)),
        policy,
        expected_version=prompt.prompt.version,
        idempotency_key="uncertified-review",
    )
    replay = await service.submit_review(
        ACCOUNT_A,
        prompt.prompt.prompt_id,
        review_command(uid(336)),
        policy,
        expected_version=prompt.prompt.version,
        idempotency_key="uncertified-review",
    )

    assert unchanged == prompt
    assert replay == prompt
    assert await counts(migration_session, prompt.prompt.prompt_id) == (1, 2, 1, 1)


async def test_failure_before_commit_rolls_back_fact_projection_receipt_event_and_outbox(
    runtime_factory,
    migration_session: AsyncSession,
) -> None:
    async def fail(stage: str) -> None:
        if stage == "before_commit":
            raise RuntimeError("simulated crash before commit")

    command = create_command(uid(340))
    service = SqlMemoryService(
        runtime_factory,
        FsrsV6Scheduler(),
        transaction_hook=fail,
    )
    with pytest.raises(RuntimeError, match="before commit"):
        await service.create(
            ACCOUNT_A,
            command,
            SchedulerPolicy.default(),
            idempotency_key="crash-before",
        )
    assert await counts(migration_session, command.prompt_id) == (0, 0, 0, 0)


async def test_failure_after_commit_replays_committed_result_without_second_effect(
    runtime_factory,
    migration_session: AsyncSession,
) -> None:
    raised = False

    async def fail_once(stage: str) -> None:
        nonlocal raised
        if stage == "after_commit" and not raised:
            raised = True
            raise RuntimeError("simulated lost response")

    command = create_command(uid(350))
    service = SqlMemoryService(
        runtime_factory,
        FsrsV6Scheduler(),
        transaction_hook=fail_once,
    )
    with pytest.raises(RuntimeError, match="lost response"):
        await service.create(
            ACCOUNT_A,
            command,
            SchedulerPolicy.default(),
            idempotency_key="crash-after",
        )
    replay = await service.create(
        ACCOUNT_A,
        command,
        SchedulerPolicy.default(),
        idempotency_key="crash-after",
    )
    assert replay.prompt.prompt_id == command.prompt_id
    assert await counts(migration_session, command.prompt_id) == (1, 1, 1, 1)
