import asyncio
from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.modules.identity.domain import FakeOidcProvider, OidcAssertion, SessionSecrets
from polyglot.platform.clock import FrozenClock
from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 8, 10, 11, 0, tzinfo=UTC)
REQUEST_ID = UUID("019fe900-3000-7000-8000-000000000001")
CORRELATION_ID = UUID("019fe900-3000-7000-8000-000000000002")


def application() -> object:
    try:
        return import_module("polyglot.modules.identity.application")
    except ModuleNotFoundError:
        pytest.fail("identity application service is not implemented")


def build_service(
    factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime = NOW,
) -> object:
    module = application()
    return module.IdentityApplicationService(
        factory,
        clock=FrozenClock(now),
        session_secrets=SessionSecrets.from_key(b"application-test-session-key-32b"),
        oidc_provider=FakeOidcProvider(
            {
                "oidc-register": OidcAssertion(
                    issuer="https://fixture-oidc.invalid",
                    subject="fixture-subject-register",
                )
            }
        ),
    )


def context(module: object) -> object:
    return module.RequestContext(
        request_id=REQUEST_ID,
        correlation_id=CORRELATION_ID,
        truncated_ip="127.0.0.0/24",
    )


async def register_local(service: object, *, key: str = "register-owner") -> object:
    module = application()
    return await service.register_account(
        module.RegisterAccount(
            provider_type="local_password",
            identifier="owner@example.test",
            password="correct horse battery staple",
            authorization_code=None,
            idempotency_key=key,
            context=context(module),
        )
    )


async def authenticate_local(service: object, *, key: str = "authenticate-owner") -> object:
    module = application()
    return await service.authenticate_session(
        module.AuthenticateSession(
            provider_type="local_password",
            identifier="owner@example.test",
            password="correct horse battery staple",
            authorization_code=None,
            idempotency_key=key,
            context=context(module),
        )
    )


async def test_registration_replays_one_account_and_conflicting_body_is_rejected(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = build_service(factory)

    first = await register_local(service)
    replay = await register_local(service)

    assert replay == first
    with pytest.raises(DomainError) as captured:
        module = application()
        await service.register_account(
            module.RegisterAccount(
                provider_type="local_password",
                identifier="owner@example.test",
                password="different password value",
                authorization_code=None,
                idempotency_key="register-owner",
                context=context(module),
            )
        )
    assert captured.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    with pytest.raises(DomainError) as duplicate:
        await register_local(service, key="new-command-key")
    assert duplicate.value.code is ErrorCode.IDENTITY_CONFLICT
    await engine.dispose()


async def test_concurrent_same_registration_serializes_to_one_account(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    services = (build_service(factory), build_service(factory))

    first, second = await asyncio.gather(*(register_local(service) for service in services))

    assert first == second
    async with factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM identity.accounts")) == 1
        assert await session.scalar(text("SELECT count(*) FROM platform.domain_events")) == 1
        assert await session.scalar(text("SELECT count(*) FROM platform.outbox_messages")) == 1
    await engine.dispose()


async def test_authentication_is_safe_for_invalid_locked_and_deleted_accounts(
    database_url: str,
    migration_session: AsyncSession,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = build_service(factory)
    registered = await register_local(service)
    module = application()

    with pytest.raises(DomainError) as invalid:
        await service.authenticate_session(
            module.AuthenticateSession(
                provider_type="local_password",
                identifier="owner@example.test",
                password="incorrect password value",
                authorization_code=None,
                idempotency_key="invalid-password",
                context=context(module),
            )
        )
    assert invalid.value.code is ErrorCode.INVALID_CREDENTIALS

    await migration_session.execute(
        text("UPDATE identity.accounts SET status = 'locked' WHERE account_id = :account_id"),
        {"account_id": registered.account_id},
    )
    await migration_session.commit()
    with pytest.raises(DomainError) as locked:
        await authenticate_local(service, key="locked-account")
    assert locked.value.code is ErrorCode.ACCOUNT_LOCKED

    await migration_session.execute(
        text(
            "UPDATE identity.accounts SET status = 'deleted', deleted_at = :now "
            "WHERE account_id = :account_id"
        ),
        {"account_id": registered.account_id, "now": NOW},
    )
    await migration_session.commit()
    with pytest.raises(DomainError) as deleted:
        await authenticate_local(service, key="deleted-account")
    assert deleted.value.code is ErrorCode.INVALID_CREDENTIALS
    await engine.dispose()


async def test_authentication_rotates_fixated_input_and_replays_same_opaque_session(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = build_service(factory)
    await register_local(service)

    first = await authenticate_local(service)
    replay = await authenticate_local(service)

    assert first == replay
    assert first.session_token != "attacker-controlled-session"
    assert first.session_token != str(first.session_id)
    assert "correct horse" not in repr(first)
    await engine.dispose()


async def test_role_change_and_24_hour_boundary_rotate_to_current_roles(
    database_url: str,
    migration_session: AsyncSession,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = build_service(factory)
    registered = await register_local(service)
    authenticated = await authenticate_local(service)
    await migration_session.execute(
        text(
            "INSERT INTO identity.account_roles "
            "(role_grant_id, account_id, role, granted_at, granted_by_actor_id, revoked_at) "
            "VALUES ('019fe900-3000-7000-8000-000000000099', :account_id, 'author', "
            ":now, :account_id, NULL)"
        ),
        {"account_id": registered.account_id, "now": NOW + timedelta(minutes=1)},
    )
    await migration_session.execute(
        text(
            "UPDATE identity.accounts SET session_version = session_version + 1, "
            "security_version = security_version + 1, version = version + 1 "
            "WHERE account_id = :account_id"
        ),
        {"account_id": registered.account_id},
    )
    await migration_session.commit()

    role_rotated = await service.get_current_session(authenticated.session_token)

    assert role_rotated.session_token != authenticated.session_token
    assert set(role_rotated.roles) == {"learner", "author"}
    service_after_24h = build_service(factory, now=NOW + timedelta(hours=24))
    time_rotated = await service_after_24h.get_current_session(role_rotated.session_token)
    assert time_rotated.session_token != role_rotated.session_token
    await engine.dispose()


async def test_expired_session_and_replayed_or_conflicting_consent_are_closed(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = build_service(factory)
    await register_local(service)
    authenticated = await authenticate_local(service)
    module = application()
    command = module.UpdateConsent(
        session_token=authenticated.session_token,
        csrf_token=authenticated.csrf_token,
        purpose_code="speech_training",
        status="granted",
        policy_revision_id=UUID("019fe900-3000-7000-8000-000000000077"),
        expected_version=0,
        idempotency_key="consent-v1",
        context=context(module),
    )

    first = await service.update_consent(command)
    replay = await service.update_consent(command)
    assert replay == first
    with pytest.raises(DomainError) as conflict:
        await service.update_consent(
            module.UpdateConsent(
                session_token=authenticated.session_token,
                csrf_token=authenticated.csrf_token,
                purpose_code="speech_training",
                status="withdrawn",
                policy_revision_id=UUID("019fe900-3000-7000-8000-000000000077"),
                expected_version=0,
                idempotency_key="consent-v1",
                context=context(module),
            )
        )
    assert conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT

    expired_service = build_service(factory, now=NOW + timedelta(hours=12))
    with pytest.raises(DomainError) as expired:
        await expired_service.get_current_session(authenticated.session_token)
    assert expired.value.code is ErrorCode.UNAUTHENTICATED
    await engine.dispose()
