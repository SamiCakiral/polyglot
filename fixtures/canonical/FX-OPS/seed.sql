-- FX-OPS contains synthetic records only. Run it only in a disposable database.
INSERT INTO identity.accounts (
    account_id, status, security_version, session_version, version,
    created_at, security_last_activity_at, deleted_at
) VALUES (
    '019bc186-de00-7101-8101-010101010101', 'active', 1, 1, 1,
    '2026-08-10T12:00:00+00:00', '2026-08-10T12:00:00+00:00', NULL
);

INSERT INTO platform.domain_events (
    event_id, event_type, schema_version, aggregate_type, aggregate_id,
    aggregate_version, actor_type, actor_id, profile_id, occurred_at,
    recorded_at, correlation_id, causation_id, command_id, privacy_class,
    policy_versions, payload, expires_at, subject_type, subject_id
) VALUES (
    '019bc186-de00-7303-8303-030303030303', 'fixture.outbox_pending', 1,
    'fixture_account', '019bc186-de00-7101-8101-010101010101', 1,
    'system', '019bc186-de00-7404-8404-040404040404', NULL,
    '2026-08-10T12:00:00+00:00', '2026-08-10T12:00:00+00:00',
    '019bc186-de00-7505-8505-050505050505', NULL,
    '019bc186-de00-7606-8606-060606060606', 'internal', '{}',
    '{"fixture":"FX-OPS"}', NULL, NULL, NULL
);

INSERT INTO platform.outbox_messages (
    outbox_id, event_id, destination, created_at, published_at, attempt_count,
    lease_owner, lease_token, lease_expires_at, last_error_code
) VALUES (
    '019bc186-de00-7707-8707-070707070707',
    '019bc186-de00-7303-8303-030303030303', 'fx-ops-local',
    '2026-08-10T12:00:00+00:00', NULL, 0, NULL, NULL, NULL, NULL
);

INSERT INTO platform.deletion_tombstones (
    tombstone_id, subject_type, subject_fingerprint, effective_at,
    policy_revision_id, purged_scopes, last_applied_at, expires_at
) VALUES (
    '019bc186-de00-7808-8808-080808080808', 'account',
    'a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1',
    '2026-08-10T12:00:00+00:00', '019bc186-de00-7909-8909-090909090909',
    ARRAY['identity.accounts', 'platform.domain_events'],
    '2026-08-10T12:00:00+00:00', NULL
);
