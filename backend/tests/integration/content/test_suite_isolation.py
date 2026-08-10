from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.modules.catalogue.core.persistence import language_packs


async def test_content_suite_starts_without_catalogue_pack_state(
    migration_session: AsyncSession,
) -> None:
    pack_count = await migration_session.scalar(select(func.count()).select_from(language_packs))

    assert pack_count == 0
