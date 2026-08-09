"""Create the shared platform foundation.

Revision ID: 0001_platform
Revises:
"""

from alembic import op
from asyncpg import Connection


revision = "0001_platform"
down_revision = None
branch_labels = None
depends_on = None


PLATFORM_DDL = """
DO $roles$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'polyglot_migration') THEN
        CREATE ROLE polyglot_migration NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'polyglot_runtime') THEN
        CREATE ROLE polyglot_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'polyglot_retention') THEN
        CREATE ROLE polyglot_retention NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END
$roles$;

CREATE SCHEMA platform;

CREATE TABLE platform.command_receipts (
    command_id uuid PRIMARY KEY,
    command_type varchar(120) NOT NULL,
    actor_id uuid NOT NULL,
    aggregate_type varchar(120) NOT NULL,
    aggregate_id uuid NOT NULL,
    idempotency_key varchar(255) NOT NULL,
    request_fingerprint varchar(64) NOT NULL,
    expected_version integer,
    received_at timestamptz NOT NULL,
    result_ref uuid,
    result_payload jsonb,
    status varchar(24) NOT NULL,
    expires_at timestamptz NOT NULL,
    CONSTRAINT ck_command_receipt_fingerprint_hex
        CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_command_receipt_status
        CHECK (status IN ('started', 'succeeded', 'rejected', 'failed')),
    CONSTRAINT ck_command_receipt_replay_shape CHECK (
        (status = 'started' AND result_ref IS NULL AND result_payload IS NULL)
        OR (
            status = 'succeeded'
            AND result_ref IS NOT NULL
            AND octet_length(result_payload::text) <= 512
            AND result_payload = jsonb_build_object(
                'resource_id', result_payload->'resource_id',
                'version', result_payload->'version'
            )
            AND result_payload->>'resource_id' = result_ref::text
            AND jsonb_typeof(result_payload->'version') = 'number'
        ) OR (
            status IN ('rejected', 'failed')
            AND result_ref IS NULL
            AND octet_length(result_payload::text) <= 512
            AND result_payload = jsonb_build_object(
                'code', result_payload->'code',
                'message_key', result_payload->'message_key'
            )
            AND jsonb_typeof(result_payload->'code') = 'string'
            AND jsonb_typeof(result_payload->'message_key') = 'string'
        )
    ),
    CONSTRAINT uq_command_receipt_scope UNIQUE (actor_id, command_type, idempotency_key)
);
CREATE INDEX ix_command_receipts_expires_at ON platform.command_receipts (expires_at);

CREATE TABLE platform.domain_events (
    event_id uuid PRIMARY KEY,
    event_type varchar(120) NOT NULL,
    schema_version integer NOT NULL,
    aggregate_type varchar(120) NOT NULL,
    aggregate_id uuid NOT NULL,
    aggregate_version integer NOT NULL,
    actor_type varchar(40) NOT NULL,
    actor_id uuid NOT NULL,
    profile_id uuid,
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL,
    correlation_id uuid NOT NULL,
    causation_id uuid,
    command_id uuid NOT NULL,
    privacy_class varchar(24) NOT NULL,
    policy_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
    payload jsonb NOT NULL,
    expires_at timestamptz,
    subject_type varchar(32),
    subject_id uuid,
    CONSTRAINT ck_domain_event_schema_version CHECK (schema_version >= 1),
    CONSTRAINT ck_domain_event_aggregate_version CHECK (aggregate_version >= 1),
    CONSTRAINT ck_domain_event_privacy_class
        CHECK (privacy_class IN ('public', 'internal', 'personal', 'sensitive', 'secret')),
    CONSTRAINT ck_domain_event_no_secret CHECK (privacy_class <> 'secret'),
    CONSTRAINT ck_domain_event_private_retention CHECK (
        privacy_class NOT IN ('personal', 'sensitive')
        OR (
            expires_at IS NOT NULL
            AND subject_type IN ('account', 'profile')
            AND subject_id IS NOT NULL
        )
    ),
    CONSTRAINT uq_domain_event_aggregate_version
        UNIQUE (aggregate_type, aggregate_id, aggregate_version)
);
CREATE INDEX ix_domain_events_recorded_at
    ON platform.domain_events (recorded_at, event_id);
CREATE INDEX ix_domain_events_correlation_id
    ON platform.domain_events (correlation_id);
CREATE INDEX ix_domain_events_expires_at
    ON platform.domain_events (expires_at);
CREATE INDEX ix_domain_events_subject
    ON platform.domain_events (subject_type, subject_id);

CREATE TABLE platform.outbox_messages (
    outbox_id uuid PRIMARY KEY,
    event_id uuid NOT NULL UNIQUE REFERENCES platform.domain_events(event_id) ON DELETE RESTRICT,
    destination varchar(120) NOT NULL,
    created_at timestamptz NOT NULL,
    published_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0,
    lease_owner varchar(120),
    lease_token uuid,
    lease_expires_at timestamptz,
    last_error_code varchar(120),
    CONSTRAINT ck_outbox_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT ck_outbox_lease_complete CHECK (
        (lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL)
        OR (lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
    )
);
CREATE INDEX ix_outbox_messages_available
    ON platform.outbox_messages (lease_expires_at, created_at)
    WHERE published_at IS NULL;

CREATE TABLE platform.inbox_receipts (
    consumer_code varchar(120) NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL,
    result_checksum varchar(64) NOT NULL,
    CONSTRAINT ck_inbox_result_checksum_hex CHECK (result_checksum ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (consumer_code, event_id)
);
CREATE INDEX ix_inbox_receipts_processed_at ON platform.inbox_receipts (processed_at);

CREATE TABLE platform.projection_checkpoints (
    projection_name varchar(120) NOT NULL,
    partition_key varchar(255) NOT NULL,
    last_event_id uuid NOT NULL,
    last_recorded_at timestamptz NOT NULL,
    projection_version integer NOT NULL,
    CONSTRAINT ck_projection_checkpoint_version CHECK (projection_version >= 1),
    PRIMARY KEY (projection_name, partition_key)
);

CREATE TABLE platform.jobs (
    job_id uuid PRIMARY KEY,
    job_type varchar(120) NOT NULL,
    requested_by_actor_id uuid NOT NULL,
    profile_id uuid,
    status varchar(32) NOT NULL,
    idempotency_key varchar(255) NOT NULL,
    request_fingerprint varchar(64) NOT NULL,
    correlation_id uuid NOT NULL,
    payload_schema_version integer NOT NULL,
    requested_at timestamptz NOT NULL,
    queued_at timestamptz,
    started_at timestamptz,
    finished_at timestamptz,
    cancel_requested_at timestamptz,
    retry_not_before_at timestamptz,
    progress_completed bigint NOT NULL DEFAULT 0,
    progress_total bigint NOT NULL DEFAULT 0,
    result_ref uuid,
    error_code varchar(120),
    version integer NOT NULL DEFAULT 1,
    CONSTRAINT ck_job_status CHECK (
        status IN ('requested', 'queued', 'running', 'retry_wait', 'cancel_requested',
                   'succeeded', 'failed', 'cancelled')
    ),
    CONSTRAINT ck_job_request_fingerprint_hex
        CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_job_payload_schema_version CHECK (payload_schema_version >= 1),
    CONSTRAINT ck_job_progress_completed CHECK (progress_completed >= 0),
    CONSTRAINT ck_job_progress_total CHECK (progress_total >= 0),
    CONSTRAINT ck_job_progress_bounds CHECK (progress_completed <= progress_total),
    CONSTRAINT ck_job_version CHECK (version >= 1),
    CONSTRAINT uq_job_idempotency_scope
        UNIQUE (requested_by_actor_id, job_type, idempotency_key)
);
CREATE INDEX ix_jobs_profile_status ON platform.jobs (profile_id, status);
CREATE INDEX ix_jobs_retry_not_before_at ON platform.jobs (retry_not_before_at);

CREATE TABLE platform.job_claims (
    job_id uuid PRIMARY KEY REFERENCES platform.jobs(job_id) ON DELETE CASCADE,
    attempt_no integer NOT NULL,
    worker_id varchar(120) NOT NULL,
    lease_token uuid NOT NULL UNIQUE,
    lease_expires_at timestamptz NOT NULL,
    started_at timestamptz NOT NULL,
    CONSTRAINT ck_job_claim_attempt_number CHECK (attempt_no >= 1)
);
CREATE INDEX ix_job_claims_lease_expires_at ON platform.job_claims (lease_expires_at);

CREATE TABLE platform.job_attempts (
    job_attempt_id uuid PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES platform.jobs(job_id) ON DELETE RESTRICT,
    attempt_no integer NOT NULL,
    status varchar(32) NOT NULL,
    worker_id varchar(120) NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz NOT NULL,
    retry_not_before_at timestamptz,
    provider_code varchar(120),
    operation_code varchar(120),
    error_code varchar(120),
    retryable boolean NOT NULL DEFAULT false,
    CONSTRAINT ck_job_attempt_number CHECK (attempt_no >= 1),
    CONSTRAINT ck_job_attempt_status
        CHECK (status IN ('succeeded', 'retryable_failed', 'failed', 'cancelled')),
    CONSTRAINT uq_job_attempt_number UNIQUE (job_id, attempt_no)
);
CREATE INDEX ix_job_attempts_finished_at ON platform.job_attempts (finished_at);

CREATE TABLE platform.provenance_records (
    provenance_id uuid PRIMARY KEY,
    source_type varchar(120) NOT NULL,
    source_ref varchar(500) NOT NULL,
    created_by_actor_id uuid,
    tool_revision_id uuid,
    model_code varchar(120),
    prompt_revision_id uuid,
    transformation_chain jsonb NOT NULL,
    input_fingerprint varchar(64) NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT ck_provenance_input_fingerprint_hex
        CHECK (input_fingerprint ~ '^[0-9a-f]{64}$')
);

CREATE TABLE platform.security_audit_entries (
    audit_id uuid PRIMARY KEY,
    actor_pseudonym varchar(255) NOT NULL,
    action_code varchar(120) NOT NULL,
    resource_type varchar(120) NOT NULL,
    resource_id uuid NOT NULL,
    result varchar(80) NOT NULL,
    reason_code varchar(120) NOT NULL,
    occurred_at timestamptz NOT NULL,
    request_id uuid NOT NULL,
    correlation_id uuid NOT NULL,
    session_fingerprint varchar(64) NOT NULL,
    truncated_ip varchar(64) NOT NULL,
    expires_at timestamptz NOT NULL,
    CONSTRAINT ck_security_audit_session_fingerprint_hex
        CHECK (session_fingerprint ~ '^[0-9a-f]{64}$')
);
CREATE INDEX ix_security_audit_entries_expires_at
    ON platform.security_audit_entries (expires_at);
CREATE INDEX ix_security_audit_entries_correlation_id
    ON platform.security_audit_entries (correlation_id);

CREATE TABLE platform.feature_flags (
    flag_id uuid PRIMARY KEY,
    flag_code varchar(120) NOT NULL UNIQUE,
    owner varchar(120) NOT NULL,
    reason text NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE INDEX ix_feature_flags_expires_at ON platform.feature_flags (expires_at);

CREATE TABLE platform.feature_flag_values (
    flag_id uuid NOT NULL REFERENCES platform.feature_flags(flag_id) ON DELETE CASCADE,
    environment varchar(40) NOT NULL,
    value jsonb NOT NULL,
    version integer NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT ck_feature_flag_value_version CHECK (version >= 1),
    PRIMARY KEY (flag_id, environment)
);

CREATE TABLE platform.deletion_requests (
    deletion_request_id uuid PRIMARY KEY,
    subject_type varchar(120) NOT NULL,
    subject_id uuid NOT NULL,
    requested_by_account_id uuid NOT NULL,
    status varchar(32) NOT NULL,
    requested_at timestamptz NOT NULL,
    confirmed_at timestamptz,
    purge_due_at timestamptz,
    completed_at timestamptz,
    policy_revision_id uuid NOT NULL,
    CONSTRAINT ck_deletion_request_status CHECK (
        status IN ('requested', 'confirmed', 'blocked', 'purging', 'completed', 'cancelled', 'failed')
    )
);
CREATE INDEX ix_deletion_requests_purge_due_at
    ON platform.deletion_requests (purge_due_at);

CREATE TABLE platform.deletion_tombstones (
    tombstone_id uuid PRIMARY KEY,
    subject_type varchar(120) NOT NULL,
    subject_fingerprint varchar(64) NOT NULL,
    effective_at timestamptz NOT NULL,
    policy_revision_id uuid NOT NULL,
    purged_scopes varchar(120)[] NOT NULL DEFAULT '{}',
    last_applied_at timestamptz NOT NULL,
    expires_at timestamptz,
    CONSTRAINT ck_tombstone_fingerprint_hex
        CHECK (subject_fingerprint ~ '^[0-9a-f]{64}$'),
    CONSTRAINT uq_tombstone_subject UNIQUE (subject_type, subject_fingerprint)
);
CREATE INDEX ix_deletion_tombstones_expires_at
    ON platform.deletion_tombstones (expires_at);

CREATE TABLE platform.retention_purge_authorizations (
    transaction_id bigint PRIMARY KEY,
    purge_kind varchar(24) NOT NULL,
    cutoff timestamptz,
    subject_type varchar(32),
    subject_id uuid,
    deletion_request_id uuid,
    CONSTRAINT ck_retention_purge_authorization_scope CHECK (
        (
            purge_kind = 'expiry'
            AND cutoff IS NOT NULL
            AND subject_type IS NULL
            AND subject_id IS NULL
            AND deletion_request_id IS NULL
        ) OR (
            purge_kind = 'subject'
            AND cutoff IS NULL
            AND subject_type IN ('account', 'profile')
            AND subject_id IS NOT NULL
            AND deletion_request_id IS NOT NULL
        )
    )
);
REVOKE ALL ON platform.retention_purge_authorizations FROM PUBLIC;

CREATE FUNCTION platform.reject_append_only_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION platform.guard_domain_event_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND EXISTS (
        SELECT 1
        FROM platform.retention_purge_authorizations AS auth
        WHERE auth.transaction_id = txid_current()
          AND (
              (
                  auth.purge_kind = 'expiry'
                  AND OLD.expires_at IS NOT NULL
                  AND OLD.expires_at <= auth.cutoff
              ) OR (
                  auth.purge_kind = 'subject'
                  AND OLD.privacy_class IN ('personal', 'sensitive')
                  AND OLD.subject_type = auth.subject_type
                  AND OLD.subject_id = auth.subject_id
              )
          )
    ) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION platform.guard_retained_append_only_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND EXISTS (
        SELECT 1
        FROM platform.retention_purge_authorizations
        WHERE transaction_id = txid_current()
          AND purge_kind = 'expiry'
          AND OLD.expires_at IS NOT NULL
          AND OLD.expires_at <= cutoff
    ) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = '55000';
END;
$$;

CREATE TRIGGER domain_events_append_only
BEFORE UPDATE OR DELETE ON platform.domain_events
FOR EACH ROW EXECUTE FUNCTION platform.guard_domain_event_mutation();

CREATE TRIGGER job_attempts_append_only
BEFORE UPDATE OR DELETE ON platform.job_attempts
FOR EACH ROW EXECUTE FUNCTION platform.reject_append_only_mutation();

CREATE TRIGGER security_audit_entries_append_only
BEFORE UPDATE OR DELETE ON platform.security_audit_entries
FOR EACH ROW EXECUTE FUNCTION platform.guard_retained_append_only_mutation();

CREATE FUNCTION platform.purge_expired_append_only(
    p_cutoff timestamptz,
    p_audit_id uuid,
    p_actor_pseudonym varchar,
    p_reason_code varchar,
    p_request_id uuid,
    p_correlation_id uuid
) RETURNS TABLE (domain_event_count bigint, security_audit_count bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = platform, pg_temp
AS $$
DECLARE
    deleted_events bigint;
    deleted_audits bigint;
BEGIN
    INSERT INTO platform.retention_purge_authorizations(
        transaction_id, purge_kind, cutoff
    ) VALUES (txid_current(), 'expiry', p_cutoff);

    DELETE FROM platform.outbox_messages AS outbox
    USING platform.domain_events AS event
    WHERE outbox.event_id = event.event_id
      AND event.expires_at IS NOT NULL
      AND event.expires_at <= p_cutoff;

    DELETE FROM platform.domain_events
    WHERE expires_at IS NOT NULL AND expires_at <= p_cutoff;
    GET DIAGNOSTICS deleted_events = ROW_COUNT;

    DELETE FROM platform.security_audit_entries
    WHERE expires_at <= p_cutoff;
    GET DIAGNOSTICS deleted_audits = ROW_COUNT;

    DELETE FROM platform.retention_purge_authorizations
    WHERE transaction_id = txid_current();

    INSERT INTO platform.security_audit_entries (
        audit_id, actor_pseudonym, action_code, resource_type, resource_id,
        result, reason_code, occurred_at, request_id, correlation_id,
        session_fingerprint, truncated_ip, expires_at
    ) VALUES (
        p_audit_id, p_actor_pseudonym, 'retention.purge', 'retention_batch', p_audit_id,
        'succeeded', p_reason_code, clock_timestamp(), p_request_id, p_correlation_id,
        repeat('0', 64), 'system', clock_timestamp() + interval '180 days'
    );

    RETURN QUERY SELECT deleted_events, deleted_audits;
END;
$$;
REVOKE ALL ON FUNCTION platform.purge_expired_append_only(
    timestamptz, uuid, varchar, varchar, uuid, uuid
) FROM PUBLIC;

CREATE FUNCTION platform.purge_subject_private_events(
    p_deletion_request_id uuid,
    p_subject_type varchar,
    p_subject_id uuid,
    p_subject_fingerprint varchar,
    p_tombstone_id uuid,
    p_audit_id uuid,
    p_request_id uuid,
    p_correlation_id uuid
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = platform, pg_temp
AS $$
DECLARE
    deletion platform.deletion_requests%ROWTYPE;
    deleted_events bigint;
    applied_at timestamptz;
BEGIN
    IF p_subject_type NOT IN ('account', 'profile') THEN
        RAISE EXCEPTION 'unsupported private event subject type' USING ERRCODE = '22023';
    END IF;

    SELECT * INTO deletion
    FROM platform.deletion_requests
    WHERE deletion_request_id = p_deletion_request_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'deletion request not found' USING ERRCODE = 'P0002';
    END IF;
    IF deletion.status NOT IN ('confirmed', 'purging') OR deletion.confirmed_at IS NULL THEN
        RAISE EXCEPTION 'deletion request is not confirmed' USING ERRCODE = '55000';
    END IF;
    IF deletion.subject_type <> p_subject_type OR deletion.subject_id <> p_subject_id THEN
        RAISE EXCEPTION 'deletion request subject mismatch' USING ERRCODE = '22023';
    END IF;

    applied_at := clock_timestamp();
    UPDATE platform.deletion_requests
    SET status = 'purging'
    WHERE deletion_request_id = p_deletion_request_id;

    INSERT INTO platform.retention_purge_authorizations(
        transaction_id, purge_kind, subject_type, subject_id, deletion_request_id
    ) VALUES (
        txid_current(), 'subject', p_subject_type, p_subject_id, p_deletion_request_id
    );

    DELETE FROM platform.outbox_messages AS outbox
    USING platform.domain_events AS event
    WHERE outbox.event_id = event.event_id
      AND event.privacy_class IN ('personal', 'sensitive')
      AND event.subject_type = p_subject_type
      AND event.subject_id = p_subject_id;

    DELETE FROM platform.domain_events
    WHERE privacy_class IN ('personal', 'sensitive')
      AND subject_type = p_subject_type
      AND subject_id = p_subject_id;
    GET DIAGNOSTICS deleted_events = ROW_COUNT;

    DELETE FROM platform.retention_purge_authorizations
    WHERE transaction_id = txid_current();

    INSERT INTO platform.deletion_tombstones (
        tombstone_id, subject_type, subject_fingerprint, effective_at,
        policy_revision_id, purged_scopes, last_applied_at, expires_at
    ) VALUES (
        p_tombstone_id, p_subject_type, p_subject_fingerprint, applied_at,
        deletion.policy_revision_id, ARRAY['domain_events', 'outbox_messages'],
        applied_at, NULL
    )
    ON CONFLICT (subject_type, subject_fingerprint) DO UPDATE SET
        policy_revision_id = EXCLUDED.policy_revision_id,
        purged_scopes = EXCLUDED.purged_scopes,
        last_applied_at = EXCLUDED.last_applied_at;

    UPDATE platform.deletion_requests
    SET status = 'completed', completed_at = applied_at
    WHERE deletion_request_id = p_deletion_request_id;

    INSERT INTO platform.security_audit_entries (
        audit_id, actor_pseudonym, action_code, resource_type, resource_id,
        result, reason_code, occurred_at, request_id, correlation_id,
        session_fingerprint, truncated_ip, expires_at
    ) VALUES (
        p_audit_id, 'retention-worker', 'privacy.subject_purge',
        'deletion_request', p_deletion_request_id,
        'succeeded', 'confirmed_subject_deletion', applied_at,
        p_request_id, p_correlation_id,
        repeat('0', 64), 'system', applied_at + interval '180 days'
    );

    RETURN deleted_events;
END;
$$;
REVOKE ALL ON FUNCTION platform.purge_subject_private_events(
    uuid, varchar, uuid, varchar, uuid, uuid, uuid, uuid
) FROM PUBLIC;

GRANT USAGE ON SCHEMA platform TO polyglot_migration, polyglot_runtime, polyglot_retention;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA platform
    TO polyglot_migration, polyglot_runtime;
REVOKE ALL ON TABLE platform.retention_purge_authorizations FROM polyglot_runtime;

ALTER FUNCTION platform.purge_expired_append_only(
    timestamptz, uuid, varchar, varchar, uuid, uuid
) OWNER TO polyglot_migration;
ALTER FUNCTION platform.purge_subject_private_events(
    uuid, varchar, uuid, varchar, uuid, uuid, uuid, uuid
) OWNER TO polyglot_migration;

REVOKE ALL ON FUNCTION platform.purge_expired_append_only(
    timestamptz, uuid, varchar, varchar, uuid, uuid
) FROM PUBLIC, polyglot_migration, polyglot_runtime;
REVOKE ALL ON FUNCTION platform.purge_subject_private_events(
    uuid, varchar, uuid, varchar, uuid, uuid, uuid, uuid
) FROM PUBLIC, polyglot_migration, polyglot_runtime;
GRANT EXECUTE ON FUNCTION platform.purge_expired_append_only(
    timestamptz, uuid, varchar, varchar, uuid, uuid
) TO polyglot_retention;
GRANT EXECUTE ON FUNCTION platform.purge_subject_private_events(
    uuid, varchar, uuid, varchar, uuid, uuid, uuid, uuid
) TO polyglot_retention;
"""


async def _execute_platform_ddl(connection: Connection) -> None:
    await connection.execute(PLATFORM_DDL)


def upgrade() -> None:
    op.get_bind().connection.run_async(_execute_platform_ddl)


def downgrade() -> None:
    op.execute("DROP SCHEMA platform CASCADE")
