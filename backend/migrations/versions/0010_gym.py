"""Persist deterministic Gym plans and G0-G4 cycle evidence.

Revision ID: 0010_gym
Revises: 0009_exercises
"""

# ruff: noqa: E501

from alembic import op
from asyncpg import Connection

revision = "0010_gym"
down_revision = "0009_exercises"
branch_labels = None
depends_on = None


GYM_DDL = r"""
CREATE TABLE exercises.gym_plans (
  gym_plan_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  current_revision_id uuid,
  status varchar(24) NOT NULL,
  version integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_gym_plan_profile UNIQUE (profile_id,gym_plan_id),
  CONSTRAINT ck_gym_plan_uuid7 CHECK (
    exercises.is_uuid7(gym_plan_id) AND exercises.is_uuid7(profile_id)
    AND (current_revision_id IS NULL OR exercises.is_uuid7(current_revision_id))
  ),
  CONSTRAINT ck_gym_plan_shape CHECK (
    status IN ('draft','ready','active','completed','abandoned')
    AND version >= 1 AND updated_at >= created_at
  )
);

CREATE TABLE exercises.gym_plan_revisions (
  gym_plan_revision_id uuid PRIMARY KEY,
  gym_plan_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  revision_no integer NOT NULL,
  grammar_target_revision_id uuid NOT NULL
    REFERENCES catalogue.grammar_structure_revisions(structure_revision_id) ON DELETE RESTRICT,
  policy_revision_id uuid NOT NULL,
  language_pack_revision_id uuid NOT NULL
    REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
  lexical_support_snapshot_id uuid NOT NULL,
  seed bigint NOT NULL,
  invariants jsonb NOT NULL,
  exit_evidence_spec jsonb NOT NULL,
  provenance_id uuid NOT NULL REFERENCES platform.provenance_records(provenance_id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_gym_plan_revision_plan FOREIGN KEY (profile_id,gym_plan_id)
    REFERENCES exercises.gym_plans(profile_id,gym_plan_id) ON DELETE RESTRICT,
  CONSTRAINT fk_gym_plan_revision_lexical_snapshot FOREIGN KEY (profile_id,lexical_support_snapshot_id)
    REFERENCES lexicon.list_snapshots(profile_id,snapshot_id) ON DELETE RESTRICT,
  CONSTRAINT uq_gym_plan_revision UNIQUE (gym_plan_id,revision_no),
  CONSTRAINT uq_gym_plan_revision_owner UNIQUE (gym_plan_id,gym_plan_revision_id),
  CONSTRAINT uq_gym_plan_revision_profile UNIQUE (profile_id,gym_plan_revision_id),
  CONSTRAINT ck_gym_plan_revision_uuid7 CHECK (
    exercises.is_uuid7(gym_plan_revision_id) AND exercises.is_uuid7(gym_plan_id)
    AND exercises.is_uuid7(profile_id) AND exercises.is_uuid7(grammar_target_revision_id)
    AND exercises.is_uuid7(policy_revision_id) AND exercises.is_uuid7(language_pack_revision_id)
    AND exercises.is_uuid7(lexical_support_snapshot_id) AND exercises.is_uuid7(provenance_id)
  ),
  CONSTRAINT ck_gym_plan_revision_shape CHECK (
    revision_no >= 1 AND seed BETWEEN 0 AND 9223372036854775807
    AND jsonb_typeof(invariants)='array' AND jsonb_array_length(invariants) >= 1
    AND jsonb_typeof(exit_evidence_spec)='object'
  )
);

ALTER TABLE exercises.gym_plans ADD CONSTRAINT fk_gym_plan_current_revision
  FOREIGN KEY (gym_plan_id,current_revision_id)
  REFERENCES exercises.gym_plan_revisions(gym_plan_id,gym_plan_revision_id)
  ON DELETE RESTRICT;

CREATE TABLE exercises.gym_steps (
  gym_step_id uuid PRIMARY KEY,
  gym_plan_revision_id uuid NOT NULL,
  gym_plan_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  ordinal smallint NOT NULL,
  case_revision_ref varchar(240) NOT NULL,
  gym_operation varchar(8) NOT NULL,
  instance_id uuid NOT NULL REFERENCES exercises.exercise_instances(instance_id) ON DELETE RESTRICT,
  instance_seed bigint NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_gym_step_plan_revision FOREIGN KEY (gym_plan_id,gym_plan_revision_id)
    REFERENCES exercises.gym_plan_revisions(gym_plan_id,gym_plan_revision_id) ON DELETE RESTRICT,
  CONSTRAINT fk_gym_step_profile_revision FOREIGN KEY (profile_id,gym_plan_revision_id)
    REFERENCES exercises.gym_plan_revisions(profile_id,gym_plan_revision_id) ON DELETE RESTRICT,
  CONSTRAINT uq_gym_step_ordinal UNIQUE (gym_plan_revision_id,ordinal),
  CONSTRAINT uq_gym_step_case UNIQUE (gym_plan_revision_id,case_revision_ref),
  CONSTRAINT ck_gym_step_uuid7 CHECK (
    exercises.is_uuid7(gym_step_id) AND exercises.is_uuid7(gym_plan_revision_id)
    AND exercises.is_uuid7(gym_plan_id) AND exercises.is_uuid7(profile_id)
    AND exercises.is_uuid7(instance_id)
  ),
  CONSTRAINT ck_gym_step_shape CHECK (
    ordinal BETWEEN 1 AND 3 AND instance_seed BETWEEN 0 AND 9223372036854775807
    AND length(case_revision_ref) BETWEEN 1 AND 240
    AND gym_operation ~ '^GYM-(0[1-9]|1[0-5])$'
  )
);

CREATE TABLE exercises.gym_cycles (
  gym_cycle_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL,
  gym_plan_revision_id uuid NOT NULL,
  grammar_target_revision_id uuid NOT NULL
    REFERENCES catalogue.grammar_structure_revisions(structure_revision_id) ON DELETE RESTRICT,
  stage varchar(2) NOT NULL,
  completed boolean NOT NULL,
  started_at timestamptz NOT NULL,
  completed_at timestamptz,
  completed_g1_requirement_ids jsonb NOT NULL,
  version integer NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT fk_gym_cycle_plan_revision FOREIGN KEY (profile_id,gym_plan_revision_id)
    REFERENCES exercises.gym_plan_revisions(profile_id,gym_plan_revision_id) ON DELETE RESTRICT,
  CONSTRAINT uq_gym_cycle_profile UNIQUE (profile_id,gym_cycle_id),
  CONSTRAINT ck_gym_cycle_uuid7 CHECK (
    exercises.is_uuid7(gym_cycle_id) AND exercises.is_uuid7(profile_id)
    AND exercises.is_uuid7(gym_plan_revision_id) AND exercises.is_uuid7(grammar_target_revision_id)
  ),
  CONSTRAINT ck_gym_cycle_shape CHECK (
    stage IN ('g0','g1','g2','g3','g4') AND version >= 1 AND updated_at >= started_at
    AND jsonb_typeof(completed_g1_requirement_ids)='array'
    AND ((completed=false AND completed_at IS NULL) OR (completed=true AND stage='g4' AND completed_at IS NOT NULL))
  )
);

CREATE TABLE exercises.gym_cycle_requirements (
  gym_cycle_requirement_id uuid PRIMARY KEY,
  gym_cycle_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  requirement_id varchar(160) NOT NULL,
  requirement_kind varchar(32) NOT NULL,
  definition_revision_id uuid NOT NULL
    REFERENCES exercises.exercise_definition_revisions(definition_revision_id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_gym_cycle_requirement_cycle FOREIGN KEY (profile_id,gym_cycle_id)
    REFERENCES exercises.gym_cycles(profile_id,gym_cycle_id) ON DELETE RESTRICT,
  CONSTRAINT uq_gym_cycle_requirement UNIQUE (gym_cycle_id,requirement_id),
  CONSTRAINT ck_gym_cycle_requirement_uuid7 CHECK (
    exercises.is_uuid7(gym_cycle_requirement_id) AND exercises.is_uuid7(gym_cycle_id)
    AND exercises.is_uuid7(profile_id) AND exercises.is_uuid7(definition_revision_id)
  ),
  CONSTRAINT ck_gym_cycle_requirement_shape CHECK (
    length(requirement_id) BETWEEN 1 AND 160
    AND requirement_kind IN ('guided_production','transformation')
  )
);

CREATE TABLE exercises.gym_cycle_records (
  gym_cycle_record_id uuid PRIMARY KEY,
  gym_cycle_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  ordinal integer NOT NULL,
  stage varchar(2) NOT NULL,
  verdict varchar(32) NOT NULL,
  hint_level smallint NOT NULL,
  context_id varchar(240) NOT NULL,
  scene_id varchar(240) NOT NULL,
  structure_cued boolean NOT NULL,
  credit numeric(5,4) NOT NULL,
  is_evidence boolean NOT NULL,
  g1_requirement_id varchar(160),
  attempt_id uuid REFERENCES exercises.exercise_attempts(attempt_id) ON DELETE RESTRICT,
  idempotency_key varchar(255) NOT NULL,
  request_fingerprint char(64) NOT NULL,
  recorded_at timestamptz NOT NULL,
  CONSTRAINT fk_gym_cycle_record_cycle FOREIGN KEY (profile_id,gym_cycle_id)
    REFERENCES exercises.gym_cycles(profile_id,gym_cycle_id) ON DELETE RESTRICT,
  CONSTRAINT uq_gym_cycle_record_ordinal UNIQUE (gym_cycle_id,ordinal),
  CONSTRAINT uq_gym_cycle_record_idempotency UNIQUE (profile_id,gym_cycle_id,idempotency_key),
  CONSTRAINT ck_gym_cycle_record_uuid7 CHECK (
    exercises.is_uuid7(gym_cycle_record_id) AND exercises.is_uuid7(gym_cycle_id)
    AND exercises.is_uuid7(profile_id) AND (attempt_id IS NULL OR exercises.is_uuid7(attempt_id))
  ),
  CONSTRAINT ck_gym_cycle_record_shape CHECK (
    ordinal >= 1 AND stage IN ('g0','g1','g2','g3','g4')
    AND verdict IN ('correct','partially_correct','incorrect','ambiguous','invalid_answer','not_evaluable')
    AND hint_level BETWEEN 0 AND 4 AND credit BETWEEN -1 AND 1
    AND length(context_id) BETWEEN 1 AND 240 AND length(scene_id) BETWEEN 1 AND 240
    AND request_fingerprint ~ '^[0-9a-f]{64}$'
    AND ((stage='g1') = (g1_requirement_id IS NOT NULL))
    AND (is_evidence = (credit <> 0))
  )
);

CREATE INDEX ix_gym_plan_profile_status
  ON exercises.gym_plans(profile_id,status,updated_at,gym_plan_id);
CREATE INDEX ix_gym_cycle_profile_stage
  ON exercises.gym_cycles(profile_id,stage,updated_at,gym_cycle_id);
CREATE INDEX ix_gym_cycle_record_cycle
  ON exercises.gym_cycle_records(gym_cycle_id,recorded_at,ordinal);

DO $guards$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'gym_plan_revisions','gym_steps','gym_cycle_requirements','gym_cycle_records'
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON exercises.%I FOR EACH ROW EXECUTE FUNCTION exercises.guard_append_only()',
      'guard_' || table_name,table_name
    );
  END LOOP;
END
$guards$;

DO $rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'gym_plans','gym_plan_revisions','gym_steps','gym_cycles',
    'gym_cycle_requirements','gym_cycle_records'
  ] LOOP
    EXECUTE format('ALTER TABLE exercises.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE exercises.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY %I ON exercises.%I USING (exercises.owns_profile(profile_id)) WITH CHECK (exercises.owns_profile(profile_id))',
      table_name || '_owner',table_name
    );
  END LOOP;
END
$rls$;

GRANT SELECT,INSERT ON exercises.gym_plans,exercises.gym_cycles TO polyglot_runtime;
GRANT UPDATE(current_revision_id,status,version,updated_at) ON exercises.gym_plans
  TO polyglot_runtime;
GRANT UPDATE(stage,completed,completed_at,completed_g1_requirement_ids,version,updated_at)
  ON exercises.gym_cycles TO polyglot_runtime;
GRANT SELECT,INSERT ON exercises.gym_plan_revisions,exercises.gym_steps,
  exercises.gym_cycle_requirements,exercises.gym_cycle_records TO polyglot_runtime;
GRANT ALL PRIVILEGES ON exercises.gym_plans,exercises.gym_plan_revisions,
  exercises.gym_steps,exercises.gym_cycles,exercises.gym_cycle_requirements,
  exercises.gym_cycle_records TO polyglot_migration;
REVOKE ALL ON exercises.gym_plans,exercises.gym_plan_revisions,exercises.gym_steps,
  exercises.gym_cycles,exercises.gym_cycle_requirements,exercises.gym_cycle_records FROM PUBLIC;
ALTER TABLE exercises.gym_plans OWNER TO polyglot_migration;
ALTER TABLE exercises.gym_plan_revisions OWNER TO polyglot_migration;
ALTER TABLE exercises.gym_steps OWNER TO polyglot_migration;
ALTER TABLE exercises.gym_cycles OWNER TO polyglot_migration;
ALTER TABLE exercises.gym_cycle_requirements OWNER TO polyglot_migration;
ALTER TABLE exercises.gym_cycle_records OWNER TO polyglot_migration;
"""

DROP_DDL = r"""
DROP TABLE IF EXISTS exercises.gym_cycle_records CASCADE;
DROP TABLE IF EXISTS exercises.gym_cycle_requirements CASCADE;
DROP TABLE IF EXISTS exercises.gym_cycles CASCADE;
DROP TABLE IF EXISTS exercises.gym_steps CASCADE;
ALTER TABLE IF EXISTS exercises.gym_plans DROP CONSTRAINT IF EXISTS fk_gym_plan_current_revision;
DROP TABLE IF EXISTS exercises.gym_plan_revisions CASCADE;
DROP TABLE IF EXISTS exercises.gym_plans CASCADE;
"""


async def _execute(connection: Connection, sql: str) -> None:
    await connection.execute(sql)


def upgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, GYM_DDL))


def downgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DROP_DDL))
