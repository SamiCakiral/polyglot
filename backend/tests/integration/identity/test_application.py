import asyncio
import logging
from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.modules.identity.domain import FakeOidcProvider, OidcAssertion, SessionSecrets
from polyglot.modules.identity.passwords import Argon2idPasswordHasher
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
    password_hasher: object | None = None,
    login_throttle: object | None = None,
    registration_enabled: bool = True,
    oidc_enabled: bool = True,
) -> object:
    module = application()
    options: dict[str, object] = {
        "clock": FrozenClock(now),
        "session_secrets": SessionSecrets.from_key(b"application-test-session-key-32b"),
        "oidc_provider": FakeOidcProvider(
            {
                "oidc-register": OidcAssertion(
                    issuer="https://fixture-oidc.invalid",
                    subject="fixture-subject-register",
                )
            }
        ),
    }
    if password_hasher is not None:
        options["password_hasher"] = password_hasher
    if login_throttle is not None:
        options["login_throttle"] = login_throttle
    if not registration_enabled:
        options["registration_enabled"] = False
    if not oidc_enabled:
        options["oidc_enabled"] = False
    return module.IdentityApplicationService(
        factory,
        **options,
    )


def context(module: object) -> object:
    return module.RequestContext(
        request_id=REQUEST_ID,
        correlation_id=CORRELATION_ID,
        truncated_ip="127.0.0.0/24",
        origin="https://polyglot.test",
    )


class RecordingPasswordHasher:
    def __init__(self) -> None:
        self.delegate = Argon2idPasswordHasher()
        self.verified_hashes: list[str] = []

    def hash(self, password: str) -> str:
        return self.delegate.hash(password)

    def verify(self, encoded_hash: str, password: str) -> bool:
        self.verified_hashes.append(encoded_hash)
        return self.delegate.verify(encoded_hash, password)


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
    migration_session: AsyncSession,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    services = (build_service(factory), build_service(factory))

    first, second = await asyncio.gather(*(register_local(service) for service in services))

    assert first == second
    assert await migration_session.scalar(text("SELECT count(*) FROM identity.accounts")) == 1
    assert await migration_session.scalar(text("SELECT count(*) FROM platform.domain_events")) == 1
    outbox_count = await migration_session.scalar(
        text("SELECT count(*) FROM platform.outbox_messages")
    )
    assert outbox_count == 1
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
    await migration_session.execute(
        text(
            "UPDATE identity.auth_sessions SET last_seen_at = :last_seen_at, "
            "idle_expires_at = :idle_expires_at WHERE session_id = :session_id"
        ),
        {
            "session_id": role_rotated.session_id,
            "last_seen_at": NOW + timedelta(hours=23, minutes=59),
            "idle_expires_at": NOW + timedelta(hours=24, minutes=29),
        },
    )
    await migration_session.commit()
    service_after_24h = build_service(factory, now=NOW + timedelta(hours=24))
    time_rotated = await service_after_24h.get_current_session(role_rotated.session_token)
    assert time_rotated.session_token != role_rotated.session_token
    await engine.dispose()


async def test_rotation_preserves_original_absolute_boundary(
    database_url: str,
    migration_session: AsyncSession,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = build_service(factory)
    registered = await register_local(service)
    authenticated = await authenticate_local(service)
    original_deadline = authenticated.absolute_expires_at
    await migration_session.execute(
        text(
            "UPDATE identity.accounts SET session_version = session_version + 1, "
            "security_version = security_version + 1, version = version + 1 "
            "WHERE account_id = :account_id"
        ),
        {"account_id": registered.account_id},
    )
    await migration_session.execute(
        text(
            "UPDATE identity.auth_sessions SET last_seen_at = :last_seen_at, "
            "idle_expires_at = :idle_expires_at WHERE session_id = :session_id"
        ),
        {
            "session_id": authenticated.session_id,
            "last_seen_at": NOW + timedelta(hours=23),
            "idle_expires_at": NOW + timedelta(days=1, hours=1),
        },
    )
    await migration_session.commit()

    rotated = await build_service(
        factory,
        now=NOW + timedelta(days=1),
    ).get_current_session(authenticated.session_token)

    assert rotated.absolute_expires_at == original_deadline
    await migration_session.execute(
        text(
            "UPDATE identity.auth_sessions SET last_seen_at = :last_seen_at, "
            "idle_expires_at = absolute_expires_at WHERE session_id = :session_id"
        ),
        {
            "session_id": rotated.session_id,
            "last_seen_at": original_deadline - timedelta(minutes=1),
        },
    )
    await migration_session.commit()
    with pytest.raises(DomainError) as expired:
        await build_service(factory, now=original_deadline).get_current_session(
            rotated.session_token
        )
    assert expired.value.code is ErrorCode.UNAUTHENTICATED
    await engine.dispose()


async def test_concurrent_rotation_creates_one_successor_and_one_set_of_facts(
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
            "UPDATE identity.accounts SET session_version = session_version + 1, "
            "security_version = security_version + 1, version = version + 1 "
            "WHERE account_id = :account_id"
        ),
        {"account_id": registered.account_id},
    )
    await migration_session.commit()
    services = (build_service(factory), build_service(factory))

    first, second = await asyncio.gather(
        *(candidate.get_current_session(authenticated.session_token) for candidate in services)
    )

    assert first.session_id == second.session_id
    assert first.session_token == second.session_token
    assert await migration_session.scalar(
        text(
            "SELECT count(*) FROM identity.auth_sessions "
            "WHERE account_id = :account_id AND revoked_at IS NULL"
        ),
        {"account_id": registered.account_id},
    ) == 1
    assert await migration_session.scalar(
        text("SELECT count(*) FROM platform.domain_events WHERE event_type = 'session_revoked'")
    ) == 1
    assert await migration_session.scalar(
        text(
            "SELECT count(*) FROM platform.domain_events "
            "WHERE event_type = 'session_authenticated'"
        )
    ) == 2
    assert await migration_session.scalar(
        text(
            "SELECT count(*) FROM platform.security_audit_entries "
            "WHERE action_code = 'identity.revoke_session'"
        )
    ) == 1
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


async def test_local_authentication_uses_valid_dummy_hash_for_unknown_identifier(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    hasher = RecordingPasswordHasher()
    service = build_service(factory, password_hasher=hasher)
    await register_local(service)
    module = application()

    for identifier, key in (
        ("owner@example.test", "wrong-known"),
        ("unknown@example.test", "wrong-unknown"),
    ):
        before = len(hasher.verified_hashes)
        with pytest.raises(DomainError) as captured:
            await service.authenticate_session(
                module.AuthenticateSession(
                    provider_type="local_password",
                    identifier=identifier,
                    password="incorrect password value",
                    authorization_code=None,
                    idempotency_key=key,
                    context=context(module),
                )
            )
        assert captured.value.code is ErrorCode.INVALID_CREDENTIALS
        assert len(hasher.verified_hashes) == before + 1

    assert hasher.verified_hashes[-1] == module.DUMMY_PASSWORD_HASH
    assert hasher.delegate.verify(module.DUMMY_PASSWORD_HASH, "incorrect password value") is False
    await engine.dispose()


async def test_timing_padding_value_never_authenticates_an_incomplete_command(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = build_service(factory)
    module = application()
    await service.register_account(
        module.RegisterAccount(
            provider_type="local_password",
            identifier="padding@example.test",
            password="invalid credential padding",
            authorization_code=None,
            idempotency_key="register-padding",
            context=context(module),
        )
    )

    with pytest.raises(DomainError) as captured:
        await service.authenticate_session(
            module.AuthenticateSession(
                provider_type="local_password",
                identifier="padding@example.test",
                password=None,
                authorization_code=None,
                idempotency_key="missing-password",
                context=context(module),
            )
        )

    assert captured.value.code is ErrorCode.INVALID_CREDENTIALS
    await engine.dispose()


async def test_authentication_throttles_source_and_identifier_with_bounded_state(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    module = application()
    throttle = module.LoginThrottle(
        max_failures=2,
        window=timedelta(minutes=5),
        max_buckets=4,
    )
    service = build_service(factory, login_throttle=throttle)

    async def attempt(identifier: str, key: str, request_context: object) -> ErrorCode:
        with pytest.raises(DomainError) as captured:
            await service.authenticate_session(
                module.AuthenticateSession(
                    provider_type="local_password",
                    identifier=identifier,
                    password="incorrect password value",
                    authorization_code=None,
                    idempotency_key=key,
                    context=request_context,
                )
            )
        return captured.value.code

    base = context(module)
    assert await attempt("first@example.test", "source-1", base) is ErrorCode.INVALID_CREDENTIALS
    assert await attempt("second@example.test", "source-2", base) is ErrorCode.INVALID_CREDENTIALS
    assert await attempt("third@example.test", "source-3", base) is ErrorCode.RATE_LIMITED

    alternate_sources = [
        module.RequestContext(
            request_id=UUID(f"019fe900-3000-7000-8000-{index:012d}"),
            correlation_id=CORRELATION_ID,
            truncated_ip=f"10.0.{index}.0/24",
            origin=f"https://origin-{index}.example.test",
        )
        for index in range(10, 13)
    ]
    assert (
        await attempt("shared@example.test", "identifier-1", alternate_sources[0])
        is ErrorCode.INVALID_CREDENTIALS
    )
    assert (
        await attempt("shared@example.test", "identifier-2", alternate_sources[1])
        is ErrorCode.INVALID_CREDENTIALS
    )
    assert (
        await attempt("shared@example.test", "identifier-3", alternate_sources[2])
        is ErrorCode.RATE_LIMITED
    )
    assert throttle.tracked_bucket_count <= 4
    await engine.dispose()


def test_identity_commands_redact_all_credentials_from_repr_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    module = application()
    commands = (
        module.RegisterAccount(
            provider_type="local_password",
            identifier="secret@example.test",
            password="register-secret-value",
            authorization_code=None,
            idempotency_key="register-secret",
            context=context(module),
        ),
        module.AuthenticateSession(
            provider_type="oidc",
            identifier=None,
            password=None,
            authorization_code="oidc-secret-value",
            idempotency_key="oidc-secret",
            context=context(module),
        ),
        module.RevokeSession(
            session_token="session-secret-value",
            csrf_token="csrf-secret-value",
            idempotency_key="logout-secret",
            context=context(module),
        ),
        module.ChangePassword(
            session_token="change-session-secret",
            csrf_token="change-csrf-secret",
            current_password="current-secret-value",
            new_password="new-secret-value",
            expected_version=1,
            idempotency_key="change-secret",
            context=context(module),
        ),
    )
    secrets = (
        "register-secret-value",
        "oidc-secret-value",
        "session-secret-value",
        "csrf-secret-value",
        "change-session-secret",
        "change-csrf-secret",
        "current-secret-value",
        "new-secret-value",
    )

    with caplog.at_level(logging.INFO):
        for command in commands:
            assert all(secret not in repr(command) for secret in secrets)
            logging.getLogger("identity-test").info("command=%r", command)
    assert all(secret not in caplog.text for secret in secrets)


async def test_registration_idempotency_is_scoped_before_account_allocation(
    database_url: str,
    migration_session: AsyncSession,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = build_service(factory)
    await register_local(service, key="public-register")
    module = application()

    with pytest.raises(DomainError) as captured:
        await service.register_account(
            module.RegisterAccount(
                provider_type="local_password",
                identifier="different@example.test",
                password="different password value",
                authorization_code=None,
                idempotency_key="public-register",
                context=context(module),
            )
        )

    assert captured.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert await migration_session.scalar(text("SELECT count(*) FROM identity.accounts")) == 1
    assert await migration_session.scalar(
        text("SELECT count(*) FROM platform.command_receipts")
    ) == 1
    await engine.dispose()


async def test_logout_exact_terminal_replay_survives_revocation(
    database_url: str,
    migration_session: AsyncSession,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = build_service(factory)
    await register_local(service)
    authenticated = await authenticate_local(service)
    module = application()
    command = module.RevokeSession(
        session_token=authenticated.session_token,
        csrf_token=authenticated.csrf_token,
        idempotency_key="terminal-logout",
        context=context(module),
    )

    first = await service.revoke_session(command)
    replay = await service.revoke_session(command)

    assert replay == first
    assert await migration_session.scalar(
        text(
            "SELECT count(*) FROM platform.domain_events "
            "WHERE event_type = 'session_revoked'"
        )
    ) == 1
    with pytest.raises(DomainError) as fresh:
        await service.revoke_session(
            module.RevokeSession(
                session_token=authenticated.session_token,
                csrf_token=authenticated.csrf_token,
                idempotency_key="fresh-logout",
                context=context(module),
            )
        )
    assert fresh.value.code is ErrorCode.UNAUTHENTICATED
    await engine.dispose()


async def test_password_change_requires_version_and_supports_exact_terminal_replay(
    database_url: str,
    migration_session: AsyncSession,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = build_service(factory)
    registered = await register_local(service)
    authenticated = await authenticate_local(service)
    module = application()
    command = module.ChangePassword(
        session_token=authenticated.session_token,
        csrf_token=authenticated.csrf_token,
        current_password="correct horse battery staple",
        new_password="replacement password value",
        expected_version=registered.version,
        idempotency_key="terminal-password",
        context=context(module),
    )

    first = await service.change_password(command)
    replay = await service.change_password(command)

    assert replay == first
    assert first.version == registered.version + 1
    assert await migration_session.scalar(
        text("SELECT count(*) FROM platform.domain_events WHERE event_type = 'password_changed'")
    ) == 1
    with pytest.raises(DomainError) as conflict:
        await service.change_password(
            module.ChangePassword(
                session_token=authenticated.session_token,
                csrf_token=authenticated.csrf_token,
                current_password="correct horse battery staple",
                new_password="changed replay body value",
                expected_version=registered.version,
                idempotency_key="terminal-password",
                context=context(module),
            )
        )
    assert conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    with pytest.raises(DomainError) as fresh:
        await service.change_password(
            module.ChangePassword(
                session_token=authenticated.session_token,
                csrf_token=authenticated.csrf_token,
                current_password="replacement password value",
                new_password="another replacement value",
                expected_version=registered.version + 1,
                idempotency_key="fresh-password",
                context=context(module),
            )
        )
    assert fresh.value.code is ErrorCode.UNAUTHENTICATED
    await engine.dispose()


async def test_concurrent_password_change_uses_account_and_credential_cas(
    database_url: str,
    migration_session: AsyncSession,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = build_service(factory)
    registered = await register_local(service)
    sessions = (
        await authenticate_local(service, key="password-session-a"),
        await authenticate_local(service, key="password-session-b"),
    )
    module = application()
    commands = tuple(
        module.ChangePassword(
            session_token=session_result.session_token,
            csrf_token=session_result.csrf_token,
            current_password="correct horse battery staple",
            new_password=f"replacement password value {index}",
            expected_version=registered.version,
            idempotency_key=f"password-race-{index}",
            context=context(module),
        )
        for index, session_result in enumerate(sessions, start=1)
    )

    outcomes = await asyncio.gather(
        *(build_service(factory).change_password(command) for command in commands),
        return_exceptions=True,
    )

    successes = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
    failures = [outcome for outcome in outcomes if isinstance(outcome, DomainError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].code is ErrorCode.VERSION_CONFLICT
    assert await migration_session.scalar(
        text("SELECT version FROM identity.accounts WHERE account_id = :account_id"),
        {"account_id": registered.account_id},
    ) == registered.version + 1
    stored_hash = await migration_session.scalar(
        text(
            "SELECT password_hash FROM identity.login_identities "
            "WHERE account_id = :account_id"
        ),
        {"account_id": registered.account_id},
    )
    matches = [
        Argon2idPasswordHasher().verify(stored_hash, f"replacement password value {index}")
        for index in (1, 2)
    ]
    assert matches.count(True) == 1
    await engine.dispose()


async def test_concurrent_consent_versions_are_serialized_across_sessions(
    database_url: str,
    migration_session: AsyncSession,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = build_service(factory)
    await register_local(service)
    sessions = (
        await authenticate_local(service, key="consent-session-a"),
        await authenticate_local(service, key="consent-session-b"),
    )
    module = application()
    commands = tuple(
        module.UpdateConsent(
            session_token=session_result.session_token,
            csrf_token=session_result.csrf_token,
            purpose_code="speech_training",
            status="granted" if index == 1 else "withdrawn",
            policy_revision_id=UUID("019fe900-3000-7000-8000-000000000077"),
            expected_version=0,
            idempotency_key=f"consent-race-{index}",
            context=context(module),
        )
        for index, session_result in enumerate(sessions, start=1)
    )

    outcomes = await asyncio.gather(
        *(build_service(factory).update_consent(command) for command in commands),
        return_exceptions=True,
    )

    successes = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
    failures = [outcome for outcome in outcomes if isinstance(outcome, DomainError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].code is ErrorCode.VERSION_CONFLICT
    assert await migration_session.scalar(text("SELECT count(*) FROM identity.consent_grants")) == 1
    await engine.dispose()


async def test_registration_and_oidc_kill_switches_are_enforced(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    module = application()

    with pytest.raises(DomainError) as registration_disabled:
        await register_local(build_service(factory, registration_enabled=False))
    assert registration_disabled.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE

    oidc_disabled = build_service(factory, oidc_enabled=False)
    for command in (
        module.RegisterAccount(
            provider_type="oidc",
            identifier=None,
            password=None,
            authorization_code="oidc-register",
            idempotency_key="oidc-register-disabled",
            context=context(module),
        ),
        module.AuthenticateSession(
            provider_type="oidc",
            identifier=None,
            password=None,
            authorization_code="oidc-register",
            idempotency_key="oidc-auth-disabled",
            context=context(module),
        ),
    ):
        operation = (
            oidc_disabled.register_account
            if isinstance(command, module.RegisterAccount)
            else oidc_disabled.authenticate_session
        )
        with pytest.raises(DomainError) as disabled:
            await operation(command)
        assert disabled.value.code is ErrorCode.DEPENDENCY_UNAVAILABLE
    await engine.dispose()


async def test_global_session_revoke_is_atomic_and_explicit(
    database_url: str,
    migration_session: AsyncSession,
) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = build_service(factory)
    registered = await register_local(service)
    sessions = (
        await authenticate_local(service, key="global-session-a"),
        await authenticate_local(service, key="global-session-b"),
    )
    module = application()

    version = await service.global_revoke_sessions(
        registered.account_id,
        expected_version=registered.version,
        reason="incident_response",
        context=context(module),
    )

    assert version == registered.version + 1
    assert await migration_session.scalar(
        text(
            "SELECT count(*) FROM identity.auth_sessions "
            "WHERE account_id = :account_id AND revoked_at IS NULL"
        ),
        {"account_id": registered.account_id},
    ) == 0
    assert await migration_session.scalar(
        text("SELECT count(*) FROM platform.domain_events WHERE event_type = 'sessions_revoked'")
    ) == 1
    for authenticated in sessions:
        with pytest.raises(DomainError) as revoked:
            await service.get_current_session(authenticated.session_token)
        assert revoked.value.code is ErrorCode.UNAUTHENTICATED
    await engine.dispose()
