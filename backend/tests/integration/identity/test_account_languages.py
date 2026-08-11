from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.modules.identity.application import RequestContext
from polyglot.modules.identity.language_persistence import AccountLanguageApplicationService
from polyglot.modules.identity.languages import LanguageRelationship, SelfAssessedBand
from polyglot.platform.clock import FrozenClock

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
ACCOUNT_ID = UUID("019f0000-0000-7000-8000-000000000301")


async def test_account_language_create_replays_and_never_grants_mastery(
    migration_session: AsyncSession,
    database_url: str,
) -> None:
    await migration_session.execute(
        text(
            "INSERT INTO identity.accounts "
            "(account_id,status,security_version,session_version,version,created_at,"
            "security_last_activity_at,deleted_at) "
            "VALUES (:id,'active',1,1,1,:now,:now,NULL)"
        ),
        {"id": ACCOUNT_ID, "now": NOW},
    )
    variety_id = await migration_session.scalar(
        text("SELECT variety_id FROM catalogue.language_varieties WHERE language_tag='fr-FR'")
    )
    await migration_session.commit()
    assert variety_id is not None

    engine = create_async_engine(database_url)
    service = AccountLanguageApplicationService(
        async_sessionmaker(engine, expire_on_commit=False),
        clock=FrozenClock(NOW),
    )
    context = RequestContext(
        request_id=UUID("019f0000-0000-7000-8000-000000000302"),
        correlation_id=UUID("019f0000-0000-7000-8000-000000000303"),
        truncated_ip="127.0.0.0/24",
    )

    first = await service.create_language(
        account_id=ACCOUNT_ID,
        variety_id=variety_id,
        relationship=LanguageRelationship.NATIVE,
        self_assessed_band=SelfAssessedBand.ADVANCED,
        use_for_explanations=True,
        use_for_contrasts=True,
        idempotency_key="language-fr",
        context=context,
    )
    replay = await service.create_language(
        account_id=ACCOUNT_ID,
        variety_id=variety_id,
        relationship=LanguageRelationship.NATIVE,
        self_assessed_band=SelfAssessedBand.ADVANCED,
        use_for_explanations=True,
        use_for_contrasts=True,
        idempotency_key="language-fr",
        context=context,
    )

    assert replay == first
    assert first.grants_mastery is False
    assert await service.list_languages(ACCOUNT_ID) == (first,)

    revised = await service.revise_language(
        account_id=ACCOUNT_ID,
        language_id=first.account_language_id,
        relationship=LanguageRelationship.FLUENT,
        self_assessed_band=SelfAssessedBand.INDEPENDENT,
        use_for_explanations=True,
        use_for_contrasts=False,
        expected_version=1,
        idempotency_key="language-fr-revise",
        context=context,
    )
    archived = await service.archive_language(
        account_id=ACCOUNT_ID,
        language_id=first.account_language_id,
        expected_version=2,
        idempotency_key="language-fr-archive",
        context=context,
    )

    assert revised.version == 2
    assert revised.relationship is LanguageRelationship.FLUENT
    assert archived.version == 3
    assert archived.archived_at is not None
    assert await service.list_languages(ACCOUNT_ID) == ()
    await engine.dispose()
