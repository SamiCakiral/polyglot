"""Create revisioned editorial content.

Revision ID: 0005_content
Revises: 0004_language_profiles
"""

from alembic import op
from asyncpg import Connection

revision = "0005_content"
down_revision = "0004_language_profiles"
branch_labels = None
depends_on = None


CONTENT_DDL = r"""
CREATE SCHEMA content;
CREATE FUNCTION content.is_uuid7(value uuid) RETURNS boolean LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
    SELECT value IS NOT NULL AND (get_byte(uuid_send(value), 6) >> 4) = 7
$function$;
CREATE TABLE content.content_items (
    content_id uuid PRIMARY KEY, content_type varchar(120) NOT NULL,
    pack_id uuid NOT NULL REFERENCES catalogue.language_packs(pack_id) ON DELETE RESTRICT,
    variety_id uuid NOT NULL REFERENCES catalogue.language_varieties(variety_id) ON DELETE RESTRICT,
    editorial_owner_id uuid NOT NULL, lineage_root_id uuid NOT NULL,
    parent_content_id uuid REFERENCES content.content_items(content_id) ON DELETE RESTRICT,
    version integer NOT NULL, created_at timestamptz NOT NULL,
    CONSTRAINT ck_content_item_uuid7 CHECK (content.is_uuid7(content_id) AND content.is_uuid7(pack_id) AND content.is_uuid7(variety_id) AND content.is_uuid7(editorial_owner_id) AND content.is_uuid7(lineage_root_id)),
    CONSTRAINT ck_content_item_version CHECK (version >= 1)
);
CREATE TABLE content.content_revisions (
    content_revision_id uuid PRIMARY KEY, content_id uuid NOT NULL REFERENCES content.content_items(content_id) ON DELETE RESTRICT,
    revision_no integer NOT NULL, schema_version integer NOT NULL, payload jsonb NOT NULL,
    payload_checksum varchar(64) NOT NULL, provenance_id uuid NOT NULL REFERENCES platform.provenance_records(provenance_id) ON DELETE RESTRICT,
    rights_ref varchar(500) NOT NULL, pinned_revision_refs jsonb NOT NULL,
    created_by_actor_id uuid NOT NULL, approved_by_actor_id uuid, status varchar(24) NOT NULL,
    channel_code varchar(40), compatibility_range varchar(120),
    supersedes_revision_id uuid REFERENCES content.content_revisions(content_revision_id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL, validated_at timestamptz, approved_at timestamptz, published_at timestamptz, retired_at timestamptz,
    CONSTRAINT ck_content_revision_numbers CHECK (revision_no >= 1 AND schema_version >= 1),
    CONSTRAINT ck_content_revision_checksum CHECK (payload_checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_content_revision_uuid7 CHECK (
        content.is_uuid7(content_revision_id) AND content.is_uuid7(content_id)
        AND content.is_uuid7(provenance_id) AND content.is_uuid7(created_by_actor_id)
        AND (approved_by_actor_id IS NULL OR content.is_uuid7(approved_by_actor_id))
        AND (supersedes_revision_id IS NULL OR content.is_uuid7(supersedes_revision_id))
    ),
    CONSTRAINT ck_content_revision_distinct_approver CHECK (
        approved_by_actor_id IS NULL OR approved_by_actor_id <> created_by_actor_id
    ),
    CONSTRAINT ck_content_revision_status CHECK (status IN ('draft','validating','validated','approved','published','retired','superseded','rejected','abandoned')),
    CONSTRAINT ck_content_revision_payload CHECK (jsonb_typeof(payload) = 'object' AND payload->>'schema_version' ~ '^[1-9][0-9]*$' AND jsonb_typeof(pinned_revision_refs) = 'array'),
    CONSTRAINT ck_content_revision_dates CHECK (
        created_at <= COALESCE(validated_at, created_at)
        AND created_at <= COALESCE(approved_at, created_at)
        AND created_at <= COALESCE(published_at, created_at)
        AND created_at <= COALESCE(retired_at, created_at)
    ),
    CONSTRAINT uq_content_revision_number UNIQUE (content_id, revision_no)
);
CREATE INDEX ix_content_revisions_content_status ON content.content_revisions(content_id, status, revision_no);
CREATE TABLE content.validation_reports (
    report_id uuid PRIMARY KEY, subject_revision_id uuid NOT NULL REFERENCES content.content_revisions(content_revision_id) ON DELETE RESTRICT,
    validator_set_revision_id uuid NOT NULL, command_id uuid, status varchar(24) NOT NULL,
    started_at timestamptz NOT NULL, completed_at timestamptz,
    finding_count integer NOT NULL DEFAULT 0, summary_checksum varchar(64),
    CONSTRAINT ck_content_validation_report_status CHECK (status IN ('pending','running','passed','failed','human_required','cancelled')),
    CONSTRAINT ck_content_validation_report_checksum CHECK (summary_checksum IS NULL OR summary_checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_content_validation_report_count CHECK (finding_count >= 0),
    CONSTRAINT ck_content_validation_report_uuid7 CHECK (
        content.is_uuid7(report_id) AND content.is_uuid7(subject_revision_id)
        AND content.is_uuid7(validator_set_revision_id)
    ),
    CONSTRAINT ck_content_validation_report_dates CHECK (
        (status = 'running' AND completed_at IS NULL AND summary_checksum IS NULL)
        OR (completed_at IS NOT NULL AND completed_at >= started_at
            AND summary_checksum IS NOT NULL
            AND status IN ('passed','failed','human_required'))
    )
);
CREATE INDEX ix_content_validation_report_revision ON content.validation_reports(subject_revision_id, completed_at, report_id);
CREATE TABLE content.validation_findings (
    finding_id uuid PRIMARY KEY, report_id uuid NOT NULL REFERENCES content.validation_reports(report_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL, validator_code varchar(120) NOT NULL, severity varchar(24) NOT NULL, path varchar(500) NOT NULL, message_code varchar(120) NOT NULL,
    redacted_value varchar(1000), resolved_by_revision_id uuid REFERENCES content.content_revisions(content_revision_id) ON DELETE RESTRICT,
    CONSTRAINT ck_content_validation_finding_severity CHECK (severity IN ('blocking','warning','information','human_required')),
    CONSTRAINT ck_content_validation_finding_uuid7 CHECK (
        content.is_uuid7(finding_id) AND content.is_uuid7(report_id)
        AND (resolved_by_revision_id IS NULL OR content.is_uuid7(resolved_by_revision_id))
    ),
    CONSTRAINT uq_content_validation_finding_ordinal UNIQUE (report_id, ordinal)
);
CREATE TABLE content.content_approval_decisions (
    approval_decision_id uuid PRIMARY KEY, content_revision_id uuid NOT NULL REFERENCES content.content_revisions(content_revision_id) ON DELETE RESTRICT,
    author_id uuid NOT NULL, reviewer_id uuid NOT NULL, command_id uuid, decision varchar(16) NOT NULL, reason_code varchar(120), decided_at timestamptz NOT NULL,
    CONSTRAINT ck_content_approval_distinct CHECK (decision IN ('approved','rejected') AND author_id <> reviewer_id),
    CONSTRAINT uq_content_approval_decision_revision UNIQUE (content_revision_id),
    CONSTRAINT ck_content_approval_uuid7 CHECK (
        content.is_uuid7(approval_decision_id) AND content.is_uuid7(content_revision_id)
        AND content.is_uuid7(author_id) AND content.is_uuid7(reviewer_id)
    )
);
CREATE TABLE content.publication_manifests (
    publication_manifest_id uuid PRIMARY KEY, content_id uuid NOT NULL REFERENCES content.content_items(content_id) ON DELETE RESTRICT,
    content_revision_id uuid NOT NULL UNIQUE REFERENCES content.content_revisions(content_revision_id) ON DELETE RESTRICT,
    channel_code varchar(40) NOT NULL, compatibility_range varchar(120) NOT NULL, checksum varchar(64) NOT NULL,
    provenance_id uuid NOT NULL REFERENCES platform.provenance_records(provenance_id) ON DELETE RESTRICT, command_id uuid,
    entry_count integer NOT NULL,
    published_at timestamptz NOT NULL, retired_at timestamptz,
    CONSTRAINT ck_content_publication_manifest_checksum CHECK (checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_content_publication_manifest_count CHECK (entry_count >= 0),
    CONSTRAINT ck_content_publication_manifest_uuid7 CHECK (
        content.is_uuid7(publication_manifest_id) AND content.is_uuid7(content_id)
        AND content.is_uuid7(content_revision_id) AND content.is_uuid7(provenance_id)
    ),
    CONSTRAINT ck_content_publication_manifest_dates CHECK (
        retired_at IS NULL OR retired_at >= published_at
    )
);
CREATE UNIQUE INDEX uq_content_active_publication ON content.publication_manifests(content_id, channel_code, compatibility_range) WHERE retired_at IS NULL;
CREATE TABLE content.publication_manifest_entries (
    publication_manifest_id uuid NOT NULL REFERENCES content.publication_manifests(publication_manifest_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL, referenced_revision_id uuid NOT NULL, reference_kind varchar(120) NOT NULL,
    reference_checksum varchar(64) NOT NULL,
    reference_provenance_id uuid NOT NULL REFERENCES platform.provenance_records(provenance_id) ON DELETE RESTRICT,
    reference_rights_ref varchar(500) NOT NULL, reference_status varchar(24) NOT NULL,
    CONSTRAINT ck_content_publication_entry_uuid7 CHECK (
        content.is_uuid7(publication_manifest_id) AND content.is_uuid7(referenced_revision_id)
        AND content.is_uuid7(reference_provenance_id)
    ),
    CONSTRAINT ck_content_publication_entry_checksum CHECK (reference_checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_content_publication_entry_status CHECK (reference_status = 'published'),
    PRIMARY KEY (publication_manifest_id, ordinal)
);
CREATE TABLE content.historical_content_references (
    reference_id uuid PRIMARY KEY, content_revision_id uuid NOT NULL REFERENCES content.content_revisions(content_revision_id) ON DELETE RESTRICT,
    usage_type varchar(120) NOT NULL, usage_ref varchar(500) NOT NULL, context_checksum varchar(64) NOT NULL, recorded_at timestamptz NOT NULL,
    CONSTRAINT ck_content_history_checksum CHECK (context_checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_content_history_uuid7 CHECK (
        content.is_uuid7(reference_id) AND content.is_uuid7(content_revision_id)
    )
);
CREATE INDEX ix_content_history_revision ON content.historical_content_references(content_revision_id, recorded_at, reference_id);

CREATE TABLE content.editorial_pack_assignments (
    assignment_id uuid PRIMARY KEY,
    actor_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
    pack_id uuid NOT NULL REFERENCES catalogue.language_packs(pack_id) ON DELETE RESTRICT,
    editorial_role varchar(16) NOT NULL,
    granted_at timestamptz NOT NULL,
    granted_by_actor_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
    revoked_at timestamptz,
    CONSTRAINT ck_content_assignment_uuid7 CHECK (
        content.is_uuid7(assignment_id) AND content.is_uuid7(actor_id)
        AND content.is_uuid7(pack_id) AND content.is_uuid7(granted_by_actor_id)
    ),
    CONSTRAINT ck_content_assignment_role CHECK (editorial_role IN ('author','reviewer','admin')),
    CONSTRAINT ck_content_assignment_dates CHECK (revoked_at IS NULL OR revoked_at >= granted_at)
);
CREATE UNIQUE INDEX uq_content_editorial_pack_assignment_active
ON content.editorial_pack_assignments(actor_id, pack_id, editorial_role)
WHERE revoked_at IS NULL;

CREATE TABLE content.command_contexts (
    command_id uuid PRIMARY KEY REFERENCES platform.command_receipts(command_id) ON DELETE CASCADE,
    transaction_id bigint NOT NULL UNIQUE,
    command_type varchar(120) NOT NULL,
    actor_id uuid NOT NULL,
    actor_type varchar(16) NOT NULL,
    session_id uuid NOT NULL,
    pack_id uuid NOT NULL,
    opened_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_content_command_context_uuid7 CHECK (
        content.is_uuid7(command_id) AND content.is_uuid7(actor_id)
        AND content.is_uuid7(session_id) AND content.is_uuid7(pack_id)
    ),
    CONSTRAINT ck_content_command_context_actor_type CHECK (actor_type = 'account'),
    CONSTRAINT ck_content_command_context_type CHECK (command_type IN (
        'CreateContentDraft','ReviseContentDraft','ValidateContentRevision',
        'ApproveContentRevision','PublishContentRevision','RetireContentRevision'
    ))
);

CREATE FUNCTION content.current_command(allowed_types text[]) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, content, platform AS $function$
DECLARE active_command uuid;
BEGIN
    IF NOT pg_has_role(session_user, 'polyglot_runtime', 'member') THEN
        RETURN NULL;
    END IF;
    SELECT command_id INTO active_command
    FROM content.command_contexts
    WHERE transaction_id = txid_current() AND command_type = ANY(allowed_types);
    IF active_command IS NULL THEN
        RAISE EXCEPTION 'content command context required' USING ERRCODE = '42501';
    END IF;
    RETURN active_command;
END;
$function$;

CREATE FUNCTION content.begin_command(
    requested_command_id uuid, requested_actor_type text,
    requested_session_id uuid, requested_pack_id uuid, requested_session_proof text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, content, platform AS $function$
DECLARE
    receipt_type text;
    receipt_actor_id uuid;
    receipt_received_at timestamptz;
    session_roles varchar[];
    required_roles text[];
BEGIN
    IF NOT pg_has_role(session_user, 'polyglot_runtime', 'member') THEN
        RAISE EXCEPTION 'content command context is runtime only' USING ERRCODE = '42501';
    END IF;
    IF requested_actor_type <> 'account' THEN
        RAISE EXCEPTION 'human account command context required' USING ERRCODE = '42501';
    END IF;
    SELECT command_type, actor_id, received_at
    INTO receipt_type, receipt_actor_id, receipt_received_at
    FROM platform.command_receipts
    WHERE command_id = requested_command_id AND status = 'started' FOR UPDATE;
    IF receipt_type IS NULL OR receipt_type NOT IN (
        'CreateContentDraft','ReviseContentDraft','ValidateContentRevision',
        'ApproveContentRevision','PublishContentRevision','RetireContentRevision'
    ) THEN
        RAISE EXCEPTION 'started content command receipt required' USING ERRCODE = '23514';
    END IF;
    SELECT session.roles_snapshot INTO session_roles
    FROM identity.auth_sessions AS session
    JOIN identity.accounts AS account ON account.account_id = session.account_id
    WHERE session.session_id = requested_session_id
      AND session.account_id = receipt_actor_id
      AND session.session_fingerprint = encode(
          sha256(convert_to(requested_session_proof, 'UTF8')), 'hex'
      )
      AND session.revoked_at IS NULL
      AND account.status = 'active'
      AND account.session_version = session.account_session_version
      AND receipt_received_at >= session.last_seen_at
      AND receipt_received_at < session.idle_expires_at
      AND receipt_received_at < session.absolute_expires_at;
    IF session_roles IS NULL THEN
        RAISE EXCEPTION 'active human session required' USING ERRCODE = '42501';
    END IF;
    required_roles := CASE receipt_type
        WHEN 'CreateContentDraft' THEN ARRAY['author']
        WHEN 'ReviseContentDraft' THEN ARRAY['author']
        WHEN 'ValidateContentRevision' THEN ARRAY['author','reviewer']
        WHEN 'ApproveContentRevision' THEN ARRAY['reviewer']
        WHEN 'PublishContentRevision' THEN ARRAY['reviewer','admin']
        WHEN 'RetireContentRevision' THEN ARRAY['reviewer','admin']
    END;
    IF NOT session_roles && required_roles::varchar[] OR 'worker' = ANY(session_roles) THEN
        RAISE EXCEPTION 'editorial role required' USING ERRCODE = '42501';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM content.editorial_pack_assignments AS assignment
        WHERE assignment.actor_id = receipt_actor_id
          AND assignment.pack_id = requested_pack_id
          AND assignment.revoked_at IS NULL
          AND assignment.editorial_role = ANY(required_roles)
          AND assignment.editorial_role = ANY(session_roles)
    ) THEN
        RAISE EXCEPTION 'editorial pack scope required' USING ERRCODE = '42501';
    END IF;
    IF receipt_type = 'PublishContentRevision'
       AND NOT (
           receipt_received_at >= (
               SELECT authenticated_at FROM identity.auth_sessions
               WHERE session_id = requested_session_id
           )
           AND receipt_received_at - (
               SELECT authenticated_at FROM identity.auth_sessions
               WHERE session_id = requested_session_id
           ) <= interval '5 minutes'
       ) THEN
        RAISE EXCEPTION 'recent human authentication required' USING ERRCODE = '42501';
    END IF;
    INSERT INTO content.command_contexts(
        command_id, transaction_id, command_type, actor_id, actor_type, session_id, pack_id
    ) VALUES (
        requested_command_id, txid_current(), receipt_type, receipt_actor_id,
        requested_actor_type, requested_session_id, requested_pack_id
    );
END;
$function$;

CREATE FUNCTION content.verify_command_context() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, content, platform AS $function$
DECLARE
    receipt_status text;
    expected_event text;
    event_count integer;
    total_event_count integer;
    outbox_count integer;
BEGIN
    SELECT status INTO receipt_status FROM platform.command_receipts
    WHERE command_id = NEW.command_id;
    expected_event := CASE NEW.command_type
        WHEN 'CreateContentDraft' THEN 'content_draft_created'
        WHEN 'ReviseContentDraft' THEN 'content_draft_revised'
        WHEN 'PublishContentRevision' THEN 'content_published'
        WHEN 'RetireContentRevision' THEN 'content_retired'
        ELSE NULL
    END;
    SELECT count(*) INTO event_count FROM platform.domain_events
    WHERE command_id = NEW.command_id
      AND aggregate_type = 'content_item'
      AND actor_type = 'account'
      AND actor_id = NEW.actor_id
      AND (event_type = expected_event OR (
          NEW.command_type = 'ValidateContentRevision'
          AND event_type IN ('content_validated','content_validation_failed')
      ) OR (
          NEW.command_type = 'ApproveContentRevision'
          AND event_type IN ('content_approved','content_rejected')
      ));
    SELECT count(*) INTO total_event_count FROM platform.domain_events
    WHERE command_id = NEW.command_id;
    SELECT count(*) INTO outbox_count
    FROM platform.outbox_messages AS outbox
    JOIN platform.domain_events AS event ON event.event_id = outbox.event_id
    WHERE event.command_id = NEW.command_id;
    IF receipt_status <> 'succeeded' OR event_count <> 1
       OR total_event_count <> 1 OR outbox_count <> 1 THEN
        RAISE EXCEPTION 'content command requires succeeded receipt, exact event and outbox'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION content.require_item_pack(requested_content_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, content AS $function$
DECLARE context_pack uuid; item_pack uuid;
BEGIN
    SELECT pack_id INTO context_pack FROM content.command_contexts
    WHERE transaction_id = txid_current();
    IF context_pack IS NULL THEN
        RETURN;
    END IF;
    SELECT pack_id INTO item_pack FROM content.content_items
    WHERE content_id = requested_content_id;
    IF item_pack IS NULL OR item_pack <> context_pack THEN
        RAISE EXCEPTION 'editorial command pack mismatch' USING ERRCODE = '42501';
    END IF;
END;
$function$;

CREATE FUNCTION content.guard_content_item() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, content, catalogue AS $function$
DECLARE parent_root uuid; context_pack uuid;
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM content.current_command(ARRAY['CreateContentDraft']);
        SELECT pack_id INTO context_pack FROM content.command_contexts
        WHERE transaction_id = txid_current();
        IF context_pack IS NOT NULL AND NEW.pack_id <> context_pack THEN
            RAISE EXCEPTION 'editorial command pack mismatch' USING ERRCODE = '42501';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM catalogue.language_pack_revisions AS revision
            JOIN catalogue.language_pack_publications AS publication
              ON publication.pack_revision_id = revision.pack_revision_id
            WHERE revision.pack_id = NEW.pack_id
              AND revision.target_variety_id = NEW.variety_id
              AND revision.status = 'published' AND publication.retired_at IS NULL
        ) THEN
            RAISE EXCEPTION 'content pack and variety mismatch' USING ERRCODE = '23514';
        END IF;
        IF NEW.parent_content_id IS NULL AND NEW.lineage_root_id <> NEW.content_id THEN
            RAISE EXCEPTION 'invalid content lineage' USING ERRCODE = '23514';
        END IF;
        IF NEW.parent_content_id IS NOT NULL THEN
            SELECT lineage_root_id INTO parent_root FROM content.content_items
            WHERE content_id = NEW.parent_content_id;
            IF parent_root IS NULL OR parent_root <> NEW.lineage_root_id THEN
                RAISE EXCEPTION 'invalid content lineage' USING ERRCODE = '23514';
            END IF;
        END IF;
        RETURN NEW;
    END IF;
    PERFORM content.current_command(ARRAY[
        'ReviseContentDraft','ValidateContentRevision','ApproveContentRevision',
        'PublishContentRevision','RetireContentRevision'
    ]);
    IF TG_OP = 'DELETE' OR NEW.content_id <> OLD.content_id
       OR NEW.content_type <> OLD.content_type OR NEW.pack_id <> OLD.pack_id
       OR NEW.variety_id <> OLD.variety_id
       OR NEW.editorial_owner_id <> OLD.editorial_owner_id
       OR NEW.lineage_root_id <> OLD.lineage_root_id
       OR NEW.parent_content_id IS DISTINCT FROM OLD.parent_content_id
       OR NEW.created_at <> OLD.created_at OR NEW.version <> OLD.version + 1 THEN
        RAISE EXCEPTION 'content item is immutable except next version' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION content.guard_content_revision() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.revision_no = 1 THEN
            PERFORM content.current_command(ARRAY['CreateContentDraft']);
        ELSE
            PERFORM content.current_command(ARRAY['ReviseContentDraft']);
        END IF;
        PERFORM content.require_item_pack(NEW.content_id);
        IF NEW.status <> 'draft' OR NEW.approved_by_actor_id IS NOT NULL
           OR NEW.channel_code IS NOT NULL OR NEW.compatibility_range IS NOT NULL
           OR NEW.validated_at IS NOT NULL OR NEW.approved_at IS NOT NULL
           OR NEW.published_at IS NOT NULL OR NEW.retired_at IS NOT NULL THEN
            RAISE EXCEPTION 'new content revision must be draft' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'content revision is immutable' USING ERRCODE = '23514';
    END IF;
    PERFORM content.require_item_pack(NEW.content_id);
    IF ROW(NEW.content_revision_id, NEW.content_id, NEW.revision_no, NEW.schema_version,
           NEW.payload, NEW.payload_checksum, NEW.provenance_id, NEW.rights_ref,
           NEW.pinned_revision_refs, NEW.created_by_actor_id, NEW.supersedes_revision_id,
           NEW.created_at)
       IS DISTINCT FROM
       ROW(OLD.content_revision_id, OLD.content_id, OLD.revision_no, OLD.schema_version,
           OLD.payload, OLD.payload_checksum, OLD.provenance_id, OLD.rights_ref,
           OLD.pinned_revision_refs, OLD.created_by_actor_id, OLD.supersedes_revision_id,
           OLD.created_at) THEN
        RAISE EXCEPTION 'content revision is immutable' USING ERRCODE = '23514';
    END IF;
    IF NOT ((OLD.status = 'draft' AND NEW.status IN ('validating','abandoned'))
        OR (OLD.status = 'validating' AND NEW.status IN ('validated','draft'))
        OR (OLD.status = 'validated' AND NEW.status IN ('approved','rejected'))
        OR (OLD.status = 'approved' AND NEW.status = 'published')
        OR (OLD.status = 'published' AND NEW.status IN ('retired','superseded'))) THEN
        RAISE EXCEPTION 'invalid content revision transition' USING ERRCODE = '23514';
    END IF;
    IF OLD.status = 'draft' AND NEW.status = 'validating' THEN
        PERFORM content.current_command(ARRAY['ValidateContentRevision']);
    ELSIF OLD.status = 'validating' THEN
        PERFORM content.current_command(ARRAY['ValidateContentRevision']);
    ELSIF OLD.status = 'validated' THEN
        PERFORM content.current_command(ARRAY['ApproveContentRevision']);
    ELSIF OLD.status = 'approved' THEN
        PERFORM content.current_command(ARRAY['PublishContentRevision']);
    ELSIF OLD.status = 'published' AND NEW.status = 'superseded' THEN
        PERFORM content.current_command(ARRAY['PublishContentRevision']);
    ELSIF OLD.status = 'published' AND NEW.status = 'retired' THEN
        PERFORM content.current_command(ARRAY['RetireContentRevision']);
    END IF;
    IF OLD.status = 'validating' AND NEW.status = 'validated' AND NOT EXISTS (
        SELECT 1 FROM content.validation_reports
        WHERE subject_revision_id = NEW.content_revision_id AND status = 'passed'
    ) THEN RAISE EXCEPTION 'validated revision requires passed report' USING ERRCODE = '23514'; END IF;
    IF OLD.status = 'validating' AND NEW.status = 'draft' AND NOT EXISTS (
        SELECT 1 FROM content.validation_reports
        WHERE subject_revision_id = NEW.content_revision_id AND status IN ('failed','human_required')
    ) THEN RAISE EXCEPTION 'draft return requires failed report' USING ERRCODE = '23514'; END IF;
    IF OLD.status = 'validated' AND NEW.status = 'approved' AND (
        NEW.approved_by_actor_id IS NULL OR NEW.approved_by_actor_id = NEW.created_by_actor_id
        OR NOT EXISTS (
            SELECT 1 FROM content.content_approval_decisions
            WHERE content_revision_id = NEW.content_revision_id AND decision = 'approved'
              AND author_id = NEW.created_by_actor_id
              AND reviewer_id = NEW.approved_by_actor_id
        )
    ) THEN RAISE EXCEPTION 'self approval forbidden or decision missing' USING ERRCODE = '23514'; END IF;
    IF OLD.status = 'validated' AND NEW.status = 'rejected' AND (
        NEW.approved_by_actor_id IS NOT NULL OR NEW.approved_at IS NOT NULL
        OR NEW.retired_at IS NULL OR NOT EXISTS (
            SELECT 1 FROM content.content_approval_decisions
            WHERE content_revision_id = NEW.content_revision_id AND decision = 'rejected'
              AND author_id = NEW.created_by_actor_id
              AND reviewer_id <> NEW.created_by_actor_id
        )
    ) THEN RAISE EXCEPTION 'rejected revision requires decision' USING ERRCODE = '23514'; END IF;
    IF OLD.status = 'approved' AND NEW.status = 'published' AND NOT EXISTS (
        SELECT 1 FROM content.publication_manifests AS manifest
        WHERE manifest.content_revision_id = NEW.content_revision_id
          AND manifest.content_id = NEW.content_id
          AND manifest.channel_code = NEW.channel_code
          AND manifest.compatibility_range = NEW.compatibility_range
          AND manifest.retired_at IS NULL
          AND manifest.entry_count = (
              SELECT count(*) FROM content.publication_manifest_entries AS entry
              WHERE entry.publication_manifest_id = manifest.publication_manifest_id
          )
          AND (
              manifest.entry_count = 0 OR manifest.entry_count = (
                  SELECT max(entry.ordinal) FROM content.publication_manifest_entries AS entry
                  WHERE entry.publication_manifest_id = manifest.publication_manifest_id
              )
          )
    ) THEN RAISE EXCEPTION 'published revision requires complete active manifest' USING ERRCODE = '23514'; END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION content.guard_validation_report_insert() RETURNS trigger LANGUAGE plpgsql AS $function$
DECLARE active_command uuid;
BEGIN
    active_command := content.current_command(ARRAY['ValidateContentRevision']);
    IF active_command IS NOT NULL AND NEW.command_id IS DISTINCT FROM active_command THEN
        RAISE EXCEPTION 'validation report command mismatch' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM content.content_revisions WHERE content_revision_id = NEW.subject_revision_id AND status = 'validating') THEN
        RAISE EXCEPTION 'validation report requires validating revision' USING ERRCODE = '23514';
    END IF;
    IF NEW.status <> 'running' OR NEW.completed_at IS NOT NULL
       OR NEW.summary_checksum IS NOT NULL OR NEW.finding_count <> 0 THEN
        RAISE EXCEPTION 'validation report must start open' USING ERRCODE = '23514';
    END IF;
    PERFORM content.require_item_pack((
        SELECT content_id FROM content.content_revisions
        WHERE content_revision_id = NEW.subject_revision_id
    ));
    RETURN NEW;
END;
$function$;

CREATE FUNCTION content.guard_validation_report_seal() RETURNS trigger LANGUAGE plpgsql AS $function$
DECLARE
    finding_total integer;
    highest_ordinal integer;
    blocking_total integer;
    human_total integer;
    canonical_findings jsonb;
BEGIN
    IF TG_OP = 'DELETE' OR OLD.status <> 'running'
       OR NEW.status NOT IN ('passed','failed','human_required')
       OR ROW(NEW.report_id, NEW.subject_revision_id, NEW.validator_set_revision_id,
              NEW.command_id, NEW.started_at)
          IS DISTINCT FROM
          ROW(OLD.report_id, OLD.subject_revision_id, OLD.validator_set_revision_id,
              OLD.command_id, OLD.started_at) THEN
        RAISE EXCEPTION 'validation_reports is append-only after seal' USING ERRCODE = '23514';
    END IF;
    PERFORM content.current_command(ARRAY['ValidateContentRevision']);
    SELECT count(*), COALESCE(max(ordinal), 0),
           count(*) FILTER (WHERE severity = 'blocking'),
           count(*) FILTER (WHERE severity = 'human_required'),
           COALESCE(
               jsonb_agg(
                   jsonb_build_object(
                       'ordinal', ordinal, 'validator_code', validator_code,
                       'severity', severity, 'path', path,
                       'message_code', message_code, 'redacted_value', redacted_value
                   ) ORDER BY ordinal
               ), '[]'::jsonb
           )
    INTO finding_total, highest_ordinal, blocking_total, human_total, canonical_findings
    FROM content.validation_findings WHERE report_id = NEW.report_id;
    IF highest_ordinal <> finding_total THEN
        RAISE EXCEPTION 'validation finding ordinals must be contiguous' USING ERRCODE = '23514';
    END IF;
    IF (NEW.status = 'passed' AND (blocking_total <> 0 OR human_total <> 0))
       OR (NEW.status = 'failed' AND (blocking_total = 0 OR human_total <> 0))
       OR (NEW.status = 'human_required' AND human_total = 0) THEN
        RAISE EXCEPTION 'validation report status contradicts findings' USING ERRCODE = '23514';
    END IF;
    NEW.finding_count := finding_total;
    NEW.summary_checksum := encode(
        sha256(convert_to(jsonb_build_object(
            'status', NEW.status, 'findings', canonical_findings
        )::text, 'UTF8')), 'hex'
    );
    IF NEW.completed_at IS NULL OR NEW.completed_at < NEW.started_at THEN
        RAISE EXCEPTION 'validation report completion required' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION content.guard_approval_decision_insert() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, content AS $function$
DECLARE active_command uuid; context_actor uuid;
BEGIN
    active_command := content.current_command(ARRAY['ApproveContentRevision']);
    IF active_command IS NOT NULL AND NEW.command_id IS DISTINCT FROM active_command THEN
        RAISE EXCEPTION 'approval decision command mismatch' USING ERRCODE = '23514';
    END IF;
    SELECT actor_id INTO context_actor FROM content.command_contexts
    WHERE transaction_id = txid_current();
    IF context_actor IS NOT NULL AND NEW.reviewer_id <> context_actor THEN
        RAISE EXCEPTION 'approval decision reviewer mismatch' USING ERRCODE = '42501';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM content.content_revisions
        WHERE content_revision_id = NEW.content_revision_id AND status = 'validated'
          AND created_by_actor_id = NEW.author_id AND created_by_actor_id <> NEW.reviewer_id
    ) THEN RAISE EXCEPTION 'approval decision requires distinct reviewer' USING ERRCODE = '23514'; END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION content.guard_manifest_insert() RETURNS trigger LANGUAGE plpgsql AS $function$
DECLARE active_command uuid;
BEGIN
    active_command := content.current_command(ARRAY['PublishContentRevision']);
    IF active_command IS NOT NULL AND NEW.command_id IS DISTINCT FROM active_command THEN
        RAISE EXCEPTION 'publication manifest command mismatch' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM content.content_revisions
        WHERE content_revision_id = NEW.content_revision_id AND content_id = NEW.content_id
          AND status = 'approved'
    ) THEN RAISE EXCEPTION 'manifest requires approved revision' USING ERRCODE = '23514'; END IF;
    PERFORM content.require_item_pack(NEW.content_id);
    RETURN NEW;
END;
$function$;

CREATE FUNCTION content.guard_validation_finding_insert() RETURNS trigger LANGUAGE plpgsql AS $function$
DECLARE active_command uuid;
BEGIN
    BEGIN
        active_command := content.current_command(ARRAY['ValidateContentRevision']);
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE EXCEPTION 'terminal proof cannot be extended' USING ERRCODE = '23514';
    END;
    IF active_command IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM content.validation_reports
        WHERE report_id = NEW.report_id AND command_id = active_command
          AND status = 'running'
          AND EXISTS (
              SELECT 1 FROM content.content_revisions
              WHERE content_revision_id = subject_revision_id AND status = 'validating'
          )
    ) THEN
        RAISE EXCEPTION 'terminal proof cannot be extended: sealed validation report' USING ERRCODE = '23514';
    ELSIF active_command IS NULL AND NOT EXISTS (
        SELECT 1 FROM content.validation_reports
        WHERE report_id = NEW.report_id AND status = 'running'
          AND EXISTS (
              SELECT 1 FROM content.content_revisions
              WHERE content_revision_id = subject_revision_id AND status = 'validating'
          )
    ) THEN
        RAISE EXCEPTION 'terminal proof cannot be extended: sealed validation report' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION content.guard_manifest_entry_insert() RETURNS trigger LANGUAGE plpgsql AS $function$
DECLARE active_command uuid;
BEGIN
    BEGIN
        active_command := content.current_command(ARRAY['PublishContentRevision']);
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE EXCEPTION 'terminal proof cannot be extended' USING ERRCODE = '23514';
    END;
    IF active_command IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM content.publication_manifests AS manifest
        JOIN content.content_revisions AS revision
          ON revision.content_revision_id = manifest.content_revision_id
        WHERE manifest.publication_manifest_id = NEW.publication_manifest_id
          AND manifest.command_id = active_command
          AND revision.status = 'approved'
          AND NEW.ordinal BETWEEN 1 AND manifest.entry_count
    ) THEN
        RAISE EXCEPTION 'terminal proof cannot be extended: sealed publication manifest' USING ERRCODE = '23514';
    ELSIF active_command IS NULL AND NOT EXISTS (
        SELECT 1 FROM content.publication_manifests AS manifest
        JOIN content.content_revisions AS revision
          ON revision.content_revision_id = manifest.content_revision_id
        WHERE manifest.publication_manifest_id = NEW.publication_manifest_id
          AND revision.status = 'approved'
          AND NEW.ordinal BETWEEN 1 AND manifest.entry_count
    ) THEN
        RAISE EXCEPTION 'terminal proof cannot be extended: sealed publication manifest' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION content.guard_append_only() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = '23514';
END;
$function$;

CREATE FUNCTION content.guard_manifest_closure() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
    IF OLD.retired_at IS NULL AND NEW.retired_at IS NOT NULL THEN
        PERFORM content.current_command(ARRAY['PublishContentRevision','RetireContentRevision']);
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.retired_at IS NULL AND NEW.retired_at IS NOT NULL
       AND ROW(NEW.publication_manifest_id, NEW.content_id, NEW.content_revision_id,
               NEW.channel_code, NEW.compatibility_range, NEW.checksum,
               NEW.provenance_id, NEW.entry_count, NEW.published_at)
           IS NOT DISTINCT FROM
           ROW(OLD.publication_manifest_id, OLD.content_id, OLD.content_revision_id,
               OLD.channel_code, OLD.compatibility_range, OLD.checksum,
               OLD.provenance_id, OLD.entry_count, OLD.published_at) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'publication_manifests is append-only except closure' USING ERRCODE = '23514';
END;
$function$;

CREATE TRIGGER guard_content_item BEFORE INSERT OR UPDATE OR DELETE ON content.content_items FOR EACH ROW EXECUTE FUNCTION content.guard_content_item();
CREATE TRIGGER guard_content_revision BEFORE INSERT OR UPDATE OR DELETE ON content.content_revisions FOR EACH ROW EXECUTE FUNCTION content.guard_content_revision();
CREATE TRIGGER guard_validation_report_insert BEFORE INSERT ON content.validation_reports FOR EACH ROW EXECUTE FUNCTION content.guard_validation_report_insert();
CREATE TRIGGER guard_validation_finding_insert BEFORE INSERT ON content.validation_findings FOR EACH ROW EXECUTE FUNCTION content.guard_validation_finding_insert();
CREATE TRIGGER guard_approval_decision_insert BEFORE INSERT ON content.content_approval_decisions FOR EACH ROW EXECUTE FUNCTION content.guard_approval_decision_insert();
CREATE TRIGGER guard_manifest_insert BEFORE INSERT ON content.publication_manifests FOR EACH ROW EXECUTE FUNCTION content.guard_manifest_insert();
CREATE TRIGGER guard_manifest_entry_insert BEFORE INSERT ON content.publication_manifest_entries FOR EACH ROW EXECUTE FUNCTION content.guard_manifest_entry_insert();
CREATE TRIGGER guard_validation_report_seal BEFORE UPDATE OR DELETE ON content.validation_reports FOR EACH ROW EXECUTE FUNCTION content.guard_validation_report_seal();
CREATE TRIGGER guard_validation_finding_append_only BEFORE UPDATE OR DELETE ON content.validation_findings FOR EACH ROW EXECUTE FUNCTION content.guard_append_only();
CREATE TRIGGER guard_approval_decision_append_only BEFORE UPDATE OR DELETE ON content.content_approval_decisions FOR EACH ROW EXECUTE FUNCTION content.guard_append_only();
CREATE TRIGGER guard_manifest_closure BEFORE UPDATE OR DELETE ON content.publication_manifests FOR EACH ROW EXECUTE FUNCTION content.guard_manifest_closure();
CREATE TRIGGER guard_manifest_entry_append_only BEFORE UPDATE OR DELETE ON content.publication_manifest_entries FOR EACH ROW EXECUTE FUNCTION content.guard_append_only();
CREATE TRIGGER guard_history_append_only BEFORE UPDATE OR DELETE ON content.historical_content_references FOR EACH ROW EXECUTE FUNCTION content.guard_append_only();
CREATE CONSTRAINT TRIGGER verify_content_command
AFTER INSERT ON content.command_contexts DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION content.verify_command_context();
REVOKE ALL ON SCHEMA content FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA content TO polyglot_migration;
GRANT USAGE ON SCHEMA content TO polyglot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA content TO polyglot_migration;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA content TO polyglot_runtime;
REVOKE ALL ON TABLE content.command_contexts FROM polyglot_runtime;
REVOKE INSERT, UPDATE, DELETE ON TABLE content.editorial_pack_assignments FROM polyglot_runtime;
ALTER SCHEMA content OWNER TO polyglot_migration;
DO $owners$ DECLARE item record; BEGIN FOR item IN SELECT tablename FROM pg_tables WHERE schemaname = 'content' LOOP EXECUTE format('ALTER TABLE content.%I OWNER TO polyglot_migration', item.tablename); END LOOP; END; $owners$;
ALTER FUNCTION content.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION content.current_command(text[]) OWNER TO polyglot_migration;
ALTER FUNCTION content.begin_command(uuid,text,uuid,uuid,text) OWNER TO polyglot_migration;
ALTER FUNCTION content.verify_command_context() OWNER TO polyglot_migration;
ALTER FUNCTION content.require_item_pack(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_content_item() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_content_revision() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_validation_report_insert() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_validation_report_seal() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_validation_finding_insert() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_approval_decision_insert() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_manifest_insert() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_manifest_entry_insert() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_append_only() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_manifest_closure() OWNER TO polyglot_migration;
REVOKE ALL ON FUNCTION content.begin_command(uuid,text,uuid,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION content.begin_command(uuid,text,uuid,uuid,text) TO polyglot_runtime;
"""


async def _execute_content_ddl(connection: Connection) -> None:
    await connection.execute(CONTENT_DDL)


def upgrade() -> None:
    op.get_bind().connection.run_async(_execute_content_ddl)


def downgrade() -> None:
    op.execute("DROP SCHEMA content CASCADE")
