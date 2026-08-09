from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polyglot.platform.clock import FrozenClock


class RecordingPublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.event_ids: list[UUID] = []

    async def publish(self, event_id: UUID, destination: str, correlation_id: UUID) -> None:
        self.event_ids.append(event_id)
        if self.fail:
            raise RuntimeError("publisher unavailable")


def make_event() -> object:
    from polyglot.platform.persistence.records import DomainEvent

    now = datetime.now(UTC)
    return DomainEvent(
        event_id=uuid4(),
        event_type="example_dispatched",
        schema_version=1,
        aggregate_type="example",
        aggregate_id=uuid4(),
        aggregate_version=1,
        actor_type="system",
        actor_id=uuid4(),
        profile_id=None,
        occurred_at=now,
        recorded_at=now,
        correlation_id=uuid4(),
        causation_id=None,
        command_id=uuid4(),
        privacy_class="internal",
        policy_versions={},
        payload={"schema_version": 1},
    )


async def test_dispatcher_publishes_and_acknowledges_each_message_once(database_url: str) -> None:
    from polyglot.interfaces.tasks.dispatcher import LocalOutboxDispatcher
    from polyglot.platform.persistence.repositories import SqlEventOutboxRepository

    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    event = make_event()
    async with factory() as session:
        await SqlEventOutboxRepository(session).add(event, destinations=("local",))
        await session.commit()
    publisher = RecordingPublisher()
    dispatcher = LocalOutboxDispatcher(
        session_factory=factory,
        publisher=publisher,
        clock=FrozenClock(datetime.now(UTC)),
        worker_id="worker-1",
    )

    first_count = await dispatcher.run_once()
    second_count = await dispatcher.run_once()

    assert first_count == 1
    assert second_count == 0
    assert publisher.event_ids == [event.event_id]
    await engine.dispose()


async def test_dispatcher_does_not_retry_a_failed_publish_in_the_same_run(
    database_url: str,
) -> None:
    from polyglot.interfaces.tasks.dispatcher import LocalOutboxDispatcher
    from polyglot.platform.persistence.repositories import SqlEventOutboxRepository

    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    event = make_event()
    async with factory() as session:
        await SqlEventOutboxRepository(session).add(event, destinations=("local",))
        await session.commit()
    publisher = RecordingPublisher(fail=True)
    dispatcher = LocalOutboxDispatcher(
        session_factory=factory,
        publisher=publisher,
        clock=FrozenClock(datetime.now(UTC)),
        worker_id="worker-1",
    )

    published_count = await dispatcher.run_once()

    assert published_count == 0
    assert publisher.event_ids == [event.event_id]
    await engine.dispose()
