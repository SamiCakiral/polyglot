from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.modules.lexicon.core.commands import (
    LexiconCommandService,
    MentionCandidateInput,
    RecordLexicalEncounter,
)
from polyglot.platform.errors import DomainError, ErrorCode


def uid(number: int) -> UUID:
    return UUID(f"019feb30-0000-7000-8000-{number:012x}")


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


async def seed_profiles(session: AsyncSession) -> None:
    for account_id in (uid(1), uid(2)):
        await session.execute(
            text(
                "INSERT INTO identity.accounts "
                "(account_id,status,security_version,session_version,version,created_at,"
                "security_last_activity_at) VALUES (:id,'active',1,1,1,:now,:now) "
                "ON CONFLICT (account_id) DO NOTHING"
            ),
            {"id": account_id, "now": NOW},
        )
    for profile_id, account_id, suffix in ((uid(11), uid(1), 1), (uid(12), uid(2), 2)):
        await session.execute(
            text(
                "INSERT INTO language_profiles.learner_language_profiles "
                "(profile_id,account_id,target_variety_id,native_variety_id,status,current_phase,"
                "goals,interests,excluded_themes,correction_preference,availability_pattern,"
                "version,created_at,updated_at) VALUES "
                "(:profile,:account,:target,:native,'active','module_learning','[]','[]','[]',"
                "'{}','{}',1,:now,:now) ON CONFLICT (profile_id) DO NOTHING"
            ),
            {
                "profile": profile_id,
                "account": account_id,
                "target": uid(100 + suffix),
                "native": uid(200 + suffix),
                "now": NOW,
            },
        )
    await session.commit()


def command(*, surface: str = "piano", fingerprint: str = "a" * 64) -> RecordLexicalEncounter:
    return RecordLexicalEncounter(
        encounter_id=uid(20),
        profile_id=uid(11),
        exact_surface=surface,
        source_type="manual",
        source_ref="outside-polyglot",
        source_revision_ref="manual-v1",
        modality="writing",
        lexical_role="production",
        operation="queried",
        help_state="none",
        result_state="not_evaluable",
        correction_ref="none",
        correction_confidence=0.0,
        context_private="Je voulais dire doucement",
        context_fingerprint="c" * 64,
        context_retention="private_until_deleted",
        occurred_at=NOW,
        mention_id=uid(21),
        form_analysis_id=None,
        analysis_revision_ref="manual-v1",
        candidates=(MentionCandidateInput(uid(22), uid(23), "shared", 0.5, "manual"),),
        idempotency_key="record-piano",
        request_fingerprint=fingerprint,
    )


async def test_postgres_ingestion_is_idempotent_and_rejects_payload_reuse(
    migration_session: AsyncSession,
) -> None:
    await seed_profiles(migration_session)
    service = LexiconCommandService(migration_session)

    first = await service.record_encounter(command())
    replay = await service.record_encounter(command())
    with pytest.raises(DomainError) as error:
        await service.record_encounter(command(surface="forte", fingerprint="b" * 64))

    assert first == replay == uid(20)
    assert error.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert await migration_session.scalar(
        text("SELECT count(*) FROM lexicon.lexical_encounters WHERE profile_id=:profile"),
        {"profile": uid(11)},
    ) == 1
    assert await migration_session.scalar(
        text("SELECT count(*) FROM lexicon.lexical_mentions WHERE profile_id=:profile"),
        {"profile": uid(11)},
    ) == 1


async def test_private_context_delete_keeps_fact_and_minimal_provenance(
    migration_session: AsyncSession,
) -> None:
    await seed_profiles(migration_session)
    service = LexiconCommandService(migration_session)
    await service.record_encounter(command())

    await service.delete_private_context(
        profile_id=uid(11),
        encounter_id=uid(20),
        deleted_at=NOW + timedelta(hours=1),
    )
    row = (
        await migration_session.execute(
            text(
                "SELECT exact_surface,context_private,context_fingerprint,context_deleted_at "
                "FROM lexicon.lexical_encounters WHERE encounter_id=:id"
            ),
            {"id": uid(20)},
        )
    ).one()

    assert row.exact_surface == "piano"
    assert row.context_private is None
    assert row.context_fingerprint == "c" * 64
    assert row.context_deleted_at == NOW + timedelta(hours=1)


async def test_rls_hides_another_users_encounter(
    migration_session: AsyncSession,
) -> None:
    await seed_profiles(migration_session)
    await LexiconCommandService(migration_session).record_encounter(command())
    await migration_session.commit()
    await migration_session.execute(text("SET ROLE polyglot_runtime"))
    await migration_session.execute(text("SELECT set_config('app.user_id', :user_id, false)"), {"user_id": str(uid(2))})

    visible = await migration_session.scalar(text("SELECT count(*) FROM lexicon.lexical_encounters"))

    assert visible == 0
