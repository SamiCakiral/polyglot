from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.platform.errors import DomainError, ErrorCode


async def test_same_actor_command_key_and_fingerprint_replays_one_receipt(
    session: AsyncSession,
) -> None:
    from polyglot.platform.persistence.records import CommandReceipt
    from polyglot.platform.persistence.repositories import SqlCommandReceiptStore

    actor_id = uuid4()
    receipt = CommandReceipt(
        command_id=uuid4(),
        command_type="ExampleCommand",
        actor_id=actor_id,
        aggregate_type="example",
        aggregate_id=uuid4(),
        idempotency_key="same-key",
        request_fingerprint="a" * 64,
        expected_version=1,
        received_at=datetime.now(UTC),
        result_ref=uuid4(),
        status="succeeded",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    store = SqlCommandReceiptStore(session)

    first = await store.reserve(receipt)
    await session.commit()
    replays = [await store.reserve(receipt) for _ in range(100)]

    assert first.created is True
    assert all(not replay.created for replay in replays)
    assert {replay.receipt.command_id for replay in replays} == {receipt.command_id}


async def test_same_actor_command_key_with_another_body_is_a_conflict(
    session: AsyncSession,
) -> None:
    from polyglot.platform.persistence.records import CommandReceipt
    from polyglot.platform.persistence.repositories import SqlCommandReceiptStore

    actor_id = uuid4()
    baseline = CommandReceipt(
        command_id=uuid4(),
        command_type="ExampleCommand",
        actor_id=actor_id,
        aggregate_type="example",
        aggregate_id=uuid4(),
        idempotency_key="conflicting-key",
        request_fingerprint="b" * 64,
        expected_version=None,
        received_at=datetime.now(UTC),
        result_ref=None,
        status="started",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    store = SqlCommandReceiptStore(session)
    await store.reserve(baseline)
    await session.commit()
    conflicting = replace(
        baseline,
        command_id=uuid4(),
        request_fingerprint="c" * 64,
    )

    with pytest.raises(DomainError) as captured:
        await store.reserve(conflicting)

    assert captured.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
