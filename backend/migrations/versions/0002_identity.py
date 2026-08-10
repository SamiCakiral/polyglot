"""Create identity, session, preference, and consent persistence.

Downgrade is disposable-environment-only because it permanently deletes all
identity, consent, preference, and session data.

Revision ID: 0002_identity
Revises: 0001_platform
"""

import os

from alembic import op
from asyncpg import Connection

revision = "0002_identity"
down_revision = "0001_platform"
branch_labels = None
depends_on = None


IDENTITY_DDL = r"""
CREATE SCHEMA identity;

CREATE FUNCTION identity.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $function$
    SELECT value IS NOT NULL AND (get_byte(uuid_send(value), 6) >> 4) = 7
$function$;

CREATE FUNCTION identity.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE
AS $function$
    SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
$function$;

CREATE TABLE identity.accounts (
    account_id uuid PRIMARY KEY,
    status varchar(32) NOT NULL,
    security_version integer NOT NULL,
    session_version integer NOT NULL,
    version integer NOT NULL,
    created_at timestamptz NOT NULL,
    security_last_activity_at timestamptz NOT NULL,
    deleted_at timestamptz,
    CONSTRAINT ck_account_uuid7 CHECK (identity.is_uuid7(account_id)),
    CONSTRAINT ck_account_status CHECK (
        status IN ('active', 'locked', 'pending_deletion', 'deleted')
    ),
    CONSTRAINT ck_account_versions CHECK (
        security_version >= 1 AND session_version >= 1 AND version >= 1
    ),
    CONSTRAINT ck_account_deleted_shape CHECK (
        (status = 'deleted') = (deleted_at IS NOT NULL)
    )
);

CREATE TABLE identity.login_identities (
    identity_id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
    provider_type varchar(32) NOT NULL,
    normalized_identifier varchar(320),
    password_hash text,
    issuer varchar(500),
    subject varchar(500),
    created_at timestamptz NOT NULL,
    last_authenticated_at timestamptz,
    revoked_at timestamptz,
    CONSTRAINT ck_identity_uuid7 CHECK (
        identity.is_uuid7(identity_id) AND identity.is_uuid7(account_id)
    ),
    CONSTRAINT ck_identity_provider_type CHECK (
        provider_type IN ('local_password', 'oidc')
    ),
    CONSTRAINT ck_identity_provider_shape CHECK (
        (
            provider_type = 'local_password'
            AND normalized_identifier IS NOT NULL
            AND password_hash LIKE '$argon2id$%'
            AND issuer IS NULL
            AND subject IS NULL
        ) OR (
            provider_type = 'oidc'
            AND normalized_identifier IS NULL
            AND password_hash IS NULL
            AND issuer IS NOT NULL
            AND subject IS NOT NULL
        )
    )
);
CREATE UNIQUE INDEX uq_login_identity_local_active
    ON identity.login_identities (normalized_identifier)
    WHERE provider_type = 'local_password' AND revoked_at IS NULL;
CREATE UNIQUE INDEX uq_login_identity_oidc_active
    ON identity.login_identities (issuer, subject)
    WHERE provider_type = 'oidc' AND revoked_at IS NULL;
CREATE INDEX ix_login_identities_account_id
    ON identity.login_identities (account_id);

CREATE TABLE identity.account_roles (
    role_grant_id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
    role varchar(32) NOT NULL,
    granted_at timestamptz NOT NULL,
    granted_by_actor_id uuid NOT NULL,
    revoked_at timestamptz,
    CONSTRAINT ck_account_role_uuid7 CHECK (
        identity.is_uuid7(role_grant_id)
        AND identity.is_uuid7(account_id)
        AND identity.is_uuid7(granted_by_actor_id)
    ),
    CONSTRAINT ck_account_role CHECK (
        role IN ('learner', 'author', 'reviewer', 'support', 'admin', 'worker')
    ),
    CONSTRAINT ck_account_role_revoke_order CHECK (
        revoked_at IS NULL OR revoked_at >= granted_at
    )
);
CREATE UNIQUE INDEX uq_account_role_active
    ON identity.account_roles (account_id, role)
    WHERE revoked_at IS NULL;
CREATE INDEX ix_account_roles_account_id ON identity.account_roles (account_id);

CREATE TABLE identity.auth_sessions (
    session_id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
    session_fingerprint varchar(64) NOT NULL UNIQUE,
    csrf_secret_hash varchar(64) NOT NULL,
    roles_snapshot varchar(32)[] NOT NULL,
    account_session_version integer NOT NULL,
    created_at timestamptz NOT NULL,
    authenticated_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    rotated_at timestamptz NOT NULL,
    idle_expires_at timestamptz NOT NULL,
    absolute_expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    revoke_reason varchar(120),
    replaced_by_session_id uuid,
    CONSTRAINT ck_session_uuid7 CHECK (
        identity.is_uuid7(session_id) AND identity.is_uuid7(account_id)
    ),
    CONSTRAINT ck_session_fingerprints CHECK (
        session_fingerprint ~ '^[0-9a-f]{64}$'
        AND csrf_secret_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_session_roles CHECK (
        cardinality(roles_snapshot) >= 1
        AND NOT roles_snapshot && ARRAY['worker']::varchar[]
        AND roles_snapshot <@ ARRAY[
            'learner', 'author', 'reviewer', 'support', 'admin'
        ]::varchar[]
    ),
    CONSTRAINT ck_session_version CHECK (account_session_version >= 1),
    CONSTRAINT ck_session_expiry_order CHECK (
        authenticated_at <= created_at
        AND created_at <= last_seen_at
        AND created_at <= rotated_at
        AND last_seen_at < idle_expires_at
        AND idle_expires_at <= absolute_expires_at
        AND absolute_expires_at = authenticated_at + interval '7 days'
    ),
    CONSTRAINT ck_session_revoke_shape CHECK (
        (revoked_at IS NULL AND revoke_reason IS NULL)
        OR (revoked_at IS NOT NULL AND revoke_reason IS NOT NULL)
    ),
    CONSTRAINT ck_session_replacement_shape CHECK (
        replaced_by_session_id IS NULL OR (
            revoked_at IS NOT NULL
            AND revoke_reason IN ('role_changed', 'periodic_rotation')
            AND identity.is_uuid7(replaced_by_session_id)
        )
    ),
    CONSTRAINT uq_session_replacement UNIQUE (replaced_by_session_id),
    CONSTRAINT fk_session_replacement FOREIGN KEY (replaced_by_session_id)
        REFERENCES identity.auth_sessions(session_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX ix_auth_sessions_account_id ON identity.auth_sessions (account_id);
CREATE INDEX ix_auth_sessions_idle_expires_at ON identity.auth_sessions (idle_expires_at);
CREATE INDEX ix_auth_sessions_absolute_expires_at
    ON identity.auth_sessions (absolute_expires_at);
CREATE INDEX ix_auth_sessions_open_account
    ON identity.auth_sessions (account_id, created_at)
    WHERE revoked_at IS NULL;

CREATE TABLE identity.user_preferences (
    account_id uuid PRIMARY KEY REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
    interface_locale varchar(35) NOT NULL,
    timezone varchar(120) NOT NULL,
    day_cutover_local_time time NOT NULL,
    preferred_sprint_minutes integer NOT NULL,
    accessibility_preferences jsonb NOT NULL,
    media_preferences jsonb NOT NULL,
    preferred_voice_id uuid,
    voice_catalog_revision_id uuid,
    version integer NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT ck_preferences_uuid7 CHECK (identity.is_uuid7(account_id)),
    CONSTRAINT ck_preferences_sprint_minutes CHECK (
        preferred_sprint_minutes BETWEEN 10 AND 60
        AND preferred_sprint_minutes % 5 = 0
    ),
    CONSTRAINT ck_preferences_json CHECK (
        jsonb_typeof(accessibility_preferences) = 'object'
        AND accessibility_preferences->>'schema_version' = '1'
        AND jsonb_typeof(media_preferences) = 'object'
        AND media_preferences->>'schema_version' = '1'
    ),
    CONSTRAINT ck_preferences_voice_pair CHECK (
        (preferred_voice_id IS NULL) = (voice_catalog_revision_id IS NULL)
        AND (preferred_voice_id IS NULL OR (
            identity.is_uuid7(preferred_voice_id)
            AND identity.is_uuid7(voice_catalog_revision_id)
        ))
    ),
    CONSTRAINT ck_preferences_version CHECK (version >= 1),
    CONSTRAINT ck_preferences_update_order CHECK (updated_at >= created_at)
);

CREATE TABLE identity.consent_purposes (
    purpose_code varchar(64) PRIMARY KEY,
    active boolean NOT NULL,
    CONSTRAINT ck_consent_purpose_code CHECK (
        purpose_code ~ '^[a-z][a-z0-9_]{2,63}$'
    )
);
INSERT INTO identity.consent_purposes (purpose_code, active) VALUES
    ('private_ai_context', true),
    ('product_analytics', true),
    ('retained_audio', true),
    ('speech_training', true);

CREATE TABLE identity.consent_grants (
    consent_id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
    purpose_code varchar(64) NOT NULL
        REFERENCES identity.consent_purposes(purpose_code) ON DELETE RESTRICT,
    status varchar(32) NOT NULL,
    policy_revision_id uuid NOT NULL,
    version integer NOT NULL,
    decided_at timestamptz NOT NULL,
    withdrawn_at timestamptz,
    CONSTRAINT ck_consent_uuid7 CHECK (
        identity.is_uuid7(consent_id)
        AND identity.is_uuid7(account_id)
        AND identity.is_uuid7(policy_revision_id)
    ),
    CONSTRAINT ck_consent_status CHECK (status IN ('granted', 'withdrawn')),
    CONSTRAINT ck_consent_withdrawal_shape CHECK (
        (status = 'granted' AND withdrawn_at IS NULL)
        OR (status = 'withdrawn' AND withdrawn_at = decided_at)
    ),
    CONSTRAINT ck_consent_version CHECK (version >= 1),
    CONSTRAINT uq_consent_account_purpose_version
        UNIQUE (account_id, purpose_code, version)
);
CREATE INDEX ix_consent_grants_account_purpose_decided
    ON identity.consent_grants (account_id, purpose_code, decided_at DESC);

CREATE FUNCTION identity.reject_consent_mutation() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
    RAISE EXCEPTION 'consent_grants is append-only' USING ERRCODE = '55000';
END;
$function$;
CREATE TRIGGER consent_grants_append_only
BEFORE UPDATE OR DELETE ON identity.consent_grants
FOR EACH ROW EXECUTE FUNCTION identity.reject_consent_mutation();

CREATE FUNCTION identity.lookup_local_identity(p_identifier text)
RETURNS TABLE (
    identity_id uuid,
    account_id uuid,
    password_hash text,
    account_status varchar,
    security_version integer,
    session_version integer,
    account_version integer,
    account_created_at timestamptz,
    security_last_activity_at timestamptz,
    deleted_at timestamptz,
    last_authenticated_at timestamptz,
    current_roles varchar[]
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, identity
AS $function$
    SELECT login.identity_id, login.account_id, login.password_hash,
           account.status, account.security_version, account.session_version,
           account.version, account.created_at, account.security_last_activity_at,
           account.deleted_at, login.last_authenticated_at,
           ARRAY(
               SELECT grant_row.role
               FROM identity.account_roles AS grant_row
               WHERE grant_row.account_id = account.account_id
                 AND grant_row.revoked_at IS NULL
               ORDER BY grant_row.role
           )
    FROM identity.login_identities AS login
    JOIN identity.accounts AS account ON account.account_id = login.account_id
    WHERE login.provider_type = 'local_password'
      AND login.normalized_identifier = p_identifier
      AND login.revoked_at IS NULL
    LIMIT 1
$function$;

CREATE FUNCTION identity.lookup_oidc_identity(p_issuer text, p_subject text)
RETURNS TABLE (
    identity_id uuid,
    account_id uuid,
    account_status varchar,
    security_version integer,
    session_version integer,
    account_version integer,
    account_created_at timestamptz,
    security_last_activity_at timestamptz,
    deleted_at timestamptz,
    last_authenticated_at timestamptz,
    current_roles varchar[]
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, identity
AS $function$
    SELECT login.identity_id, login.account_id, account.status,
           account.security_version, account.session_version, account.version,
           account.created_at, account.security_last_activity_at, account.deleted_at,
           login.last_authenticated_at,
           ARRAY(
               SELECT grant_row.role
               FROM identity.account_roles AS grant_row
               WHERE grant_row.account_id = account.account_id
                 AND grant_row.revoked_at IS NULL
               ORDER BY grant_row.role
           )
    FROM identity.login_identities AS login
    JOIN identity.accounts AS account ON account.account_id = login.account_id
    WHERE login.provider_type = 'oidc'
      AND login.issuer = p_issuer
      AND login.subject = p_subject
      AND login.revoked_at IS NULL
    LIMIT 1
$function$;

CREATE FUNCTION identity.lookup_session(p_fingerprint text)
RETURNS TABLE (
    session_id uuid,
    account_id uuid,
    session_fingerprint varchar,
    csrf_secret_hash varchar,
    roles_snapshot varchar[],
    account_session_version integer,
    created_at timestamptz,
    authenticated_at timestamptz,
    last_seen_at timestamptz,
    rotated_at timestamptz,
    idle_expires_at timestamptz,
    absolute_expires_at timestamptz,
    revoked_at timestamptz,
    revoke_reason varchar,
    replaced_by_session_id uuid,
    account_status varchar,
    current_security_version integer,
    current_session_version integer,
    account_version integer,
    account_created_at timestamptz,
    security_last_activity_at timestamptz,
    deleted_at timestamptz,
    current_roles varchar[]
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, identity
AS $function$
    SELECT active.session_id, active.account_id, active.session_fingerprint,
           active.csrf_secret_hash, active.roles_snapshot,
           active.account_session_version, active.created_at,
           active.authenticated_at, active.last_seen_at, active.rotated_at,
           active.idle_expires_at, active.absolute_expires_at,
           active.revoked_at, active.revoke_reason, active.replaced_by_session_id,
           account.status,
           account.security_version, account.session_version, account.version,
           account.created_at, account.security_last_activity_at, account.deleted_at,
           ARRAY(
               SELECT grant_row.role
               FROM identity.account_roles AS grant_row
               WHERE grant_row.account_id = account.account_id
                 AND grant_row.revoked_at IS NULL
               ORDER BY grant_row.role
           )
    FROM identity.auth_sessions AS active
    JOIN identity.accounts AS account ON account.account_id = active.account_id
    WHERE active.session_fingerprint = p_fingerprint
    LIMIT 1
$function$;

ALTER TABLE identity.accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity.login_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity.account_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity.auth_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity.user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity.consent_grants ENABLE ROW LEVEL SECURITY;

CREATE POLICY account_owner ON identity.accounts
    USING (account_id = identity.current_user_id())
    WITH CHECK (account_id = identity.current_user_id());
CREATE POLICY login_identity_owner ON identity.login_identities
    USING (account_id = identity.current_user_id())
    WITH CHECK (account_id = identity.current_user_id());
CREATE POLICY account_role_owner ON identity.account_roles
    USING (account_id = identity.current_user_id())
    WITH CHECK (account_id = identity.current_user_id());
CREATE POLICY auth_session_owner ON identity.auth_sessions
    USING (account_id = identity.current_user_id())
    WITH CHECK (account_id = identity.current_user_id());
CREATE POLICY user_preferences_owner ON identity.user_preferences
    USING (account_id = identity.current_user_id())
    WITH CHECK (account_id = identity.current_user_id());
CREATE POLICY consent_grant_owner ON identity.consent_grants
    USING (account_id = identity.current_user_id())
    WITH CHECK (account_id = identity.current_user_id());

REVOKE ALL ON SCHEMA identity FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA identity TO polyglot_migration;
GRANT USAGE ON SCHEMA identity TO polyglot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA identity
    TO polyglot_migration;
GRANT SELECT, INSERT, UPDATE ON TABLE
    identity.accounts,
    identity.login_identities,
    identity.account_roles,
    identity.auth_sessions,
    identity.user_preferences
    TO polyglot_runtime;
GRANT SELECT, INSERT ON TABLE identity.consent_grants TO polyglot_runtime;
GRANT SELECT ON TABLE identity.consent_purposes TO polyglot_runtime;

ALTER SCHEMA identity OWNER TO polyglot_migration;
ALTER TABLE identity.accounts OWNER TO polyglot_migration;
ALTER TABLE identity.login_identities OWNER TO polyglot_migration;
ALTER TABLE identity.account_roles OWNER TO polyglot_migration;
ALTER TABLE identity.auth_sessions OWNER TO polyglot_migration;
ALTER TABLE identity.user_preferences OWNER TO polyglot_migration;
ALTER TABLE identity.consent_purposes OWNER TO polyglot_migration;
ALTER TABLE identity.consent_grants OWNER TO polyglot_migration;
ALTER FUNCTION identity.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION identity.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION identity.reject_consent_mutation() OWNER TO polyglot_migration;
ALTER FUNCTION identity.lookup_local_identity(text) OWNER TO polyglot_migration;
ALTER FUNCTION identity.lookup_oidc_identity(text, text) OWNER TO polyglot_migration;
ALTER FUNCTION identity.lookup_session(text) OWNER TO polyglot_migration;

REVOKE ALL ON FUNCTION identity.lookup_local_identity(text)
    FROM PUBLIC, polyglot_migration;
REVOKE ALL ON FUNCTION identity.lookup_oidc_identity(text, text)
    FROM PUBLIC, polyglot_migration;
REVOKE ALL ON FUNCTION identity.lookup_session(text)
    FROM PUBLIC, polyglot_migration;
GRANT EXECUTE ON FUNCTION identity.lookup_local_identity(text) TO polyglot_runtime;
GRANT EXECUTE ON FUNCTION identity.lookup_oidc_identity(text, text) TO polyglot_runtime;
GRANT EXECUTE ON FUNCTION identity.lookup_session(text) TO polyglot_runtime;
"""


async def _execute_identity_ddl(connection: Connection) -> None:
    await connection.execute(IDENTITY_DDL)


def upgrade() -> None:
    op.get_bind().connection.run_async(_execute_identity_ddl)


def downgrade() -> None:
    if os.environ.get("POLYGLOT_ALLOW_DESTRUCTIVE_IDENTITY_DOWNGRADE") != "true":
        raise RuntimeError(
            "0002 downgrade is disposable-environment-only and causes permanent data loss"
        )
    op.execute("DROP SCHEMA identity CASCADE")
