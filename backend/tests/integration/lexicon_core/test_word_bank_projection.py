from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import migration_database_url_from_environment
from polyglot.interfaces.http.routes.word_bank import SqlWordBankService

from .test_ingestion_postgres import NOW, seed_profiles, uid


async def test_reference_projection_rebuilds_from_facts_with_user_overrides(
    migration_session,
) -> None:
    await seed_profiles(migration_session)
    await migration_session.execute(
        text(
            "INSERT INTO lexicon.lexical_reference_sets "
            "(reference_set_id,code,revision,label,created_at) VALUES "
            "(:id,'it-core','2026.1','Italian core',:now)"
        ),
        {"id": uid(4000), "now": NOW},
    )
    for ordinal, sense, label in ((1, 4001, "andare"), (2, 4002, "venire")):
        await migration_session.execute(
            text(
                "INSERT INTO lexicon.lexical_reference_entries "
                "(reference_set_id,sense_id,ordinal,label,definition) VALUES "
                "(:set,:sense,:ordinal,:label,:definition)"
            ),
            {
                "set": uid(4000),
                "sense": uid(sense),
                "ordinal": ordinal,
                "label": label,
                "definition": f"definition {label}",
            },
        )
    await migration_session.commit()

    engine = create_async_engine(migration_database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = SqlWordBankService(factory)
    try:
        first = await service.get_word_bank(
            account_id=uid(1),
            profile_id=uid(11),
            limit=100,
            cursor=None,
            reference_set_code="it-core",
        )
        rebuilt = await service.get_word_bank(
            account_id=uid(1),
            profile_id=uid(11),
            limit=100,
            cursor=None,
            reference_set_code="it-core",
        )
    finally:
        await engine.dispose()

    assert first == rebuilt
    assert tuple(item.label for item in first.items) == ("andare", "venire")
    assert first.reference_revision == "2026.1"
    assert first.reference_coverage_count == 0
    assert first.reference_total_count == 2
