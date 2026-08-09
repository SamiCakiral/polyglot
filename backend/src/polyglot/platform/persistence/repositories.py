from dataclasses import asdict
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.persistence.models import (
    command_receipts,
    domain_events,
    inbox_receipts,
    outbox_messages,
)
from polyglot.platform.persistence.records import (
    CommandReceipt,
    CommandReservation,
    DomainEvent,
    InboxReceipt,
    OutboxClaim,
)


class SqlCommandReceiptStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(self, receipt: CommandReceipt) -> CommandReservation:
        statement = (
            postgresql_insert(command_receipts)
            .values(asdict(receipt))
            .on_conflict_do_nothing(
                index_elements=("actor_id", "command_type", "idempotency_key")
            )
            .returning(command_receipts.c.command_id)
        )
        inserted_id = await self._session.scalar(statement)
        if inserted_id is not None:
            return CommandReservation(receipt=receipt, created=True)

        existing = (
            await self._session.execute(
                select(command_receipts).where(
                    command_receipts.c.actor_id == receipt.actor_id,
                    command_receipts.c.command_type == receipt.command_type,
                    command_receipts.c.idempotency_key == receipt.idempotency_key,
                )
            )
        ).mappings().one()
        if existing["request_fingerprint"] != receipt.request_fingerprint:
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        stored = CommandReceipt(
            **{
                field: existing[field]
                for field in CommandReceipt.__dataclass_fields__
            }
        )
        return CommandReservation(receipt=stored, created=False)


class SqlEventOutboxRepository:
    def __init__(
        self,
        session: AsyncSession,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._session = session
        self._id_generator = id_generator or Uuid7Generator()

    async def add(self, event: DomainEvent, *, destinations: tuple[str, ...]) -> None:
        if len(destinations) != 1:
            raise ValueError("each domain event requires exactly one outbox destination")
        await self._session.execute(domain_events.insert().values(asdict(event)))
        await self._session.execute(
            outbox_messages.insert().values(
                outbox_id=self._id_generator.new(),
                event_id=event.event_id,
                destination=destinations[0],
                created_at=event.recorded_at,
                published_at=None,
                attempt_count=0,
                lease_owner=None,
                lease_expires_at=None,
                last_error_code=None,
            )
        )


class SqlInboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, receipt: InboxReceipt) -> bool:
        statement = (
            postgresql_insert(inbox_receipts)
            .values(asdict(receipt))
            .on_conflict_do_nothing(index_elements=("consumer_code", "event_id"))
            .returning(inbox_receipts.c.event_id)
        )
        return await self._session.scalar(statement) is not None


class SqlOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_for: timedelta,
        limit: int,
    ) -> list[OutboxClaim]:
        if limit < 1:
            return []
        available = (
            select(outbox_messages.c.outbox_id)
            .where(
                outbox_messages.c.published_at.is_(None),
                (outbox_messages.c.lease_expires_at.is_(None))
                | (outbox_messages.c.lease_expires_at <= now),
            )
            .order_by(outbox_messages.c.created_at, outbox_messages.c.outbox_id)
            .limit(limit)
            .with_for_update(skip_locked=True, of=outbox_messages)
        )
        identifiers = list((await self._session.execute(available)).scalars())
        if not identifiers:
            return []
        lease_expires_at = now + lease_for
        await self._session.execute(
            outbox_messages.update()
            .where(outbox_messages.c.outbox_id.in_(identifiers))
            .values(lease_owner=worker_id, lease_expires_at=lease_expires_at)
        )
        rows = (
            await self._session.execute(
                select(
                    outbox_messages.c.outbox_id,
                    outbox_messages.c.event_id,
                    outbox_messages.c.destination,
                    domain_events.c.correlation_id,
                    outbox_messages.c.created_at,
                    outbox_messages.c.attempt_count,
                )
                .join(domain_events, domain_events.c.event_id == outbox_messages.c.event_id)
                .where(outbox_messages.c.outbox_id.in_(identifiers))
                .order_by(outbox_messages.c.created_at, outbox_messages.c.outbox_id)
            )
        ).mappings()
        return [
            OutboxClaim(
                **row,
                lease_owner=worker_id,
                lease_expires_at=lease_expires_at,
            )
            for row in rows
        ]

    async def mark_published(
        self,
        *,
        outbox_id: UUID,
        worker_id: str,
        published_at: datetime,
    ) -> None:
        await self._session.execute(
            outbox_messages.update()
            .where(
                outbox_messages.c.outbox_id == outbox_id,
                outbox_messages.c.lease_owner == worker_id,
                outbox_messages.c.published_at.is_(None),
            )
            .values(
                published_at=published_at,
                attempt_count=outbox_messages.c.attempt_count + 1,
                lease_owner=None,
                lease_expires_at=None,
                last_error_code=None,
            )
        )

    async def mark_failed(
        self,
        *,
        outbox_id: UUID,
        worker_id: str,
        error_code: str,
    ) -> None:
        await self._session.execute(
            outbox_messages.update()
            .where(
                and_(
                    outbox_messages.c.outbox_id == outbox_id,
                    outbox_messages.c.lease_owner == worker_id,
                    outbox_messages.c.published_at.is_(None),
                )
            )
            .values(
                attempt_count=outbox_messages.c.attempt_count + 1,
                lease_owner=None,
                lease_expires_at=None,
                last_error_code=error_code,
            )
        )
