from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import migration_database_url_from_environment
from polyglot.interfaces.http.routes.word_bank import SqlWordBankService
from polyglot.platform.errors import DomainError, ErrorCode

from .test_ingestion_postgres import NOW, seed_profiles, set_actor, uid


async def seed_same_account_profiles_and_private_senses(session) -> None:
    await seed_profiles(session)
    await session.execute(
        text(
            "INSERT INTO language_profiles.learner_language_profiles "
            "(profile_id,account_id,target_variety_id,native_variety_id,status,current_phase,"
            "goals,interests,excluded_themes,correction_preference,availability_pattern,version,"
            "created_at,updated_at) VALUES "
            "(:profile,:account,:target,:native,'active','module_learning','[]','[]','[]','{}',"
            "'{}',1,:now,:now)"
        ),
        {
            "profile": uid(13),
            "account": uid(1),
            "target": uid(103),
            "native": uid(203),
            "now": NOW,
        },
    )
    for offset, profile in ((2000, 11), (2010, 13)):
        await session.execute(
            text(
                "INSERT INTO lexicon.private_lexical_units "
                "(lexical_unit_id,profile_id,variety_id,unit_type,lemma,normalization_key,"
                "components,provenance_ref,version,created_at) VALUES "
                "(:unit,:profile,:variety,'word',:lemma,:lemma,'{}','test',1,:now)"
            ),
            {
                "unit": uid(offset),
                "profile": uid(profile),
                "variety": uid(101),
                "lemma": f"mot-{profile}",
                "now": NOW,
            },
        )
        await session.execute(
            text(
                "INSERT INTO lexicon.private_lexical_senses "
                "(sense_id,profile_id,lexical_unit_id,sense_code,definition,provenance_ref,"
                "created_at) VALUES (:sense,:profile,:unit,:code,'test','test',:now)"
            ),
            {
                "sense": uid(offset + 1),
                "profile": uid(profile),
                "unit": uid(offset),
                "code": f"sense-{profile}",
                "now": NOW,
            },
        )
    await session.execute(
        text(
            "INSERT INTO lexicon.lexical_encounters "
            "(encounter_id,profile_id,exact_surface,source_type,source_ref,source_revision_ref,"
            "modality,lexical_role,operation,help_state,result_state,correction_ref,"
            "correction_confidence,context_private,context_fingerprint,context_retention,"
            "occurred_at,idempotency_key,request_fingerprint) VALUES "
            "(:id,:profile,'secret','manual','test','v1','reading','stimulus','seen','none',"
            "'not_evaluable','none',0,'private context',:fp,'private_until_deleted',:now,"
            "'reauth-target',:fp)"
        ),
        {"id": uid(2999), "profile": uid(11), "fp": "e" * 64, "now": NOW},
    )
    await session.commit()


@pytest.fixture
async def ownership_service(migration_session):
    await seed_same_account_profiles_and_private_senses(migration_session)
    engine = create_async_engine(migration_database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield SqlWordBankService(factory), factory
    finally:
        await engine.dispose()


async def test_relation_rejects_private_target_from_another_owned_profile(
    ownership_service,
) -> None:
    service, _ = ownership_service
    with pytest.raises(DomainError) as error:
        await service.execute(
            command_name="AssertLexicalRelation",
            account_id=uid(1),
            resource_id=uid(2001),
            profile_id=uid(11),
            payload={
                "relation_id": str(uid(2020)),
                "target_sense_id": str(uid(2011)),
                "relation_type": "association",
            },
            idempotency_key="cross-profile-relation",
            expected_version=None,
        )
    assert error.value.code is ErrorCode.NOT_FOUND


async def test_path_sense_is_authoritative_over_payload_sense(ownership_service) -> None:
    service, factory = ownership_service
    result = await service.execute(
        command_name="DeclareLexicalFamiliarity",
        account_id=uid(1),
        resource_id=uid(2001),
        profile_id=uid(11),
        payload={"sense_id": str(uid(2011)), "familiarity": "known"},
        idempotency_key="path-sense-authoritative",
        expected_version=None,
    )
    async with factory() as session:
        await set_actor(session, uid(1))
        stored_sense = await session.scalar(
            text("SELECT sense_id FROM lexicon.lexical_declarations WHERE declaration_id=:id"),
            {"id": result.resource_id},
        )
    assert stored_sense == uid(2001)


async def test_delete_private_context_requires_server_verified_recent_reauth(
    ownership_service,
) -> None:
    service, _ = ownership_service
    with pytest.raises(DomainError) as error:
        await service.execute(
            command_name="DeletePrivateContext",
            account_id=uid(1),
            resource_id=uid(2999),
            payload={},
            idempotency_key="delete-without-reauth",
            expected_version=None,
        )
    assert error.value.code in {ErrorCode.FORBIDDEN, ErrorCode.DEPENDENCY_UNAVAILABLE}


async def test_capture_gap_requires_owned_open_attempt_and_allowed_support_language(
    ownership_service,
) -> None:
    service, _ = ownership_service
    with pytest.raises(DomainError) as error:
        await service.execute(
            command_name="CaptureLexicalGap",
            account_id=uid(1),
            resource_id=uid(3000),
            profile_id=uid(11),
            payload={
                "intended_support_text": "mot inconnu",
                "support_language_tag": "ja-JP",
            },
            idempotency_key="unauthorized-attempt-gap",
            expected_version=None,
        )
    assert error.value.code in {
        ErrorCode.FORBIDDEN,
        ErrorCode.NOT_FOUND,
        ErrorCode.DEPENDENCY_UNAVAILABLE,
    }


async def test_schema_rejects_cross_profile_child_fk_even_with_same_account(
    ownership_service,
) -> None:
    _, factory = ownership_service
    async with factory() as session:
        await set_actor(session, uid(1))
        await session.execute(
            text(
                "INSERT INTO lexicon.lexical_encounters "
                "(encounter_id,profile_id,exact_surface,source_type,source_ref,source_revision_ref,"
                "modality,lexical_role,operation,help_state,result_state,correction_ref,"
                "correction_confidence,context_fingerprint,context_retention,occurred_at,"
                "idempotency_key,request_fingerprint) VALUES "
                "(:id,:profile,'x','manual','x','x','reading','stimulus','seen','none',"
                "'not_evaluable','none',0,:fp,'minimal',:now,'fk-parent',:fp)"
            ),
            {"id": uid(3010), "profile": uid(11), "fp": "f" * 64, "now": NOW},
        )
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    "INSERT INTO lexicon.lexical_mentions "
                    "(mention_id,profile_id,encounter_id,exact_surface,analysis_revision_ref,"
                    "ordinal,created_at) VALUES (:id,:wrong,:parent,'x','x',1,:now)"
                ),
                {
                    "id": uid(3011),
                    "wrong": uid(13),
                    "parent": uid(3010),
                    "now": NOW + timedelta(seconds=1),
                },
            )
