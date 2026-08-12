"""Persist adaptive placement runs and immutable evidence.

Revision ID: 0025_adaptive_placement
Revises: 0024_parallel_practice
"""

# ruff: noqa: E501

from alembic import op
from asyncpg import Connection

revision = "0025_adaptive_placement"
down_revision = "0024_parallel_practice"
branch_labels = None
depends_on = None


DDL = r"""
CREATE SCHEMA placement AUTHORIZATION polyglot_migration;
CREATE FUNCTION placement.current_user_id() RETURNS uuid LANGUAGE sql STABLE PARALLEL SAFE AS $$
  SELECT NULLIF(current_setting('app.user_id',true),'')::uuid
$$;
CREATE FUNCTION placement.owns_profile(value uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,language_profiles,placement AS $$
  SELECT EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles p
    WHERE p.profile_id=value AND p.account_id=placement.current_user_id() AND p.status <> 'deleted')
$$;
CREATE FUNCTION placement.guard_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'placement fact is append-only' USING ERRCODE='55000'; END
$$;

CREATE TABLE placement.policy_revisions (
  policy_revision_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(policy_revision_id)),
  policy_code text NOT NULL, revision_no integer NOT NULL CHECK (revision_no>0), status text NOT NULL CHECK (status IN ('draft','published','retired')),
  configuration jsonb NOT NULL CHECK (jsonb_typeof(configuration)='object'), created_at timestamptz NOT NULL,
  UNIQUE(policy_code,revision_no)
);
CREATE TABLE placement.item_blueprints (
  blueprint_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(blueprint_id)), blueprint_code text NOT NULL UNIQUE,
  target_variety_id uuid NOT NULL REFERENCES catalogue.language_varieties(variety_id) ON DELETE RESTRICT,
  status text NOT NULL CHECK (status IN ('draft','published','retired')), created_at timestamptz NOT NULL
);
CREATE TABLE placement.item_blueprint_revisions (
  blueprint_revision_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(blueprint_revision_id)),
  blueprint_id uuid NOT NULL REFERENCES placement.item_blueprints(blueprint_id) ON DELETE RESTRICT,
  language_pack_revision_id uuid NOT NULL REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
  revision_no integer NOT NULL CHECK (revision_no>0), primitive_ref text NOT NULL, primary_skill_ref text NOT NULL,
  level smallint NOT NULL CHECK (level BETWEEN 0 AND 8), estimated_seconds integer NOT NULL CHECK (estimated_seconds>0),
  prerequisites jsonb NOT NULL CHECK (jsonb_typeof(prerequisites)='array'), scorer_kind text NOT NULL CHECK (scorer_kind IN ('deterministic','structured','structured_lm','not_evaluable')),
  content jsonb NOT NULL CHECK (jsonb_typeof(content)='object'), created_at timestamptz NOT NULL, UNIQUE(blueprint_id,revision_no)
);
CREATE TABLE placement.rubric_revisions (
  rubric_revision_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(rubric_revision_id)), rubric_code text NOT NULL,
  revision_no integer NOT NULL CHECK (revision_no>0), schema_payload jsonb NOT NULL CHECK (jsonb_typeof(schema_payload)='object'),
  created_at timestamptz NOT NULL, UNIQUE(rubric_code,revision_no)
);
CREATE TABLE placement.variant_revisions (
  variant_revision_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(variant_revision_id)),
  blueprint_revision_id uuid NOT NULL REFERENCES placement.item_blueprint_revisions(blueprint_revision_id) ON DELETE RESTRICT,
  rubric_revision_id uuid REFERENCES placement.rubric_revisions(rubric_revision_id) ON DELETE RESTRICT,
  variant_pool_id text NOT NULL, revision_no integer NOT NULL CHECK (revision_no>0), payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='object'),
  answer_key jsonb CHECK (answer_key IS NULL OR jsonb_typeof(answer_key)='object'), media_asset_id uuid,
  status text NOT NULL CHECK (status IN ('draft','published','retired')), created_at timestamptz NOT NULL,
  UNIQUE(blueprint_revision_id,variant_pool_id,revision_no)
);
CREATE TABLE placement.runs (
  run_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(run_id)), profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  policy_revision_id uuid NOT NULL REFERENCES placement.policy_revisions(policy_revision_id) ON DELETE RESTRICT,
  entry_path text NOT NULL CHECK (entry_path IN ('complete_beginner','already_started','advanced')),
  status text NOT NULL CHECK (status IN ('active','complete','partial','cancelled')), seed text NOT NULL,
  started_at timestamptz NOT NULL, completed_at timestamptz, version integer NOT NULL CHECK (version>0)
);
CREATE UNIQUE INDEX uq_placement_active_run ON placement.runs(profile_id) WHERE status='active';
CREATE TABLE placement.item_instances (
  item_instance_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(item_instance_id)), run_id uuid NOT NULL REFERENCES placement.runs(run_id) ON DELETE RESTRICT,
  variant_revision_id uuid NOT NULL REFERENCES placement.variant_revisions(variant_revision_id) ON DELETE RESTRICT,
  ordinal integer NOT NULL CHECK (ordinal>0), frozen_payload jsonb NOT NULL CHECK (jsonb_typeof(frozen_payload)='object'),
  selected_reason jsonb NOT NULL CHECK (jsonb_typeof(selected_reason)='object'), presented_at timestamptz NOT NULL, UNIQUE(run_id,ordinal)
);
CREATE TABLE placement.responses (
  response_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(response_id)), run_id uuid NOT NULL REFERENCES placement.runs(run_id) ON DELETE RESTRICT,
  item_instance_id uuid NOT NULL REFERENCES placement.item_instances(item_instance_id) ON DELETE RESTRICT,
  idempotency_key text NOT NULL, response_payload jsonb NOT NULL CHECK (jsonb_typeof(response_payload)='object'),
  elapsed_seconds integer NOT NULL CHECK (elapsed_seconds>=0), submitted_at timestamptz NOT NULL, UNIQUE(run_id,idempotency_key), UNIQUE(item_instance_id)
);
CREATE TABLE placement.scoring_interpretations (
  interpretation_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(interpretation_id)), run_id uuid NOT NULL REFERENCES placement.runs(run_id) ON DELETE RESTRICT,
  response_id uuid NOT NULL REFERENCES placement.responses(response_id) ON DELETE RESTRICT, scorer_kind text NOT NULL,
  score numeric(6,5), confidence numeric(6,5) NOT NULL CHECK (confidence BETWEEN 0 AND 1), evaluable boolean NOT NULL,
  interpretation jsonb NOT NULL CHECK (jsonb_typeof(interpretation)='object'), provider_status text, created_at timestamptz NOT NULL,
  CHECK ((evaluable AND score BETWEEN 0 AND 1) OR (NOT evaluable AND score IS NULL))
);
CREATE TABLE placement.observations (
  observation_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(observation_id)), run_id uuid NOT NULL REFERENCES placement.runs(run_id) ON DELETE RESTRICT,
  interpretation_id uuid NOT NULL REFERENCES placement.scoring_interpretations(interpretation_id) ON DELETE RESTRICT,
  skill_ref text NOT NULL, level smallint NOT NULL CHECK (level BETWEEN 0 AND 8), score numeric(6,5), confidence numeric(6,5) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  independent boolean NOT NULL, created_at timestamptz NOT NULL
);
CREATE TABLE placement.contradictions (
  contradiction_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(contradiction_id)), run_id uuid NOT NULL REFERENCES placement.runs(run_id) ON DELETE RESTRICT,
  skill_ref text NOT NULL, status text NOT NULL CHECK (status IN ('open','resolved','expired')), detail jsonb NOT NULL CHECK (jsonb_typeof(detail)='object'), created_at timestamptz NOT NULL, resolved_at timestamptz
);
CREATE TABLE placement.skill_estimate_revisions (
  estimate_revision_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(estimate_revision_id)), run_id uuid NOT NULL REFERENCES placement.runs(run_id) ON DELETE RESTRICT,
  skill_ref text NOT NULL, revision_no integer NOT NULL CHECK (revision_no>0), status text NOT NULL,
  lower_bound smallint, probable_level smallint, upper_bound smallint, confidence numeric(6,5) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  independent_evidence_count integer NOT NULL CHECK (independent_evidence_count>=0), unresolved_contradiction_ids uuid[] NOT NULL,
  created_at timestamptz NOT NULL, UNIQUE(run_id,skill_ref,revision_no),
  CHECK ((lower_bound IS NULL AND probable_level IS NULL AND upper_bound IS NULL) OR (lower_bound BETWEEN 0 AND 8 AND probable_level BETWEEN lower_bound AND upper_bound AND upper_bound BETWEEN 0 AND 8))
);
CREATE TABLE placement.decisions (
  decision_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(decision_id)), run_id uuid NOT NULL REFERENCES placement.runs(run_id) ON DELETE RESTRICT,
  status text NOT NULL CHECK (status IN ('complete','partial')), result_snapshot jsonb NOT NULL CHECK (jsonb_typeof(result_snapshot)='object'),
  learner_choice text CHECK (learner_choice IS NULL OR learner_choice IN ('accept','start_easier','challenge','start_now')),
  idempotency_key text, created_at timestamptz NOT NULL, UNIQUE(run_id,idempotency_key)
);
CREATE TABLE placement.calibration_cycles (
  calibration_cycle_id uuid PRIMARY KEY CHECK (catalogue.is_uuid7(calibration_cycle_id)), profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  source_run_id uuid NOT NULL REFERENCES placement.runs(run_id) ON DELETE RESTRICT, phase text NOT NULL CHECK (phase IN ('P0','P1','P2','P3','complete')),
  completed_daily_runs integer NOT NULL CHECK (completed_daily_runs BETWEEN 0 AND 3), status text NOT NULL CHECK (status IN ('active','complete','cancelled')),
  created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL, UNIQUE(source_run_id)
);

DO $$ DECLARE n text; BEGIN FOREACH n IN ARRAY ARRAY['policy_revisions','item_blueprints','item_blueprint_revisions','variant_revisions','rubric_revisions','runs','item_instances','responses','scoring_interpretations','observations','skill_estimate_revisions','contradictions','decisions','calibration_cycles'] LOOP
  EXECUTE format('ALTER TABLE placement.%I ENABLE ROW LEVEL SECURITY',n); EXECUTE format('ALTER TABLE placement.%I FORCE ROW LEVEL SECURITY',n);
END LOOP; END $$;
DO $$ DECLARE n text; BEGIN FOREACH n IN ARRAY ARRAY['policy_revisions','item_blueprints','item_blueprint_revisions','variant_revisions','rubric_revisions'] LOOP
  EXECUTE format('CREATE POLICY %I ON placement.%I FOR SELECT USING (true)',n||'_read',n);
  EXECUTE format('CREATE POLICY %I ON placement.%I TO polyglot_migration USING (true) WITH CHECK (true)',n||'_migration',n);
END LOOP; END $$;
CREATE POLICY runs_owner ON placement.runs USING (placement.owns_profile(profile_id)) WITH CHECK (placement.owns_profile(profile_id));
CREATE POLICY calibration_owner ON placement.calibration_cycles USING (placement.owns_profile(profile_id)) WITH CHECK (placement.owns_profile(profile_id));
DO $$ DECLARE n text; BEGIN FOREACH n IN ARRAY ARRAY['item_instances','responses','scoring_interpretations','observations','skill_estimate_revisions','contradictions','decisions'] LOOP
  EXECUTE format('CREATE POLICY %I ON placement.%I USING (EXISTS (SELECT 1 FROM placement.runs r WHERE r.run_id=%I.run_id AND placement.owns_profile(r.profile_id))) WITH CHECK (EXISTS (SELECT 1 FROM placement.runs r WHERE r.run_id=%I.run_id AND placement.owns_profile(r.profile_id)))',n||'_owner',n,n,n);
END LOOP; END $$;
DO $$ DECLARE n text; BEGIN FOREACH n IN ARRAY ARRAY['runs','item_instances','responses','scoring_interpretations','observations','skill_estimate_revisions','contradictions','decisions','calibration_cycles'] LOOP
  EXECUTE format('CREATE POLICY %I ON placement.%I TO polyglot_migration USING (true) WITH CHECK (true)',n||'_migration',n);
END LOOP; END $$;
DO $$ DECLARE n text; BEGIN FOREACH n IN ARRAY ARRAY['item_instances','responses','scoring_interpretations','observations','skill_estimate_revisions','contradictions','decisions'] LOOP
  EXECUTE format('CREATE TRIGGER guard_%I BEFORE UPDATE OR DELETE ON placement.%I FOR EACH ROW EXECUTE FUNCTION placement.guard_append_only()',n,n);
END LOOP; END $$;
GRANT USAGE ON SCHEMA placement TO polyglot_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA placement TO polyglot_runtime;
GRANT INSERT,UPDATE ON placement.runs,placement.calibration_cycles TO polyglot_runtime;
GRANT INSERT ON placement.item_instances,placement.responses,placement.scoring_interpretations,placement.observations,placement.skill_estimate_revisions,placement.contradictions,placement.decisions TO polyglot_runtime;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA placement TO polyglot_migration;
REVOKE ALL ON ALL TABLES IN SCHEMA placement FROM PUBLIC;
"""


def upgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DDL))


def downgrade() -> None:
    op.get_bind().connection.run_async(
        lambda connection: _execute(connection, "DROP SCHEMA IF EXISTS placement CASCADE")
    )


async def _execute(connection: Connection, sql: str) -> None:
    await connection.execute(sql)
