import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

OWNER_A = UUID("019fe900-1000-7000-8000-000000000001")
OWNER_B = UUID("019fe900-1000-7000-8000-000000000002")
IDENTITY_A = UUID("019fe900-1000-7000-8000-000000000011")
IDENTITY_B = UUID("019fe900-1000-7000-8000-000000000012")
NOW = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)


async def seed_account(
    database_session: AsyncSession,
    *,
    account_id: UUID,
    identity_id: UUID,
    identifier: str,
) -> None:
    await database_session.execute(
        text(
            "INSERT INTO identity.accounts "
            "(account_id, status, security_version, session_version, version, "
            "created_at, security_last_activity_at, deleted_at) "
            "VALUES (:account_id, 'active', 1, 1, 1, :now, :now, NULL)"
        ),
        {"account_id": account_id, "now": NOW},
    )
    await database_session.execute(
        text(
            "INSERT INTO identity.login_identities "
            "(identity_id, account_id, provider_type, normalized_identifier, "
            "password_hash, issuer, subject, created_at, last_authenticated_at, revoked_at) "
            "VALUES (:identity_id, :account_id, 'local_password', :identifier, "
            ":password_hash, NULL, NULL, :now, NULL, NULL)"
        ),
        {
            "identity_id": identity_id,
            "account_id": account_id,
            "identifier": identifier,
            "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$fixture$safe",
            "now": NOW,
        },
    )
    await database_session.execute(
        text(
            "INSERT INTO identity.account_roles "
            "(role_grant_id, account_id, role, granted_at, granted_by_actor_id, revoked_at) "
            "VALUES (:role_grant_id, :account_id, 'learner', :now, :account_id, NULL)"
        ),
        {
            "role_grant_id": UUID(
                "019fe900-1000-7000-8000-000000000021"
                if account_id == OWNER_A
                else "019fe900-1000-7000-8000-000000000022"
            ),
            "account_id": account_id,
            "now": NOW,
        },
    )
    await database_session.execute(
        text(
            "INSERT INTO identity.user_preferences "
            "(account_id, interface_locale, timezone, day_cutover_local_time, "
            "preferred_sprint_minutes, accessibility_preferences, media_preferences, "
            "preferred_voice_id, voice_catalog_revision_id, version, created_at, updated_at) "
            "VALUES (:account_id, 'en', 'UTC', '04:00', 20, "
            "'{\"schema_version\": 1}'::jsonb, '{\"schema_version\": 1}'::jsonb, "
            "NULL, NULL, 1, :now, :now)"
        ),
        {"account_id": account_id, "now": NOW},
    )


async def test_0002_identity_creates_the_owned_schema_and_tables(
    migration_session: AsyncSession,
) -> None:
    rows = await migration_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'identity'"
        )
    )
    owner = await migration_session.scalar(
        text(
            "SELECT owner.rolname FROM pg_namespace AS namespace "
            "JOIN pg_roles AS owner ON owner.oid = namespace.nspowner "
            "WHERE namespace.nspname = 'identity'"
        )
    )

    assert set(rows.scalars()) == {
        "accounts",
        "login_identities",
        "account_roles",
        "auth_sessions",
        "user_preferences",
        "consent_purposes",
        "consent_grants",
    }
    assert owner == "polyglot_migration"


async def test_0002_identity_has_strict_constraints_indexes_rls_and_runtime_grants(
    migration_session: AsyncSession,
) -> None:
    constraint_names = set(
        (
            await migration_session.execute(
                text(
                    "SELECT conname FROM pg_constraint AS item "
                    "JOIN pg_namespace AS namespace "
                    "ON namespace.oid = item.connamespace "
                    "WHERE namespace.nspname = 'identity'"
                )
            )
        ).scalars()
    )
    index_names = set(
        (
            await migration_session.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'identity'")
            )
        ).scalars()
    )
    rls_tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT relation.relname FROM pg_class AS relation "
                    "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
                    "WHERE namespace.nspname = 'identity' AND relation.relrowsecurity"
                )
            )
        ).scalars()
    )
    forced_rls_tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT relation.relname FROM pg_class AS relation "
                    "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
                    "WHERE namespace.nspname = 'identity' AND relation.relforcerowsecurity"
                )
            )
        ).scalars()
    )
    session_columns = set(
        (
            await migration_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'identity' AND table_name = 'auth_sessions'"
                )
            )
        ).scalars()
    )

    assert {
        "ck_account_uuid7",
        "ck_identity_uuid7",
        "ck_identity_provider_shape",
        "ck_session_uuid7",
        "ck_session_expiry_order",
        "ck_session_replacement_shape",
        "fk_session_replacement",
        "ck_preferences_sprint_minutes",
        "ck_consent_withdrawal_shape",
        "uq_consent_account_purpose_version",
    } <= constraint_names
    assert "replaced_by_session_id" in session_columns
    assert {
        "uq_login_identity_local_active",
        "uq_login_identity_oidc_active",
        "uq_account_role_active",
        "ix_auth_sessions_idle_expires_at",
        "ix_auth_sessions_absolute_expires_at",
        "ix_consent_grants_account_purpose_decided",
    } <= index_names
    assert rls_tables == {
        "accounts",
        "login_identities",
        "account_roles",
        "auth_sessions",
        "user_preferences",
        "consent_grants",
    }
    assert forced_rls_tables == set()
    assert await migration_session.scalar(
        text("SELECT has_schema_privilege('polyglot_runtime', 'identity', 'USAGE')")
    )
    assert not await migration_session.scalar(
        text("SELECT has_schema_privilege('public', 'identity', 'USAGE')")
    )


def test_0002_destructive_downgrade_requires_explicit_disposable_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = Path(__file__).resolve().parents[3] / "migrations/versions/0002_identity.py"
    spec = importlib.util.spec_from_file_location("identity_migration_0002", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    executed: list[str] = []
    monkeypatch.setattr(migration.op, "execute", executed.append)
    monkeypatch.delenv("POLYGLOT_ALLOW_DESTRUCTIVE_IDENTITY_DOWNGRADE", raising=False)

    with pytest.raises(RuntimeError, match=r"disposable.*data loss"):
        migration.downgrade()

    monkeypatch.setenv("POLYGLOT_ALLOW_DESTRUCTIVE_IDENTITY_DOWNGRADE", "true")
    migration.downgrade()
    assert executed == ["DROP SCHEMA identity CASCADE"]


async def test_local_and_oidc_identity_uniqueness_and_argon2id_are_database_enforced(
    migration_session: AsyncSession,
) -> None:
    await seed_account(
        migration_session,
        account_id=OWNER_A,
        identity_id=IDENTITY_A,
        identifier="owner-a@example.test",
    )
    await seed_account(
        migration_session,
        account_id=OWNER_B,
        identity_id=IDENTITY_B,
        identifier="owner-b@example.test",
    )
    await migration_session.flush()

    with pytest.raises(IntegrityError):
        await migration_session.execute(
            text(
                "INSERT INTO identity.login_identities "
                "(identity_id, account_id, provider_type, normalized_identifier, "
                "password_hash, issuer, subject, created_at, last_authenticated_at, revoked_at) "
                "VALUES ('019fe900-1000-7000-8000-000000000031', :account_id, "
                "'local_password', 'owner-a@example.test', 'plaintext', "
                "NULL, NULL, :now, NULL, NULL)"
            ),
            {"account_id": OWNER_B, "now": NOW},
        )

    await migration_session.rollback()
    await seed_account(
        migration_session,
        account_id=OWNER_A,
        identity_id=IDENTITY_A,
        identifier="owner-a@example.test",
    )
    await seed_account(
        migration_session,
        account_id=OWNER_B,
        identity_id=IDENTITY_B,
        identifier="owner-b@example.test",
    )
    await migration_session.execute(
        text(
            "INSERT INTO identity.login_identities "
            "(identity_id, account_id, provider_type, normalized_identifier, password_hash, "
            "issuer, subject, created_at, last_authenticated_at, revoked_at) "
            "VALUES ('019fe900-1000-7000-8000-000000000032', :account_id, 'oidc', "
            "NULL, NULL, 'https://fixture-oidc.invalid', 'subject-a', :now, NULL, NULL)"
        ),
        {"account_id": OWNER_A, "now": NOW},
    )
    await migration_session.flush()

    with pytest.raises(IntegrityError):
        await migration_session.execute(
            text(
                "INSERT INTO identity.login_identities "
                "(identity_id, account_id, provider_type, normalized_identifier, password_hash, "
                "issuer, subject, created_at, last_authenticated_at, revoked_at) "
                "VALUES ('019fe900-1000-7000-8000-000000000033', :account_id, 'oidc', "
                "NULL, NULL, 'https://fixture-oidc.invalid', 'subject-a', :now, NULL, NULL)"
            ),
            {"account_id": OWNER_B, "now": NOW},
        )


async def test_runtime_rls_uses_transaction_local_app_user_id_and_hides_other_owner(
    migration_session: AsyncSession,
    session: AsyncSession,
) -> None:
    await seed_account(
        migration_session,
        account_id=OWNER_A,
        identity_id=IDENTITY_A,
        identifier="owner-a@example.test",
    )
    await seed_account(
        migration_session,
        account_id=OWNER_B,
        identity_id=IDENTITY_B,
        identifier="owner-b@example.test",
    )
    await migration_session.commit()

    assert (
        await session.execute(text("SELECT account_id FROM identity.user_preferences"))
    ).all() == []
    await session.execute(
        text("SELECT set_config('app.user_id', :account_id, true)"),
        {"account_id": str(OWNER_A)},
    )
    visible = (
        await session.execute(text("SELECT account_id FROM identity.user_preferences"))
    ).scalars()

    assert set(visible) == {OWNER_A}
    await session.commit()
    assert await session.scalar(text("SELECT current_setting('app.user_id', true)")) == ""
    assert (
        await session.execute(text("SELECT account_id FROM identity.user_preferences"))
    ).all() == []


async def test_session_expiry_order_and_append_only_consent_history_are_enforced(
    migration_session: AsyncSession,
) -> None:
    await seed_account(
        migration_session,
        account_id=OWNER_A,
        identity_id=IDENTITY_A,
        identifier="owner-a@example.test",
    )
    with pytest.raises(IntegrityError):
        await migration_session.execute(
            text(
                "INSERT INTO identity.auth_sessions "
                "(session_id, account_id, session_fingerprint, csrf_secret_hash, "
                "roles_snapshot, account_session_version, created_at, authenticated_at, "
                "last_seen_at, rotated_at, idle_expires_at, absolute_expires_at, "
                "revoked_at, revoke_reason) VALUES "
                "('019fe900-1000-7000-8000-000000000041', :account_id, :fingerprint, "
                ":csrf_hash, ARRAY['learner'], 1, :now, :now, :now, :now, "
                ":absolute_expiry, :idle_expiry, NULL, NULL)"
            ),
            {
                "account_id": OWNER_A,
                "fingerprint": "a" * 64,
                "csrf_hash": "b" * 64,
                "now": NOW,
                "absolute_expiry": NOW + timedelta(days=7),
                "idle_expiry": NOW + timedelta(hours=12),
            },
        )

    await migration_session.rollback()
    await seed_account(
        migration_session,
        account_id=OWNER_A,
        identity_id=IDENTITY_A,
        identifier="owner-a@example.test",
    )
    await migration_session.execute(
        text(
            "INSERT INTO identity.consent_grants "
            "(consent_id, account_id, purpose_code, status, policy_revision_id, version, "
            "decided_at, withdrawn_at) VALUES "
            "('019fe900-1000-7000-8000-000000000051', :account_id, 'speech_training', "
            "'granted', '019fe900-1000-7000-8000-000000000052', 1, :now, NULL)"
        ),
        {"account_id": OWNER_A, "now": NOW},
    )
    await migration_session.flush()

    with pytest.raises(DBAPIError):
        await migration_session.execute(
            text(
                "UPDATE identity.consent_grants SET status = 'withdrawn' "
                "WHERE account_id = :account_id"
            ),
            {"account_id": OWNER_A},
        )


async def test_pre_authentication_lookup_is_narrow_and_not_public(
    migration_session: AsyncSession,
) -> None:
    functions = (
        await migration_session.execute(
            text(
                "SELECT procedure.proname, procedure.prosecdef, "
                "has_function_privilege('public', procedure.oid, 'EXECUTE'), "
                "has_function_privilege('polyglot_runtime', procedure.oid, 'EXECUTE') "
                "FROM pg_proc AS procedure "
                "JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace "
                "WHERE namespace.nspname = 'identity' "
                "AND procedure.proname IN "
                "('lookup_local_identity', 'lookup_oidc_identity', 'lookup_session')"
            )
        )
    ).all()

    assert set(functions) == {
        ("lookup_local_identity", True, False, True),
        ("lookup_oidc_identity", True, False, True),
        ("lookup_session", True, False, True),
    }
