from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if self.session is None:
            return False
        if exc_type is not None:
            await self.session.rollback()
        await self.session.close()
        self.session = None
        return False

    async def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("unit of work is not active")
        await self.session.commit()

    async def rollback(self) -> None:
        if self.session is None:
            raise RuntimeError("unit of work is not active")
        await self.session.rollback()
