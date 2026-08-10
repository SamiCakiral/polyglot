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
    await migration_session.execute(
        text(
            "INSERT INTO lexicon.lexical_declarations "
            "(declaration_id,profile_id,sense_id,familiarity,declared_at,idempotency_key,"
            "request_fingerprint) VALUES (:id,:profile,:sense,'known',:now,'decl',:fp)"
        ),
        {
            "id": uid(4010),
            "profile": uid(11),
            "sense": uid(4001),
            "now": NOW,
            "fp": "d" * 64,
        },
    )
    await migration_session.execute(
        text(
            "INSERT INTO lexicon.lexical_preferences "
            "(preference_id,profile_id,sense_id,preference,version,set_at,idempotency_key,"
            "request_fingerprint) VALUES (:id,:profile,:sense,'prioritize',1,:now,'pref',:fp)"
        ),
        {
            "id": uid(4011),
            "profile": uid(11),
            "sense": uid(4001),
            "now": NOW,
            "fp": "e" * 64,
        },
    )
    await migration_session.execute(
        text(
            "INSERT INTO lexicon.lexical_encounters "
            "(encounter_id,profile_id,exact_surface,source_type,source_ref,source_revision_ref,"
            "modality,lexical_role,operation,help_state,result_state,correction_ref,"
            "correction_confidence,context_fingerprint,context_retention,occurred_at,"
            "idempotency_key,request_fingerprint) VALUES "
            "(:id,:profile,'boh','manual','test','v1','listening','stimulus','seen','none',"
            "'not_evaluable','none',0,:fp,'minimal',:now,'unresolved',:fp)"
        ),
        {
            "id": uid(4020),
            "profile": uid(11),
            "fp": "f" * 64,
            "now": NOW,
        },
    )
    await migration_session.execute(
        text(
            "INSERT INTO lexicon.lexical_mentions "
            "(mention_id,profile_id,encounter_id,exact_surface,analysis_revision_ref,ordinal,"
            "created_at) VALUES (:id,:profile,:encounter,'boh','v1',1,:now)"
        ),
        {
            "id": uid(4021),
            "profile": uid(11),
            "encounter": uid(4020),
            "now": NOW,
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
    assert first.items[0].familiarity_declaration == "known"
    assert first.items[0].learning_preference == "prioritize"
    assert tuple(item.mention_id for item in first.unresolved_mentions) == (uid(4021),)
    assert first.unresolved_mentions[0].exact_surface == "boh"


async def test_reference_cursor_uses_persisted_ordinal_and_revision(migration_session) -> None:
    await seed_profiles(migration_session)
    await migration_session.execute(
        text(
            "INSERT INTO lexicon.lexical_reference_sets "
            "(reference_set_id,code,revision,label,created_at) VALUES "
            "(:id,'cursor-set','r1','Cursor set',:now)"
        ),
        {"id": uid(4100), "now": NOW},
    )
    for ordinal in range(1, 4):
        await migration_session.execute(
            text(
                "INSERT INTO lexicon.lexical_reference_entries "
                "(reference_set_id,sense_id,ordinal,label,definition) VALUES "
                "(:set,:sense,:ordinal,:label,'definition')"
            ),
            {
                "set": uid(4100),
                "sense": uid(4100 + ordinal),
                "ordinal": ordinal,
                "label": f"item-{ordinal}",
            },
        )
    await migration_session.commit()
    engine = create_async_engine(migration_database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = SqlWordBankService(factory)
    try:
        first = await service.get_word_bank(
            account_id=uid(1), profile_id=uid(11), limit=2, cursor=None,
            reference_set_code="cursor-set",
        )
        second = await service.get_word_bank(
            account_id=uid(1), profile_id=uid(11), limit=2,
            cursor=first.next_cursor, reference_set_code="cursor-set",
        )
    finally:
        await engine.dispose()
    assert tuple(item.label for item in first.items + second.items) == (
        "item-1", "item-2", "item-3"
    )
