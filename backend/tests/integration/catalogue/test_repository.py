from uuid import UUID

import pytest
from sqlalchemy import text
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
    assert unaccented.items[0].analysis.morphological_features == {"accepted_reference": False}
    assert [item.surface for item in accented.items] == ["può"]
    assert (
        accented.items[0].analysis.form_analysis_id != unaccented.items[0].analysis.form_analysis_id
    )
    assert [sense.sense_code for sense in polysemous.items[0].senses] == ["floor", "slowly"]
    assert multiword.items[0].analysis.unit_type == "multiword_expression"


async def test_lexicon_search_applies_cursor_and_limit_in_sql(
    migration_session: AsyncSession,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await seed_catalogue(migration_session, publish_lexical=False)
    await migration_session.execute(
        text(
            "INSERT INTO catalogue.form_analyses "
            "(form_analysis_id, unit_revision_id, surface, morphological_features, "
            "pronunciation_refs, normalization_key) VALUES "
            "('019fe900-5000-7000-8024-000000000100', :unit, 'piano', "
            "'{\"alternate\": true}'::jsonb, ARRAY[]::uuid[], 'piano')"
        ),
        {"unit": IDS["unit_revision_piano"]},
    )
    await migration_session.execute(
        text(
            "INSERT INTO catalogue.form_realizations "
            "(realization_id, form_analysis_id, unit_revision_id, sense_revision_id) "
            "VALUES ('019fe900-5000-7000-8025-000000000100', "
            "'019fe900-5000-7000-8024-000000000100', :unit, :sense)"
        ),
        {
            "unit": IDS["unit_revision_piano"],
            "sense": IDS["sense_revision_piano_slow"],
        },
    )
    await migration_session.execute(
        text("UPDATE catalogue.lexical_unit_revisions SET status = 'published'")
    )
    await migration_session.execute(
        text("UPDATE catalogue.lexical_sense_revisions SET status = 'published'")
    )
    await migration_session.commit()
    repository = SqlCatalogueRepository(session)
    executed: list[tuple[str, object]] = []
    original_execute = session.execute

    async def observe(statement: object, parameters: object = None, **kwargs: object) -> object:
        executed.append((str(statement), parameters))
        return await original_execute(statement, parameters, **kwargs)

    monkeypatch.setattr(session, "execute", observe)
    first = await repository.search_lexicon(
        query="piano",
        language_tag="it-IT",
        limit=1,
        cursor=None,
    )
    assert first.next_cursor is not None
    second = await repository.search_lexicon(
        query="piano", language_tag="it-IT", limit=1, cursor=first.next_cursor
    )
    assert [item.analysis.form_analysis_id for item in first.items] == [IDS["form_piano"]]
    assert [item.analysis.form_analysis_id for item in second.items] == [
        UUID("019fe900-5000-7000-8024-000000000100")
    ]

    statement, parameters = executed[-1]
    assert "LIMIT :query_limit" in statement
    assert "(surface, form_analysis_id) >" in statement
    assert parameters == {
        "language_tag": "it-IT",
        "query": "piano",
        "after_surface": "piano",
        "after_id": str(IDS["form_piano"]),
        "query_limit": 2,
    }


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


async def test_repository_reads_only_the_complete_published_foundation_aggregate(
    migration_session: AsyncSession,
    session: AsyncSession,
) -> None:
    repository = SqlCatalogueRepository(session)
    reader = getattr(repository, "read_foundations", None)
    assert callable(reader), "W04F foundation catalogue reader is missing"

    await seed_catalogue(migration_session, include_foundations=True)
    published = await reader(pack_revision_id=IDS["pack_revision"])
    missing = await reader(pack_revision_id=UUID("019fe900-5000-7000-8fff-000000000001"))

    assert published is not None
    assert [block.block_code for block in published.definition.blocks] == [
        "F1",
        "F2",
        "F3",
        "F4",
        "F5",
    ]
    assert published.definition.gate.gate_code == "FOUNDATIONS_IT_V0"
    assert published.definition.gate.blocking_facet_minimum_status == "reliable"
    assert published.definition.gate.delayed_control_block_code == "F1"
    assert published.definition.gate.survival_exchange_without_reveal is True
    assert {item.reference_code for item in published.references} >= {
        "IT-PHON-001",
        "IT-GRAM-003",
        "grapheme_sound_discrimination",
        "DIAGNOSTIC_WAIVER_V0",
    }
    assert missing is None
