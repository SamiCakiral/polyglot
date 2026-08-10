from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.platform.errors import DomainError, ErrorCode

PROGRESS_EVENT_TYPES = frozenset(
    {
        "exercise_attempt_corrected",
        "attempt_not_evaluable",
    }
)


class ProgressEventConsumer(Protocol):
    async def consume_event(self, *, actor_id: UUID, event_id: UUID) -> object: ...


class LocalLearningEventPublisher:
    """Fan out local learning events to registered deterministic consumers."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        progress_consumer: ProgressEventConsumer,
    ) -> None:
        self._sessions = sessions
        self._progress = progress_consumer

    async def publish(self, event_id: UUID, destination: str, correlation_id: UUID) -> None:
        del correlation_id
        if destination != "learning-events":
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="unsupported event destination")
        async with self._sessions() as session:
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT event_type,actor_id FROM platform.domain_events "
                            "WHERE event_id=:event"
                        ),
                        {"event": event_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        if row["event_type"] in PROGRESS_EVENT_TYPES:
            await self._progress.consume_event(
                actor_id=UUID(str(row["actor_id"])),
                event_id=event_id,
            )
