from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.ids import Uuid7Generator


def new_id() -> object:
    return Uuid7Generator().new()


def make_event() -> object:
    from polyglot.platform.persistence.records import DomainEvent

    now = datetime.now(UTC)
    return DomainEvent(
        event_id=new_id(),
        event_type="account_registered",
        schema_version=1,
        aggregate_type="example",
        aggregate_id=new_id(),
        aggregate_version=1,
        actor_type="system",
        actor_id=new_id(),
        profile_id=None,
        occurred_at=now,
        recorded_at=now,
        correlation_id=new_id(),
        causation_id=None,
        command_id=new_id(),
        privacy_class="internal",
        policy_versions={},
        payload={"schema_version": 1},
    )


async def test_event_and_outbox_are_rolled_back_together(session: AsyncSession) -> None:
    from polyglot.platform.persistence.models import domain_events, outbox_messages
    from polyglot.platform.persistence.repositories import SqlEventOutboxRepository

    event = make_event()
    repository = SqlEventOutboxRepository(session)
    await repository.add(event, destinations=("local",))
    await session.rollback()

    event_count = await session.scalar(
        select(func.count())
        .select_from(domain_events)
        .where(domain_events.c.event_id == event.event_id)
    )
    outbox_count = await session.scalar(
        select(func.count())
        .select_from(outbox_messages)
        .where(outbox_messages.c.event_id == event.event_id)
    )

    assert event_count == 0
    assert outbox_count == 0


async def test_event_and_outbox_commit_together(session: AsyncSession) -> None:
    from polyglot.platform.persistence.models import domain_events, outbox_messages
    from polyglot.platform.persistence.repositories import SqlEventOutboxRepository

    event = make_event()
    repository = SqlEventOutboxRepository(session)
    await repository.add(event, destinations=("local",))
    await session.commit()

    assert await session.scalar(
        select(func.count())
        .select_from(domain_events)
        .where(domain_events.c.event_id == event.event_id)
    ) == 1
    assert await session.scalar(
        select(func.count())
        .select_from(outbox_messages)
        .where(outbox_messages.c.event_id == event.event_id)
    ) == 1


async def test_inbox_deduplicates_consumer_and_event(session: AsyncSession) -> None:
    from polyglot.platform.persistence.records import InboxReceipt
    from polyglot.platform.persistence.repositories import SqlInboxRepository

    receipt = InboxReceipt(
        consumer_code="example_projection",
        event_id=uuid4(),
        processed_at=datetime.now(UTC),
        result_checksum="d" * 64,
    )
    repository = SqlInboxRepository(session)

    assert await repository.record(receipt) is True
    await session.commit()
    assert await repository.record(receipt) is False


async def test_inbox_rejects_a_divergent_duplicate_checksum(session: AsyncSession) -> None:
    from dataclasses import replace

    from polyglot.platform.persistence.records import InboxReceipt
    from polyglot.platform.persistence.repositories import SqlInboxRepository

    receipt = InboxReceipt(
        consumer_code="example_projection",
        event_id=uuid4(),
        processed_at=datetime.now(UTC),
        result_checksum="a" * 64,
    )
    repository = SqlInboxRepository(session)
    assert await repository.record(receipt)
    await session.commit()

    with pytest.raises(DomainError) as captured:
        await repository.record(replace(receipt, result_checksum="b" * 64))

    assert captured.value.code is ErrorCode.RESPONSE_CONFLICT


async def test_expired_outbox_lease_can_be_recovered(session: AsyncSession) -> None:
    from polyglot.platform.persistence.models import outbox_messages
    from polyglot.platform.persistence.repositories import SqlOutboxRepository

    event = make_event()
    from polyglot.platform.persistence.repositories import SqlEventOutboxRepository

    await SqlEventOutboxRepository(session).add(event, destinations=("local",))
    await session.flush()
    await session.execute(
        outbox_messages.update()
        .where(outbox_messages.c.event_id == event.event_id)
        .values(
            lease_owner="dead-worker",
            lease_token=uuid4(),
            lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    await session.commit()

    claimed = await SqlOutboxRepository(session).claim(
        worker_id="replacement-worker",
        now=datetime.now(UTC),
        lease_for=timedelta(minutes=5),
        limit=10,
    )

    assert [message.event_id for message in claimed] == [event.event_id]
    assert claimed[0].lease_owner == "replacement-worker"


async def test_stale_outbox_claim_cannot_ack_after_same_worker_reclaims(
    session: AsyncSession,
) -> None:
    from polyglot.platform.persistence.repositories import (
        SqlEventOutboxRepository,
        SqlOutboxRepository,
    )

    event = make_event()
    await SqlEventOutboxRepository(session).add(event, destinations=("local",))
    await session.commit()
    store = SqlOutboxRepository(session)
    claimed_at = datetime.now(UTC)
    first = (
        await store.claim(
            worker_id="worker-reused",
            now=claimed_at,
            lease_for=timedelta(minutes=5),
            limit=1,
        )
    )[0]
    await session.commit()
    replacement = (
        await store.claim(
            worker_id="worker-reused",
            now=claimed_at + timedelta(minutes=6),
            lease_for=timedelta(minutes=5),
            limit=1,
        )
    )[0]
    await session.commit()

    assert first.lease_token != replacement.lease_token
    stale_acknowledged = await store.mark_published(
        claim=first,
        published_at=claimed_at + timedelta(minutes=6),
    )
    assert not stale_acknowledged
    assert await store.mark_published(
        claim=replacement,
        published_at=claimed_at + timedelta(minutes=7),
    )


async def test_domain_events_are_append_only(session: AsyncSession) -> None:
    from polyglot.platform.persistence.models import domain_events
    from polyglot.platform.persistence.repositories import SqlEventOutboxRepository

    event = make_event()
    await SqlEventOutboxRepository(session).add(event, destinations=("local",))
    await session.commit()

    with pytest.raises(DBAPIError):
        await session.execute(
            domain_events.update()
            .where(domain_events.c.event_id == event.event_id)
            .values(event_type="changed")
        )
        await session.commit()
    await session.rollback()


async def test_job_attempts_are_append_only(session: AsyncSession) -> None:
    from polyglot.platform.persistence.models import job_attempts, jobs

    now = datetime.now(UTC)
    job_id = uuid4()
    attempt_id = uuid4()
    await session.execute(
        jobs.insert().values(
            job_id=job_id,
            job_type="example",
            requested_by_actor_id=uuid4(),
            profile_id=None,
            status="running",
            idempotency_key="job-attempt-append-only",
            request_fingerprint="e" * 64,
            correlation_id=uuid4(),
            payload_schema_version=1,
            requested_at=now,
            queued_at=now,
            started_at=now,
            finished_at=None,
            cancel_requested_at=None,
            retry_not_before_at=None,
            progress_completed=0,
            progress_total=1,
            result_ref=None,
            error_code=None,
            version=1,
        )
    )
    await session.execute(
        job_attempts.insert().values(
            job_attempt_id=attempt_id,
            job_id=job_id,
            attempt_no=1,
            status="succeeded",
            worker_id="worker-1",
            started_at=now,
            finished_at=now + timedelta(seconds=1),
            retry_not_before_at=None,
            provider_code=None,
            operation_code=None,
            error_code=None,
            retryable=False,
        )
    )
    await session.commit()

    with pytest.raises(DBAPIError):
        await session.execute(
            job_attempts.update()
            .where(job_attempts.c.job_attempt_id == attempt_id)
            .values(status="failed")
        )
        await session.commit()
    await session.rollback()
