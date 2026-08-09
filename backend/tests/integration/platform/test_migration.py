import pytest
from sqlalchemy import make_url, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

LOGIN_GROUPS = {
    "polyglot_migration_login": "polyglot_migration",
    "polyglot_runtime_login": "polyglot_runtime",
    "polyglot_retention_login": "polyglot_retention",
}


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
        "ix_domain_events_subject",
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
            "subject_type",
            "subject_id",
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
        "ck_command_receipt_replay_shape",
        "ck_domain_event_no_secret",
        "ck_domain_event_private_retention",
        "ck_retention_purge_authorization_scope",
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
        "uq_tombstone_subject",
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
    purge_functions = (
        await session.execute(
            text(
                "SELECT procedure.proname, procedure.prosecdef, "
                "has_function_privilege('public', procedure.oid, 'EXECUTE') "
                "FROM pg_proc AS procedure "
                "JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace "
                "WHERE namespace.nspname = 'platform' "
                "AND procedure.proname IN "
                "('purge_expired_append_only', 'purge_subject_private_events')"
            )
        )
    ).all()
    assert set(purge_functions) == {
        ("purge_expired_append_only", True, False),
        ("purge_subject_private_events", True, False),
    }


async def test_purge_functions_are_owned_and_executable_only_by_dedicated_roles(
    session: AsyncSession,
) -> None:
    roles = set(
        (
            await session.execute(
                text(
                    "SELECT rolname FROM pg_roles WHERE rolname IN "
                    "('polyglot_migration', 'polyglot_runtime', 'polyglot_retention')"
                )
            )
        ).scalars()
    )
    privileges = (
        await session.execute(
            text(
                "SELECT procedure.proname, owner.rolname, "
                "has_function_privilege('polyglot_migration', procedure.oid, 'EXECUTE'), "
                "has_function_privilege('polyglot_runtime', procedure.oid, 'EXECUTE'), "
                "has_function_privilege('polyglot_retention', procedure.oid, 'EXECUTE') "
                "FROM pg_proc AS procedure "
                "JOIN pg_namespace AS namespace ON namespace.oid = procedure.pronamespace "
                "JOIN pg_roles AS owner ON owner.oid = procedure.proowner "
                "WHERE namespace.nspname = 'platform' AND procedure.proname IN "
                "('purge_expired_append_only', 'purge_subject_private_events')"
            )
        )
    ).all()

    assert roles == {"polyglot_migration", "polyglot_runtime", "polyglot_retention"}
    assert set(privileges) == {
        ("purge_expired_append_only", "polyglot_migration", False, False, True),
        ("purge_subject_private_events", "polyglot_migration", False, False, True),
    }

    with pytest.raises(DBAPIError):
        await session.execute(
            text(
                "SELECT * FROM platform.purge_expired_append_only("
                "clock_timestamp(), '00000000-0000-0000-0000-000000000001'::uuid, "
                "'runtime', 'forbidden', "
                "'00000000-0000-0000-0000-000000000002'::uuid, "
                "'00000000-0000-0000-0000-000000000003'::uuid)"
            )
        )
    await session.rollback()


async def test_database_logins_are_distinct_non_privileged_and_single_group(
    database_url: str,
    migration_database_url: str,
    retention_database_url: str,
) -> None:
    urls = (migration_database_url, database_url, retention_database_url)
    assert {make_url(url).username for url in urls} == set(LOGIN_GROUPS)

    for database_url_under_test in urls:
        expected_login = make_url(database_url_under_test).username
        assert expected_login is not None
        engine = create_async_engine(database_url_under_test)
        try:
            async with engine.connect() as connection:
                identity = (
                    await connection.execute(
                        text(
                            "SELECT current_user, session_user, role.rolsuper, "
                            "role.rolcreatedb, role.rolcreaterole, role.rolreplication, "
                            "role.rolbypassrls FROM pg_roles AS role "
                            "WHERE role.rolname = current_user"
                        )
                    )
                ).one()
                memberships = set(
                    (
                        await connection.execute(
                            text(
                                "SELECT parent.rolname FROM pg_auth_members AS membership "
                                "JOIN pg_roles AS parent ON parent.oid = membership.roleid "
                                "JOIN pg_roles AS member ON member.oid = membership.member "
                                "WHERE member.rolname = current_user"
                            )
                        )
                    ).scalars()
                )
        finally:
            await engine.dispose()

        assert identity == (expected_login, expected_login, False, False, False, False, False)
        assert memberships == {LOGIN_GROUPS[expected_login]}


async def test_workload_logins_receive_only_their_intended_database_rights(
    database_url: str,
    migration_database_url: str,
    retention_database_url: str,
) -> None:
    expected_privileges = {
        "polyglot_migration_login": (True, True, False),
        "polyglot_runtime_login": (False, False, False),
        "polyglot_retention_login": (False, False, True),
    }

    for database_url_under_test in (
        migration_database_url,
        database_url,
        retention_database_url,
    ):
        login = make_url(database_url_under_test).username
        assert login is not None
        engine = create_async_engine(database_url_under_test)
        try:
            async with engine.connect() as connection:
                privileges = (
                    await connection.execute(
                        text(
                            "SELECT "
                            "has_database_privilege(current_user, current_database(), 'CREATE'), "
                            "has_schema_privilege(current_user, 'platform', 'CREATE'), "
                            "has_function_privilege(current_user, "
                            "'platform.purge_expired_append_only(timestamptz,uuid,varchar,"
                            "varchar,uuid,uuid)', 'EXECUTE')"
                        )
                    )
                ).one()
        finally:
            await engine.dispose()

        assert privileges == expected_privileges[login]
