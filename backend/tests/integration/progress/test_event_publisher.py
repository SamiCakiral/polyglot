from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.interfaces.tasks.progress import LocalLearningEventPublisher

from .conftest import ACCOUNT_A, NOW, uid


@dataclass
class RecordingConsumer:
    calls: list[tuple[UUID, UUID]] = field(default_factory=list)

    async def consume_event(self, *, actor_id: UUID, event_id: UUID) -> object:
        self.calls.append((actor_id, event_id))
        return object()


async def test_local_learning_publisher_routes_supported_progress_event(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    consumer = RecordingConsumer()
    event_id = uid(901)
    await migration_session.execute(
        text(
            "INSERT INTO platform.domain_events "
            "(event_id,event_type,schema_version,aggregate_type,aggregate_id,aggregate_version,"
            "actor_type,actor_id,occurred_at,recorded_at,correlation_id,command_id,privacy_class,"
            "policy_versions,payload) VALUES (:event,'exercise_attempt_corrected',1,'attempt',"
            ":aggregate,1,'account',:actor,:now,:now,:correlation,:command,'internal','{}','{}')"
        ),
        {
            "event": event_id,
            "aggregate": uid(902),
            "actor": ACCOUNT_A,
            "now": NOW,
            "correlation": uid(903),
            "command": uid(904),
        },
    )
    await migration_session.commit()

    publisher = LocalLearningEventPublisher(runtime_factory, consumer)
    await publisher.publish(event_id, "learning-events", uid(905))

    assert consumer.calls == [(ACCOUNT_A, event_id)]
