"""Create vocabulary lists and transactional exchange storage.

Revision ID: 0008_exchange
Revises: 0007_memory
"""

# ruff: noqa: E501

from alembic import op
from asyncpg import Connection

revision = "0008_exchange"
down_revision = "0007_memory"
branch_labels = None
depends_on = None


EXCHANGE_DDL = r"""
CREATE TABLE lexicon.vocabulary_lists (
  list_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  editorial_owner_id uuid,
  variety_id uuid NOT NULL,
  list_type varchar(24) NOT NULL,
  status varchar(24) NOT NULL,
  current_revision_id uuid,
  version integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_vocabulary_list_profile UNIQUE (profile_id,list_id),
  CONSTRAINT ck_vocabulary_list_uuid7 CHECK (
    lexicon.is_uuid7(list_id) AND lexicon.is_uuid7(profile_id)
    AND lexicon.is_uuid7(variety_id)
    AND (editorial_owner_id IS NULL OR lexicon.is_uuid7(editorial_owner_id))
  ),
  CONSTRAINT ck_vocabulary_list_shape CHECK (
    list_type IN ('manual','editorial','dynamic')
    AND status IN ('active','archived') AND version >= 1 AND updated_at >= created_at
  )
);

CREATE TABLE lexicon.vocabulary_list_revisions (
  list_revision_id uuid PRIMARY KEY,
  list_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  revision_no integer NOT NULL,
  name varchar(200) NOT NULL,
  purpose text NOT NULL,
  query_definition jsonb,
  ordered boolean NOT NULL,
  color varchar(32),
  tags jsonb NOT NULL DEFAULT '[]'::jsonb,
  provenance_id uuid NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_list_revision_list FOREIGN KEY (profile_id,list_id)
    REFERENCES lexicon.vocabulary_lists(profile_id,list_id) ON DELETE RESTRICT,
  CONSTRAINT uq_list_revision_no UNIQUE (list_id,revision_no),
  CONSTRAINT uq_list_revision_profile UNIQUE (profile_id,list_revision_id),
  CONSTRAINT ck_list_revision_uuid7 CHECK (
    lexicon.is_uuid7(list_revision_id) AND lexicon.is_uuid7(list_id)
    AND lexicon.is_uuid7(profile_id) AND lexicon.is_uuid7(provenance_id)
  ),
  CONSTRAINT ck_list_revision_shape CHECK (
    revision_no >= 1 AND length(name) BETWEEN 1 AND 200
    AND length(purpose) BETWEEN 1 AND 2000
    AND jsonb_typeof(tags) = 'array'
    AND (query_definition IS NULL OR jsonb_typeof(query_definition) = 'object')
  )
);
ALTER TABLE lexicon.vocabulary_lists ADD CONSTRAINT fk_vocabulary_list_current_revision
  FOREIGN KEY (profile_id,current_revision_id)
  REFERENCES lexicon.vocabulary_list_revisions(profile_id,list_revision_id) ON DELETE RESTRICT;

CREATE TABLE lexicon.list_memberships (
  membership_id uuid PRIMARY KEY,
  list_revision_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  sense_id uuid NOT NULL,
  position integer NOT NULL,
  role varchar(40) NOT NULL,
  CONSTRAINT fk_list_membership_revision FOREIGN KEY (profile_id,list_revision_id)
    REFERENCES lexicon.vocabulary_list_revisions(profile_id,list_revision_id) ON DELETE RESTRICT,
  CONSTRAINT uq_list_membership UNIQUE (list_revision_id,sense_id,role),
  CONSTRAINT uq_list_membership_position UNIQUE (list_revision_id,position),
  CONSTRAINT ck_list_membership_uuid7 CHECK (
    lexicon.is_uuid7(membership_id) AND lexicon.is_uuid7(list_revision_id)
    AND lexicon.is_uuid7(profile_id) AND lexicon.is_uuid7(sense_id)
  ),
  CONSTRAINT ck_list_membership_shape CHECK (position >= 1 AND length(role) BETWEEN 1 AND 40)
);

CREATE TABLE lexicon.list_snapshots (
  snapshot_id uuid PRIMARY KEY,
  list_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  source_revision_id uuid NOT NULL,
  created_at timestamptz NOT NULL,
  checksum char(64) NOT NULL,
  CONSTRAINT fk_list_snapshot_list FOREIGN KEY (profile_id,list_id)
    REFERENCES lexicon.vocabulary_lists(profile_id,list_id) ON DELETE RESTRICT,
  CONSTRAINT fk_list_snapshot_revision FOREIGN KEY (profile_id,source_revision_id)
    REFERENCES lexicon.vocabulary_list_revisions(profile_id,list_revision_id) ON DELETE RESTRICT,
  CONSTRAINT uq_list_snapshot_profile UNIQUE (profile_id,snapshot_id),
  CONSTRAINT uq_list_snapshot_checksum UNIQUE (list_id,checksum),
  CONSTRAINT ck_list_snapshot_uuid7 CHECK (
    lexicon.is_uuid7(snapshot_id) AND lexicon.is_uuid7(list_id)
    AND lexicon.is_uuid7(profile_id) AND lexicon.is_uuid7(source_revision_id)
  ),
  CONSTRAINT ck_list_snapshot_checksum CHECK (checksum ~ '^[0-9a-f]{64}$')
);

CREATE TABLE lexicon.list_snapshot_members (
  snapshot_member_id uuid PRIMARY KEY,
  snapshot_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  sense_revision_id uuid NOT NULL,
  position integer NOT NULL,
  role varchar(40) NOT NULL,
  CONSTRAINT fk_list_snapshot_member FOREIGN KEY (profile_id,snapshot_id)
    REFERENCES lexicon.list_snapshots(profile_id,snapshot_id) ON DELETE RESTRICT,
  CONSTRAINT uq_list_snapshot_member UNIQUE (snapshot_id,sense_revision_id,role),
  CONSTRAINT uq_list_snapshot_position UNIQUE (snapshot_id,position),
  CONSTRAINT ck_list_snapshot_member_uuid7 CHECK (
    lexicon.is_uuid7(snapshot_member_id) AND lexicon.is_uuid7(snapshot_id)
    AND lexicon.is_uuid7(profile_id) AND lexicon.is_uuid7(sense_revision_id)
  ),
  CONSTRAINT ck_list_snapshot_member_shape CHECK (position >= 1 AND length(role) BETWEEN 1 AND 40)
);

CREATE TABLE lexicon.list_associations (
  association_id uuid PRIMARY KEY,
  list_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  target_type varchar(32) NOT NULL,
  target_id uuid NOT NULL,
  role varchar(40) NOT NULL,
  valid_from timestamptz NOT NULL,
  valid_until timestamptz,
  version integer NOT NULL,
  CONSTRAINT fk_list_association_list FOREIGN KEY (profile_id,list_id)
    REFERENCES lexicon.vocabulary_lists(profile_id,list_id) ON DELETE RESTRICT,
  CONSTRAINT ck_list_association_uuid7 CHECK (
    lexicon.is_uuid7(association_id) AND lexicon.is_uuid7(list_id)
    AND lexicon.is_uuid7(profile_id) AND lexicon.is_uuid7(target_id)
  ),
  CONSTRAINT ck_list_association_shape CHECK (
    target_type IN ('module','module_day','session_plan','exercise')
    AND version >= 1 AND (valid_until IS NULL OR valid_until > valid_from)
  )
);
CREATE INDEX ix_vocabulary_lists_profile ON lexicon.vocabulary_lists(profile_id,status,list_id);
CREATE INDEX ix_list_associations_target ON lexicon.list_associations(profile_id,target_type,target_id);

CREATE SCHEMA exchange;
CREATE FUNCTION exchange.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
  SELECT value IS NOT NULL AND (get_byte(uuid_send(value), 6) >> 4) = 7
$function$;
CREATE FUNCTION exchange.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE AS $function$
  SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
$function$;
CREATE FUNCTION exchange.owns_profile(value uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, language_profiles, exchange AS $function$
  SELECT EXISTS (
    SELECT 1 FROM language_profiles.learner_language_profiles profile
    WHERE profile.profile_id=value AND profile.account_id=exchange.current_user_id()
      AND profile.status <> 'deleted'
  )
$function$;

CREATE TABLE exchange.import_runs (
  import_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  editorial_owner_id uuid,
  format_id varchar(80) NOT NULL,
  schema_version integer NOT NULL,
  status varchar(32) NOT NULL,
  media_revision_id uuid,
  source_checksum char(64) NOT NULL,
  encoding varchar(40) NOT NULL,
  strategy varchar(32),
  catalogue_version_at_preview varchar(120),
  preview_checksum char(64),
  created_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  committed_at timestamptz,
  reverted_at timestamptz,
  version integer NOT NULL,
  CONSTRAINT uq_import_profile UNIQUE (profile_id,import_id),
  CONSTRAINT ck_import_uuid7 CHECK (
    exchange.is_uuid7(import_id) AND exchange.is_uuid7(profile_id)
    AND (editorial_owner_id IS NULL OR exchange.is_uuid7(editorial_owner_id))
    AND (media_revision_id IS NULL OR exchange.is_uuid7(media_revision_id))
  ),
  CONSTRAINT ck_import_status CHECK (status IN (
    'uploaded','quarantined','parsing','invalid','preview_ready','awaiting_decision',
    'committing','committed','failed','cancelled','reverted')),
  CONSTRAINT ck_import_strategy CHECK (strategy IS NULL OR strategy IN (
    'fail_on_conflict','reuse_exact','create_distinct','interactive')),
  CONSTRAINT ck_import_shape CHECK (
    format_id IN ('polyglot.lexicon.bundle/v1','polyglot.memory.prompts/v1',
      'polyglot.generic.qa/v1','polyglot.authoring.bundle/v1','polyglot.user.export/v1')
    AND schema_version >= 1 AND version >= 1 AND expires_at > created_at
    AND source_checksum ~ '^[0-9a-f]{64}$'
    AND (preview_checksum IS NULL OR preview_checksum ~ '^[0-9a-f]{64}$')
  )
);

CREATE TABLE exchange.import_lines (
  import_line_id uuid PRIMARY KEY,
  import_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  line_no integer NOT NULL,
  source_path text NOT NULL,
  status varchar(24) NOT NULL,
  intermediate_payload jsonb,
  redacted_error_value text,
  result_entity_refs jsonb,
  CONSTRAINT fk_import_line_run FOREIGN KEY (profile_id,import_id)
    REFERENCES exchange.import_runs(profile_id,import_id) ON DELETE RESTRICT,
  CONSTRAINT uq_import_line_no UNIQUE (import_id,line_no),
  CONSTRAINT uq_import_line_profile UNIQUE (profile_id,import_line_id),
  CONSTRAINT ck_import_line_uuid7 CHECK (
    exchange.is_uuid7(import_line_id) AND exchange.is_uuid7(import_id)
    AND exchange.is_uuid7(profile_id)
  ),
  CONSTRAINT ck_import_line_shape CHECK (
    line_no >= 1 AND status IN ('pending','accepted','rejected','conflict','committed','reverted')
    AND (intermediate_payload IS NULL OR jsonb_typeof(intermediate_payload)='object')
    AND (result_entity_refs IS NULL OR jsonb_typeof(result_entity_refs)='array')
  )
);

CREATE TABLE exchange.import_conflicts (
  conflict_id uuid PRIMARY KEY,
  import_line_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  conflict_class varchar(40) NOT NULL,
  candidate_refs jsonb NOT NULL,
  allowed_actions jsonb NOT NULL,
  selected_action varchar(40),
  decided_by_actor_id uuid,
  decided_at timestamptz,
  version integer NOT NULL,
  CONSTRAINT fk_import_conflict_line FOREIGN KEY (profile_id,import_line_id)
    REFERENCES exchange.import_lines(profile_id,import_line_id) ON DELETE RESTRICT,
  CONSTRAINT uq_import_conflict_profile UNIQUE (profile_id,conflict_id),
  CONSTRAINT ck_import_conflict_uuid7 CHECK (
    exchange.is_uuid7(conflict_id) AND exchange.is_uuid7(import_line_id)
    AND exchange.is_uuid7(profile_id)
    AND (decided_by_actor_id IS NULL OR exchange.is_uuid7(decided_by_actor_id))
  ),
  CONSTRAINT ck_import_conflict_class CHECK (conflict_class IN (
    'exact_identity','same_sense','same_form_other_sense','same_prompt',
    'content_revision_conflict','private_public_collision','ambiguous')),
  CONSTRAINT ck_import_conflict_shape CHECK (
    jsonb_typeof(candidate_refs)='array' AND jsonb_typeof(allowed_actions)='array'
    AND version >= 1
    AND ((selected_action IS NULL AND decided_by_actor_id IS NULL AND decided_at IS NULL)
      OR (selected_action IS NOT NULL AND decided_by_actor_id IS NOT NULL AND decided_at IS NOT NULL))
  )
);

CREATE TABLE exchange.import_manifests (
  manifest_id uuid PRIMARY KEY,
  import_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  created_refs jsonb NOT NULL,
  reused_refs jsonb NOT NULL,
  inverse_operations jsonb NOT NULL,
  checksum char(64) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_import_manifest_run FOREIGN KEY (profile_id,import_id)
    REFERENCES exchange.import_runs(profile_id,import_id) ON DELETE RESTRICT,
  CONSTRAINT uq_import_manifest UNIQUE (import_id),
  CONSTRAINT ck_import_manifest_uuid7 CHECK (
    exchange.is_uuid7(manifest_id) AND exchange.is_uuid7(import_id)
    AND exchange.is_uuid7(profile_id)
  ),
  CONSTRAINT ck_import_manifest_shape CHECK (
    jsonb_typeof(created_refs)='array' AND jsonb_typeof(reused_refs)='array'
    AND jsonb_typeof(inverse_operations)='array' AND checksum ~ '^[0-9a-f]{64}$'
  )
);

CREATE TABLE exchange.shared_list_publications (
  publication_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL,
  list_snapshot_id uuid NOT NULL,
  license_ref text NOT NULL,
  provenance_id uuid NOT NULL,
  status varchar(24) NOT NULL,
  published_at timestamptz NOT NULL,
  retired_at timestamptz,
  version integer NOT NULL,
  public_payload jsonb NOT NULL,
  CONSTRAINT fk_shared_list_snapshot FOREIGN KEY (profile_id,list_snapshot_id)
    REFERENCES lexicon.list_snapshots(profile_id,snapshot_id) ON DELETE RESTRICT,
  CONSTRAINT ck_shared_list_uuid7 CHECK (
    exchange.is_uuid7(publication_id) AND exchange.is_uuid7(profile_id)
    AND exchange.is_uuid7(list_snapshot_id) AND exchange.is_uuid7(provenance_id)
  ),
  CONSTRAINT ck_shared_list_shape CHECK (
    status IN ('published','retired') AND version >= 1
    AND jsonb_typeof(public_payload)='object'
    AND ((status='published' AND retired_at IS NULL) OR (status='retired' AND retired_at IS NOT NULL))
  )
);

CREATE TABLE exchange.export_runs (
  export_id uuid PRIMARY KEY,
  account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  job_id uuid NOT NULL,
  scope jsonb NOT NULL,
  status varchar(24) NOT NULL,
  requested_at timestamptz NOT NULL,
  completed_at timestamptz,
  expires_at timestamptz NOT NULL,
  manifest_checksum char(64),
  version integer NOT NULL,
  CONSTRAINT uq_export_profile UNIQUE (profile_id,export_id),
  CONSTRAINT ck_export_uuid7 CHECK (
    exchange.is_uuid7(export_id) AND exchange.is_uuid7(account_id)
    AND exchange.is_uuid7(profile_id) AND exchange.is_uuid7(job_id)
  ),
  CONSTRAINT ck_export_shape CHECK (
    status IN ('requested','queued','running','ready','failed','expired','cancelled')
    AND jsonb_typeof(scope)='object' AND expires_at > requested_at AND version >= 1
    AND (manifest_checksum IS NULL OR manifest_checksum ~ '^[0-9a-f]{64}$')
  )
);

CREATE TABLE exchange.export_artifacts (
  export_artifact_id uuid PRIMARY KEY,
  export_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  media_revision_id uuid NOT NULL,
  encryption_scheme varchar(80) NOT NULL,
  schema_version integer NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_export_artifact_run FOREIGN KEY (profile_id,export_id)
    REFERENCES exchange.export_runs(profile_id,export_id) ON DELETE RESTRICT,
  CONSTRAINT ck_export_artifact_uuid7 CHECK (
    exchange.is_uuid7(export_artifact_id) AND exchange.is_uuid7(export_id)
    AND exchange.is_uuid7(profile_id) AND exchange.is_uuid7(media_revision_id)
  ),
  CONSTRAINT ck_export_artifact_shape CHECK (
    schema_version >= 1 AND length(encryption_scheme) BETWEEN 1 AND 80
  )
);
CREATE INDEX ix_import_runs_profile ON exchange.import_runs(profile_id,status,created_at,import_id);
CREATE INDEX ix_export_runs_profile ON exchange.export_runs(profile_id,status,requested_at,export_id);

CREATE FUNCTION exchange.guard_append_only() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
  RAISE EXCEPTION 'exchange artifact is append-only' USING ERRCODE='55000';
END
$function$;

CREATE FUNCTION exchange.revert_import_lexical(
  owner_profile_id uuid,
  owner_import_id uuid,
  unit_ids uuid[],
  sense_ids uuid[]
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog,exchange,lexicon AS $function$
DECLARE created_refs jsonb;
DECLARE current_id uuid;
BEGIN
  SELECT manifest.created_refs INTO created_refs
  FROM exchange.import_manifests manifest
  WHERE manifest.profile_id=owner_profile_id AND manifest.import_id=owner_import_id;
  IF created_refs IS NULL THEN
    RAISE EXCEPTION 'import manifest missing' USING ERRCODE='P0002';
  END IF;
  FOREACH current_id IN ARRAY unit_ids LOOP
    IF NOT created_refs ? ('lexical_unit:' || current_id::text) THEN
      RAISE EXCEPTION 'unit not owned by import' USING ERRCODE='42501';
    END IF;
  END LOOP;
  FOREACH current_id IN ARRAY sense_ids LOOP
    IF NOT created_refs ? ('lexical_sense:' || current_id::text) THEN
      RAISE EXCEPTION 'sense not owned by import' USING ERRCODE='42501';
    END IF;
  END LOOP;
  DELETE FROM lexicon.private_lexical_senses
  WHERE profile_id=owner_profile_id AND sense_id=ANY(sense_ids);
  DELETE FROM lexicon.private_lexical_units
  WHERE profile_id=owner_profile_id AND lexical_unit_id=ANY(unit_ids);
END
$function$;

CREATE TRIGGER vocabulary_list_revisions_append_only BEFORE UPDATE OR DELETE ON lexicon.vocabulary_list_revisions
FOR EACH ROW EXECUTE FUNCTION lexicon.guard_append_only();
CREATE TRIGGER list_memberships_append_only BEFORE UPDATE OR DELETE ON lexicon.list_memberships
FOR EACH ROW EXECUTE FUNCTION lexicon.guard_append_only();
CREATE TRIGGER list_snapshots_append_only BEFORE UPDATE OR DELETE ON lexicon.list_snapshots
FOR EACH ROW EXECUTE FUNCTION lexicon.guard_append_only();
CREATE TRIGGER list_snapshot_members_append_only BEFORE UPDATE OR DELETE ON lexicon.list_snapshot_members
FOR EACH ROW EXECUTE FUNCTION lexicon.guard_append_only();
CREATE TRIGGER import_manifests_append_only BEFORE UPDATE OR DELETE ON exchange.import_manifests
FOR EACH ROW EXECUTE FUNCTION exchange.guard_append_only();

DO $rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'vocabulary_lists','vocabulary_list_revisions','list_memberships',
    'list_snapshots','list_snapshot_members','list_associations'
  ] LOOP
    EXECUTE format('ALTER TABLE lexicon.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE lexicon.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY %I ON lexicon.%I USING (lexicon.owns_profile(profile_id)) WITH CHECK (lexicon.owns_profile(profile_id))',
      table_name || '_owner',table_name
    );
  END LOOP;
  FOREACH table_name IN ARRAY ARRAY[
    'import_runs','import_lines','import_conflicts','import_manifests',
    'shared_list_publications','export_runs','export_artifacts'
  ] LOOP
    EXECUTE format('ALTER TABLE exchange.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE exchange.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY %I ON exchange.%I USING (exchange.owns_profile(profile_id)) WITH CHECK (exchange.owns_profile(profile_id))',
      table_name || '_owner',table_name
    );
  END LOOP;
END
$rls$;
CREATE POLICY shared_list_public_read ON exchange.shared_list_publications
FOR SELECT USING (status='published');

GRANT SELECT,INSERT ON lexicon.vocabulary_lists,lexicon.vocabulary_list_revisions,
  lexicon.list_memberships,lexicon.list_snapshots,lexicon.list_snapshot_members,
  lexicon.list_associations TO polyglot_runtime;
GRANT UPDATE ON lexicon.vocabulary_lists,lexicon.list_associations TO polyglot_runtime;
GRANT ALL PRIVILEGES ON lexicon.vocabulary_lists,lexicon.vocabulary_list_revisions,
  lexicon.list_memberships,lexicon.list_snapshots,lexicon.list_snapshot_members,
  lexicon.list_associations TO polyglot_migration;
GRANT USAGE ON SCHEMA exchange TO polyglot_runtime;
GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA exchange TO polyglot_runtime;
GRANT UPDATE ON exchange.import_runs,exchange.import_lines,exchange.import_conflicts,
  exchange.shared_list_publications,exchange.export_runs TO polyglot_runtime;
GRANT USAGE,CREATE ON SCHEMA exchange TO polyglot_migration;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA exchange TO polyglot_migration;
ALTER FUNCTION exchange.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION exchange.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION exchange.owns_profile(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION exchange.guard_append_only() OWNER TO polyglot_migration;
ALTER FUNCTION exchange.revert_import_lexical(uuid,uuid,uuid[],uuid[]) OWNER TO polyglot_migration;
REVOKE ALL ON FUNCTION exchange.revert_import_lexical(uuid,uuid,uuid[],uuid[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION exchange.revert_import_lexical(uuid,uuid,uuid[],uuid[]) TO polyglot_runtime;
"""

DROP_DDL = r"""
DROP SCHEMA IF EXISTS exchange CASCADE;
DROP TABLE IF EXISTS lexicon.list_associations CASCADE;
DROP TABLE IF EXISTS lexicon.list_snapshot_members CASCADE;
DROP TABLE IF EXISTS lexicon.list_snapshots CASCADE;
DROP TABLE IF EXISTS lexicon.list_memberships CASCADE;
ALTER TABLE IF EXISTS lexicon.vocabulary_lists DROP CONSTRAINT IF EXISTS fk_vocabulary_list_current_revision;
DROP TABLE IF EXISTS lexicon.vocabulary_list_revisions CASCADE;
DROP TABLE IF EXISTS lexicon.vocabulary_lists CASCADE;
"""


async def _execute(connection: Connection, sql: str) -> None:
    await connection.execute(sql)


def upgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, EXCHANGE_DDL))


def downgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DROP_DDL))
