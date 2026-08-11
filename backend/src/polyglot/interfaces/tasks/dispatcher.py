from datetime import timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.platform.clock import Clock
from polyglot.platform.persistence.repositories import SqlOutboxRepository


class EventPublisher(Protocol):
    async def publish(self, event_id: UUID, destination: str, correlation_id: UUID) -> None: ...


class LocalOutboxDispatcher:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        publisher: EventPublisher,
        clock: Clock,
        worker_id: str,
        lease_for: timedelta = timedelta(minutes=5),
        batch_size: int = 100,
        destination: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher
        self._clock = clock
        self._worker_id = worker_id
        self._lease_for = lease_for
        self._batch_size = batch_size
        self._destination = destination

    async def run_once(self) -> int:
        async with self._session_factory() as session:
            claims = await SqlOutboxRepository(session).claim(
                worker_id=self._worker_id,
                now=self._clock.now(),
                lease_for=self._lease_for,
                limit=self._batch_size,
                destination=self._destination,
            )
            await session.commit()

        published_count = 0
        for claim in claims:
            try:
                await self._publisher.publish(
                    claim.event_id,
                    claim.destination,
                    claim.correlation_id,
                )
            except Exception:
                async with self._session_factory() as session:
                    failed_at = self._clock.now()
                    await SqlOutboxRepository(session).mark_failed(
                        claim=claim,
                        failed_at=failed_at,
                        error_code="publisher_error",
                    )
                    await session.commit()
                continue
            async with self._session_factory() as session:
                acknowledged = await SqlOutboxRepository(session).mark_published(
                    claim=claim,
                    published_at=self._clock.now(),
                )
                await session.commit()
            if acknowledged:
                published_count += 1
        return published_count
