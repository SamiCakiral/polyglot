"""Persist versioned learning modules and learner enrollments.

Revision ID: 0011_curriculum
Revises: 0010_gym
"""

# ruff: noqa: E501

from alembic import op
from asyncpg import Connection

revision = "0011_curriculum"
down_revision = "0010_gym"
branch_labels = None
depends_on = None


CURRICULUM_DDL = r"""
CREATE SCHEMA curriculum AUTHORIZATION polyglot_migration;

CREATE FUNCTION curriculum.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
  SELECT value IS NOT NULL AND (get_byte(uuid_send(value),6) >> 4) = 7
$function$;
CREATE FUNCTION curriculum.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE AS $function$
  SELECT NULLIF(current_setting('app.user_id',true),'')::uuid
$function$;
CREATE FUNCTION curriculum.owns_profile(value uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,language_profiles,curriculum AS $function$
  SELECT EXISTS (
    SELECT 1 FROM language_profiles.learner_language_profiles profile
    WHERE profile.profile_id=value AND profile.account_id=curriculum.current_user_id()
      AND profile.status <> 'deleted'
  )
$function$;
CREATE FUNCTION curriculum.has_role(roles text[]) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,identity,curriculum AS $function$
  SELECT EXISTS (
    SELECT 1 FROM identity.account_roles role_grant
    WHERE role_grant.account_id=curriculum.current_user_id()
      AND role_grant.role=ANY(roles) AND role_grant.revoked_at IS NULL
  )
$function$;
CREATE FUNCTION curriculum.guard_append_only() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
  RAISE EXCEPTION 'curriculum fact is append-only' USING ERRCODE='55000';
END
$function$;

CREATE TABLE curriculum.learning_modules (
  module_id uuid PRIMARY KEY,
  module_code varchar(120) NOT NULL UNIQUE,
  pack_id uuid NOT NULL REFERENCES catalogue.language_packs(pack_id) ON DELETE RESTRICT,
  editorial_owner_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  current_revision_id uuid,
  status varchar(24) NOT NULL,
  version integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT ck_learning_module_uuid7 CHECK (
    curriculum.is_uuid7(module_id) AND curriculum.is_uuid7(pack_id)
    AND curriculum.is_uuid7(editorial_owner_id)
    AND (current_revision_id IS NULL OR curriculum.is_uuid7(current_revision_id))
  ),
  CONSTRAINT ck_learning_module_shape CHECK (
    module_code ~ '^[A-Z0-9][A-Z0-9._-]{2,119}$'
    AND status IN ('draft','published','retired')
    AND version >= 1 AND updated_at >= created_at
  )
);

CREATE TABLE curriculum.module_revisions (
  module_revision_id uuid PRIMARY KEY,
  module_id uuid NOT NULL REFERENCES curriculum.learning_modules(module_id) ON DELETE RESTRICT,
  revision_no integer NOT NULL,
  status varchar(24) NOT NULL,
  pack_revision_id uuid NOT NULL REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
  target_variety_id uuid NOT NULL REFERENCES catalogue.language_varieties(variety_id) ON DELETE RESTRICT,
  support_variety_ids uuid[] NOT NULL,
  primary_intention text NOT NULL,
  final_mission_revision_id uuid NOT NULL,
  entry_profile_codes varchar(80)[] NOT NULL,
  nominal_days smallint NOT NULL,
  max_days smallint NOT NULL,
  min_minutes smallint NOT NULL,
  max_minutes smallint NOT NULL,
  prerequisite_skill_revision_ids uuid[] NOT NULL,
  target_skill_revision_ids uuid[] NOT NULL,
  lexicon_set_revision_ids uuid[] NOT NULL,
  exit_policy_revision_id uuid NOT NULL,
  recall_policy_revision_id uuid NOT NULL,
  provenance_ref varchar(500) NOT NULL,
  rights_refs varchar(500)[] NOT NULL,
  validator_set_revision_id uuid NOT NULL,
  schema_version integer NOT NULL,
  compatibility_range varchar(120) NOT NULL,
  reference_manifest_checksum varchar(71) NOT NULL,
  supersedes_revision_id uuid REFERENCES curriculum.module_revisions(module_revision_id) ON DELETE RESTRICT,
  payload_checksum varchar(71) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_module_revision UNIQUE (module_id,revision_no),
  CONSTRAINT uq_module_revision_owner UNIQUE (module_id,module_revision_id),
  CONSTRAINT ck_module_revision_uuid7 CHECK (
    curriculum.is_uuid7(module_revision_id) AND curriculum.is_uuid7(module_id)
    AND curriculum.is_uuid7(pack_revision_id) AND curriculum.is_uuid7(target_variety_id)
    AND curriculum.is_uuid7(final_mission_revision_id)
    AND curriculum.is_uuid7(exit_policy_revision_id)
    AND curriculum.is_uuid7(recall_policy_revision_id)
    AND curriculum.is_uuid7(validator_set_revision_id)
    AND (supersedes_revision_id IS NULL OR curriculum.is_uuid7(supersedes_revision_id))
  ),
  CONSTRAINT ck_module_revision_shape CHECK (
    revision_no >= 1 AND schema_version >= 1
    AND status IN ('draft','machine_valid','published','retired')
    AND cardinality(support_variety_ids) >= 1
    AND cardinality(entry_profile_codes) >= 1
    AND cardinality(target_skill_revision_ids) >= 1
    AND 3 <= nominal_days AND nominal_days <= max_days AND max_days <= 30
    AND 10 <= min_minutes AND min_minutes <= max_minutes AND max_minutes <= 60
    AND length(primary_intention) >= 1 AND length(provenance_ref) >= 1
    AND cardinality(rights_refs) >= 1 AND length(compatibility_range) >= 1
    AND (reference_manifest_checksum ~ '^sha256:[0-9a-f]{64}$'
      OR (status='draft' AND reference_manifest_checksum=''))
    AND payload_checksum ~ '^sha256:[0-9a-f]{64}$'
    AND (supersedes_revision_id IS NULL OR supersedes_revision_id <> module_revision_id)
  )
);

ALTER TABLE curriculum.learning_modules ADD CONSTRAINT fk_learning_module_current_revision
  FOREIGN KEY (module_id,current_revision_id)
  REFERENCES curriculum.module_revisions(module_id,module_revision_id)
  ON DELETE RESTRICT;

CREATE TABLE curriculum.module_days (
  module_day_id uuid PRIMARY KEY,
  module_revision_id uuid NOT NULL REFERENCES curriculum.module_revisions(module_revision_id) ON DELETE RESTRICT,
  ordinal smallint NOT NULL,
  arc_type varchar(24) NOT NULL,
  objective_codes varchar(160)[] NOT NULL,
  modality_objectives jsonb NOT NULL,
  primary_target_refs varchar(240)[] NOT NULL,
  secondary_target_refs varchar(240)[] NOT NULL,
  encountered_target_refs varchar(240)[] NOT NULL,
  output_target_refs varchar(240)[] NOT NULL,
  content_revision_ids uuid[] NOT NULL,
  exercise_definition_revision_ids uuid[] NOT NULL,
  context_revision_ids uuid[] NOT NULL,
  target_bindings jsonb NOT NULL,
  recall_specs jsonb NOT NULL,
  recall_source_day_ordinals smallint[] NOT NULL,
  minimum_useful_minutes smallint NOT NULL,
  novelty_budget numeric(7,3) NOT NULL,
  required_block_roles varchar(80)[] NOT NULL,
  new_grammar_family_codes varchar(160)[] NOT NULL,
  explained_grammar_family_codes varchar(160)[] NOT NULL,
  gym_grammar_family_codes varchar(160)[] NOT NULL,
  fallback_revision_ids uuid[] NOT NULL,
  final_output_spec text NOT NULL,
  validator_revision_ids uuid[] NOT NULL,
  prerequisite_day_ordinals smallint[] NOT NULL,
  payload_checksum varchar(71) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_module_day_ordinal UNIQUE (module_revision_id,ordinal),
  CONSTRAINT ck_module_day_uuid7 CHECK (
    curriculum.is_uuid7(module_day_id) AND curriculum.is_uuid7(module_revision_id)
  ),
  CONSTRAINT ck_module_day_shape CHECK (
    ordinal BETWEEN 1 AND 30
    AND arc_type IN ('discovery','guided_use','integration','transfer','consolidation')
    AND cardinality(objective_codes) >= 1
    AND jsonb_typeof(modality_objectives)='array' AND jsonb_array_length(modality_objectives) >= 1
    AND cardinality(primary_target_refs) >= 1
    AND primary_target_refs <@ encountered_target_refs
    AND primary_target_refs <@ output_target_refs
    AND jsonb_typeof(target_bindings)='object'
    AND jsonb_typeof(recall_specs)='array'
    AND minimum_useful_minutes BETWEEN 10 AND 60
    AND novelty_budget >= 0
    AND (arc_type NOT IN ('transfer','consolidation') OR novelty_budget = 0)
    AND cardinality(required_block_roles) >= 1
    AND cardinality(new_grammar_family_codes) <= 1
    AND new_grammar_family_codes <@ explained_grammar_family_codes
    AND gym_grammar_family_codes <@ explained_grammar_family_codes
    AND payload_checksum ~ '^sha256:[0-9a-f]{64}$'
  )
);

CREATE TABLE curriculum.module_revision_mappings (
  mapping_id uuid PRIMARY KEY,
  module_id uuid NOT NULL REFERENCES curriculum.learning_modules(module_id) ON DELETE RESTRICT,
  source_revision_id uuid NOT NULL REFERENCES curriculum.module_revisions(module_revision_id) ON DELETE RESTRICT,
  target_revision_id uuid NOT NULL REFERENCES curriculum.module_revisions(module_revision_id) ON DELETE RESTRICT,
  enrollment_migration_consented boolean NOT NULL,
  provenance_ref varchar(500) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_module_revision_mapping UNIQUE (source_revision_id,target_revision_id),
  CONSTRAINT ck_module_revision_mapping_uuid7 CHECK (
    curriculum.is_uuid7(mapping_id) AND curriculum.is_uuid7(module_id)
    AND curriculum.is_uuid7(source_revision_id) AND curriculum.is_uuid7(target_revision_id)
  ),
  CONSTRAINT ck_module_revision_mapping_shape CHECK (
    source_revision_id <> target_revision_id AND length(provenance_ref) >= 1
  )
);

CREATE TABLE curriculum.module_revision_mapping_entries (
  mapping_entry_id uuid PRIMARY KEY,
  mapping_id uuid NOT NULL REFERENCES curriculum.module_revision_mappings(mapping_id) ON DELETE RESTRICT,
  source_day_ordinal smallint NOT NULL,
  target_day_ordinal smallint NOT NULL,
  source_target_ref varchar(240) NOT NULL,
  target_target_ref varchar(240) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_mapping_entry_source UNIQUE (mapping_id,source_day_ordinal,source_target_ref),
  CONSTRAINT uq_mapping_entry_target UNIQUE (mapping_id,target_day_ordinal,target_target_ref),
  CONSTRAINT ck_mapping_entry_uuid7 CHECK (
    curriculum.is_uuid7(mapping_entry_id) AND curriculum.is_uuid7(mapping_id)
  ),
  CONSTRAINT ck_mapping_entry_shape CHECK (
    source_day_ordinal BETWEEN 1 AND 30 AND target_day_ordinal BETWEEN 1 AND 30
    AND length(source_target_ref) >= 1 AND length(target_target_ref) >= 1
  )
);

CREATE TABLE curriculum.module_enrollments (
  enrollment_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  module_revision_id uuid NOT NULL REFERENCES curriculum.module_revisions(module_revision_id) ON DELETE RESTRICT,
  nominal_days smallint NOT NULL,
  max_days smallint NOT NULL,
  status varchar(24) NOT NULL,
  current_day_ordinal smallint NOT NULL,
  started_on_pedagogical_day date,
  completed_at timestamptz,
  terminal_at timestamptz,
  paused_at timestamptz,
  waiver_refs varchar(240)[] NOT NULL,
  migration_map_revision_id uuid REFERENCES curriculum.module_revision_mappings(mapping_id) ON DELETE RESTRICT,
  version integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_module_enrollment_profile UNIQUE (profile_id,enrollment_id),
  CONSTRAINT ck_module_enrollment_uuid7 CHECK (
    curriculum.is_uuid7(enrollment_id) AND curriculum.is_uuid7(profile_id)
    AND curriculum.is_uuid7(module_revision_id)
    AND (migration_map_revision_id IS NULL OR curriculum.is_uuid7(migration_map_revision_id))
  ),
  CONSTRAINT ck_module_enrollment_shape CHECK (
    status IN ('planned','active','paused','completed','abandoned','cancelled')
    AND 3 <= nominal_days AND nominal_days <= max_days AND max_days <= 30
    AND current_day_ordinal BETWEEN 1 AND nominal_days
    AND version >= 1 AND updated_at >= created_at
    AND ((status='completed') = (completed_at IS NOT NULL))
    AND ((status IN ('completed','abandoned','cancelled')) = (terminal_at IS NOT NULL))
    AND ((status='paused') = (paused_at IS NOT NULL))
    AND ((status IN ('planned','cancelled')) = (started_on_pedagogical_day IS NULL))
  )
);
CREATE UNIQUE INDEX uq_curriculum_active_enrollment
  ON curriculum.module_enrollments(profile_id)
  WHERE status IN ('planned','active','paused');

CREATE TABLE curriculum.adaptive_day_instances (
  adaptive_day_id uuid PRIMARY KEY,
  enrollment_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  insert_before_ordinal smallint NOT NULL,
  reason_need_ids varchar(240)[] NOT NULL,
  day_payload_revision_id uuid NOT NULL,
  status varchar(24) NOT NULL,
  created_at timestamptz NOT NULL,
  completed_at timestamptz,
  CONSTRAINT fk_adaptive_day_enrollment FOREIGN KEY (profile_id,enrollment_id)
    REFERENCES curriculum.module_enrollments(profile_id,enrollment_id) ON DELETE RESTRICT,
  CONSTRAINT uq_adaptive_day_position UNIQUE (enrollment_id,insert_before_ordinal,adaptive_day_id),
  CONSTRAINT ck_adaptive_day_uuid7 CHECK (
    curriculum.is_uuid7(adaptive_day_id) AND curriculum.is_uuid7(enrollment_id)
    AND curriculum.is_uuid7(profile_id) AND curriculum.is_uuid7(day_payload_revision_id)
  ),
  CONSTRAINT ck_adaptive_day_shape CHECK (
    insert_before_ordinal BETWEEN 1 AND 30 AND cardinality(reason_need_ids) >= 1
    AND status IN ('planned','active','completed','cancelled')
    AND ((status='completed') = (completed_at IS NOT NULL))
  )
);

CREATE INDEX ix_module_revision_status ON curriculum.module_revisions(status,module_id,revision_no);
CREATE INDEX ix_module_day_revision ON curriculum.module_days(module_revision_id,ordinal);
CREATE INDEX ix_enrollment_profile_status ON curriculum.module_enrollments(profile_id,status,updated_at);
CREATE INDEX ix_adaptive_day_enrollment ON curriculum.adaptive_day_instances(enrollment_id,status,insert_before_ordinal);

DO $guards$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'module_revisions','module_days','module_revision_mappings','module_revision_mapping_entries'
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON curriculum.%I FOR EACH ROW EXECUTE FUNCTION curriculum.guard_append_only()',
      'guard_' || table_name,table_name
    );
  END LOOP;
END
$guards$;

DO $rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['module_enrollments','adaptive_day_instances'] LOOP
    EXECUTE format('ALTER TABLE curriculum.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE curriculum.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY %I ON curriculum.%I USING (curriculum.owns_profile(profile_id)) WITH CHECK (curriculum.owns_profile(profile_id))',
      table_name || '_owner',table_name
    );
  END LOOP;
END
$rls$;

GRANT USAGE ON SCHEMA curriculum TO polyglot_runtime;
GRANT SELECT ON curriculum.learning_modules,curriculum.module_revisions,curriculum.module_days,
  curriculum.module_revision_mappings,curriculum.module_revision_mapping_entries TO polyglot_runtime;
GRANT SELECT,INSERT ON curriculum.module_enrollments,curriculum.adaptive_day_instances TO polyglot_runtime;
GRANT UPDATE(status,current_day_ordinal,started_on_pedagogical_day,completed_at,terminal_at,
  paused_at,migration_map_revision_id,version,updated_at) ON curriculum.module_enrollments TO polyglot_runtime;
GRANT UPDATE(status,completed_at) ON curriculum.adaptive_day_instances TO polyglot_runtime;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA curriculum TO polyglot_migration;
REVOKE ALL ON ALL TABLES IN SCHEMA curriculum FROM PUBLIC;
ALTER FUNCTION curriculum.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION curriculum.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION curriculum.owns_profile(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION curriculum.has_role(text[]) OWNER TO polyglot_migration;
ALTER FUNCTION curriculum.guard_append_only() OWNER TO polyglot_migration;
ALTER TABLE curriculum.learning_modules OWNER TO polyglot_migration;
ALTER TABLE curriculum.module_revisions OWNER TO polyglot_migration;
ALTER TABLE curriculum.module_days OWNER TO polyglot_migration;
ALTER TABLE curriculum.module_revision_mappings OWNER TO polyglot_migration;
ALTER TABLE curriculum.module_revision_mapping_entries OWNER TO polyglot_migration;
ALTER TABLE curriculum.module_enrollments OWNER TO polyglot_migration;
ALTER TABLE curriculum.adaptive_day_instances OWNER TO polyglot_migration;
"""


DROP_DDL = r"""
DROP SCHEMA IF EXISTS curriculum CASCADE;
"""


async def _execute(connection: Connection, sql: str) -> None:
    await connection.execute(sql)


def upgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, CURRICULUM_DDL))


def downgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DROP_DDL))
