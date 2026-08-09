from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData(schema="platform")

command_receipts = Table(
    "command_receipts",
    metadata,
    Column("command_id", UUID(as_uuid=True), primary_key=True),
    Column("command_type", String(120), nullable=False),
    Column("actor_id", UUID(as_uuid=True), nullable=False),
    Column("aggregate_type", String(120), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_fingerprint", String(64), nullable=False),
    Column("expected_version", Integer),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("result_ref", UUID(as_uuid=True)),
    Column("result_payload", JSONB),
    Column("status", String(24), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "request_fingerprint ~ '^[0-9a-f]{64}$'",
        name="ck_command_receipt_fingerprint_hex",
    ),
    CheckConstraint(
        "status IN ('started', 'succeeded', 'rejected', 'failed')",
        name="ck_command_receipt_status",
    ),
    UniqueConstraint(
        "actor_id",
        "command_type",
        "idempotency_key",
        name="uq_command_receipt_scope",
    ),
)
Index("ix_command_receipts_expires_at", command_receipts.c.expires_at)

domain_events = Table(
    "domain_events",
    metadata,
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("event_type", String(120), nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("aggregate_type", String(120), nullable=False),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("aggregate_version", Integer, nullable=False),
    Column("actor_type", String(40), nullable=False),
    Column("actor_id", UUID(as_uuid=True), nullable=False),
    Column("profile_id", UUID(as_uuid=True)),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("causation_id", UUID(as_uuid=True)),
    Column("command_id", UUID(as_uuid=True), nullable=False),
    Column("privacy_class", String(24), nullable=False),
    Column("policy_versions", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("payload", JSONB, nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    CheckConstraint("schema_version >= 1", name="ck_domain_event_schema_version"),
    CheckConstraint("aggregate_version >= 1", name="ck_domain_event_aggregate_version"),
    CheckConstraint(
        "privacy_class IN ('public', 'internal', 'personal', 'sensitive', 'secret')",
        name="ck_domain_event_privacy_class",
    ),
    CheckConstraint("privacy_class <> 'secret'", name="ck_domain_event_no_secret"),
    CheckConstraint(
        "privacy_class NOT IN ('personal', 'sensitive') "
        "OR (profile_id IS NOT NULL AND expires_at IS NOT NULL)",
        name="ck_domain_event_private_retention",
    ),
    UniqueConstraint(
        "aggregate_type",
        "aggregate_id",
        "aggregate_version",
        name="uq_domain_event_aggregate_version",
    ),
)
Index("ix_domain_events_recorded_at", domain_events.c.recorded_at, domain_events.c.event_id)
Index("ix_domain_events_correlation_id", domain_events.c.correlation_id)
Index("ix_domain_events_expires_at", domain_events.c.expires_at)

outbox_messages = Table(
    "outbox_messages",
    metadata,
    Column("outbox_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "event_id",
        UUID(as_uuid=True),
        ForeignKey("platform.domain_events.event_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    ),
    Column("destination", String(120), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempt_count", Integer, nullable=False, server_default="0"),
    Column("lease_owner", String(120)),
    Column("lease_token", UUID(as_uuid=True)),
    Column("lease_expires_at", DateTime(timezone=True)),
    Column("last_error_code", String(120)),
    CheckConstraint("attempt_count >= 0", name="ck_outbox_attempt_count"),
    CheckConstraint(
        "(lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) "
        "OR (lease_owner IS NOT NULL AND lease_token IS NOT NULL "
        "AND lease_expires_at IS NOT NULL)",
        name="ck_outbox_lease_complete",
    ),
)
Index(
    "ix_outbox_messages_available",
    outbox_messages.c.lease_expires_at,
    outbox_messages.c.created_at,
    postgresql_where=outbox_messages.c.published_at.is_(None),
)

inbox_receipts = Table(
    "inbox_receipts",
    metadata,
    Column("consumer_code", String(120), primary_key=True),
    Column("event_id", UUID(as_uuid=True), primary_key=True),
    Column("processed_at", DateTime(timezone=True), nullable=False),
    Column("result_checksum", String(64), nullable=False),
    CheckConstraint(
        "result_checksum ~ '^[0-9a-f]{64}$'",
        name="ck_inbox_result_checksum_hex",
    ),
)
Index("ix_inbox_receipts_processed_at", inbox_receipts.c.processed_at)

projection_checkpoints = Table(
    "projection_checkpoints",
    metadata,
    Column("projection_name", String(120), primary_key=True),
    Column("partition_key", String(255), primary_key=True),
    Column("last_event_id", UUID(as_uuid=True), nullable=False),
    Column("last_recorded_at", DateTime(timezone=True), nullable=False),
    Column("projection_version", Integer, nullable=False),
    CheckConstraint("projection_version >= 1", name="ck_projection_checkpoint_version"),
)

jobs = Table(
    "jobs",
    metadata,
    Column("job_id", UUID(as_uuid=True), primary_key=True),
    Column("job_type", String(120), nullable=False),
    Column("requested_by_actor_id", UUID(as_uuid=True), nullable=False),
    Column("profile_id", UUID(as_uuid=True)),
    Column("status", String(32), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_fingerprint", String(64), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("payload_schema_version", Integer, nullable=False),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column("queued_at", DateTime(timezone=True)),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("cancel_requested_at", DateTime(timezone=True)),
    Column("retry_not_before_at", DateTime(timezone=True)),
    Column("progress_completed", BigInteger, nullable=False, server_default="0"),
    Column("progress_total", BigInteger, nullable=False, server_default="0"),
    Column("result_ref", UUID(as_uuid=True)),
    Column("error_code", String(120)),
    Column("version", Integer, nullable=False, server_default="1"),
    CheckConstraint(
        "request_fingerprint ~ '^[0-9a-f]{64}$'",
        name="ck_job_request_fingerprint_hex",
    ),
    CheckConstraint("payload_schema_version >= 1", name="ck_job_payload_schema_version"),
    CheckConstraint("progress_completed >= 0", name="ck_job_progress_completed"),
    CheckConstraint("progress_total >= 0", name="ck_job_progress_total"),
    CheckConstraint("progress_completed <= progress_total", name="ck_job_progress_bounds"),
    CheckConstraint("version >= 1", name="ck_job_version"),
    CheckConstraint(
        "status IN ('requested', 'queued', 'running', 'retry_wait', 'cancel_requested', "
        "'succeeded', 'failed', 'cancelled')",
        name="ck_job_status",
    ),
    UniqueConstraint(
        "requested_by_actor_id",
        "job_type",
        "idempotency_key",
        name="uq_job_idempotency_scope",
    ),
)
Index("ix_jobs_profile_status", jobs.c.profile_id, jobs.c.status)
Index("ix_jobs_retry_not_before_at", jobs.c.retry_not_before_at)

job_claims = Table(
    "job_claims",
    metadata,
    Column(
        "job_id",
        UUID(as_uuid=True),
        ForeignKey("platform.jobs.job_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("attempt_no", Integer, nullable=False),
    Column("worker_id", String(120), nullable=False),
    Column("lease_token", UUID(as_uuid=True), nullable=False, unique=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("attempt_no >= 1", name="ck_job_claim_attempt_number"),
)
Index("ix_job_claims_lease_expires_at", job_claims.c.lease_expires_at)

job_attempts = Table(
    "job_attempts",
    metadata,
    Column("job_attempt_id", UUID(as_uuid=True), primary_key=True),
    Column(
        "job_id",
        UUID(as_uuid=True),
        ForeignKey("platform.jobs.job_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("attempt_no", Integer, nullable=False),
    Column("status", String(32), nullable=False),
    Column("worker_id", String(120), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=False),
    Column("retry_not_before_at", DateTime(timezone=True)),
    Column("provider_code", String(120)),
    Column("operation_code", String(120)),
    Column("error_code", String(120)),
    Column("retryable", Boolean, nullable=False, server_default=text("false")),
    CheckConstraint("attempt_no >= 1", name="ck_job_attempt_number"),
    CheckConstraint(
        "status IN ('succeeded', 'retryable_failed', 'failed', 'cancelled')",
        name="ck_job_attempt_status",
    ),
    UniqueConstraint("job_id", "attempt_no", name="uq_job_attempt_number"),
)
Index("ix_job_attempts_finished_at", job_attempts.c.finished_at)

provenance_records = Table(
    "provenance_records",
    metadata,
    Column("provenance_id", UUID(as_uuid=True), primary_key=True),
    Column("source_type", String(120), nullable=False),
    Column("source_ref", String(500), nullable=False),
    Column("created_by_actor_id", UUID(as_uuid=True)),
    Column("tool_revision_id", UUID(as_uuid=True)),
    Column("model_code", String(120)),
    Column("prompt_revision_id", UUID(as_uuid=True)),
    Column("transformation_chain", JSONB, nullable=False),
    Column("input_fingerprint", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "input_fingerprint ~ '^[0-9a-f]{64}$'",
        name="ck_provenance_input_fingerprint_hex",
    ),
)

security_audit_entries = Table(
    "security_audit_entries",
    metadata,
    Column("audit_id", UUID(as_uuid=True), primary_key=True),
    Column("actor_pseudonym", String(255), nullable=False),
    Column("action_code", String(120), nullable=False),
    Column("resource_type", String(120), nullable=False),
    Column("resource_id", UUID(as_uuid=True), nullable=False),
    Column("result", String(80), nullable=False),
    Column("reason_code", String(120), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("request_id", UUID(as_uuid=True), nullable=False),
    Column("correlation_id", UUID(as_uuid=True), nullable=False),
    Column("session_fingerprint", String(64), nullable=False),
    Column("truncated_ip", String(64), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "session_fingerprint ~ '^[0-9a-f]{64}$'",
        name="ck_security_audit_session_fingerprint_hex",
    ),
)
Index("ix_security_audit_entries_expires_at", security_audit_entries.c.expires_at)
Index("ix_security_audit_entries_correlation_id", security_audit_entries.c.correlation_id)

feature_flags = Table(
    "feature_flags",
    metadata,
    Column("flag_id", UUID(as_uuid=True), primary_key=True),
    Column("flag_code", String(120), nullable=False, unique=True),
    Column("owner", String(120), nullable=False),
    Column("reason", Text, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
Index("ix_feature_flags_expires_at", feature_flags.c.expires_at)

feature_flag_values = Table(
    "feature_flag_values",
    metadata,
    Column(
        "flag_id",
        UUID(as_uuid=True),
        ForeignKey("platform.feature_flags.flag_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("environment", String(40), primary_key=True),
    Column("value", JSONB, nullable=False),
    Column("version", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("version >= 1", name="ck_feature_flag_value_version"),
)

deletion_requests = Table(
    "deletion_requests",
    metadata,
    Column("deletion_request_id", UUID(as_uuid=True), primary_key=True),
    Column("subject_type", String(120), nullable=False),
    Column("subject_id", UUID(as_uuid=True), nullable=False),
    Column("requested_by_account_id", UUID(as_uuid=True), nullable=False),
    Column("status", String(32), nullable=False),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column("confirmed_at", DateTime(timezone=True)),
    Column("purge_due_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("policy_revision_id", UUID(as_uuid=True), nullable=False),
    CheckConstraint(
        "status IN ('requested', 'confirmed', 'blocked', 'purging', 'completed', "
        "'cancelled', 'failed')",
        name="ck_deletion_request_status",
    ),
)
Index("ix_deletion_requests_purge_due_at", deletion_requests.c.purge_due_at)

deletion_tombstones = Table(
    "deletion_tombstones",
    metadata,
    Column("tombstone_id", UUID(as_uuid=True), primary_key=True),
    Column("subject_type", String(120), nullable=False),
    Column("subject_fingerprint", String(64), nullable=False),
    Column("effective_at", DateTime(timezone=True), nullable=False),
    Column("policy_revision_id", UUID(as_uuid=True), nullable=False),
    Column("purged_scopes", ARRAY(String(120)), nullable=False, server_default="{}"),
    Column("last_applied_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True)),
    CheckConstraint(
        "subject_fingerprint ~ '^[0-9a-f]{64}$'",
        name="ck_tombstone_fingerprint_hex",
    ),
)
Index("ix_deletion_tombstones_expires_at", deletion_tombstones.c.expires_at)

retention_purge_authorizations = Table(
    "retention_purge_authorizations",
    metadata,
    Column("transaction_id", BigInteger, primary_key=True),
    Column("cutoff", DateTime(timezone=True), nullable=False),
)
