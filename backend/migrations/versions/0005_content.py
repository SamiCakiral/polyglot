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
    CONSTRAINT ck_content_revision_status CHECK (status IN ('draft','validating','validated','approved','published','retired','superseded','rejected','abandoned')),
    CONSTRAINT ck_content_revision_payload CHECK (jsonb_typeof(payload) = 'object' AND payload->>'schema_version' ~ '^[1-9][0-9]*$' AND jsonb_typeof(pinned_revision_refs) = 'array'),
    CONSTRAINT uq_content_revision_number UNIQUE (content_id, revision_no)
);
CREATE INDEX ix_content_revisions_content_status ON content.content_revisions(content_id, status, revision_no);
CREATE TABLE content.validation_reports (
    report_id uuid PRIMARY KEY, subject_revision_id uuid NOT NULL REFERENCES content.content_revisions(content_revision_id) ON DELETE RESTRICT,
    validator_set_revision_id uuid NOT NULL, status varchar(24) NOT NULL, started_at timestamptz NOT NULL, completed_at timestamptz, summary_checksum varchar(64) NOT NULL,
    CONSTRAINT ck_content_validation_report_status CHECK (status IN ('pending','running','passed','failed','human_required','cancelled')),
    CONSTRAINT ck_content_validation_report_checksum CHECK (summary_checksum ~ '^[0-9a-f]{64}$')
);
CREATE TABLE content.validation_findings (
    finding_id uuid PRIMARY KEY, report_id uuid NOT NULL REFERENCES content.validation_reports(report_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL, validator_code varchar(120) NOT NULL, severity varchar(24) NOT NULL, path varchar(500) NOT NULL, message_code varchar(120) NOT NULL,
    redacted_value varchar(1000), resolved_by_revision_id uuid REFERENCES content.content_revisions(content_revision_id) ON DELETE RESTRICT,
    CONSTRAINT ck_content_validation_finding_severity CHECK (severity IN ('blocking','warning','information','human_required')),
    CONSTRAINT uq_content_validation_finding_ordinal UNIQUE (report_id, ordinal)
);
CREATE TABLE content.content_approval_decisions (
    approval_decision_id uuid PRIMARY KEY, content_revision_id uuid NOT NULL REFERENCES content.content_revisions(content_revision_id) ON DELETE RESTRICT,
    author_id uuid NOT NULL, reviewer_id uuid NOT NULL, decision varchar(16) NOT NULL, reason_code varchar(120), decided_at timestamptz NOT NULL,
    CONSTRAINT ck_content_approval_distinct CHECK (decision IN ('approved','rejected') AND author_id <> reviewer_id)
);
CREATE TABLE content.publication_manifests (
    publication_manifest_id uuid PRIMARY KEY, content_id uuid NOT NULL REFERENCES content.content_items(content_id) ON DELETE RESTRICT,
    content_revision_id uuid NOT NULL UNIQUE REFERENCES content.content_revisions(content_revision_id) ON DELETE RESTRICT,
    channel_code varchar(40) NOT NULL, compatibility_range varchar(120) NOT NULL, checksum varchar(64) NOT NULL,
    provenance_id uuid NOT NULL REFERENCES platform.provenance_records(provenance_id) ON DELETE RESTRICT,
    published_at timestamptz NOT NULL, retired_at timestamptz,
    CONSTRAINT ck_content_publication_manifest_checksum CHECK (checksum ~ '^[0-9a-f]{64}$')
);
CREATE UNIQUE INDEX uq_content_active_publication ON content.publication_manifests(content_id, channel_code, compatibility_range) WHERE retired_at IS NULL;
CREATE TABLE content.publication_manifest_entries (
    publication_manifest_id uuid NOT NULL REFERENCES content.publication_manifests(publication_manifest_id) ON DELETE RESTRICT,
    ordinal integer NOT NULL, referenced_revision_id uuid NOT NULL, reference_kind varchar(120) NOT NULL,
    PRIMARY KEY (publication_manifest_id, ordinal)
);
CREATE TABLE content.historical_content_references (
    reference_id uuid PRIMARY KEY, content_revision_id uuid NOT NULL REFERENCES content.content_revisions(content_revision_id) ON DELETE RESTRICT,
    usage_type varchar(120) NOT NULL, usage_ref varchar(500) NOT NULL, context_checksum varchar(64) NOT NULL, recorded_at timestamptz NOT NULL,
    CONSTRAINT ck_content_history_checksum CHECK (context_checksum ~ '^[0-9a-f]{64}$')
);
CREATE FUNCTION content.guard_published_revision() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
    IF TG_OP = 'DELETE' AND OLD.status IN ('published','retired','superseded') THEN RAISE EXCEPTION 'published revision is immutable' USING ERRCODE = '23514'; END IF;
    IF TG_OP = 'UPDATE' AND OLD.status IN ('published','retired','superseded') AND (
        NEW.content_revision_id <> OLD.content_revision_id OR NEW.content_id <> OLD.content_id OR NEW.revision_no <> OLD.revision_no OR NEW.schema_version <> OLD.schema_version OR NEW.payload <> OLD.payload OR NEW.payload_checksum <> OLD.payload_checksum OR NEW.provenance_id <> OLD.provenance_id OR NEW.rights_ref <> OLD.rights_ref OR NEW.pinned_revision_refs <> OLD.pinned_revision_refs OR NEW.created_by_actor_id <> OLD.created_by_actor_id OR NEW.approved_by_actor_id IS DISTINCT FROM OLD.approved_by_actor_id OR NEW.channel_code IS DISTINCT FROM OLD.channel_code OR NEW.compatibility_range IS DISTINCT FROM OLD.compatibility_range OR NEW.supersedes_revision_id IS DISTINCT FROM OLD.supersedes_revision_id OR NEW.created_at <> OLD.created_at OR NEW.validated_at IS DISTINCT FROM OLD.validated_at OR NEW.approved_at IS DISTINCT FROM OLD.approved_at OR NEW.published_at IS DISTINCT FROM OLD.published_at OR (OLD.status IN ('retired','superseded') AND NEW.status <> OLD.status)
    ) THEN RAISE EXCEPTION 'published revision is immutable' USING ERRCODE = '23514'; END IF;
    RETURN COALESCE(NEW, OLD);
END;
$function$;
CREATE TRIGGER guard_published_content_revision BEFORE UPDATE OR DELETE ON content.content_revisions FOR EACH ROW EXECUTE FUNCTION content.guard_published_revision();
REVOKE ALL ON SCHEMA content FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA content TO polyglot_migration;
GRANT USAGE ON SCHEMA content TO polyglot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA content TO polyglot_migration, polyglot_runtime;
ALTER SCHEMA content OWNER TO polyglot_migration;
DO $owners$ DECLARE item record; BEGIN FOR item IN SELECT tablename FROM pg_tables WHERE schemaname = 'content' LOOP EXECUTE format('ALTER TABLE content.%I OWNER TO polyglot_migration', item.tablename); END LOOP; END; $owners$;
ALTER FUNCTION content.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION content.guard_published_revision() OWNER TO polyglot_migration;
"""


async def _execute_content_ddl(connection: Connection) -> None:
    await connection.execute(CONTENT_DDL)


def upgrade() -> None:
    op.get_bind().connection.run_async(_execute_content_ddl)


def downgrade() -> None:
    op.execute("DROP SCHEMA content CASCADE")
