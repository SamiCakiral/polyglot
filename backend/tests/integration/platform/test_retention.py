from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.platform.ids import Uuid7Generator


def new_id() -> object:
    return Uuid7Generator().new()


def private_account_event(subject_id: object, *, expires_at: datetime) -> object:
    from polyglot.platform.persistence.records import DomainEvent

    now = datetime.now(UTC)
    return DomainEvent(
        event_id=new_id(),
        event_type="account_registered",
        schema_version=1,
        aggregate_type="account",
        aggregate_id=subject_id,
        aggregate_version=1,
        actor_type="system",
        actor_id=new_id(),
        profile_id=None,
        occurred_at=now,
        recorded_at=now,
        correlation_id=new_id(),
        causation_id=None,
        command_id=new_id(),
        privacy_class="personal",
        policy_versions={"retention": "v1"},
        payload={"account_id": str(subject_id)},
        expires_at=expires_at,
        subject_type="account",
        subject_id=subject_id,
    )


async def insert_deletion_request(
    session: AsyncSession,
    *,
    deletion_request_id: object,
    subject_id: object,
    status: str = "confirmed",
) -> object:
    from polyglot.platform.persistence.models import deletion_requests

    now = datetime.now(UTC)
    policy_revision_id = new_id()
    await session.execute(
        deletion_requests.insert().values(
            deletion_request_id=deletion_request_id,
            subject_type="account",
            subject_id=subject_id,
            requested_by_account_id=new_id(),
            status=status,
            requested_at=now,
            confirmed_at=now if status in {"confirmed", "purging"} else None,
            purge_due_at=now,
            completed_at=None,
            policy_revision_id=policy_revision_id,
        )
    )
    return policy_revision_id


async def test_controlled_retention_purges_only_expired_append_only_rows_and_audits(
    session: AsyncSession,
) -> None:
    from polyglot.platform.persistence.models import domain_events, security_audit_entries
    from polyglot.platform.persistence.records import DomainEvent
    from polyglot.platform.persistence.repositories import (
        SqlEventOutboxRepository,
        SqlRetentionStore,
    )

    now = datetime.now(UTC)
    expired_event_subject_id = new_id()
    expired_event = DomainEvent(
        event_id=new_id(),
        event_type="account_registered",
        schema_version=1,
        aggregate_type="account",
        aggregate_id=expired_event_subject_id,
        aggregate_version=1,
        actor_type="system",
        actor_id=new_id(),
        profile_id=None,
        occurred_at=now,
        recorded_at=now,
        correlation_id=new_id(),
        causation_id=None,
        command_id=new_id(),
        privacy_class="personal",
        policy_versions={"retention": "v1"},
        payload={"account_id": str(expired_event_subject_id)},
        expires_at=now - timedelta(seconds=1),
        subject_type="account",
        subject_id=expired_event_subject_id,
    )
    await SqlEventOutboxRepository(session).add(expired_event, destinations=("local",))
    await session.commit()

    with pytest.raises(DBAPIError):
        await session.execute(
            domain_events.delete().where(domain_events.c.event_id == expired_event.event_id)
        )
        await session.commit()
    await session.rollback()

    await session.execute(text("SET LOCAL ROLE polyglot_retention"))
    result = await SqlRetentionStore(session).purge_expired(
        cutoff=now,
        audit_id=new_id(),
        actor_pseudonym="retention-worker",
        reason_code="retention_expired",
        request_id=new_id(),
        correlation_id=new_id(),
    )
    await session.commit()

    assert result.domain_event_count == 1
    assert result.security_audit_count == 0
    assert await session.scalar(
        select(func.count()).select_from(domain_events).where(
            domain_events.c.event_id == expired_event.event_id
        )
    ) == 0
    audit = (
        await session.execute(
            select(security_audit_entries).where(
                security_audit_entries.c.audit_id == result.audit_id
            )
        )
    ).mappings().one()
    assert audit["action_code"] == "retention.purge"
    assert audit["reason_code"] == "retention_expired"


async def test_subject_purge_removes_only_authorized_private_events_and_audits(
    session: AsyncSession,
) -> None:
    from polyglot.platform.persistence.models import (
        deletion_requests,
        deletion_tombstones,
        domain_events,
        security_audit_entries,
    )
    from polyglot.platform.persistence.repositories import (
        SqlEventOutboxRepository,
        SqlRetentionStore,
    )

    target_subject_id = new_id()
    other_subject_id = new_id()
    deletion_request_id = new_id()
    tombstone_id = new_id()
    request_id = new_id()
    subject_fingerprint = "a" * 64
    policy_revision_id = await insert_deletion_request(
        session,
        deletion_request_id=deletion_request_id,
        subject_id=target_subject_id,
    )
    expires_at = datetime.now(UTC) + timedelta(days=30)
    target_event = private_account_event(target_subject_id, expires_at=expires_at)
    other_event = private_account_event(other_subject_id, expires_at=expires_at)
    repository = SqlEventOutboxRepository(session)
    await repository.add(target_event, destinations=("local",))
    await repository.add(other_event, destinations=("local",))
    await session.commit()

    with pytest.raises(DBAPIError):
        await session.execute(
            domain_events.delete().where(domain_events.c.event_id == target_event.event_id)
        )
        await session.commit()
    await session.rollback()

    await session.execute(text("SET LOCAL ROLE polyglot_retention"))
    result = await SqlRetentionStore(session).purge_subject_private_events(
        deletion_request_id=deletion_request_id,
        subject_type="account",
        subject_id=target_subject_id,
        subject_fingerprint=subject_fingerprint,
        tombstone_id=tombstone_id,
        audit_id=new_id(),
        request_id=request_id,
        correlation_id=new_id(),
    )
    await session.commit()

    remaining_ids = set(
        (
            await session.execute(
                select(domain_events.c.event_id).where(
                    domain_events.c.event_id.in_(
                        (target_event.event_id, other_event.event_id)
                    )
                )
            )
        ).scalars()
    )
    assert result.domain_event_count == 1
    assert remaining_ids == {other_event.event_id}
    audit = (
        await session.execute(
            select(security_audit_entries).where(
                security_audit_entries.c.audit_id == result.audit_id
            )
        )
    ).mappings().one()
    assert audit["action_code"] == "privacy.subject_purge"
    assert audit["resource_type"] == "deletion_request"
    assert audit["resource_id"] == deletion_request_id
    assert audit["request_id"] == request_id
    assert audit["reason_code"] == "confirmed_subject_deletion"
    deletion = (
        await session.execute(
            select(deletion_requests).where(
                deletion_requests.c.deletion_request_id == deletion_request_id
            )
        )
    ).mappings().one()
    assert deletion["status"] == "completed"
    assert deletion["completed_at"] is not None
    tombstone = (
        await session.execute(
            select(deletion_tombstones).where(
                deletion_tombstones.c.subject_type == "account",
                deletion_tombstones.c.subject_fingerprint == subject_fingerprint,
            )
        )
    ).mappings().one()
    assert tombstone["tombstone_id"] == tombstone_id
    assert tombstone["policy_revision_id"] == policy_revision_id
    assert set(tombstone["purged_scopes"]) == {"domain_events", "outbox_messages"}


@pytest.mark.parametrize("request_case", ["absent", "unconfirmed", "mismatched"])
async def test_subject_purge_rejects_unauthorized_deletion_requests(
    session: AsyncSession,
    request_case: str,
) -> None:
    from polyglot.platform.persistence.models import deletion_tombstones, domain_events
    from polyglot.platform.persistence.repositories import (
        SqlEventOutboxRepository,
        SqlRetentionStore,
    )

    subject_id = new_id()
    deletion_request_id = new_id()
    event = private_account_event(
        subject_id,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    await SqlEventOutboxRepository(session).add(event, destinations=("local",))
    if request_case != "absent":
        await insert_deletion_request(
            session,
            deletion_request_id=deletion_request_id,
            subject_id=new_id() if request_case == "mismatched" else subject_id,
            status="requested" if request_case == "unconfirmed" else "confirmed",
        )
    await session.commit()

    await session.execute(text("SET LOCAL ROLE polyglot_retention"))
    with pytest.raises(DBAPIError):
        await SqlRetentionStore(session).purge_subject_private_events(
            deletion_request_id=deletion_request_id,
            subject_type="account",
            subject_id=subject_id,
            subject_fingerprint="b" * 64,
            tombstone_id=new_id(),
            audit_id=new_id(),
            request_id=new_id(),
            correlation_id=new_id(),
        )
    await session.rollback()

    assert await session.scalar(
        select(func.count()).select_from(domain_events).where(
            domain_events.c.event_id == event.event_id
        )
    ) == 1
    assert await session.scalar(select(func.count()).select_from(deletion_tombstones)) == 0
