"""Add immutable vocabulary stacks, presets, runs and sprint injections.

Revision ID: 0021_practice_stacks
Revises: 0020_multilingual_onboarding
"""

# ruff: noqa: E501

from alembic import op
from asyncpg import Connection

revision = "0021_practice_stacks"
down_revision = "0020_multilingual_onboarding"
branch_labels = None
depends_on = None


DDL = r"""
CREATE SCHEMA practice AUTHORIZATION polyglot_migration;

CREATE FUNCTION practice.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
  SELECT value IS NOT NULL AND (get_byte(uuid_send(value),6) >> 4) = 7
$function$;
CREATE FUNCTION practice.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE AS $function$
  SELECT NULLIF(current_setting('app.user_id',true),'')::uuid
$function$;
CREATE FUNCTION practice.owns_profile(value uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,language_profiles,practice AS $function$
  SELECT EXISTS (
    SELECT 1 FROM language_profiles.learner_language_profiles profile
    WHERE profile.profile_id=value AND profile.account_id=practice.current_user_id()
      AND profile.status <> 'deleted'
  )
$function$;
CREATE FUNCTION practice.guard_append_only() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
  RAISE EXCEPTION 'practice snapshot is append-only' USING ERRCODE='55000';
END
$function$;

CREATE TABLE practice.practice_stacks (
  stack_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  language_pack_revision_id uuid NOT NULL REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
  name varchar(200) NOT NULL,
  stack_kind varchar(32) NOT NULL,
  pedagogical_day date,
  source_refs jsonb NOT NULL,
  member_count integer NOT NULL,
  checksum char(64) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_practice_stack_profile UNIQUE (profile_id,stack_id),
  CONSTRAINT ck_practice_stack_uuid7 CHECK (
    practice.is_uuid7(stack_id) AND practice.is_uuid7(profile_id)
    AND practice.is_uuid7(language_pack_revision_id)
  ),
  CONSTRAINT ck_practice_stack_shape CHECK (
    length(name) BETWEEN 1 AND 200 AND stack_kind IN
      ('daily','list_snapshot','due','weak','selection','combined')
    AND jsonb_typeof(source_refs)='array' AND member_count BETWEEN 1 AND 5000
    AND checksum ~ '^[0-9a-f]{64}$'
    AND ((stack_kind='daily') = (pedagogical_day IS NOT NULL))
  )
);

CREATE TABLE practice.practice_stack_members (
  stack_member_id uuid PRIMARY KEY,
  stack_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  sense_id uuid NOT NULL,
  sense_revision_id uuid NOT NULL,
  position integer NOT NULL,
  label text NOT NULL,
  definition text NOT NULL,
  source_kind varchar(40) NOT NULL,
  source_ref varchar(500) NOT NULL,
  CONSTRAINT fk_practice_stack_member_sense FOREIGN KEY (sense_id)
    REFERENCES catalogue.lexical_senses(sense_id) ON DELETE RESTRICT,
  CONSTRAINT fk_practice_stack_member_sense_revision FOREIGN KEY (sense_revision_id)
    REFERENCES catalogue.lexical_sense_revisions(sense_revision_id) ON DELETE RESTRICT,
  CONSTRAINT fk_practice_stack_member FOREIGN KEY (profile_id,stack_id)
    REFERENCES practice.practice_stacks(profile_id,stack_id) ON DELETE RESTRICT,
  CONSTRAINT uq_practice_stack_sense UNIQUE (stack_id,sense_id),
  CONSTRAINT uq_practice_stack_position UNIQUE (stack_id,position),
  CONSTRAINT ck_practice_stack_member_uuid7 CHECK (
    practice.is_uuid7(stack_member_id) AND practice.is_uuid7(stack_id)
    AND practice.is_uuid7(profile_id) AND practice.is_uuid7(sense_id)
    AND practice.is_uuid7(sense_revision_id)
  ),
  CONSTRAINT ck_practice_stack_member_shape CHECK (
    position >= 1 AND length(label) BETWEEN 1 AND 500
    AND length(definition) BETWEEN 1 AND 2000
    AND length(source_kind) BETWEEN 1 AND 40 AND length(source_ref) BETWEEN 1 AND 500
  )
);

CREATE TABLE practice.practice_presets (
  preset_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  current_revision_id uuid,
  status varchar(24) NOT NULL,
  version integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  archived_at timestamptz,
  CONSTRAINT uq_practice_preset_profile UNIQUE (profile_id,preset_id),
  CONSTRAINT ck_practice_preset_uuid7 CHECK (
    practice.is_uuid7(preset_id) AND practice.is_uuid7(profile_id)
    AND (current_revision_id IS NULL OR practice.is_uuid7(current_revision_id))
  ),
  CONSTRAINT ck_practice_preset_shape CHECK (
    status IN ('active','archived') AND version >= 1 AND updated_at >= created_at
    AND ((status='archived') = (archived_at IS NOT NULL))
  )
);

CREATE TABLE practice.practice_preset_revisions (
  preset_revision_id uuid PRIMARY KEY,
  preset_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  revision_no integer NOT NULL,
  name varchar(200) NOT NULL,
  stack_ids uuid[] NOT NULL,
  direction varchar(32) NOT NULL,
  mode varchar(24) NOT NULL,
  settings jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_practice_preset_revision FOREIGN KEY (profile_id,preset_id)
    REFERENCES practice.practice_presets(profile_id,preset_id) ON DELETE RESTRICT,
  CONSTRAINT uq_practice_preset_revision UNIQUE (preset_id,revision_no),
  CONSTRAINT uq_practice_preset_revision_profile UNIQUE (profile_id,preset_revision_id),
  CONSTRAINT ck_practice_preset_revision_uuid7 CHECK (
    practice.is_uuid7(preset_revision_id) AND practice.is_uuid7(preset_id)
    AND practice.is_uuid7(profile_id)
  ),
  CONSTRAINT ck_practice_preset_revision_shape CHECK (
    revision_no >= 1 AND length(name) BETWEEN 1 AND 200
    AND cardinality(stack_ids) BETWEEN 1 AND 31
    AND direction IN ('target_to_support','support_to_target','bidirectional')
    AND mode IN ('cards','recognition','recall','mixed')
    AND jsonb_typeof(settings)='object'
  )
);
ALTER TABLE practice.practice_presets ADD CONSTRAINT fk_practice_preset_current_revision
  FOREIGN KEY (profile_id,current_revision_id)
  REFERENCES practice.practice_preset_revisions(profile_id,preset_revision_id) ON DELETE RESTRICT;

CREATE TABLE practice.practice_runs (
  run_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL,
  preset_id uuid NOT NULL,
  preset_revision_id uuid NOT NULL,
  status varchar(24) NOT NULL,
  current_position integer NOT NULL,
  member_count integer NOT NULL,
  version integer NOT NULL,
  run_snapshot jsonb NOT NULL,
  snapshot_fingerprint char(64) NOT NULL,
  started_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  completed_at timestamptz,
  CONSTRAINT fk_practice_run_preset FOREIGN KEY (profile_id,preset_id)
    REFERENCES practice.practice_presets(profile_id,preset_id) ON DELETE RESTRICT,
  CONSTRAINT fk_practice_run_revision FOREIGN KEY (profile_id,preset_revision_id)
    REFERENCES practice.practice_preset_revisions(profile_id,preset_revision_id) ON DELETE RESTRICT,
  CONSTRAINT uq_practice_run_profile UNIQUE (profile_id,run_id),
  CONSTRAINT ck_practice_run_uuid7 CHECK (
    practice.is_uuid7(run_id) AND practice.is_uuid7(profile_id)
    AND practice.is_uuid7(preset_id) AND practice.is_uuid7(preset_revision_id)
  ),
  CONSTRAINT ck_practice_run_shape CHECK (
    status IN ('in_progress','interrupted','completed','abandoned')
    AND current_position BETWEEN 0 AND member_count AND member_count >= 1 AND version >= 1
    AND jsonb_typeof(run_snapshot)='object' AND snapshot_fingerprint ~ '^[0-9a-f]{64}$'
    AND updated_at >= started_at
    AND ((status='completed') = (completed_at IS NOT NULL))
  )
);

CREATE TABLE practice.practice_run_items (
  run_item_id uuid PRIMARY KEY,
  run_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  sense_id uuid NOT NULL,
  sense_revision_id uuid NOT NULL,
  position integer NOT NULL,
  prompt_snapshot jsonb NOT NULL,
  CONSTRAINT fk_practice_run_item FOREIGN KEY (profile_id,run_id)
    REFERENCES practice.practice_runs(profile_id,run_id) ON DELETE RESTRICT,
  CONSTRAINT uq_practice_run_item_position UNIQUE (run_id,position),
  CONSTRAINT ck_practice_run_item_uuid7 CHECK (
    practice.is_uuid7(run_item_id) AND practice.is_uuid7(run_id)
    AND practice.is_uuid7(profile_id) AND practice.is_uuid7(sense_id)
    AND practice.is_uuid7(sense_revision_id)
  ),
  CONSTRAINT ck_practice_run_item_shape CHECK (
    position >= 1 AND jsonb_typeof(prompt_snapshot)='object'
  )
);

CREATE TABLE practice.sprint_stack_injections (
  injection_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL,
  stack_id uuid NOT NULL,
  status varchar(24) NOT NULL,
  requested_at timestamptz NOT NULL,
  consumed_by_plan_revision_id uuid,
  cancelled_at timestamptz,
  version integer NOT NULL,
  CONSTRAINT fk_sprint_stack_injection FOREIGN KEY (profile_id,stack_id)
    REFERENCES practice.practice_stacks(profile_id,stack_id) ON DELETE RESTRICT,
  CONSTRAINT ck_sprint_stack_injection_uuid7 CHECK (
    practice.is_uuid7(injection_id) AND practice.is_uuid7(profile_id)
    AND practice.is_uuid7(stack_id)
    AND (consumed_by_plan_revision_id IS NULL OR practice.is_uuid7(consumed_by_plan_revision_id))
  ),
  CONSTRAINT ck_sprint_stack_injection_shape CHECK (
    status IN ('pending','consumed','cancelled') AND version >= 1
    AND ((status='consumed') = (consumed_by_plan_revision_id IS NOT NULL))
    AND ((status='cancelled') = (cancelled_at IS NOT NULL))
  )
);

CREATE INDEX ix_practice_stacks_profile_day ON practice.practice_stacks(profile_id,pedagogical_day DESC,created_at DESC);
CREATE INDEX ix_practice_presets_profile_status ON practice.practice_presets(profile_id,status,updated_at DESC);
CREATE INDEX ix_practice_runs_profile_status ON practice.practice_runs(profile_id,status,updated_at DESC);
CREATE INDEX ix_sprint_stack_injections_pending ON practice.sprint_stack_injections(profile_id,status,requested_at);
CREATE UNIQUE INDEX uq_sprint_stack_injection_pending
  ON practice.sprint_stack_injections(profile_id,stack_id) WHERE status='pending';

CREATE TRIGGER practice_stacks_append_only BEFORE UPDATE OR DELETE ON practice.practice_stacks
FOR EACH ROW EXECUTE FUNCTION practice.guard_append_only();
CREATE TRIGGER practice_stack_members_append_only BEFORE UPDATE OR DELETE ON practice.practice_stack_members
FOR EACH ROW EXECUTE FUNCTION practice.guard_append_only();
CREATE TRIGGER practice_preset_revisions_append_only BEFORE UPDATE OR DELETE ON practice.practice_preset_revisions
FOR EACH ROW EXECUTE FUNCTION practice.guard_append_only();
CREATE TRIGGER practice_run_items_append_only BEFORE UPDATE OR DELETE ON practice.practice_run_items
FOR EACH ROW EXECUTE FUNCTION practice.guard_append_only();

DO $rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'practice_stacks','practice_stack_members','practice_presets',
    'practice_preset_revisions','practice_runs','practice_run_items','sprint_stack_injections'
  ] LOOP
    EXECUTE format('ALTER TABLE practice.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE practice.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY %I ON practice.%I USING (practice.owns_profile(profile_id)) WITH CHECK (practice.owns_profile(profile_id))',
      table_name || '_owner',table_name
    );
  END LOOP;
END
$rls$;

GRANT USAGE ON SCHEMA practice TO polyglot_runtime;
GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA practice TO polyglot_runtime;
GRANT UPDATE ON practice.practice_presets,practice.practice_runs,practice.sprint_stack_injections TO polyglot_runtime;
GRANT USAGE,CREATE ON SCHEMA practice TO polyglot_migration;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA practice TO polyglot_migration;
ALTER FUNCTION practice.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION practice.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION practice.owns_profile(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION practice.guard_append_only() OWNER TO polyglot_migration;
"""

DROP_DDL = "DROP SCHEMA IF EXISTS practice CASCADE;"


async def _execute(connection: Connection, sql: str) -> None:
    await connection.execute(sql)


def upgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DDL))


def downgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DROP_DDL))
