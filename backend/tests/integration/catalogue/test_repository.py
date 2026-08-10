from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.modules.catalogue.core.persistence import SqlCatalogueRepository
from polyglot.platform.errors import DomainError, ErrorCode

from .conftest import IDS, seed_catalogue


async def test_repository_lists_active_pack_and_deterministic_paginated_targets(
    migration_session: AsyncSession,
    session: AsyncSession,
) -> None:
    await seed_catalogue(migration_session)
    repository = SqlCatalogueRepository(session)

    packs = await repository.list_language_packs(limit=10, cursor=None)
    first = await repository.list_targets(pack_code="it-IT__fr-FR", limit=2, cursor=None)
    second = await repository.list_targets(
        pack_code="it-IT__fr-FR",
        limit=2,
        cursor=first.next_cursor,
    )

    assert [(item.pack_code, item.target_language_tag) for item in packs.items] == [
        ("it-IT__fr-FR", "it-IT")
    ]
    assert [item.skill_code for item in first.items] == ["IT-GRAM-002", "IT-GRAM-004"]
    assert first.next_cursor is not None
    assert [item.skill_code for item in second.items] == ["IT-PRAG-001"]
    assert second.next_cursor is None
    target = first.items[1]
    assert target.skill_revision_id == IDS["skill_revision_c"]
    assert target.required_prerequisite_codes == ("IT-GRAM-002",)


async def test_lexicon_search_preserves_diacritics_analyses_senses_and_multiwords(
    migration_session: AsyncSession,
    session: AsyncSession,
) -> None:
    await seed_catalogue(migration_session)
    repository = SqlCatalogueRepository(session)

    unaccented = await repository.search_lexicon(
        query="puo", language_tag="it-IT", limit=10, cursor=None
    )
    accented = await repository.search_lexicon(
        query="può", language_tag="it-IT", limit=10, cursor=None
    )
    polysemous = await repository.search_lexicon(
        query="piano", language_tag="it-IT", limit=10, cursor=None
    )
    multiword = await repository.search_lexicon(
        query="per favore", language_tag="it-IT", limit=10, cursor=None
    )

    assert [item.surface for item in unaccented.items] == ["puo"]
    assert unaccented.items[0].analysis.morphological_features == {
        "accepted_reference": False
    }
    assert [item.surface for item in accented.items] == ["può"]
    assert accented.items[0].analysis.form_analysis_id != unaccented.items[0].analysis.form_analysis_id
    assert [sense.sense_code for sense in polysemous.items[0].senses] == ["floor", "slowly"]
    assert multiword.items[0].analysis.unit_type == "multiword_expression"


async def test_repository_rejects_tampered_cursor(
    session: AsyncSession,
) -> None:
    repository = SqlCatalogueRepository(session)

    try:
        await repository.list_language_packs(limit=10, cursor="not-a-cursor")
    except DomainError as error:
        assert error.code is ErrorCode.CURSOR_INVALID
    else:
        raise AssertionError("tampered cursor was accepted")
