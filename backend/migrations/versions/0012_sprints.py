"""Persist deterministic sprint snapshots, plans and runs.

Revision ID: 0012_sprints
Revises: 0011_curriculum
"""

# ruff: noqa: E501

from alembic import op
from asyncpg import Connection

revision = "0012_sprints"
down_revision = "0011_curriculum"
branch_labels = None
depends_on = None


SPRINTS_DDL = r"""
CREATE SCHEMA planning AUTHORIZATION polyglot_migration;

CREATE FUNCTION planning.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
  SELECT value IS NOT NULL AND (get_byte(uuid_send(value),6) >> 4) = 7
$function$;
CREATE FUNCTION planning.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE AS $function$
  SELECT NULLIF(current_setting('app.user_id',true),'')::uuid
$function$;
CREATE FUNCTION planning.owns_profile(value uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,language_profiles,planning AS $function$
  SELECT EXISTS (
    SELECT 1 FROM language_profiles.learner_language_profiles profile
    WHERE profile.profile_id=value AND profile.account_id=planning.current_user_id()
      AND profile.status <> 'deleted'
  )
$function$;
CREATE FUNCTION planning.guard_append_only() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
  RAISE EXCEPTION 'planning fact is append-only' USING ERRCODE='55000';
END
$function$;

CREATE TABLE planning.delayed_recode_specs (
  delayed_recode_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  source_attempt_id uuid NOT NULL REFERENCES exercises.exercise_attempts(attempt_id) ON DELETE RESTRICT,
  source_correction_id uuid NOT NULL REFERENCES exercises.exercise_corrections(correction_id) ON DELETE RESTRICT,
  source_exercise_instance_id uuid NOT NULL REFERENCES exercises.exercise_instances(instance_id) ON DELETE RESTRICT,
  target_stimulus text NOT NULL,
  corrected_support_text text NOT NULL,
  accepted_target_answers jsonb NOT NULL,
  target_language_tag varchar(40) NOT NULL,
  support_language_tag varchar(40) NOT NULL,
  target_refs varchar(240)[] NOT NULL,
  correction_policy_revision_id uuid NOT NULL,
  content_revision_ids uuid[] NOT NULL,
  source_corrected_at timestamptz NOT NULL,
  not_before timestamptz NOT NULL,
  due_policy varchar(32) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_delayed_recode_source UNIQUE (source_attempt_id,source_correction_id),
  CONSTRAINT uq_delayed_recode_profile UNIQUE (profile_id,delayed_recode_id),
  CONSTRAINT ck_delayed_recode_uuid7 CHECK (
    planning.is_uuid7(delayed_recode_id) AND planning.is_uuid7(profile_id)
    AND planning.is_uuid7(source_attempt_id) AND planning.is_uuid7(source_correction_id)
    AND planning.is_uuid7(source_exercise_instance_id)
    AND planning.is_uuid7(correction_policy_revision_id)
  ),
  CONSTRAINT ck_delayed_recode_shape CHECK (
    length(target_stimulus) >= 1 AND length(corrected_support_text) >= 1
    AND jsonb_typeof(accepted_target_answers)='array'
    AND jsonb_array_length(accepted_target_answers) >= 1
    AND target_language_tag <> support_language_tag AND cardinality(target_refs) >= 1
    AND not_before >= source_corrected_at + interval '12 hours'
    AND due_policy IN ('next_active_session','after_24h')
  )
);

CREATE TABLE planning.delayed_recode_tasks (
  delayed_recode_task_id uuid PRIMARY KEY,
  delayed_recode_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  status varchar(24) NOT NULL,
  due_at timestamptz NOT NULL,
  consumed_by_plan_revision_id uuid,
  cancelled_reason varchar(240),
  version integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT fk_delayed_recode_task_spec FOREIGN KEY (profile_id,delayed_recode_id)
    REFERENCES planning.delayed_recode_specs(profile_id,delayed_recode_id) ON DELETE RESTRICT,
  CONSTRAINT uq_delayed_recode_task_spec UNIQUE (delayed_recode_id),
  CONSTRAINT uq_delayed_recode_task_profile UNIQUE (profile_id,delayed_recode_task_id),
  CONSTRAINT ck_delayed_recode_task_uuid7 CHECK (
    planning.is_uuid7(delayed_recode_task_id) AND planning.is_uuid7(delayed_recode_id)
    AND planning.is_uuid7(profile_id)
    AND (consumed_by_plan_revision_id IS NULL OR planning.is_uuid7(consumed_by_plan_revision_id))
  ),
  CONSTRAINT ck_delayed_recode_task_shape CHECK (
    status IN ('pending','due','planned','consumed','cancelled')
    AND version >= 1 AND updated_at >= created_at
    AND ((status IN ('planned','consumed')) = (consumed_by_plan_revision_id IS NOT NULL))
    AND ((status='cancelled') = (cancelled_reason IS NOT NULL))
  )
);

CREATE TABLE planning.planning_snapshots (
  snapshot_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  plan_kind varchar(24) NOT NULL,
  budget_minutes smallint NOT NULL,
  pedagogical_day date NOT NULL,
  timezone varchar(80) NOT NULL,
  cutoff_at timestamptz NOT NULL,
  seed varchar(160) NOT NULL,
  policy_revision varchar(120) NOT NULL,
  planner_revision varchar(120) NOT NULL,
  profile_band varchar(24) NOT NULL,
  enrollment_id uuid REFERENCES curriculum.module_enrollments(enrollment_id) ON DELETE RESTRICT,
  module_revision_id uuid REFERENCES curriculum.module_revisions(module_revision_id) ON DELETE RESTRICT,
  module_day_id uuid REFERENCES curriculum.module_days(module_day_id) ON DELETE RESTRICT,
  mastered_refs varchar(240)[] NOT NULL,
  prerequisite_refs varchar(240)[] NOT NULL,
  due_delayed_recode_ids uuid[] NOT NULL,
  word_bank_snapshot_ids uuid[] NOT NULL,
  candidate_payload jsonb NOT NULL,
  private_context text,
  payload_fingerprint char(64) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_planning_snapshot_profile UNIQUE (profile_id,snapshot_id),
  CONSTRAINT ck_planning_snapshot_uuid7 CHECK (
    planning.is_uuid7(snapshot_id) AND planning.is_uuid7(profile_id)
    AND (enrollment_id IS NULL OR planning.is_uuid7(enrollment_id))
    AND (module_revision_id IS NULL OR planning.is_uuid7(module_revision_id))
    AND (module_day_id IS NULL OR planning.is_uuid7(module_day_id))
  ),
  CONSTRAINT ck_planning_snapshot_shape CHECK (
    plan_kind IN ('daily','free','foundation','assessment_prep')
    AND budget_minutes BETWEEN 10 AND 60 AND budget_minutes % 5 = 0
    AND length(timezone) >= 1 AND length(seed) >= 1
    AND length(policy_revision) >= 1 AND length(planner_revision) >= 1
    AND profile_band IN ('P-ABS','P-FAUX','P-INT')
    AND jsonb_typeof(candidate_payload)='array'
    AND payload_fingerprint ~ '^[0-9a-f]{64}$'
    AND ((plan_kind='daily') = (enrollment_id IS NOT NULL))
    AND ((plan_kind='daily') = (module_revision_id IS NOT NULL))
    AND ((plan_kind='daily') = (module_day_id IS NOT NULL))
  )
);

CREATE TABLE planning.session_plans (
  plan_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  plan_kind varchar(24) NOT NULL,
  pedagogical_day date NOT NULL,
  current_revision_id uuid,
  status varchar(24) NOT NULL,
  failure_code varchar(120),
  version integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_session_plan_profile UNIQUE (profile_id,plan_id),
  CONSTRAINT ck_session_plan_uuid7 CHECK (
    planning.is_uuid7(plan_id) AND planning.is_uuid7(profile_id)
    AND (current_revision_id IS NULL OR planning.is_uuid7(current_revision_id))
  ),
  CONSTRAINT ck_session_plan_shape CHECK (
    plan_kind IN ('daily','free','foundation','assessment_prep')
    AND status IN ('draft','preparing','ready','failed','expired','cancelled')
    AND version >= 1 AND updated_at >= created_at
    AND ((status='failed') = (failure_code IS NOT NULL))
  )
);

CREATE TABLE planning.session_plan_revisions (
  plan_revision_id uuid PRIMARY KEY,
  plan_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  revision_no integer NOT NULL,
  snapshot_id uuid NOT NULL,
  budget_minutes smallint NOT NULL,
  total_p50_seconds integer NOT NULL,
  total_p80_seconds integer NOT NULL,
  novelty_points numeric(7,3) NOT NULL,
  planner_revision varchar(120) NOT NULL,
  policy_revision varchar(120) NOT NULL,
  plan_fingerprint char(71) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_session_plan_revision_plan FOREIGN KEY (profile_id,plan_id)
    REFERENCES planning.session_plans(profile_id,plan_id) ON DELETE RESTRICT,
  CONSTRAINT fk_session_plan_revision_snapshot FOREIGN KEY (profile_id,snapshot_id)
    REFERENCES planning.planning_snapshots(profile_id,snapshot_id) ON DELETE RESTRICT,
  CONSTRAINT uq_session_plan_revision UNIQUE (plan_id,revision_no),
  CONSTRAINT uq_session_plan_revision_owner UNIQUE (plan_id,plan_revision_id),
  CONSTRAINT uq_session_plan_revision_profile UNIQUE (profile_id,plan_revision_id),
  CONSTRAINT ck_session_plan_revision_uuid7 CHECK (
    planning.is_uuid7(plan_revision_id) AND planning.is_uuid7(plan_id)
    AND planning.is_uuid7(profile_id) AND planning.is_uuid7(snapshot_id)
  ),
  CONSTRAINT ck_session_plan_revision_shape CHECK (
    revision_no >= 1 AND budget_minutes BETWEEN 10 AND 60 AND budget_minutes % 5 = 0
    AND total_p50_seconds >= 0 AND total_p50_seconds <= budget_minutes*54
    AND total_p80_seconds >= total_p50_seconds AND total_p80_seconds <= budget_minutes*60
    AND novelty_points >= 0 AND length(planner_revision) >= 1 AND length(policy_revision) >= 1
    AND plan_fingerprint ~ '^sha256:[0-9a-f]{64}$'
  )
);
ALTER TABLE planning.session_plans ADD CONSTRAINT fk_session_plan_current_revision
  FOREIGN KEY (plan_id,current_revision_id)
  REFERENCES planning.session_plan_revisions(plan_id,plan_revision_id) ON DELETE RESTRICT;
ALTER TABLE planning.delayed_recode_tasks ADD CONSTRAINT fk_delayed_recode_task_plan_revision
  FOREIGN KEY (profile_id,consumed_by_plan_revision_id)
  REFERENCES planning.session_plan_revisions(profile_id,plan_revision_id) ON DELETE RESTRICT;

CREATE TABLE planning.session_plan_blocks (
  session_plan_block_id uuid PRIMARY KEY,
  plan_revision_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  ordinal smallint NOT NULL,
  candidate_id uuid NOT NULL,
  family varchar(40) NOT NULL,
  roles varchar(80)[] NOT NULL,
  reason_codes varchar(120)[] NOT NULL,
  modalities varchar(24)[] NOT NULL,
  p50_seconds integer NOT NULL,
  p80_seconds integer NOT NULL,
  novelty_points numeric(7,3) NOT NULL,
  required boolean NOT NULL,
  delayed_recode_id uuid REFERENCES planning.delayed_recode_specs(delayed_recode_id) ON DELETE RESTRICT,
  exercise_definition_revision_ids uuid[] NOT NULL,
  content_revision_ids uuid[] NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_session_plan_block_revision FOREIGN KEY (profile_id,plan_revision_id)
    REFERENCES planning.session_plan_revisions(profile_id,plan_revision_id) ON DELETE RESTRICT,
  CONSTRAINT uq_session_plan_block_ordinal UNIQUE (plan_revision_id,ordinal),
  CONSTRAINT uq_session_plan_block_candidate UNIQUE (plan_revision_id,candidate_id),
  CONSTRAINT uq_session_plan_block_profile UNIQUE (profile_id,session_plan_block_id),
  CONSTRAINT ck_session_plan_block_uuid7 CHECK (
    planning.is_uuid7(session_plan_block_id) AND planning.is_uuid7(plan_revision_id)
    AND planning.is_uuid7(profile_id) AND planning.is_uuid7(candidate_id)
    AND (delayed_recode_id IS NULL OR planning.is_uuid7(delayed_recode_id))
  ),
  CONSTRAINT ck_session_plan_block_shape CHECK (
    ordinal BETWEEN 1 AND 7 AND cardinality(roles) >= 1 AND cardinality(reason_codes) >= 1
    AND family IN ('recall_warmup','lexical_acquisition','version_input','grammar_toolbox',
      'transformation_gym','listening','shadowing','guided_output','free_writing',
      'delayed_recode','reflection_close')
    AND modalities <@ ARRAY['reading','listening','writing','speaking']::varchar[]
    AND p50_seconds >= 30 AND p80_seconds >= p50_seconds AND novelty_points >= 0
  )
);

CREATE TABLE planning.session_plan_exercise_instances (
  plan_instance_link_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL,
  plan_revision_id uuid NOT NULL,
  session_plan_block_id uuid NOT NULL,
  instance_id uuid NOT NULL REFERENCES exercises.exercise_instances(instance_id) ON DELETE RESTRICT,
  ordinal smallint NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_plan_instance_revision FOREIGN KEY (profile_id,plan_revision_id)
    REFERENCES planning.session_plan_revisions(profile_id,plan_revision_id) ON DELETE RESTRICT,
  CONSTRAINT fk_plan_instance_block FOREIGN KEY (profile_id,session_plan_block_id)
    REFERENCES planning.session_plan_blocks(profile_id,session_plan_block_id) ON DELETE RESTRICT,
  CONSTRAINT uq_plan_instance_ordinal UNIQUE (session_plan_block_id,ordinal),
  CONSTRAINT uq_plan_instance_once UNIQUE (plan_revision_id,instance_id),
  CONSTRAINT ck_plan_instance_uuid7 CHECK (
    planning.is_uuid7(plan_instance_link_id) AND planning.is_uuid7(profile_id)
    AND planning.is_uuid7(plan_revision_id) AND planning.is_uuid7(session_plan_block_id)
    AND planning.is_uuid7(instance_id) AND ordinal >= 1
  )
);

CREATE TABLE planning.sprint_runs (
  sprint_run_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  plan_id uuid NOT NULL,
  plan_revision_id uuid NOT NULL,
  plan_kind varchar(24) NOT NULL,
  pedagogical_day date NOT NULL,
  enrollment_id uuid REFERENCES curriculum.module_enrollments(enrollment_id) ON DELETE RESTRICT,
  module_day_id uuid REFERENCES curriculum.module_days(module_day_id) ON DELETE RESTRICT,
  status varchar(24) NOT NULL,
  current_block_id uuid,
  started_at timestamptz NOT NULL,
  interrupted_at timestamptz,
  completed_at timestamptz,
  expires_at timestamptz NOT NULL,
  stop_reason varchar(240),
  active_duration_ms bigint NOT NULL,
  version integer NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT fk_sprint_run_plan FOREIGN KEY (profile_id,plan_id)
    REFERENCES planning.session_plans(profile_id,plan_id) ON DELETE RESTRICT,
  CONSTRAINT fk_sprint_run_revision FOREIGN KEY (profile_id,plan_revision_id)
    REFERENCES planning.session_plan_revisions(profile_id,plan_revision_id) ON DELETE RESTRICT,
  CONSTRAINT uq_sprint_run_profile UNIQUE (profile_id,sprint_run_id),
  CONSTRAINT uq_sprint_run_plan UNIQUE (plan_id),
  CONSTRAINT ck_sprint_run_uuid7 CHECK (
    planning.is_uuid7(sprint_run_id) AND planning.is_uuid7(profile_id)
    AND planning.is_uuid7(plan_id) AND planning.is_uuid7(plan_revision_id)
    AND (enrollment_id IS NULL OR planning.is_uuid7(enrollment_id))
    AND (module_day_id IS NULL OR planning.is_uuid7(module_day_id))
    AND (current_block_id IS NULL OR planning.is_uuid7(current_block_id))
  ),
  CONSTRAINT ck_sprint_run_shape CHECK (
    plan_kind IN ('daily','free','foundation','assessment_prep')
    AND status IN ('not_started','in_progress','interrupted','completed','stopped','cancelled')
    AND expires_at > started_at AND active_duration_ms >= 0 AND version >= 1
    AND updated_at >= started_at
    AND ((status='interrupted') = (interrupted_at IS NOT NULL))
    AND ((status IN ('completed','stopped','cancelled')) = (completed_at IS NOT NULL))
    AND ((plan_kind='daily') = (enrollment_id IS NOT NULL))
    AND ((plan_kind='daily') = (module_day_id IS NOT NULL))
  )
);

ALTER TABLE planning.sprint_runs ADD CONSTRAINT fk_sprint_run_current_block
  FOREIGN KEY (profile_id,current_block_id)
  REFERENCES planning.session_plan_blocks(profile_id,session_plan_block_id) ON DELETE RESTRICT;

CREATE TABLE planning.planning_command_receipts (
  receipt_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  actor_id uuid NOT NULL,
  command_type varchar(120) NOT NULL,
  idempotency_key varchar(255) NOT NULL,
  request_fingerprint char(64) NOT NULL,
  result_type varchar(40) NOT NULL,
  result_id uuid NOT NULL,
  result_version integer NOT NULL,
  result_payload jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_planning_command_receipt UNIQUE (actor_id,command_type,idempotency_key),
  CONSTRAINT ck_planning_command_receipt_uuid7 CHECK (
    planning.is_uuid7(receipt_id) AND planning.is_uuid7(profile_id)
    AND planning.is_uuid7(actor_id) AND planning.is_uuid7(result_id)
  ),
  CONSTRAINT ck_planning_command_receipt_shape CHECK (
    request_fingerprint ~ '^[0-9a-f]{64}$' AND result_version >= 1
    AND result_type IN ('session_plan','sprint_run','exercise_block')
    AND jsonb_typeof(result_payload)='object' AND octet_length(result_payload::text) <= 65536
  )
);

CREATE UNIQUE INDEX uq_planning_active_run ON planning.sprint_runs(profile_id)
  WHERE status IN ('in_progress','interrupted');
CREATE UNIQUE INDEX uq_planning_daily_plan ON planning.session_plans(profile_id,pedagogical_day)
  WHERE plan_kind='daily' AND status IN ('draft','preparing','ready');
CREATE INDEX ix_planning_recode_due ON planning.delayed_recode_tasks(profile_id,status,due_at);
CREATE INDEX ix_planning_plan_profile ON planning.session_plans(profile_id,status,pedagogical_day);
CREATE INDEX ix_planning_run_profile ON planning.sprint_runs(profile_id,status,updated_at);

ALTER TABLE exercises.exercise_instances ADD CONSTRAINT fk_exercise_instance_session_plan_revision
  FOREIGN KEY (session_plan_revision_id)
  REFERENCES planning.session_plan_revisions(plan_revision_id) ON DELETE RESTRICT;
ALTER TABLE exercises.exercise_block_runs
  ADD COLUMN session_plan_block_id uuid NOT NULL,
  ADD CONSTRAINT fk_exercise_block_sprint_run FOREIGN KEY (sprint_run_id)
    REFERENCES planning.sprint_runs(sprint_run_id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_exercise_block_plan_block FOREIGN KEY (profile_id,session_plan_block_id)
    REFERENCES planning.session_plan_blocks(profile_id,session_plan_block_id) ON DELETE RESTRICT;

DO $guards$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'delayed_recode_specs','planning_snapshots','session_plan_revisions',
    'session_plan_blocks','session_plan_exercise_instances'
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON planning.%I FOR EACH ROW EXECUTE FUNCTION planning.guard_append_only()',
      'guard_' || table_name,table_name
    );
  END LOOP;
END
$guards$;

DO $rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'delayed_recode_specs','delayed_recode_tasks','planning_snapshots','session_plans',
    'session_plan_revisions','session_plan_blocks','session_plan_exercise_instances',
    'sprint_runs','planning_command_receipts'
  ] LOOP
    EXECUTE format('ALTER TABLE planning.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE planning.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY %I ON planning.%I USING (planning.owns_profile(profile_id)) WITH CHECK (planning.owns_profile(profile_id))',
      table_name || '_owner',table_name
    );
  END LOOP;
END
$rls$;

GRANT USAGE ON SCHEMA planning TO polyglot_runtime;
GRANT SELECT,INSERT ON planning.delayed_recode_specs,planning.planning_snapshots,
  planning.session_plan_revisions,planning.session_plan_blocks,
  planning.session_plan_exercise_instances,planning.planning_command_receipts TO polyglot_runtime;
GRANT SELECT,INSERT ON planning.delayed_recode_tasks,planning.session_plans,
  planning.sprint_runs TO polyglot_runtime;
GRANT UPDATE(status,consumed_by_plan_revision_id,cancelled_reason,version,updated_at)
  ON planning.delayed_recode_tasks TO polyglot_runtime;
GRANT UPDATE(current_revision_id,status,failure_code,version,updated_at)
  ON planning.session_plans TO polyglot_runtime;
GRANT UPDATE(status,current_block_id,interrupted_at,completed_at,stop_reason,
  active_duration_ms,version,updated_at) ON planning.sprint_runs TO polyglot_runtime;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA planning TO polyglot_migration;
REVOKE ALL ON ALL TABLES IN SCHEMA planning FROM PUBLIC;
ALTER FUNCTION planning.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION planning.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION planning.owns_profile(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION planning.guard_append_only() OWNER TO polyglot_migration;
DO $owners$ DECLARE item record; BEGIN
  FOR item IN SELECT tablename FROM pg_tables WHERE schemaname='planning' LOOP
    EXECUTE format('ALTER TABLE planning.%I OWNER TO polyglot_migration',item.tablename);
  END LOOP;
END $owners$;
"""


DROP_DDL = r"""
ALTER TABLE IF EXISTS exercises.exercise_block_runs
  DROP CONSTRAINT IF EXISTS fk_exercise_block_plan_block,
  DROP CONSTRAINT IF EXISTS fk_exercise_block_sprint_run,
  DROP COLUMN IF EXISTS session_plan_block_id;
ALTER TABLE IF EXISTS exercises.exercise_instances
  DROP CONSTRAINT IF EXISTS fk_exercise_instance_session_plan_revision;
DROP SCHEMA IF EXISTS planning CASCADE;
"""


async def _execute(connection: Connection, sql: str) -> None:
    await connection.execute(sql)


def upgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, SPRINTS_DDL))


def downgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DROP_DDL))
