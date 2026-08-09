from datetime import UTC, datetime, time, timedelta
from importlib import import_module
from uuid import UUID

import pytest


NOW = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)
ACCOUNT_ID = UUID("019fe900-0000-7000-8000-000000000001")
SESSION_ID = UUID("019fe900-0000-7000-8000-000000000002")


def domain() -> object:
    try:
        return import_module("polyglot.modules.identity.domain")
    except ModuleNotFoundError:
        pytest.fail("identity domain is not implemented")


def passwords() -> object:
    try:
        return import_module("polyglot.modules.identity.passwords")
    except ModuleNotFoundError:
        pytest.fail("identity password policy is not implemented")


def test_identity_domain_exposes_exactly_the_six_canonical_roles() -> None:
    module = domain()

    assert {role.value for role in module.AccountRole} == {
        "learner",
        "author",
        "reviewer",
        "support",
        "admin",
        "worker",
    }


def test_local_identifier_normalization_is_stable_without_touching_passwords() -> None:
    module = domain()

    assert module.normalize_identifier("  SaMI\N{FULLWIDTH COMMERCIAL AT}Example.COM  ") == (
        "sami@example.com"
    )
    assert module.normalize_identifier("sami@example.com") == "sami@example.com"
    with pytest.raises(module.IdentityValidationError):
        module.normalize_identifier("   ")


def test_login_identity_accepts_only_provider_specific_non_secret_fields() -> None:
    module = domain()

    local = module.LoginIdentity.local(
        identity_id=SESSION_ID,
        account_id=ACCOUNT_ID,
        identifier=" Sami@Example.com ",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$fixture$safe",
        created_at=NOW,
    )
    oidc = module.LoginIdentity.oidc(
        identity_id=SESSION_ID,
        account_id=ACCOUNT_ID,
        issuer="https://fixture-oidc.invalid",
        subject="fixture-user-1",
        created_at=NOW,
    )

    assert local.normalized_identifier == "sami@example.com"
    assert local.issuer is None and local.subject is None
    assert oidc.password_hash is None and oidc.normalized_identifier is None
    with pytest.raises(module.IdentityValidationError):
        module.LoginIdentity.oidc(
            identity_id=SESSION_ID,
            account_id=ACCOUNT_ID,
            issuer="https://fixture-oidc.invalid",
            subject="",
            created_at=NOW,
        )


def test_argon2id_password_policy_rejects_weak_values_and_never_returns_plaintext() -> None:
    module = passwords()
    hasher = module.Argon2idPasswordHasher()

    with pytest.raises(module.PasswordPolicyError):
        hasher.hash("short")

    encoded = hasher.hash("correct horse battery staple")

    assert encoded.startswith("$argon2id$")
    assert "correct horse battery staple" not in encoded
    assert hasher.verify(encoded, "correct horse battery staple") is True
    assert hasher.verify(encoded, "wrong password value") is False
    with pytest.raises(module.PasswordPolicyError):
        hasher.verify("$argon2i$invalid", "correct horse battery staple")


def test_account_transitions_increment_security_and_revoke_stale_sessions() -> None:
    module = domain()
    account = module.Account.new(ACCOUNT_ID, NOW)

    locked = account.lock(NOW + timedelta(minutes=1))
    pending = account.request_deletion(NOW + timedelta(minutes=2))
    deleted = pending.mark_deleted(NOW + timedelta(minutes=3))

    assert account.status is module.AccountStatus.ACTIVE
    assert locked.status is module.AccountStatus.LOCKED
    assert locked.security_version == account.security_version + 1
    assert locked.session_version == account.session_version + 1
    assert pending.status is module.AccountStatus.PENDING_DELETION
    assert deleted.status is module.AccountStatus.DELETED
    assert deleted.deleted_at == NOW + timedelta(minutes=3)
    with pytest.raises(module.InvalidIdentityTransition):
        account.mark_deleted(NOW)


def test_role_change_requires_canonical_roles_and_invalidates_sessions() -> None:
    module = domain()
    account = module.Account.new(ACCOUNT_ID, NOW)

    unchanged = account.replace_roles(frozenset({module.AccountRole.LEARNER}), NOW)
    changed = account.replace_roles(
        frozenset({module.AccountRole.LEARNER, module.AccountRole.AUTHOR}),
        NOW + timedelta(minutes=1),
    )

    assert unchanged is account
    assert changed.roles == frozenset({module.AccountRole.LEARNER, module.AccountRole.AUTHOR})
    assert changed.session_version == account.session_version + 1
    with pytest.raises(module.IdentityValidationError):
        account.replace_roles(frozenset(), NOW)


@pytest.mark.parametrize(
    ("roles", "idle_for"),
    [
        (frozenset({"learner"}), timedelta(hours=12)),
        (frozenset({"learner", "author"}), timedelta(minutes=30)),
        (frozenset({"learner", "reviewer"}), timedelta(minutes=30)),
        (frozenset({"learner", "support"}), timedelta(minutes=30)),
        (frozenset({"learner", "admin"}), timedelta(minutes=30)),
    ],
)
def test_session_uses_exact_idle_and_absolute_deadlines(
    roles: frozenset[str],
    idle_for: timedelta,
) -> None:
    module = domain()
    canonical_roles = frozenset(module.AccountRole(role) for role in roles)

    session = module.AuthSession.issue(
        session_id=SESSION_ID,
        account_id=ACCOUNT_ID,
        session_fingerprint="a" * 64,
        csrf_secret_hash="b" * 64,
        roles=canonical_roles,
        account_session_version=3,
        now=NOW,
    )

    assert session.idle_expires_at == NOW + idle_for
    assert session.absolute_expires_at == NOW + timedelta(days=7)
    assert session.is_active(NOW + idle_for - timedelta(microseconds=1), 3)
    assert not session.is_active(NOW + idle_for, 3)
    assert not session.is_active(NOW + timedelta(days=7), 3)


def test_interactive_worker_session_is_refused() -> None:
    module = domain()

    with pytest.raises(module.IdentityValidationError):
        module.AuthSession.issue(
            session_id=SESSION_ID,
            account_id=ACCOUNT_ID,
            session_fingerprint="a" * 64,
            csrf_secret_hash="b" * 64,
            roles=frozenset({module.AccountRole.WORKER}),
            account_session_version=1,
            now=NOW,
        )


def test_session_touch_is_bounded_by_absolute_expiry_and_rotation_is_exact() -> None:
    module = domain()
    session = module.AuthSession.issue(
        session_id=SESSION_ID,
        account_id=ACCOUNT_ID,
        session_fingerprint="a" * 64,
        csrf_secret_hash="b" * 64,
        roles=frozenset({module.AccountRole.LEARNER}),
        account_session_version=1,
        now=NOW,
    )

    touched = session.touch(NOW + timedelta(days=6, hours=23))

    assert touched.idle_expires_at == session.absolute_expires_at
    assert not session.requires_rotation(NOW + timedelta(hours=24) - timedelta(microseconds=1), 1)
    assert session.requires_rotation(NOW + timedelta(hours=24), 1)
    assert session.requires_rotation(NOW + timedelta(minutes=1), 2)


def test_session_revoke_is_individual_and_idempotent() -> None:
    module = domain()
    session = module.AuthSession.issue(
        session_id=SESSION_ID,
        account_id=ACCOUNT_ID,
        session_fingerprint="a" * 64,
        csrf_secret_hash="b" * 64,
        roles=frozenset({module.AccountRole.LEARNER}),
        account_session_version=1,
        now=NOW,
    )

    revoked = session.revoke(NOW + timedelta(minutes=1), "logout")

    assert revoked.revoked_at == NOW + timedelta(minutes=1)
    assert revoked.revoke_reason == "logout"
    assert revoked.revoke(NOW + timedelta(minutes=2), "again") is revoked
    assert not revoked.is_active(NOW + timedelta(minutes=1), 1)


def test_session_tokens_are_opaque_and_csrf_is_bound_to_the_session() -> None:
    module = domain()
    secrets = module.SessionSecrets.from_key(b"x" * 32)

    first = secrets.issue(SESSION_ID)
    second = secrets.issue(UUID("019fe900-0000-7000-8000-000000000003"))

    assert first.session_token != str(SESSION_ID)
    assert first.csrf_token != second.csrf_token
    assert len(first.session_fingerprint) == 64
    assert module.verify_session_csrf(
        first.session_fingerprint,
        first.csrf_token,
        first.csrf_secret_hash,
    )
    assert not module.verify_session_csrf(
        first.session_fingerprint,
        second.csrf_token,
        first.csrf_secret_hash,
    )


def test_preferences_validate_timezone_cutover_and_five_minute_steps() -> None:
    module = domain()

    preferences = module.UserPreferences.defaults(ACCOUNT_ID, NOW)
    updated = preferences.update(
        interface_locale="fr-FR",
        timezone="Europe/Paris",
        day_cutover_local_time=time(4, 30),
        preferred_sprint_minutes=35,
        accessibility_preferences={"schema_version": 1, "reduced_motion": True},
        media_preferences={"schema_version": 1, "autoplay_audio": False},
        now=NOW + timedelta(minutes=1),
    )

    assert preferences.preferred_sprint_minutes == 20
    assert updated.version == preferences.version + 1
    with pytest.raises(module.IdentityValidationError):
        preferences.update(preferred_sprint_minutes=33, now=NOW)
    with pytest.raises(module.IdentityValidationError):
        preferences.update(timezone="Not/AZone", now=NOW)


def test_consent_grant_and_withdrawal_are_new_append_only_decisions() -> None:
    module = domain()
    policy_revision_id = UUID("019fe900-0000-7000-8000-000000000004")

    granted = module.ConsentDecision.decide(
        consent_id=SESSION_ID,
        account_id=ACCOUNT_ID,
        purpose_code="speech_training",
        status=module.ConsentStatus.GRANTED,
        policy_revision_id=policy_revision_id,
        version=1,
        now=NOW,
    )
    withdrawn = granted.next(
        consent_id=UUID("019fe900-0000-7000-8000-000000000005"),
        status=module.ConsentStatus.WITHDRAWN,
        policy_revision_id=policy_revision_id,
        now=NOW + timedelta(days=1),
    )

    assert granted.withdrawn_at is None
    assert withdrawn.version == 2
    assert withdrawn.withdrawn_at == NOW + timedelta(days=1)
    assert withdrawn.consent_id != granted.consent_id


def test_authorization_requires_actor_action_resource_and_owner_scope() -> None:
    module = domain()
    policy = module.AuthorizationPolicy()
    actor = module.Actor(
        account_id=ACCOUNT_ID,
        roles=frozenset({module.AccountRole.LEARNER}),
    )
    other_id = UUID("019fe900-0000-7000-8000-000000000099")

    assert policy.allows(
        actor,
        action=module.IdentityAction.READ_SESSION,
        resource_type="account",
        resource_id=ACCOUNT_ID,
        scope="owner",
    )
    assert not policy.allows(
        actor,
        action=module.IdentityAction.READ_SESSION,
        resource_type="account",
        resource_id=other_id,
        scope="owner",
    )
    assert not policy.allows(
        actor,
        action="unknown",
        resource_type="account",
        resource_id=ACCOUNT_ID,
        scope="owner",
    )


def test_fake_oidc_accepts_only_declared_fixture_assertions() -> None:
    module = domain()
    provider = module.FakeOidcProvider(
        {
            "fixture-code": module.OidcAssertion(
                issuer="https://fixture-oidc.invalid",
                subject="fixture-user-1",
            )
        }
    )

    assert provider.authenticate("fixture-code").subject == "fixture-user-1"
    with pytest.raises(module.InvalidOidcAssertion):
        provider.authenticate("unknown-code")
