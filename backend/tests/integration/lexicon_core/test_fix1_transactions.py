import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import migration_database_url_from_environment
from polyglot.interfaces.http.routes.word_bank import SqlWordBankService
from polyglot.platform.errors import DomainError, ErrorCode

from .test_ingestion_postgres import NOW, seed_profiles, set_actor, uid


def encounter_payload(*, encounter: int = 1000, mention: int = 1001) -> dict[str, object]:
    return {
        "encounter_id": str(uid(encounter)),
        "mention_id": str(uid(mention)),
        "exact_surface": "piano",
        "source_type": "manual",
        "source_ref": "fix1",
        "source_revision_ref": "fix1-v1",
        "modality": "reading",
        "lexical_role": "stimulus",
        "operation": "seen",
        "help_state": "none",
        "result_state": "not_evaluable",
        "correction_ref": "none",
        "correction_confidence": 0.0,
        "context_fingerprint": "a" * 64,
        "context_retention": "minimal",
        "occurred_at": NOW.isoformat(),
        "candidates": [
            {
                "candidate_id": str(uid(1002)),
                "sense_id": str(uid(1003)),
                "sense_scope": "shared",
                "confidence": 0.8,
                "source": "fixture",
            }
        ],
    }


@pytest.fixture
async def service_factory(migration_session):
    await seed_profiles(migration_session)
    engine = create_async_engine(migration_database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield SqlWordBankService(factory), factory
    finally:
        await engine.dispose()


async def test_encounter_materializes_candidate_then_resolve_is_api_reachable(
    service_factory,
) -> None:
    service, factory = service_factory
    recorded = await service.execute(
        command_name="RecordLexicalEncounter",
        account_id=uid(1),
        resource_id=uid(11),
        payload=encounter_payload(),
        idempotency_key="fix1-record",
        expected_version=None,
    )
    resolved = await service.execute(
        command_name="ResolveMention",
        account_id=uid(1),
        resource_id=uid(1001),
        payload={"candidate_id": str(uid(1002)), "resolution_id": str(uid(1004))},
        idempotency_key="fix1-resolve",
        expected_version=None,
    )

    async with factory() as session:
        await set_actor(session, uid(1))
        candidate_count = await session.scalar(
            text("SELECT count(*) FROM lexicon.mention_candidates WHERE mention_id=:id"),
            {"id": uid(1001)},
        )
        event_types = tuple(
            (
                await session.execute(
                    text(
                        "SELECT event_type FROM platform.domain_events "
                        "WHERE profile_id=:profile ORDER BY occurred_at,event_id"
                    ),
                    {"profile": uid(11)},
                )
            ).scalars()
        )
        outbox_count = await session.scalar(
            text(
                "SELECT count(*) FROM platform.outbox_messages outbox "
                "JOIN platform.domain_events event ON event.event_id=outbox.event_id "
                "WHERE event.profile_id=:profile"
            ),
            {"profile": uid(11)},
        )

    assert recorded.resource_id == uid(1000)
    assert resolved.resource_id == uid(1004)
    assert candidate_count == 1
    assert event_types == ("lexical_encounter_recorded", "mention_resolved")
    assert outbox_count == 2


async def test_failed_resolution_rolls_back_receipt_event_and_outbox(service_factory) -> None:
    service, factory = service_factory
    with pytest.raises(DomainError) as error:
        await service.execute(
            command_name="ResolveMention",
            account_id=uid(1),
            resource_id=uid(9999),
            payload={"candidate_id": str(uid(9998))},
            idempotency_key="fix1-invalid-resolution",
            expected_version=None,
        )
    assert error.value.code is ErrorCode.NOT_FOUND

    async with factory() as session:
        await set_actor(session, uid(1))
        assert await session.scalar(
            text(
                "SELECT count(*) FROM platform.command_receipts "
                "WHERE idempotency_key='fix1-invalid-resolution'"
            )
        ) == 0
        assert await session.scalar(
            text("SELECT count(*) FROM platform.domain_events WHERE profile_id=:profile"),
            {"profile": uid(11)},
        ) == 0


async def test_concurrent_same_key_same_hash_replays_one_atomic_effect(service_factory) -> None:
    service, factory = service_factory

    async def invoke():
        return await service.execute(
            command_name="RecordLexicalEncounter",
            account_id=uid(1),
            resource_id=uid(11),
            payload=encounter_payload(encounter=1100, mention=1101),
            idempotency_key="fix1-concurrent-same",
            expected_version=None,
        )

    first, second = await asyncio.gather(invoke(), invoke())
    assert first == second
    async with factory() as session:
        await set_actor(session, uid(1))
        assert await session.scalar(
            text("SELECT count(*) FROM lexicon.lexical_encounters WHERE encounter_id=:id"),
            {"id": uid(1100)},
        ) == 1
        assert await session.scalar(
            text(
                "SELECT count(*) FROM platform.domain_events "
                "WHERE aggregate_id=:id AND event_type='lexical_encounter_recorded'"
            ),
            {"id": uid(1100)},
        ) == 1


async def test_concurrent_same_key_different_hash_conflicts_without_second_effect(
    service_factory,
) -> None:
    service, factory = service_factory

    async def invoke(encounter: int):
        try:
            return await service.execute(
                command_name="RecordLexicalEncounter",
                account_id=uid(1),
                resource_id=uid(11),
                payload=encounter_payload(encounter=encounter, mention=encounter + 1),
                idempotency_key="fix1-concurrent-conflict",
                expected_version=None,
            )
        except DomainError as error:
            return error.code

    outcomes = await asyncio.gather(invoke(1200), invoke(1210))
    assert ErrorCode.IDEMPOTENCY_CONFLICT in outcomes
    async with factory() as session:
        await set_actor(session, uid(1))
        assert await session.scalar(
            text(
                "SELECT count(*) FROM lexicon.lexical_encounters "
                "WHERE encounter_id IN (:one,:two)"
            ),
            {"one": uid(1200), "two": uid(1210)},
        ) == 1


async def test_neighborhood_is_explicitly_scoped_to_one_owned_profile(service_factory) -> None:
    service, factory = service_factory
    async with factory() as session:
        await set_actor(session, uid(1))
        # Same account, two profiles: account-level RLS alone cannot separate these graphs.
        await session.execute(
            text(
                "INSERT INTO language_profiles.learner_language_profiles "
                "(profile_id,account_id,target_variety_id,native_variety_id,status,current_phase,"
                "goals,interests,excluded_themes,correction_preference,availability_pattern,"
                "version,created_at,updated_at) VALUES "
                "(:profile,:account,:target,:native,'active','module_learning','[]','[]','[]',"
                "'{}','{}',1,:now,:now)"
            ),
            {
                "profile": uid(13),
                "account": uid(1),
                "target": uid(103),
                "native": uid(203),
                "now": datetime.now(UTC),
            },
        )
        for relation_id, profile_id, target_id in (
            (1300, 11, 1301),
            (1310, 13, 1311),
        ):
            await session.execute(
                text(
                    "INSERT INTO lexicon.personal_lexical_relations "
                    "(relation_id,profile_id,source_sense_id,target_sense_id,relation_type,"
                    "direction,provenance_ref,confidence,created_at,version) VALUES "
                    "(:id,:profile,:source,:target,'association','directed','test',1,:now,1)"
                ),
                {
                    "id": uid(relation_id),
                    "profile": uid(profile_id),
                    "source": uid(1003),
                    "target": uid(target_id),
                    "now": NOW,
                },
                )
        await session.execute(
            text(
                "INSERT INTO lexicon.private_lexical_units "
                "(lexical_unit_id,profile_id,variety_id,unit_type,lemma,normalization_key,"
                "components,provenance_ref,version,created_at) VALUES "
                "(:unit,:profile,:variety,'word','piano','piano','{}','test',1,:now)"
            ),
            {"unit": uid(1298), "profile": uid(11), "variety": uid(101), "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO lexicon.private_lexical_senses "
                "(sense_id,profile_id,lexical_unit_id,sense_code,definition,provenance_ref,"
                "created_at) VALUES (:sense,:profile,:unit,'piano.1','doucement','test',:now)"
            ),
            {"sense": uid(1003), "profile": uid(11), "unit": uid(1298), "now": NOW},
        )
        await session.commit()

    result = await service.get_sense(
        account_id=uid(1),
        profile_id=uid(11),
        sense_id=uid(1003),
        depth=1,
        edge_types=("association",),
        max_nodes=10,
    )
    assert uid(1301) in result.nodes
    assert uid(1311) not in result.nodes
