import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from polyglot.modules.identity.domain import (
    AccountRole,
    Actor,
    AuthorizationPolicy,
    FakeOidcProvider,
    IdentityAction,
    OidcAssertion,
)

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "fixtures/canonical"
EXPECTED_ROLES = {role.value for role in AccountRole}
FORBIDDEN_SECRET_FIELDS = {
    "password",
    "plaintext_password",
    "authorization_code",
    "access_token",
    "refresh_token",
    "id_token",
    "recovery_secret",
    "session_token",
    "csrf_token",
}


def _load_fixture(code: str, payload_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    fixture = FIXTURES / code
    manifest = json.loads((fixture / "manifest.json").read_text())
    payload_path = fixture / payload_name
    payload = json.loads(payload_path.read_text())
    fingerprint = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    assert manifest["payloads"] == {payload_name: f"sha256:{fingerprint}"}
    return manifest, payload


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested_key
            for nested in value.values()
            for nested_key in _all_keys(nested)
        }
    if isinstance(value, list):
        return {nested_key for nested in value for nested_key in _all_keys(nested)}
    return set()


def test_fx_users_manifest_has_clock_seed_fingerprint_and_owner_oracles() -> None:
    manifest, users = _load_fixture("FX-USERS", "users.json")

    assert manifest["fixture_code"] == "FX-USERS"
    assert manifest["schema_version"] == 1
    assert manifest["synthetic"] is True
    assert isinstance(manifest["seed"], int)
    assert datetime.fromisoformat(manifest["clock"])
    assert set(manifest["oracles"]) == {
        "all_six_roles_present",
        "owner_can_read_own_account",
        "owner_cannot_read_foreign_account",
    }
    assert {grant["role"] for grant in users["role_grants"]} == EXPECTED_ROLES

    account_ids = {account["account_id"] for account in users["accounts"]}
    assert len(account_ids) == 6
    assert all(UUID(account_id).version == 7 for account_id in account_ids)
    assert users["local_identity"]["password_hash"].startswith("$argon2id$")

    owner_cases = users["authorization_oracles"]
    assert {case["expected"] for case in owner_cases} == {"allowed", "forbidden"}
    policy = AuthorizationPolicy()
    for case in owner_cases:
        allowed = policy.allows(
            Actor(
                account_id=UUID(case["actor_account_id"]),
                roles=frozenset({AccountRole.LEARNER}),
            ),
            action=IdentityAction.READ_SESSION,
            resource_type="account",
            resource_id=UUID(case["resource_account_id"]),
            scope="owner",
        )
        assert allowed is (case["expected"] == "allowed")


def test_fx_auth_covers_expiry_invalid_csrf_fake_oidc_and_role_rotation() -> None:
    manifest, auth = _load_fixture("FX-AUTH", "auth.json")

    assert manifest["fixture_code"] == "FX-AUTH"
    assert manifest["schema_version"] == 1
    assert manifest["synthetic"] is True
    assert isinstance(manifest["seed"], int)
    clock = datetime.fromisoformat(manifest["clock"])
    assert set(manifest["oracles"]) == {
        "expired_session_rejected",
        "invalid_csrf_rejected",
        "fake_oidc_accepted",
        "role_change_rotates_session",
    }

    expired = auth["expired_session"]
    assert datetime.fromisoformat(expired["absolute_expires_at"]) <= clock
    assert expired["expected_error"] == "session_expired"

    csrf = auth["invalid_csrf"]
    assert csrf["stored_csrf_hash"] != csrf["presented_csrf_hash"]
    assert csrf["expected_error"] == "forbidden"

    claims = auth["fake_oidc"]
    provider = FakeOidcProvider(
        {
            str(manifest["seed"]): OidcAssertion(
                issuer=claims["issuer"],
                subject=claims["subject"],
            )
        }
    )
    assert provider.authenticate(str(manifest["seed"])) == OidcAssertion(
        issuer=claims["issuer"],
        subject=claims["subject"],
    )

    role_change = auth["role_change"]
    assert role_change["session_roles"] != role_change["current_roles"]
    assert role_change["expected_action"] == "rotate_session"


def test_canonical_identity_fixtures_never_store_plaintext_secrets_or_tokens() -> None:
    documents = []
    for fixture_code, payload_name in (
        ("FX-USERS", "users.json"),
        ("FX-AUTH", "auth.json"),
    ):
        manifest, payload = _load_fixture(fixture_code, payload_name)
        documents.extend((manifest, payload))

    assert not (set().union(*(_all_keys(document) for document in documents)) & FORBIDDEN_SECRET_FIELDS)
