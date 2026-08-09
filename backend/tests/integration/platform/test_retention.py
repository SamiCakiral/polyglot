from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.platform.ids import Uuid7Generator


def new_id() -> object:
    return Uuid7Generator().new()


async def test_controlled_retention_purges_only_expired_append_only_rows_and_audits(
    session: AsyncSession,
) -> None:
    from polyglot.platform.persistence.models import domain_events, security_audit_entries
    from polyglot.platform.persistence.records import DomainEvent
    from polyglot.platform.persistence.repositories import SqlEventOutboxRepository, SqlRetentionStore

    now = datetime.now(UTC)
    expired_event = DomainEvent(
        event_id=new_id(),
        event_type="account_registered",
        schema_version=1,
        aggregate_type="account",
        aggregate_id=new_id(),
        aggregate_version=1,
        actor_type="system",
        actor_id=new_id(),
        profile_id=new_id(),
        occurred_at=now,
        recorded_at=now,
        correlation_id=new_id(),
        causation_id=None,
        command_id=new_id(),
        privacy_class="personal",
        policy_versions={"retention": "v1"},
        payload={"account_id": str(new_id())},
        expires_at=now - timedelta(seconds=1),
    )
    await SqlEventOutboxRepository(session).add(expired_event, destinations=("local",))
    await session.commit()

    with pytest.raises(DBAPIError):
        await session.execute(
            domain_events.delete().where(domain_events.c.event_id == expired_event.event_id)
        )
        await session.commit()
    await session.rollback()

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
