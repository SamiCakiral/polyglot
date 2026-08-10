from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import database_url_from_environment
from polyglot.interfaces.http.routes.word_bank import SqlWordBankService
from polyglot.platform.errors import DomainError, ErrorCode

from .test_ingestion_postgres import NOW, seed_profiles, set_actor, uid


async def seed_auth_session(session, *, session_id, authenticated_at: datetime) -> None:
    await session.execute(
        text(
            "INSERT INTO identity.auth_sessions "
            "(session_id,account_id,session_fingerprint,csrf_secret_hash,roles_snapshot,"
            "account_session_version,created_at,authenticated_at,last_seen_at,rotated_at,"
            "idle_expires_at,absolute_expires_at) VALUES "
            "(:session,:account,:fingerprint,:csrf,ARRAY['learner'],1,:created,:authenticated,"
            ":created,:created,:idle,:absolute)"
        ),
        {
            "session": session_id,
            "account": uid(1),
            "fingerprint": f"{session_id.int % (16**64):064x}",
            "csrf": "c" * 64,
            "created": authenticated_at,
            "authenticated": authenticated_at,
            "idle": authenticated_at + timedelta(hours=1),
            "absolute": authenticated_at + timedelta(days=7),
        },
    )


async def runtime_service():
    engine = create_async_engine(database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return SqlWordBankService(factory), engine


async def test_delete_private_context_accepts_only_recent_real_session(
    migration_session,
) -> None:
    await seed_profiles(migration_session)
    await migration_session.execute(
        text(
            "INSERT INTO lexicon.lexical_encounters "
            "(encounter_id,profile_id,exact_surface,source_type,source_ref,source_revision_ref,"
            "modality,lexical_role,operation,help_state,result_state,correction_ref,"
            "correction_confidence,context_private,context_fingerprint,context_retention,"
            "occurred_at,idempotency_key,request_fingerprint) VALUES "
            "(:id,:profile,'secret','manual','test','v1','reading','stimulus','seen','none',"
            "'not_evaluable','none',0,'private',:fp,'private_until_deleted',:now,'delete-real',:fp)"
        ),
        {"id": uid(5000), "profile": uid(11), "fp": "a" * 64, "now": NOW},
    )
    recent_session = uid(5001)
    await seed_auth_session(
        migration_session,
        session_id=recent_session,
        authenticated_at=datetime.now(UTC),
    )
    await migration_session.commit()

    service, engine = await runtime_service()
    try:
        result = await service.execute(
            command_name="DeletePrivateContext",
            account_id=uid(1),
            session_id=recent_session,
            resource_id=uid(5000),
            payload={},
            idempotency_key="delete-real-context",
            expected_version=None,
        )
    finally:
        await engine.dispose()
    assert result.resource_id == uid(5000)


async def test_delete_private_context_rejects_stale_real_session(migration_session) -> None:
    await seed_profiles(migration_session)
    await migration_session.execute(
        text(
            "INSERT INTO lexicon.lexical_encounters "
            "(encounter_id,profile_id,exact_surface,source_type,source_ref,source_revision_ref,"
            "modality,lexical_role,operation,help_state,result_state,correction_ref,"
            "correction_confidence,context_private,context_fingerprint,context_retention,"
            "occurred_at,idempotency_key,request_fingerprint) VALUES "
            "(:id,:profile,'secret','manual','test','v1','reading','stimulus','seen','none',"
            "'not_evaluable','none',0,'private',:fp,'private_until_deleted',:now,'delete-stale',:fp)"
        ),
        {"id": uid(5999), "profile": uid(11), "fp": "b" * 64, "now": NOW},
    )
    stale_session = uid(5010)
    await seed_auth_session(
        migration_session,
        session_id=stale_session,
        authenticated_at=datetime.now(UTC) - timedelta(minutes=6),
    )
    await migration_session.commit()
    service, engine = await runtime_service()
    try:
        with pytest.raises(DomainError) as error:
            await service.execute(
                command_name="DeletePrivateContext",
                account_id=uid(1),
                session_id=stale_session,
                resource_id=uid(5999),
                payload={},
                idempotency_key="delete-stale-context",
                expected_version=None,
            )
    finally:
        await engine.dispose()
    assert error.value.code is ErrorCode.UNAUTHENTICATED


async def seed_open_attempt_and_support_language(session) -> None:
    await session.execute(
        text(
            "INSERT INTO catalogue.language_varieties "
            "(variety_id,language_tag,script_codes,text_direction,segmentation_policy_revision_id,"
            "media_capabilities,normalization_policy_revision_id) VALUES "
            "(:variety,'fr-FR',ARRAY['Latn'],'ltr',:segment,'{\"schema_version\":\"1\"}',:normal)"
        ),
        {"variety": uid(5100), "segment": uid(5101), "normal": uid(5102)},
    )
    await session.execute(
        text(
            "INSERT INTO language_profiles.support_language_authorizations "
            "(authorization_id,profile_id,variety_id,authorized_at) VALUES "
            "(:id,:profile,:variety,:now)"
        ),
        {"id": uid(5103), "profile": uid(11), "variety": uid(5100), "now": NOW},
    )
    await session.execute(
        text(
            "INSERT INTO platform.domain_events "
            "(event_id,event_type,schema_version,aggregate_type,aggregate_id,aggregate_version,"
            "actor_type,actor_id,profile_id,occurred_at,recorded_at,correlation_id,command_id,"
            "privacy_class,policy_versions,payload,expires_at,subject_type,subject_id) VALUES "
            "(:event,'exercise_attempt_opened',1,'exercise_attempt',:attempt,1,'account',"
            ":account,:profile,:now,:now,:correlation,:command,'personal','{}','{}',"
            ":expires,'profile',:profile)"
        ),
        {
            "event": uid(5110),
            "attempt": uid(5111),
            "account": uid(1),
            "profile": uid(11),
            "now": NOW,
            "correlation": uid(5112),
            "command": uid(5113),
            "expires": NOW + timedelta(days=30),
        },
    )


async def test_capture_gap_uses_real_attempt_owner_state_and_support_authorization(
    migration_session,
) -> None:
    await seed_profiles(migration_session)
    await seed_open_attempt_and_support_language(migration_session)
    await migration_session.commit()
    service, engine = await runtime_service()
    try:
        result = await service.execute(
            command_name="CaptureLexicalGap",
            account_id=uid(1),
            profile_id=uid(11),
            resource_id=uid(5111),
            payload={
                "encounter_id": str(uid(5120)),
                "mention_id": str(uid(5121)),
                "intended_support_text": "mot inconnu",
                "support_language_tag": "fr-FR",
            },
            idempotency_key="capture-real-attempt",
            expected_version=None,
        )
    finally:
        await engine.dispose()
    assert result.resource_id == uid(5120)


async def test_capture_gap_rejects_unowned_or_unauthorized_attempt(
    migration_session,
) -> None:
    await seed_profiles(migration_session)
    await seed_open_attempt_and_support_language(migration_session)
    await migration_session.commit()
    service, engine = await runtime_service()
    try:
        with pytest.raises(DomainError) as error:
            await service.execute(
                command_name="CaptureLexicalGap",
                account_id=uid(1),
                profile_id=uid(11),
                resource_id=uid(5111),
                payload={
                    "intended_support_text": "mot inconnu",
                    "support_language_tag": "ja-JP",
                },
                idempotency_key="capture-bad-language",
                expected_version=None,
            )
    finally:
        await engine.dispose()
    assert error.value.code is ErrorCode.NOT_FOUND
