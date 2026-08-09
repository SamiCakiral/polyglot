from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
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
        result_ref=None,
        result_payload=None,
        status="started",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    store = SqlCommandReceiptStore(session)

    first = await store.reserve(receipt)
    await session.commit()
    result_ref = uuid4()
    completed = await store.complete(
        command_id=receipt.command_id,
        status="succeeded",
        result_ref=result_ref,
        result_payload={"resource_id": str(result_ref), "version": 1},
    )
    await session.commit()
    replays = [await store.reserve(receipt) for _ in range(100)]

    assert first.created is True
    assert all(not replay.created for replay in replays)
    assert {replay.receipt.command_id for replay in replays} == {receipt.command_id}
    assert completed.status == "succeeded"
    assert {replay.receipt.result_ref for replay in replays} == {result_ref}
    assert {replay.receipt.status for replay in replays} == {"succeeded"}
    assert all(replay.receipt.result_payload == completed.result_payload for replay in replays)


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
        result_payload=None,
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


@pytest.mark.parametrize(
    ("changed_field", "changed_value"),
    [("aggregate_type", "other"), ("aggregate_id", uuid4()), ("expected_version", 7)],
)
async def test_same_scoped_key_rejects_a_changed_target_or_precondition(
    session: AsyncSession,
    changed_field: str,
    changed_value: object,
) -> None:
    from polyglot.platform.persistence.records import CommandReceipt
    from polyglot.platform.persistence.repositories import SqlCommandReceiptStore

    baseline = CommandReceipt(
        command_id=uuid4(),
        command_type="ExampleCommand",
        actor_id=uuid4(),
        aggregate_type="example",
        aggregate_id=uuid4(),
        idempotency_key="target-conflict",
        request_fingerprint="d" * 64,
        expected_version=1,
        received_at=datetime.now(UTC),
        result_ref=None,
        result_payload=None,
        status="started",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    store = SqlCommandReceiptStore(session)
    await store.reserve(baseline)
    await session.commit()

    with pytest.raises(DomainError) as captured:
        await store.reserve(
            replace(baseline, command_id=uuid4(), **{changed_field: changed_value})
        )

    assert captured.value.code is ErrorCode.IDEMPOTENCY_CONFLICT


async def test_rejected_command_replays_the_same_bounded_result(session: AsyncSession) -> None:
    from polyglot.platform.persistence.records import CommandReceipt
    from polyglot.platform.persistence.repositories import SqlCommandReceiptStore

    receipt = CommandReceipt(
        command_id=uuid4(),
        command_type="ExampleCommand",
        actor_id=uuid4(),
        aggregate_type="example",
        aggregate_id=uuid4(),
        idempotency_key="stable-rejection",
        request_fingerprint="e" * 64,
        expected_version=None,
        received_at=datetime.now(UTC),
        result_ref=None,
        result_payload=None,
        status="started",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    store = SqlCommandReceiptStore(session)
    await store.reserve(receipt)
    await session.commit()
    await store.complete(
        command_id=receipt.command_id,
        status="rejected",
        result_ref=None,
        result_payload={"code": "validation_failed", "message_key": "errors.validation_failed"},
    )
    await session.commit()

    replay = await store.reserve(receipt)

    assert replay.receipt.status == "rejected"
    assert replay.receipt.result_payload == {
        "code": "validation_failed",
        "message_key": "errors.validation_failed",
    }


@pytest.mark.parametrize(
    ("status", "result_ref", "result_payload"),
    [
        ("succeeded", uuid4(), {"resource_id": str(uuid4()), "version": 1}),
        (
            "succeeded",
            uuid4(),
            {"resource_id": str(uuid4()), "version": 1, "response": "private"},
        ),
        ("rejected", None, {"code": "validation_failed", "message_key": "x" * 2_000}),
        (
            "failed",
            None,
            {
                "code": "internal_error",
                "message_key": "errors.internal_error",
                "token": "private",
            },
        ),
        (
            "rejected",
            None,
            {"code": "validation_failed", "message_key": "errors.not_found"},
        ),
    ],
)
async def test_command_receipt_rejects_unbounded_or_open_replay_payloads(
    session: AsyncSession,
    status: str,
    result_ref: object | None,
    result_payload: dict[str, object],
) -> None:
    from polyglot.platform.persistence.models import command_receipts
    from polyglot.platform.persistence.records import CommandReceipt
    from polyglot.platform.persistence.repositories import SqlCommandReceiptStore

    receipt = CommandReceipt(
        command_id=uuid4(),
        command_type="ExampleCommand",
        actor_id=uuid4(),
        aggregate_type="example",
        aggregate_id=uuid4(),
        idempotency_key=f"invalid-replay-{uuid4()}",
        request_fingerprint="f" * 64,
        expected_version=None,
        received_at=datetime.now(UTC),
        result_ref=None,
        result_payload=None,
        status="started",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    store = SqlCommandReceiptStore(session)
    await store.reserve(receipt)
    await session.flush()

    with pytest.raises(DomainError) as captured:
        await store.complete(
            command_id=receipt.command_id,
            status=status,
            result_ref=result_ref,
            result_payload=result_payload,
        )

    assert captured.value.code is ErrorCode.VALIDATION_FAILED
    stored = (
        await session.execute(
            select(command_receipts).where(
                command_receipts.c.command_id == receipt.command_id
            )
        )
    ).mappings().one()
    assert stored["status"] == "started"
    assert stored["result_ref"] is None
    assert stored["result_payload"] is None


@pytest.mark.parametrize(
    ("status", "result_ref", "result_payload"),
    [
        ("succeeded", uuid4(), {"resource_id": str(uuid4()), "version": 1}),
        ("started", uuid4(), None),
        ("started", None, {"code": "validation_failed"}),
    ],
)
def test_command_receipt_domain_accepts_only_empty_started_reservations(
    status: str,
    result_ref: object | None,
    result_payload: dict[str, object] | None,
) -> None:
    from polyglot.platform.persistence.records import CommandReceipt

    with pytest.raises(DomainError) as captured:
        CommandReceipt(
            command_id=uuid4(),
            command_type="ExampleCommand",
            actor_id=uuid4(),
            aggregate_type="example",
            aggregate_id=uuid4(),
            idempotency_key="invalid-domain-reservation",
            request_fingerprint="1" * 64,
            expected_version=None,
            received_at=datetime.now(UTC),
            result_ref=result_ref,
            result_payload=result_payload,
            status=status,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )

    assert captured.value.code is ErrorCode.VALIDATION_FAILED


async def test_command_receipt_store_rejects_a_forged_terminal_reservation(
    session: AsyncSession,
) -> None:
    from polyglot.platform.persistence.models import command_receipts
    from polyglot.platform.persistence.records import CommandReceipt
    from polyglot.platform.persistence.repositories import SqlCommandReceiptStore

    receipt = CommandReceipt(
        command_id=uuid4(),
        command_type="ExampleCommand",
        actor_id=uuid4(),
        aggregate_type="example",
        aggregate_id=uuid4(),
        idempotency_key="forged-terminal-reservation",
        request_fingerprint="2" * 64,
        expected_version=None,
        received_at=datetime.now(UTC),
        result_ref=None,
        result_payload=None,
        status="started",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    object.__setattr__(receipt, "status", "failed")
    object.__setattr__(
        receipt,
        "result_payload",
        {"code": "internal_error", "message_key": "errors.internal_error"},
    )

    with pytest.raises(DomainError) as captured:
        await SqlCommandReceiptStore(session).reserve(receipt)

    assert captured.value.code is ErrorCode.VALIDATION_FAILED
    assert await session.scalar(select(func.count()).select_from(command_receipts)) == 0


@pytest.mark.parametrize(
    "malformation",
    ["success_null", "rejection_null", "unknown_code", "message_mismatch", "decimal_version"],
)
async def test_command_receipt_sql_rejects_open_or_null_terminal_shapes(
    session: AsyncSession,
    malformation: str,
) -> None:
    from polyglot.platform.persistence.models import command_receipts

    result_ref = uuid4()
    status = "rejected"
    payload: dict[str, object] | None = {
        "code": "validation_failed",
        "message_key": "errors.validation_failed",
    }
    if malformation == "success_null":
        status, payload = "succeeded", None
    elif malformation == "rejection_null":
        payload = None
    elif malformation == "unknown_code":
        payload = {"code": "invented_error", "message_key": "errors.invented_error"}
    elif malformation == "message_mismatch":
        payload = {"code": "validation_failed", "message_key": "errors.not_found"}
    else:
        status = "succeeded"
        payload = {"resource_id": str(result_ref), "version": 1.5}

    with pytest.raises(DBAPIError):
        await session.execute(
            command_receipts.insert().values(
                command_id=uuid4(),
                command_type="ExampleCommand",
                actor_id=uuid4(),
                aggregate_type="example",
                aggregate_id=uuid4(),
                idempotency_key=f"invalid-sql-{malformation}",
                request_fingerprint="3" * 64,
                expected_version=None,
                received_at=datetime.now(UTC),
                result_ref=result_ref if status == "succeeded" else None,
                result_payload=payload,
                status=status,
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        await session.commit()
    await session.rollback()
