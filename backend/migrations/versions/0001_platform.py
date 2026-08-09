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
    status varchar(24) NOT NULL,
    expires_at timestamptz NOT NULL,
    CONSTRAINT ck_command_receipt_fingerprint CHECK (length(request_fingerprint) = 64),
    CONSTRAINT ck_command_receipt_status
        CHECK (status IN ('started', 'succeeded', 'rejected', 'failed')),
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
    policy_revision_ids uuid[] NOT NULL DEFAULT '{}',
    payload jsonb NOT NULL,
    CONSTRAINT ck_domain_event_schema_version CHECK (schema_version >= 1),
    CONSTRAINT ck_domain_event_aggregate_version CHECK (aggregate_version >= 1),
    CONSTRAINT ck_domain_event_privacy_class
        CHECK (privacy_class IN ('public', 'internal', 'personal', 'sensitive', 'secret')),
    CONSTRAINT uq_domain_event_aggregate_version
        UNIQUE (aggregate_type, aggregate_id, aggregate_version)
);
CREATE INDEX ix_domain_events_recorded_at
    ON platform.domain_events (recorded_at, event_id);
CREATE INDEX ix_domain_events_correlation_id
    ON platform.domain_events (correlation_id);

CREATE TABLE platform.outbox_messages (
    outbox_id uuid PRIMARY KEY,
    event_id uuid NOT NULL UNIQUE REFERENCES platform.domain_events(event_id) ON DELETE RESTRICT,
    destination varchar(120) NOT NULL,
    created_at timestamptz NOT NULL,
    published_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0,
    lease_owner varchar(120),
    lease_expires_at timestamptz,
    last_error_code varchar(120),
    CONSTRAINT ck_outbox_attempt_count CHECK (attempt_count >= 0)
);
CREATE INDEX ix_outbox_messages_available
    ON platform.outbox_messages (lease_expires_at, created_at)
    WHERE published_at IS NULL;

CREATE TABLE platform.inbox_receipts (
    consumer_code varchar(120) NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL,
    result_checksum varchar(64) NOT NULL,
    CONSTRAINT ck_inbox_result_checksum CHECK (length(result_checksum) = 64),
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
    progress_completed bigint NOT NULL DEFAULT 0,
    progress_total bigint NOT NULL DEFAULT 0,
    result_ref uuid,
    error_code varchar(120),
    version integer NOT NULL DEFAULT 1,
    CONSTRAINT ck_job_status CHECK (
        status IN ('requested', 'queued', 'running', 'retry_wait', 'cancel_requested',
                   'succeeded', 'failed', 'cancelled')
    ),
    CONSTRAINT ck_job_request_fingerprint CHECK (length(request_fingerprint) = 64),
    CONSTRAINT ck_job_payload_schema_version CHECK (payload_schema_version >= 1),
    CONSTRAINT ck_job_progress_completed CHECK (progress_completed >= 0),
    CONSTRAINT ck_job_progress_total CHECK (progress_total >= 0),
    CONSTRAINT ck_job_progress_bounds CHECK (progress_completed <= progress_total),
    CONSTRAINT ck_job_version CHECK (version >= 1),
    CONSTRAINT uq_job_idempotency_scope
        UNIQUE (requested_by_actor_id, job_type, idempotency_key)
);
CREATE INDEX ix_jobs_profile_status ON platform.jobs (profile_id, status);

CREATE TABLE platform.job_attempts (
    job_attempt_id uuid PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES platform.jobs(job_id) ON DELETE RESTRICT,
    attempt_no integer NOT NULL,
    status varchar(32) NOT NULL,
    lease_owner varchar(120),
    lease_expires_at timestamptz,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    retry_not_before_at timestamptz,
    provider_code varchar(120),
    operation_code varchar(120),
    error_code varchar(120),
    retryable boolean NOT NULL DEFAULT false,
    CONSTRAINT ck_job_attempt_number CHECK (attempt_no >= 1),
    CONSTRAINT ck_job_attempt_status
        CHECK (status IN ('running', 'succeeded', 'retryable_failed', 'failed', 'cancelled')),
    CONSTRAINT uq_job_attempt_number UNIQUE (job_id, attempt_no)
);
CREATE INDEX ix_job_attempts_lease_expires_at ON platform.job_attempts (lease_expires_at);

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
    CONSTRAINT ck_provenance_input_fingerprint CHECK (length(input_fingerprint) = 64)
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
    expires_at timestamptz NOT NULL
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
    CONSTRAINT ck_tombstone_fingerprint CHECK (length(subject_fingerprint) = 64)
);
CREATE INDEX ix_deletion_tombstones_expires_at
    ON platform.deletion_tombstones (expires_at);

CREATE FUNCTION platform.reject_append_only_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = '55000';
END;
$$;

CREATE TRIGGER domain_events_append_only
BEFORE UPDATE OR DELETE ON platform.domain_events
FOR EACH ROW EXECUTE FUNCTION platform.reject_append_only_mutation();

CREATE TRIGGER job_attempts_append_only
BEFORE UPDATE OR DELETE ON platform.job_attempts
FOR EACH ROW EXECUTE FUNCTION platform.reject_append_only_mutation();

CREATE TRIGGER security_audit_entries_append_only
BEFORE UPDATE OR DELETE ON platform.security_audit_entries
FOR EACH ROW EXECUTE FUNCTION platform.reject_append_only_mutation();
"""


async def _execute_platform_ddl(connection: Connection) -> None:
    await connection.execute(PLATFORM_DDL)


def upgrade() -> None:
    op.get_bind().connection.run_async(_execute_platform_ddl)


def downgrade() -> None:
    op.execute("DROP SCHEMA platform CASCADE")
