from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.catalogue.core.persistence import (
    CatalogueTarget,
    LanguagePackSummary,
    LexiconSearchItem,
    Page,
    SqlCatalogueRepository,
)


class CatalogueReader(Protocol):
    async def list_language_packs(
        self,
        *,
        limit: int,
        cursor: str | None,
    ) -> Page[LanguagePackSummary]: ...

    async def list_targets(
        self,
        *,
        pack_code: str,
        limit: int,
        cursor: str | None,
    ) -> Page[CatalogueTarget]: ...

    async def search_lexicon(
        self,
        *,
        query: str,
        language_tag: str,
        limit: int,
        cursor: str | None,
    ) -> Page[LexiconSearchItem]: ...


class CatalogueApplicationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_language_packs(
        self,
        *,
        limit: int,
        cursor: str | None,
    ) -> Page[LanguagePackSummary]:
        async with self._session_factory() as session:
            return await SqlCatalogueRepository(session).list_language_packs(
                limit=limit,
                cursor=cursor,
            )

    async def list_targets(
        self,
        *,
        pack_code: str,
        limit: int,
        cursor: str | None,
    ) -> Page[CatalogueTarget]:
        async with self._session_factory() as session:
            return await SqlCatalogueRepository(session).list_targets(
                pack_code=pack_code,
                limit=limit,
                cursor=cursor,
            )

    async def search_lexicon(
        self,
        *,
        query: str,
        language_tag: str,
        limit: int,
        cursor: str | None,
    ) -> Page[LexiconSearchItem]:
        async with self._session_factory() as session:
            return await SqlCatalogueRepository(session).search_lexicon(
                query=query,
                language_tag=language_tag,
                limit=limit,
                cursor=cursor,
            )
