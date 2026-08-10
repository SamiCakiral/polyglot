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
    variety_id uuid NOT NULL REFERENCES catalogue.language_varieties(variety_id) ON DELETE RESTRICT,
    editorial_owner_id uuid NOT NULL, lineage_root_id uuid NOT NULL,
    parent_content_id uuid REFERENCES content.content_items(content_id) ON DELETE RESTRICT,
    version integer NOT NULL, created_at timestamptz NOT NULL,
    CONSTRAINT ck_content_item_uuid7 CHECK (content.is_uuid7(content_id) AND content.is_uuid7(variety_id) AND content.is_uuid7(editorial_owner_id) AND content.is_uuid7(lineage_root_id)),
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
    validator_set_revision_id uuid NOT NULL, status varchar(24) NOT NULL, started_at timestamptz NOT NULL, completed_at timestamptz, summary_checksum varchar(64) NOT NULL,
    CONSTRAINT ck_content_validation_report_status CHECK (status IN ('pending','running','passed','failed','human_required','cancelled')),
    CONSTRAINT ck_content_validation_report_checksum CHECK (summary_checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_content_validation_report_uuid7 CHECK (
        content.is_uuid7(report_id) AND content.is_uuid7(subject_revision_id)
        AND content.is_uuid7(validator_set_revision_id)
    ),
    CONSTRAINT ck_content_validation_report_dates CHECK (
        completed_at IS NOT NULL AND completed_at >= started_at
        AND status IN ('passed','failed','human_required')
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
    author_id uuid NOT NULL, reviewer_id uuid NOT NULL, decision varchar(16) NOT NULL, reason_code varchar(120), decided_at timestamptz NOT NULL,
    CONSTRAINT ck_content_approval_distinct CHECK (decision IN ('approved','rejected') AND author_id <> reviewer_id),
    CONSTRAINT ck_content_approval_uuid7 CHECK (
        content.is_uuid7(approval_decision_id) AND content.is_uuid7(content_revision_id)
        AND content.is_uuid7(author_id) AND content.is_uuid7(reviewer_id)
    )
);
CREATE TABLE content.publication_manifests (
    publication_manifest_id uuid PRIMARY KEY, content_id uuid NOT NULL REFERENCES content.content_items(content_id) ON DELETE RESTRICT,
    content_revision_id uuid NOT NULL UNIQUE REFERENCES content.content_revisions(content_revision_id) ON DELETE RESTRICT,
    channel_code varchar(40) NOT NULL, compatibility_range varchar(120) NOT NULL, checksum varchar(64) NOT NULL,
    provenance_id uuid NOT NULL REFERENCES platform.provenance_records(provenance_id) ON DELETE RESTRICT,
    published_at timestamptz NOT NULL, retired_at timestamptz,
    CONSTRAINT ck_content_publication_manifest_checksum CHECK (checksum ~ '^[0-9a-f]{64}$'),
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

CREATE FUNCTION content.guard_content_item() RETURNS trigger LANGUAGE plpgsql AS $function$
DECLARE parent_root uuid;
BEGIN
    IF TG_OP = 'INSERT' THEN
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
    IF TG_OP = 'DELETE' OR NEW.content_id <> OLD.content_id
       OR NEW.content_type <> OLD.content_type OR NEW.variety_id <> OLD.variety_id
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
    IF OLD.status = 'approved' AND NEW.status = 'published' AND NOT EXISTS (
        SELECT 1 FROM content.publication_manifests
        WHERE content_revision_id = NEW.content_revision_id AND content_id = NEW.content_id
          AND channel_code = NEW.channel_code AND compatibility_range = NEW.compatibility_range
          AND retired_at IS NULL
    ) THEN RAISE EXCEPTION 'published revision requires active manifest' USING ERRCODE = '23514'; END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION content.guard_validation_report_insert() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM content.content_revisions WHERE content_revision_id = NEW.subject_revision_id AND status = 'validating') THEN
        RAISE EXCEPTION 'validation report requires validating revision' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION content.guard_approval_decision_insert() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM content.content_revisions
        WHERE content_revision_id = NEW.content_revision_id AND status = 'validated'
          AND created_by_actor_id = NEW.author_id AND created_by_actor_id <> NEW.reviewer_id
    ) THEN RAISE EXCEPTION 'approval decision requires distinct reviewer' USING ERRCODE = '23514'; END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION content.guard_manifest_insert() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM content.content_revisions
        WHERE content_revision_id = NEW.content_revision_id AND content_id = NEW.content_id
          AND status = 'approved'
    ) THEN RAISE EXCEPTION 'manifest requires approved revision' USING ERRCODE = '23514'; END IF;
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
    IF TG_OP = 'UPDATE' AND OLD.retired_at IS NULL AND NEW.retired_at IS NOT NULL
       AND ROW(NEW.publication_manifest_id, NEW.content_id, NEW.content_revision_id,
               NEW.channel_code, NEW.compatibility_range, NEW.checksum,
               NEW.provenance_id, NEW.published_at)
           IS NOT DISTINCT FROM
           ROW(OLD.publication_manifest_id, OLD.content_id, OLD.content_revision_id,
               OLD.channel_code, OLD.compatibility_range, OLD.checksum,
               OLD.provenance_id, OLD.published_at) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'publication_manifests is append-only except closure' USING ERRCODE = '23514';
END;
$function$;

CREATE TRIGGER guard_content_item BEFORE INSERT OR UPDATE OR DELETE ON content.content_items FOR EACH ROW EXECUTE FUNCTION content.guard_content_item();
CREATE TRIGGER guard_content_revision BEFORE INSERT OR UPDATE OR DELETE ON content.content_revisions FOR EACH ROW EXECUTE FUNCTION content.guard_content_revision();
CREATE TRIGGER guard_validation_report_insert BEFORE INSERT ON content.validation_reports FOR EACH ROW EXECUTE FUNCTION content.guard_validation_report_insert();
CREATE TRIGGER guard_approval_decision_insert BEFORE INSERT ON content.content_approval_decisions FOR EACH ROW EXECUTE FUNCTION content.guard_approval_decision_insert();
CREATE TRIGGER guard_manifest_insert BEFORE INSERT ON content.publication_manifests FOR EACH ROW EXECUTE FUNCTION content.guard_manifest_insert();
CREATE TRIGGER guard_validation_report_append_only BEFORE UPDATE OR DELETE ON content.validation_reports FOR EACH ROW EXECUTE FUNCTION content.guard_append_only();
CREATE TRIGGER guard_validation_finding_append_only BEFORE UPDATE OR DELETE ON content.validation_findings FOR EACH ROW EXECUTE FUNCTION content.guard_append_only();
CREATE TRIGGER guard_approval_decision_append_only BEFORE UPDATE OR DELETE ON content.content_approval_decisions FOR EACH ROW EXECUTE FUNCTION content.guard_append_only();
CREATE TRIGGER guard_manifest_closure BEFORE UPDATE OR DELETE ON content.publication_manifests FOR EACH ROW EXECUTE FUNCTION content.guard_manifest_closure();
CREATE TRIGGER guard_manifest_entry_append_only BEFORE UPDATE OR DELETE ON content.publication_manifest_entries FOR EACH ROW EXECUTE FUNCTION content.guard_append_only();
CREATE TRIGGER guard_history_append_only BEFORE UPDATE OR DELETE ON content.historical_content_references FOR EACH ROW EXECUTE FUNCTION content.guard_append_only();
REVOKE ALL ON SCHEMA content FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA content TO polyglot_migration;
GRANT USAGE ON SCHEMA content TO polyglot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA content TO polyglot_migration, polyglot_runtime;
ALTER SCHEMA content OWNER TO polyglot_migration;
DO $owners$ DECLARE item record; BEGIN FOR item IN SELECT tablename FROM pg_tables WHERE schemaname = 'content' LOOP EXECUTE format('ALTER TABLE content.%I OWNER TO polyglot_migration', item.tablename); END LOOP; END; $owners$;
ALTER FUNCTION content.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_content_item() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_content_revision() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_validation_report_insert() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_approval_decision_insert() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_manifest_insert() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_append_only() OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_manifest_closure() OWNER TO polyglot_migration;
"""


async def _execute_content_ddl(connection: Connection) -> None:
    await connection.execute(CONTENT_DDL)


def upgrade() -> None:
    op.get_bind().connection.run_async(_execute_content_ddl)


def downgrade() -> None:
    op.execute("DROP SCHEMA content CASCADE")
