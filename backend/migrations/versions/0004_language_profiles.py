"""Create learner language profiles, diagnostics, and foundations.

Revision ID: 0004_language_profiles
Revises: 0003_catalogue
"""

from alembic import op
from asyncpg import Connection

revision = "0004_language_profiles"
down_revision = "0003_catalogue"
branch_labels = None
depends_on = None


LANGUAGE_PROFILES_DDL = r"""
CREATE SCHEMA language_profiles;

CREATE FUNCTION language_profiles.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $function$
    SELECT value IS NOT NULL AND (get_byte(uuid_send(value), 6) >> 4) = 7
$function$;

CREATE FUNCTION language_profiles.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE
AS $function$
    SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
$function$;

CREATE TABLE language_profiles.learner_language_profiles (
    profile_id uuid PRIMARY KEY,
    account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
    target_variety_id uuid NOT NULL,
    native_variety_id uuid NOT NULL,
    status varchar(24) NOT NULL,
    current_phase varchar(24) NOT NULL,
    goals jsonb NOT NULL,
    interests jsonb NOT NULL,
    excluded_themes jsonb NOT NULL,
    correction_preference jsonb NOT NULL,
    availability_pattern jsonb NOT NULL,
    version integer NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    archived_at timestamptz,
    deleted_at timestamptz,
    CONSTRAINT ck_language_profile_uuid7 CHECK (
        language_profiles.is_uuid7(profile_id) AND language_profiles.is_uuid7(account_id)
        AND language_profiles.is_uuid7(target_variety_id)
        AND language_profiles.is_uuid7(native_variety_id)
    ),
    CONSTRAINT ck_language_profile_status CHECK (
        status IN ('onboarding', 'foundations', 'active', 'paused', 'archived', 'deleting', 'deleted')
    ),
    CONSTRAINT ck_language_profile_phase CHECK (
        current_phase IN ('diagnostic', 'foundations', 'module_learning', 'paused', 'archived')
    ),
    CONSTRAINT ck_language_profile_version CHECK (version >= 1),
    CONSTRAINT ck_language_profile_json CHECK (
        jsonb_typeof(goals) = 'array' AND jsonb_typeof(interests) = 'array'
        AND jsonb_typeof(excluded_themes) = 'array'
        AND jsonb_typeof(correction_preference) = 'object'
        AND jsonb_typeof(availability_pattern) = 'object'
    ),
    CONSTRAINT ck_language_profile_dates CHECK (
        created_at <= updated_at
        AND (status = 'archived') = (archived_at IS NOT NULL)
        AND (status = 'deleted') = (deleted_at IS NOT NULL)
        AND NOT (archived_at IS NOT NULL AND deleted_at IS NOT NULL)
    )
);
CREATE UNIQUE INDEX uq_language_profile_account_target_live
    ON language_profiles.learner_language_profiles(account_id, target_variety_id)
    WHERE status <> 'deleted';
CREATE INDEX ix_language_profile_account_status
    ON language_profiles.learner_language_profiles(account_id, status, profile_id);

CREATE TABLE language_profiles.support_language_authorizations (
    authorization_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id)
        ON DELETE RESTRICT,
    variety_id uuid NOT NULL,
    authorized_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CONSTRAINT ck_support_language_authorization_uuid7 CHECK (
        language_profiles.is_uuid7(authorization_id)
        AND language_profiles.is_uuid7(profile_id)
        AND language_profiles.is_uuid7(variety_id)
    ),
    CONSTRAINT ck_support_language_authorization_dates CHECK (
        revoked_at IS NULL OR revoked_at >= authorized_at
    )
);
CREATE UNIQUE INDEX uq_support_language_authorization_active
    ON language_profiles.support_language_authorizations(profile_id, variety_id)
    WHERE revoked_at IS NULL;

CREATE TABLE language_profiles.declared_language_experiences (
    experience_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id)
        ON DELETE RESTRICT,
    variety_id uuid NOT NULL,
    declared_level varchar(120),
    years_experience numeric(6,2),
    notes text,
    declared_at timestamptz NOT NULL,
    superseded_at timestamptz,
    CONSTRAINT ck_declared_experience_uuid7 CHECK (
        language_profiles.is_uuid7(experience_id)
        AND language_profiles.is_uuid7(profile_id)
        AND language_profiles.is_uuid7(variety_id)
    ),
    CONSTRAINT ck_declared_experience_years CHECK (
        years_experience IS NULL OR years_experience >= 0
    ),
    CONSTRAINT ck_declared_experience_dates CHECK (
        superseded_at IS NULL OR superseded_at >= declared_at
    )
);
CREATE INDEX ix_declared_experience_profile_active
    ON language_profiles.declared_language_experiences(profile_id, declared_at DESC)
    WHERE superseded_at IS NULL;

CREATE TABLE language_profiles.diagnostic_runs (
    diagnostic_run_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id)
        ON DELETE RESTRICT,
    policy_revision_id uuid NOT NULL,
    pack_revision_id uuid NOT NULL,
    status varchar(24) NOT NULL,
    seed varchar(255) NOT NULL,
    started_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    completed_at timestamptz,
    classification varchar(24),
    confidence numeric(5,4),
    stop_reason varchar(120),
    version integer NOT NULL,
    CONSTRAINT ck_diagnostic_run_uuid7 CHECK (
        language_profiles.is_uuid7(diagnostic_run_id)
        AND language_profiles.is_uuid7(profile_id)
        AND language_profiles.is_uuid7(policy_revision_id)
        AND language_profiles.is_uuid7(pack_revision_id)
    ),
    CONSTRAINT ck_diagnostic_run_status CHECK (
        status IN ('prepared', 'in_progress', 'interrupted', 'completed', 'expired', 'cancelled')
    ),
    CONSTRAINT ck_diagnostic_run_shape CHECK (
        seed <> '' AND version >= 1 AND expires_at = started_at + interval '24 hours'
        AND (status = 'completed') = (completed_at IS NOT NULL)
        AND (status <> 'completed' OR (
            classification IN ('beginner', 'false_beginner', 'intermediate', 'undetermined')
            AND confidence IS NOT NULL AND stop_reason IS NOT NULL
        ))
        AND (confidence IS NULL OR confidence BETWEEN 0 AND 1)
    )
);
CREATE UNIQUE INDEX uq_diagnostic_run_open_per_profile
    ON language_profiles.diagnostic_runs(profile_id)
    WHERE status IN ('prepared', 'in_progress', 'interrupted');
CREATE INDEX ix_diagnostic_run_resume
    ON language_profiles.diagnostic_runs(profile_id, status, expires_at);

CREATE TABLE language_profiles.diagnostic_responses (
    response_id uuid PRIMARY KEY,
    diagnostic_run_id uuid NOT NULL REFERENCES language_profiles.diagnostic_runs(diagnostic_run_id)
        ON DELETE RESTRICT,
    item_revision_id uuid NOT NULL,
    ordinal integer NOT NULL,
    answer jsonb NOT NULL,
    score numeric(5,4),
    confidence numeric(5,4),
    evaluable boolean NOT NULL,
    revealed boolean NOT NULL,
    submitted_at timestamptz NOT NULL,
    idempotency_key varchar(255) NOT NULL,
    CONSTRAINT ck_diagnostic_response_uuid7 CHECK (
        language_profiles.is_uuid7(response_id)
        AND language_profiles.is_uuid7(diagnostic_run_id)
        AND language_profiles.is_uuid7(item_revision_id)
    ),
    CONSTRAINT ck_diagnostic_response_shape CHECK (
        ordinal >= 1 AND jsonb_typeof(answer) = 'object'
        AND (score IS NULL OR score BETWEEN 0 AND 1)
        AND (confidence IS NULL OR confidence BETWEEN 0 AND 1)
        AND (evaluable OR (score IS NULL AND confidence IS NULL))
    ),
    CONSTRAINT uq_diagnostic_response_item UNIQUE(diagnostic_run_id, item_revision_id),
    CONSTRAINT uq_diagnostic_response_ordinal UNIQUE(diagnostic_run_id, ordinal),
    CONSTRAINT uq_diagnostic_response_idempotency UNIQUE(diagnostic_run_id, idempotency_key)
);
CREATE INDEX ix_diagnostic_response_run_ordinal
    ON language_profiles.diagnostic_responses(diagnostic_run_id, ordinal);

CREATE TABLE language_profiles.foundation_runs (
    foundation_run_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id)
        ON DELETE RESTRICT,
    pack_revision_id uuid NOT NULL,
    foundation_revision_id uuid NOT NULL,
    status varchar(24) NOT NULL,
    seed varchar(255) NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    version integer NOT NULL,
    CONSTRAINT ck_foundation_run_uuid7 CHECK (
        language_profiles.is_uuid7(foundation_run_id)
        AND language_profiles.is_uuid7(profile_id)
        AND language_profiles.is_uuid7(pack_revision_id)
        AND language_profiles.is_uuid7(foundation_revision_id)
    ),
    CONSTRAINT ck_foundation_run_status CHECK (
        status IN ('prepared', 'in_progress', 'interrupted', 'completed', 'expired', 'cancelled')
    ),
    CONSTRAINT ck_foundation_run_shape CHECK (
        seed <> '' AND version >= 1 AND (status = 'completed') = (completed_at IS NOT NULL)
    )
);
CREATE UNIQUE INDEX uq_foundation_run_open_per_profile
    ON language_profiles.foundation_runs(profile_id)
    WHERE status IN ('prepared', 'in_progress', 'interrupted');

CREATE TABLE language_profiles.foundation_run_blocks (
    foundation_run_block_id uuid PRIMARY KEY,
    foundation_run_id uuid NOT NULL REFERENCES language_profiles.foundation_runs(foundation_run_id)
        ON DELETE RESTRICT,
    block_revision_id uuid NOT NULL,
    block_code varchar(120) NOT NULL,
    ordinal integer NOT NULL,
    status varchar(24) NOT NULL,
    session_id uuid,
    result jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    CONSTRAINT ck_foundation_run_block_uuid7 CHECK (
        language_profiles.is_uuid7(foundation_run_block_id)
        AND language_profiles.is_uuid7(foundation_run_id)
        AND language_profiles.is_uuid7(block_revision_id)
        AND (session_id IS NULL OR language_profiles.is_uuid7(session_id))
    ),
    CONSTRAINT ck_foundation_run_block_status CHECK (
        status IN ('pending', 'available', 'in_progress', 'completed', 'failed', 'waived')
    ),
    CONSTRAINT ck_foundation_run_block_shape CHECK (
        ordinal >= 1 AND block_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
        AND (result IS NULL OR jsonb_typeof(result) = 'object')
        AND (completed_at IS NULL OR started_at IS NOT NULL)
    ),
    CONSTRAINT uq_foundation_run_block_ordinal UNIQUE(foundation_run_id, ordinal)
);

CREATE TABLE language_profiles.foundation_gate_results (
    gate_result_id uuid PRIMARY KEY,
    foundation_run_id uuid NOT NULL REFERENCES language_profiles.foundation_runs(foundation_run_id)
        ON DELETE RESTRICT,
    gate_revision_id uuid NOT NULL,
    passed boolean NOT NULL,
    coverage numeric(5,4) NOT NULL,
    confidence numeric(5,4) NOT NULL,
    reasons jsonb NOT NULL,
    details jsonb NOT NULL,
    waiver_reason varchar(120),
    waiver_evidence_ids uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],
    decided_at timestamptz NOT NULL,
    CONSTRAINT ck_foundation_gate_result_uuid7 CHECK (
        language_profiles.is_uuid7(gate_result_id)
        AND language_profiles.is_uuid7(foundation_run_id)
        AND language_profiles.is_uuid7(gate_revision_id)
    ),
    CONSTRAINT ck_foundation_gate_result_scores CHECK (
        coverage BETWEEN 0 AND 1 AND confidence BETWEEN 0 AND 1
    ),
    CONSTRAINT ck_foundation_gate_result_json CHECK (
        jsonb_typeof(reasons) = 'array' AND jsonb_typeof(details) = 'object'
    )
);
CREATE UNIQUE INDEX uq_foundation_gate_result_per_run
    ON language_profiles.foundation_gate_results(foundation_run_id);

CREATE FUNCTION language_profiles.reject_append_only_mutation() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
    RAISE EXCEPTION 'append-only record is immutable' USING ERRCODE = '23514';
END;
$function$;
CREATE TRIGGER guard_diagnostic_response_append_only
BEFORE UPDATE OR DELETE ON language_profiles.diagnostic_responses
FOR EACH ROW EXECUTE FUNCTION language_profiles.reject_append_only_mutation();
CREATE TRIGGER guard_foundation_gate_result_append_only
BEFORE UPDATE OR DELETE ON language_profiles.foundation_gate_results
FOR EACH ROW EXECUTE FUNCTION language_profiles.reject_append_only_mutation();

ALTER TABLE language_profiles.learner_language_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE language_profiles.support_language_authorizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE language_profiles.declared_language_experiences ENABLE ROW LEVEL SECURITY;
ALTER TABLE language_profiles.diagnostic_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE language_profiles.diagnostic_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE language_profiles.foundation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE language_profiles.foundation_run_blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE language_profiles.foundation_gate_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY learner_language_profile_owner ON language_profiles.learner_language_profiles
    USING (account_id = language_profiles.current_user_id())
    WITH CHECK (account_id = language_profiles.current_user_id());
CREATE POLICY support_language_authorization_owner ON language_profiles.support_language_authorizations
    USING (EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles item
        WHERE item.profile_id = language_profiles.support_language_authorizations.profile_id
        AND item.account_id = language_profiles.current_user_id()))
    WITH CHECK (EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles item
        WHERE item.profile_id = language_profiles.support_language_authorizations.profile_id
        AND item.account_id = language_profiles.current_user_id()));
CREATE POLICY declared_language_experience_owner ON language_profiles.declared_language_experiences
    USING (EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles item
        WHERE item.profile_id = language_profiles.declared_language_experiences.profile_id
        AND item.account_id = language_profiles.current_user_id()))
    WITH CHECK (EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles item
        WHERE item.profile_id = language_profiles.declared_language_experiences.profile_id
        AND item.account_id = language_profiles.current_user_id()));
CREATE POLICY diagnostic_run_owner ON language_profiles.diagnostic_runs
    USING (EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles item
        WHERE item.profile_id = language_profiles.diagnostic_runs.profile_id
        AND item.account_id = language_profiles.current_user_id()))
    WITH CHECK (EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles item
        WHERE item.profile_id = language_profiles.diagnostic_runs.profile_id
        AND item.account_id = language_profiles.current_user_id()));
CREATE POLICY diagnostic_response_owner ON language_profiles.diagnostic_responses
    USING (EXISTS (SELECT 1 FROM language_profiles.diagnostic_runs run
        JOIN language_profiles.learner_language_profiles item ON item.profile_id = run.profile_id
        WHERE run.diagnostic_run_id = language_profiles.diagnostic_responses.diagnostic_run_id
        AND item.account_id = language_profiles.current_user_id()))
    WITH CHECK (EXISTS (SELECT 1 FROM language_profiles.diagnostic_runs run
        JOIN language_profiles.learner_language_profiles item ON item.profile_id = run.profile_id
        WHERE run.diagnostic_run_id = language_profiles.diagnostic_responses.diagnostic_run_id
        AND item.account_id = language_profiles.current_user_id()));
CREATE POLICY foundation_run_owner ON language_profiles.foundation_runs
    USING (EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles item
        WHERE item.profile_id = language_profiles.foundation_runs.profile_id
        AND item.account_id = language_profiles.current_user_id()))
    WITH CHECK (EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles item
        WHERE item.profile_id = language_profiles.foundation_runs.profile_id
        AND item.account_id = language_profiles.current_user_id()));
CREATE POLICY foundation_run_block_owner ON language_profiles.foundation_run_blocks
    USING (EXISTS (SELECT 1 FROM language_profiles.foundation_runs run
        JOIN language_profiles.learner_language_profiles item ON item.profile_id = run.profile_id
        WHERE run.foundation_run_id = language_profiles.foundation_run_blocks.foundation_run_id
        AND item.account_id = language_profiles.current_user_id()))
    WITH CHECK (EXISTS (SELECT 1 FROM language_profiles.foundation_runs run
        JOIN language_profiles.learner_language_profiles item ON item.profile_id = run.profile_id
        WHERE run.foundation_run_id = language_profiles.foundation_run_blocks.foundation_run_id
        AND item.account_id = language_profiles.current_user_id()));
CREATE POLICY foundation_gate_result_owner ON language_profiles.foundation_gate_results
    USING (EXISTS (SELECT 1 FROM language_profiles.foundation_runs run
        JOIN language_profiles.learner_language_profiles item ON item.profile_id = run.profile_id
        WHERE run.foundation_run_id = language_profiles.foundation_gate_results.foundation_run_id
        AND item.account_id = language_profiles.current_user_id()))
    WITH CHECK (EXISTS (SELECT 1 FROM language_profiles.foundation_runs run
        JOIN language_profiles.learner_language_profiles item ON item.profile_id = run.profile_id
        WHERE run.foundation_run_id = language_profiles.foundation_gate_results.foundation_run_id
        AND item.account_id = language_profiles.current_user_id()));

REVOKE ALL ON SCHEMA language_profiles FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA language_profiles TO polyglot_migration;
GRANT USAGE ON SCHEMA language_profiles TO polyglot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA language_profiles
    TO polyglot_migration;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA language_profiles
    TO polyglot_runtime;

ALTER SCHEMA language_profiles OWNER TO polyglot_migration;
DO $owners$
DECLARE item record;
BEGIN
    FOR item IN SELECT tablename FROM pg_tables WHERE schemaname = 'language_profiles' LOOP
        EXECUTE format('ALTER TABLE language_profiles.%I OWNER TO polyglot_migration', item.tablename);
    END LOOP;
END;
$owners$;
ALTER FUNCTION language_profiles.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION language_profiles.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION language_profiles.reject_append_only_mutation() OWNER TO polyglot_migration;
"""


async def _execute_language_profiles_ddl(connection: Connection) -> None:
    await connection.execute(LANGUAGE_PROFILES_DDL)


def upgrade() -> None:
    op.get_bind().connection.run_async(_execute_language_profiles_ddl)


def downgrade() -> None:
    op.execute("DROP SCHEMA language_profiles CASCADE")
