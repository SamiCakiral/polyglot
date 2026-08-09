from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 8, 10, 10, 0, tzinfo=UTC)
ACCOUNT_ID = UUID("019fe900-2000-7000-8000-000000000001")
IDENTITY_ID = UUID("019fe900-2000-7000-8000-000000000002")
SESSION_ID = UUID("019fe900-2000-7000-8000-000000000003")
POLICY_ID = UUID("019fe900-2000-7000-8000-000000000004")


def persistence() -> object:
    try:
        return import_module("polyglot.modules.identity.persistence")
    except ModuleNotFoundError:
        pytest.fail("identity persistence is not implemented")


async def add_local_account(repository: object) -> object:
    from polyglot.modules.identity.domain import Account, LoginIdentity, UserPreferences

    account = Account.new(ACCOUNT_ID, NOW)
    identity = LoginIdentity.local(
        identity_id=IDENTITY_ID,
        account_id=ACCOUNT_ID,
        identifier="owner@example.test",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$fixture$safe",
        created_at=NOW,
    )
    preferences = UserPreferences.defaults(ACCOUNT_ID, NOW)
    await repository.set_actor(ACCOUNT_ID)
    await repository.add_account(account, identity, preferences)
    return account


async def test_repository_round_trips_account_identity_roles_and_preferences(
    session: AsyncSession,
) -> None:
    module = persistence()
    repository = module.SqlIdentityRepository(session)
    await add_local_account(repository)
    await session.flush()

    stored = await repository.get_account(ACCOUNT_ID)
    authentication = await repository.find_local_for_authentication("owner@example.test")

    assert stored.account_id == ACCOUNT_ID
    assert {role.value for role in stored.roles} == {"learner"}
    assert authentication.account.account_id == ACCOUNT_ID
    assert authentication.identity.password_hash.startswith("$argon2id$")
    assert authentication.preferences.version == 1


async def test_repository_finds_opaque_session_before_setting_owner_scope(
    session: AsyncSession,
) -> None:
    from polyglot.modules.identity.domain import AccountRole, AuthSession

    module = persistence()
    repository = module.SqlIdentityRepository(session)
    await add_local_account(repository)
    auth_session = AuthSession.issue(
        session_id=SESSION_ID,
        account_id=ACCOUNT_ID,
        session_fingerprint="a" * 64,
        csrf_secret_hash="b" * 64,
        roles=frozenset({AccountRole.LEARNER}),
        account_session_version=1,
        now=NOW,
    )
    await repository.add_session(auth_session)
    await session.commit()

    resolved = await repository.find_session_for_authentication("a" * 64)

    assert resolved.session.session_id == SESSION_ID
    assert resolved.account.account_id == ACCOUNT_ID
    assert resolved.session.is_active(NOW + timedelta(hours=1), 1)
    assert await repository.get_preferences(ACCOUNT_ID) is not None


async def test_repository_rejects_stale_preference_write_and_cross_owner_read(
    session: AsyncSession,
) -> None:
    module = persistence()
    repository = module.SqlIdentityRepository(session)
    await add_local_account(repository)
    await session.flush()
    preferences = await repository.get_preferences(ACCOUNT_ID)
    updated = preferences.update(interface_locale="fr-FR", now=NOW + timedelta(minutes=1))

    await repository.update_preferences(updated, expected_version=1)
    with pytest.raises(DomainError) as captured:
        await repository.update_preferences(updated, expected_version=1)

    assert captured.value.code is ErrorCode.VERSION_CONFLICT
    other_id = UUID("019fe900-2000-7000-8000-000000000099")
    await repository.set_actor(other_id)
    assert await repository.get_preferences(ACCOUNT_ID) is None


async def test_repository_appends_consent_versions_and_returns_only_latest(
    session: AsyncSession,
) -> None:
    from polyglot.modules.identity.domain import ConsentDecision, ConsentStatus

    module = persistence()
    repository = module.SqlIdentityRepository(session)
    await add_local_account(repository)
    granted = ConsentDecision.decide(
        consent_id=UUID("019fe900-2000-7000-8000-000000000011"),
        account_id=ACCOUNT_ID,
        purpose_code="speech_training",
        status=ConsentStatus.GRANTED,
        policy_revision_id=POLICY_ID,
        version=1,
        now=NOW,
    )
    withdrawn = granted.next(
        consent_id=UUID("019fe900-2000-7000-8000-000000000012"),
        status=ConsentStatus.WITHDRAWN,
        policy_revision_id=POLICY_ID,
        now=NOW + timedelta(days=1),
    )

    await repository.add_consent(granted, expected_version=0)
    await repository.add_consent(withdrawn, expected_version=1)
    latest = await repository.get_current_consents(ACCOUNT_ID)

    assert latest == {"speech_training": withdrawn}
    with pytest.raises(DomainError) as captured:
        await repository.add_consent(withdrawn, expected_version=1)
    assert captured.value.code is ErrorCode.VERSION_CONFLICT


async def test_global_revoke_updates_account_version_and_every_open_session(
    session: AsyncSession,
) -> None:
    from polyglot.modules.identity.domain import AccountRole, AuthSession

    module = persistence()
    repository = module.SqlIdentityRepository(session)
    await add_local_account(repository)
    auth_session = AuthSession.issue(
        session_id=SESSION_ID,
        account_id=ACCOUNT_ID,
        session_fingerprint="c" * 64,
        csrf_secret_hash="d" * 64,
        roles=frozenset({AccountRole.LEARNER}),
        account_session_version=1,
        now=NOW,
    )
    await repository.add_session(auth_session)

    new_version = await repository.revoke_all_sessions(
        ACCOUNT_ID,
        now=NOW + timedelta(minutes=1),
        reason="password_changed",
    )
    resolved = await repository.find_session_for_authentication("c" * 64)

    assert new_version == 2
    assert resolved.session.revoked_at == NOW + timedelta(minutes=1)
    assert resolved.account.session_version == 2
