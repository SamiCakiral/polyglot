from dataclasses import replace
from datetime import timedelta

import pytest

from polyglot.modules.practice.application import CreatePracticePreset, CreatePracticeStack
from polyglot.modules.practice.domain import (
    PracticeDirection,
    PracticeMode,
    PracticeStackKind,
    StackMember,
)
from polyglot.modules.practice.persistence import SqlPracticeService
from polyglot.platform.errors import DomainError

from .conftest import ACCOUNT_ID, NOW, PROFILE_ID


async def test_stack_preset_run_and_injection_are_frozen_and_replayable(
    seeded_practice,
) -> None:
    factory, pack_revision_id, senses = seeded_practice
    service = SqlPracticeService(factory)
    members = tuple(
        StackMember(
            sense_id=sense_id,
            sense_revision_id=revision_id,
            label=label,
            definition=definition,
            source_kind="selection",
            source_ref=f"sense:{sense_id}",
        )
        for sense_id, revision_id, label, definition in senses[:2]
    )
    create = CreatePracticeStack(
        name="Jour 1",
        stack_kind=PracticeStackKind.DAILY,
        language_pack_revision_id=pack_revision_id,
        pedagogical_day=NOW.date(),
        source_list_snapshot_id=None,
        source_refs=("module_day:1",),
        members=members,
        created_at=NOW,
    )

    stack = await service.create_stack(ACCOUNT_ID, PROFILE_ID, create, idempotency_key="stack-1")
    replay = await service.create_stack(ACCOUNT_ID, PROFILE_ID, create, idempotency_key="stack-1")
    assert replay.stack_id == stack.stack_id
    assert stack.members == members

    next_day = await service.create_stack(
        ACCOUNT_ID,
        PROFILE_ID,
        replace(
            create,
            name="Jour 2",
            pedagogical_day=NOW.date() + timedelta(days=1),
            source_refs=("module_day:2",),
            created_at=NOW + timedelta(days=1),
        ),
        idempotency_key="stack-2",
    )
    assert next_day.stack_id != stack.stack_id
    assert next_day.checksum == stack.checksum

    with pytest.raises(DomainError):
        await service.create_stack(
            ACCOUNT_ID,
            PROFILE_ID,
            replace(
                create,
                members=(
                    replace(
                        members[0],
                        sense_revision_id=members[1].sense_revision_id,
                    ),
                ),
            ),
            idempotency_key="stack-invalid-revision",
        )

    injection = await service.inject_stack(
        ACCOUNT_ID,
        stack.stack_id,
        requested_at=NOW + timedelta(minutes=1),
        idempotency_key="inject-1",
    )
    assert injection.status == "pending"

    preset = await service.create_preset(
        ACCOUNT_ID,
        PROFILE_ID,
        CreatePracticePreset(
            name="Pile du jour",
            stack_ids=(stack.stack_id,),
            direction=PracticeDirection.BIDIRECTIONAL,
            mode=PracticeMode.CARDS,
            settings={"shuffle": False},
            created_at=NOW + timedelta(minutes=2),
        ),
        idempotency_key="preset-1",
    )
    run = await service.start_run(
        ACCOUNT_ID,
        preset.preset_id,
        started_at=NOW + timedelta(minutes=3),
        idempotency_key="run-1",
    )
    assert run.current_item == members[0]
    assert run.member_count == 2

    run = await service.advance_run(
        ACCOUNT_ID,
        run.run_id,
        expected_version=run.version,
        advanced_at=NOW + timedelta(minutes=4),
        idempotency_key="advance-1",
    )
    assert run.current_item == members[1]
    run = await service.advance_run(
        ACCOUNT_ID,
        run.run_id,
        expected_version=run.version,
        advanced_at=NOW + timedelta(minutes=5),
        idempotency_key="advance-2",
    )
    assert run.status == "completed"
    assert run.current_item is None
