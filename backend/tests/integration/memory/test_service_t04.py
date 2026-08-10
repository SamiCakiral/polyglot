import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.modules.lexicon.memory.application import (
    ArchiveMemoryPrompt,
    CreateMemoryPrompt,
    DeleteMemoryPrompt,
    ResetMemoryPrompt,
    RestoreMemoryPrompt,
    ResumeMemoryPrompt,
    SuspendMemoryPrompt,
)
from polyglot.modules.lexicon.memory.domain import PromptStatus
from polyglot.modules.lexicon.memory.persistence import SqlMemoryRepository, SqlMemoryService
from polyglot.modules.lexicon.memory.policy import SchedulerPolicy
from polyglot.modules.lexicon.memory.providers.fsrs_v6 import FsrsV6Scheduler
from polyglot.platform.clock import FrozenClock
from polyglot.platform.errors import DomainError, ErrorCode

from .conftest import ACCOUNT_A, NOW, PROFILE_A, PROFILE_B, set_actor, uid


async def target_revision_available(_session, _revision_id: UUID) -> bool:
    return True


def create_command(prompt_id: UUID, *, created_at=NOW) -> CreateMemoryPrompt:
    return CreateMemoryPrompt(
        prompt_id=prompt_id,
        profile_id=PROFILE_A,
        target_ref=uid(880),
        target_revision_id=uid(881),
        direction="target_to_support",
        modality="written",
        operation="recall",
        protocol_id="certified-recall-v1",
        protocol_revision=1,
        rating_semantics_id="polyglot-recall-v1",
        scheduler_policy_id=uid(882),
        created_at=created_at,
    )


async def test_all_product_transitions_are_persisted_and_idempotent(
    runtime_factory,
) -> None:
    service = SqlMemoryService(
        runtime_factory,
        FsrsV6Scheduler(),
        target_revision_checker=target_revision_available,
    )
    policy = SchedulerPolicy.default()
    aggregate = await service.create(
        ACCOUNT_A,
        create_command(uid(600)),
        policy,
        idempotency_key="transition-create",
    )
    transitions = (
        (SuspendMemoryPrompt(NOW + timedelta(hours=1)), PromptStatus.SUSPENDED),
        (ResumeMemoryPrompt(uid(601), NOW + timedelta(hours=2)), PromptStatus.ACTIVE),
        (
            ResetMemoryPrompt(uid(602), "integration reset", NOW + timedelta(hours=3)),
            PromptStatus.ACTIVE,
        ),
        (ArchiveMemoryPrompt(NOW + timedelta(hours=4)), PromptStatus.ARCHIVED),
        (
            RestoreMemoryPrompt(uid(603), NOW + timedelta(hours=5), True),
            PromptStatus.ACTIVE,
        ),
    )
    for index, (command, expected_status) in enumerate(transitions, start=1):
        aggregate = await service.transition(
            ACCOUNT_A,
            aggregate.prompt.prompt_id,
            command,
            policy,
            expected_version=aggregate.prompt.version,
            idempotency_key=f"transition-{index}",
        )
        replay = await service.transition(
            ACCOUNT_A,
            aggregate.prompt.prompt_id,
            command,
            policy,
            expected_version=aggregate.prompt.version - 1,
            idempotency_key=f"transition-{index}",
        )
        assert replay == aggregate
        assert aggregate.prompt.status is expected_status

    assert len(aggregate.resets) == 1
    assert len(aggregate.resumptions) == 2


async def test_create_rejects_profile_not_owned_by_actor(runtime_factory) -> None:
    service = SqlMemoryService(runtime_factory, FsrsV6Scheduler())
    with pytest.raises(DomainError) as error:
        await service.create(
            ACCOUNT_A,
            replace(create_command(uid(604)), profile_id=PROFILE_B),
            SchedulerPolicy.default(),
            idempotency_key="foreign-profile-create",
        )
    assert error.value.code is ErrorCode.NOT_FOUND


async def test_restore_uses_server_catalogue_availability(runtime_factory) -> None:
    service = SqlMemoryService(runtime_factory, FsrsV6Scheduler())
    policy = SchedulerPolicy.default()
    aggregate = await service.create(
        ACCOUNT_A,
        create_command(uid(606)),
        policy,
        idempotency_key="unavailable-restore-create",
    )
    archived = await service.transition(
        ACCOUNT_A,
        aggregate.prompt.prompt_id,
        ArchiveMemoryPrompt(NOW + timedelta(hours=1)),
        policy,
        expected_version=aggregate.prompt.version,
        idempotency_key="unavailable-restore-archive",
    )
    with pytest.raises(DomainError) as error:
        await service.transition(
            ACCOUNT_A,
            archived.prompt.prompt_id,
            RestoreMemoryPrompt(uid(607), NOW + timedelta(hours=2), True),
            policy,
            expected_version=archived.prompt.version,
            idempotency_key="unavailable-restore",
        )
    assert error.value.code is ErrorCode.TARGET_REVISION_UNAVAILABLE


async def test_concurrent_same_key_creation_has_one_effect(runtime_factory) -> None:
    service = SqlMemoryService(runtime_factory, FsrsV6Scheduler())
    command = create_command(uid(605))
    results = await asyncio.gather(
        *(
            service.create(
                ACCOUNT_A,
                command,
                SchedulerPolicy.default(),
                idempotency_key="concurrent-same-create",
            )
            for _ in range(20)
        )
    )
    assert all(result == results[0] for result in results)


async def test_delete_requires_recent_server_verified_reauthentication(
    runtime_factory,
    migration_session: AsyncSession,
) -> None:
    policy = SchedulerPolicy.default()
    now = NOW + timedelta(minutes=1)
    service = SqlMemoryService(
        runtime_factory,
        FsrsV6Scheduler(),
        clock=FrozenClock(now),
    )
    aggregate = await service.create(
        ACCOUNT_A,
        create_command(uid(610)),
        policy,
        idempotency_key="delete-create",
    )
    command = DeleteMemoryPrompt(now, reauthenticated=False)
    with pytest.raises(DomainError) as error:
        await service.transition(
            ACCOUNT_A,
            aggregate.prompt.prompt_id,
            command,
            policy,
            expected_version=aggregate.prompt.version,
            idempotency_key="delete-without-session",
        )
    assert error.value.code is ErrorCode.FORBIDDEN

    session_id = uid(611)
    await migration_session.execute(
        text(
            "INSERT INTO identity.auth_sessions "
            "(session_id,account_id,session_fingerprint,csrf_secret_hash,roles_snapshot,"
            "account_session_version,created_at,authenticated_at,last_seen_at,rotated_at,"
            "idle_expires_at,absolute_expires_at) VALUES "
            "(:session,:account,:fingerprint,:csrf,ARRAY['learner'],1,:at,:at,:at,:at,"
            ":idle,:absolute)"
        ),
        {
            "session": session_id,
            "account": ACCOUNT_A,
            "fingerprint": "a" * 64,
            "csrf": "b" * 64,
            "at": NOW,
            "idle": NOW + timedelta(minutes=30),
            "absolute": NOW + timedelta(days=7),
        },
    )
    await migration_session.commit()
    deleted = await service.transition(
        ACCOUNT_A,
        aggregate.prompt.prompt_id,
        command,
        policy,
        expected_version=aggregate.prompt.version,
        idempotency_key="delete-with-session",
        session_id=session_id,
    )
    assert deleted.prompt.status is PromptStatus.DELETED


async def test_merge_preserves_source_facts_and_marks_sources_superseded(
    runtime_factory,
    migration_session: AsyncSession,
    review_command,
) -> None:
    service = SqlMemoryService(runtime_factory, FsrsV6Scheduler())
    policy = SchedulerPolicy.default()
    first = await service.create(
        ACCOUNT_A,
        create_command(uid(620)),
        policy,
        idempotency_key="merge-first",
    )
    second = await service.create(
        ACCOUNT_A,
        create_command(uid(621)),
        policy,
        idempotency_key="merge-second",
    )
    first = await service.submit_review(
        ACCOUNT_A,
        first.prompt.prompt_id,
        review_command(uid(622), target_revision_id=uid(881)),
        policy,
        expected_version=first.prompt.version,
        idempotency_key="merge-review",
    )
    canonical = await service.merge(
        ACCOUNT_A,
        (first.prompt.prompt_id, second.prompt.prompt_id),
        {
            first.prompt.prompt_id: first.prompt.version,
            second.prompt.prompt_id: second.prompt.version,
        },
        uid(623),
        NOW + timedelta(days=1),
        policy,
        idempotency_key="merge-command",
    )
    assert len(canonical.reviews) == 1
    assert len(canonical.lineages) == 2

    await set_actor(migration_session, ACCOUNT_A)
    repository = SqlMemoryRepository(migration_session)
    loaded = await repository.get(PROFILE_A, canonical.prompt.prompt_id)
    source_statuses = []
    for prompt_id in (first.prompt.prompt_id, second.prompt.prompt_id):
        source = await repository.get(PROFILE_A, prompt_id)
        assert source is not None
        source_statuses.append(source.prompt.status)
    assert loaded == canonical
    assert source_statuses == [PromptStatus.SUPERSEDED, PromptStatus.SUPERSEDED]


async def test_merge_rejects_duplicate_source_identifier(runtime_factory) -> None:
    service = SqlMemoryService(runtime_factory, FsrsV6Scheduler())
    source = await service.create(
        ACCOUNT_A,
        create_command(uid(625)),
        SchedulerPolicy.default(),
        idempotency_key="duplicate-source-create",
    )
    with pytest.raises(DomainError) as error:
        await service.merge(
            ACCOUNT_A,
            (source.prompt.prompt_id, source.prompt.prompt_id),
            {source.prompt.prompt_id: source.prompt.version},
            uid(626),
            NOW + timedelta(days=1),
            SchedulerPolicy.default(),
            idempotency_key="duplicate-source-merge",
        )
    assert error.value.code is ErrorCode.VALIDATION_FAILED


async def test_due_query_is_stable_paginated_and_excludes_suspended(
    runtime_factory,
) -> None:
    service = SqlMemoryService(runtime_factory, FsrsV6Scheduler())
    policy = SchedulerPolicy.default()
    prompts = []
    for index in range(3):
        prompts.append(
            await service.create(
                ACCOUNT_A,
                create_command(uid(630 + index), created_at=NOW + timedelta(minutes=index)),
                policy,
                idempotency_key=f"due-create-{index}",
            )
        )
    await service.transition(
        ACCOUNT_A,
        prompts[1].prompt.prompt_id,
        SuspendMemoryPrompt(NOW + timedelta(hours=1)),
        policy,
        expected_version=prompts[1].prompt.version,
        idempotency_key="due-suspend",
    )

    cutoff = NOW + timedelta(days=1)
    first, cursor = await service.list_due(
        ACCOUNT_A,
        PROFILE_A,
        cutoff,
        limit=1,
        cursor=None,
    )
    second, final_cursor = await service.list_due(
        ACCOUNT_A,
        PROFILE_A,
        cutoff,
        limit=1,
        cursor=cursor,
    )
    replay, replay_cursor = await service.list_due(
        ACCOUNT_A,
        PROFILE_A,
        cutoff,
        limit=1,
        cursor=None,
    )

    assert cursor is not None
    assert final_cursor is None
    assert first == replay and cursor == replay_cursor
    assert {first[0].aggregate.prompt.prompt_id, second[0].aggregate.prompt.prompt_id} == {
        prompts[0].prompt.prompt_id,
        prompts[2].prompt.prompt_id,
    }

    with pytest.raises(DomainError) as error:
        await service.list_due(
            ACCOUNT_A,
            PROFILE_A,
            cutoff,
            limit=1,
            cursor="%%%not-base64%%%",
        )
    assert error.value.code is ErrorCode.CURSOR_INVALID
