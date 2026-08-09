from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_0001_platform_creates_the_complete_platform_schema(
    session: AsyncSession,
) -> None:
    expected_tables = {
        "command_receipts",
        "deletion_requests",
        "deletion_tombstones",
        "domain_events",
        "feature_flag_values",
        "feature_flags",
        "inbox_receipts",
        "job_attempts",
        "job_claims",
        "jobs",
        "outbox_messages",
        "projection_checkpoints",
        "provenance_records",
        "retention_purge_authorizations",
        "security_audit_entries",
    }

    rows = await session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'platform'"
        )
    )

    assert {row[0] for row in rows} == expected_tables


async def test_0001_platform_uses_postgresql_json_and_expiration_indexes(
    session: AsyncSession,
) -> None:
    payload_type = await session.scalar(
        text(
            "SELECT format_type(attribute.atttypid, attribute.atttypmod) "
            "FROM pg_attribute AS attribute "
            "JOIN pg_class AS relation ON relation.oid = attribute.attrelid "
            "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
            "WHERE namespace.nspname = 'platform' "
            "AND relation.relname = 'domain_events' "
            "AND attribute.attname = 'payload'"
        )
    )
    index_names = set(
        (
            await session.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'platform'")
            )
        ).scalars()
    )

    assert payload_type == "jsonb"
    assert {
        "ix_command_receipts_expires_at",
        "ix_deletion_tombstones_expires_at",
        "ix_feature_flags_expires_at",
        "ix_domain_events_expires_at",
        "ix_job_claims_lease_expires_at",
        "ix_jobs_retry_not_before_at",
        "ix_outbox_messages_available",
        "ix_security_audit_entries_expires_at",
    } <= index_names


async def test_0001_platform_has_required_columns_constraints_and_foreign_keys(
    session: AsyncSession,
) -> None:
    required_columns = {
        "command_receipts": {
            "command_id",
            "command_type",
            "actor_id",
            "aggregate_type",
            "aggregate_id",
            "idempotency_key",
            "request_fingerprint",
            "expected_version",
            "received_at",
            "result_ref",
            "result_payload",
            "status",
            "expires_at",
        },
        "domain_events": {
            "event_id",
            "event_type",
            "schema_version",
            "aggregate_type",
            "aggregate_id",
            "aggregate_version",
            "actor_type",
            "actor_id",
            "profile_id",
            "occurred_at",
            "recorded_at",
            "correlation_id",
            "causation_id",
            "command_id",
            "privacy_class",
            "policy_versions",
            "payload",
            "expires_at",
        },
        "outbox_messages": {
            "outbox_id",
            "event_id",
            "destination",
            "created_at",
            "published_at",
            "attempt_count",
            "lease_owner",
            "lease_token",
            "lease_expires_at",
            "last_error_code",
        },
        "job_claims": {
            "job_id",
            "attempt_no",
            "worker_id",
            "lease_token",
            "lease_expires_at",
            "started_at",
        },
        "job_attempts": {
            "job_attempt_id",
            "job_id",
            "attempt_no",
            "status",
            "worker_id",
            "started_at",
            "finished_at",
            "retry_not_before_at",
            "provider_code",
            "operation_code",
            "error_code",
            "retryable",
        },
    }
    columns = (
        await session.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'platform'"
            )
        )
    ).all()
    actual_columns: dict[str, set[str]] = {}
    for table_name, column_name in columns:
        actual_columns.setdefault(table_name, set()).add(column_name)
    for table_name, expected in required_columns.items():
        assert actual_columns[table_name] == expected

    constraint_names = set(
        (
            await session.execute(
                text(
                    "SELECT conname FROM pg_constraint AS c "
                    "JOIN pg_namespace AS namespace ON namespace.oid = c.connamespace "
                    "WHERE namespace.nspname = 'platform'"
                )
            )
        ).scalars()
    )
    assert {
        "ck_command_receipt_fingerprint_hex",
        "ck_domain_event_no_secret",
        "ck_domain_event_private_retention",
        "ck_inbox_result_checksum_hex",
        "ck_job_request_fingerprint_hex",
        "ck_outbox_lease_complete",
        "ck_provenance_input_fingerprint_hex",
        "ck_security_audit_session_fingerprint_hex",
        "ck_tombstone_fingerprint_hex",
        "uq_command_receipt_scope",
        "uq_domain_event_aggregate_version",
        "uq_job_attempt_number",
        "uq_job_idempotency_scope",
    } <= constraint_names

    foreign_keys = set(
        (
            await session.execute(
                text(
                    "SELECT source.relname, source_column.attname, target.relname, "
                    "target_column.attname FROM pg_constraint AS c "
                    "JOIN pg_class AS source ON source.oid = c.conrelid "
                    "JOIN pg_class AS target ON target.oid = c.confrelid "
                    "JOIN pg_namespace AS namespace ON namespace.oid = source.relnamespace "
                    "JOIN pg_attribute AS source_column ON source_column.attrelid = source.oid "
                    "AND source_column.attnum = c.conkey[1] "
                    "JOIN pg_attribute AS target_column ON target_column.attrelid = target.oid "
                    "AND target_column.attnum = c.confkey[1] "
                    "WHERE namespace.nspname = 'platform' AND c.contype = 'f'"
                )
            )
        ).all()
    )
    assert {
        ("outbox_messages", "event_id", "domain_events", "event_id"),
        ("job_claims", "job_id", "jobs", "job_id"),
        ("job_attempts", "job_id", "jobs", "job_id"),
        ("feature_flag_values", "flag_id", "feature_flags", "flag_id"),
    } <= foreign_keys


async def test_0001_platform_installs_append_only_and_controlled_purge_guards(
    session: AsyncSession,
) -> None:
    triggers = set(
        (
            await session.execute(
                text(
                    "SELECT event_object_table, trigger_name "
                    "FROM information_schema.triggers WHERE trigger_schema = 'platform'"
                )
            )
        ).all()
    )
    assert {
        ("domain_events", "domain_events_append_only"),
        ("job_attempts", "job_attempts_append_only"),
        ("security_audit_entries", "security_audit_entries_append_only"),
    } <= triggers
    purge_function = (
        await session.execute(
            text(
                "SELECT procedure.prosecdef, "
                "has_function_privilege('public', procedure.oid, 'EXECUTE') "
                "FROM pg_proc AS procedure "
                "JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace "
                "WHERE namespace.nspname = 'platform' "
                "AND procedure.proname = 'purge_expired_append_only'"
            )
        )
    ).one()
    assert purge_function == (True, False)
