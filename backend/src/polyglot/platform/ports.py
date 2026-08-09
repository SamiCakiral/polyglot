from types import TracebackType
from typing import Protocol, TypeVar
from uuid import UUID

EntityT = TypeVar("EntityT")


class Repository(Protocol[EntityT]):
    async def add(self, entity: EntityT) -> None: ...

    async def get(self, entity_id: UUID) -> EntityT | None: ...


class UnitOfWork(Protocol):
    async def __aenter__(self) -> "UnitOfWork": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...
