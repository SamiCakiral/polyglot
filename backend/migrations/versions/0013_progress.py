"""Persist immutable learning evidence and reconstructible mastery projections.

Revision ID: 0013_progress
Revises: 0012_sprints
"""

# ruff: noqa: E501

from alembic import op
from asyncpg import Connection

revision = "0013_progress"
down_revision = "0012_sprints"
branch_labels = None
depends_on = None


PROGRESS_DDL = r"""
CREATE SCHEMA progress AUTHORIZATION polyglot_migration;

CREATE FUNCTION progress.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
  SELECT value IS NOT NULL AND (get_byte(uuid_send(value),6) >> 4) = 7
$function$;
CREATE FUNCTION progress.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE AS $function$
  SELECT NULLIF(current_setting('app.user_id',true),'')::uuid
$function$;
CREATE FUNCTION progress.owns_profile(value uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,language_profiles,progress AS $function$
  SELECT EXISTS (
    SELECT 1 FROM language_profiles.learner_language_profiles profile
    WHERE profile.profile_id=value AND profile.account_id=progress.current_user_id()
      AND profile.status <> 'deleted'
  )
$function$;
CREATE FUNCTION progress.guard_append_only() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
  RAISE EXCEPTION 'progress fact is append-only' USING ERRCODE='55000';
END
$function$;

ALTER TABLE planning.session_plan_blocks
  ADD COLUMN target_refs varchar(240)[] NOT NULL DEFAULT ARRAY[]::varchar[];
ALTER TABLE planning.session_plan_blocks
  ALTER COLUMN target_refs DROP DEFAULT;

CREATE TABLE progress.policy_revisions (
  policy_revision_id uuid PRIMARY KEY,
  policy_code varchar(80) NOT NULL UNIQUE,
  config jsonb NOT NULL,
  policy_fingerprint char(64) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT ck_progress_policy_uuid7 CHECK (progress.is_uuid7(policy_revision_id)),
  CONSTRAINT ck_progress_policy_shape CHECK (
    jsonb_typeof(config)='object' AND policy_fingerprint ~ '^[0-9a-f]{64}$'
  )
);
INSERT INTO progress.policy_revisions
  (policy_revision_id,policy_code,config,policy_fingerprint,created_at) VALUES
  ('019fab00-0000-7000-8000-000000000001','MASTERY_V0',
   '{"prior_mass":"2.0","prior_score":"0.50","source_weights":{"assessment":"1.00","daily_sprint":"0.90","foundations":"0.90","free_practice":"0.75","diagnostic":"0.70","declaration":"0.00","exposure":"0.00"}}',
   'a093e8e172c0b9dfe8bbbc5ec89b8b4254e91de2d60d3ae9746387a6f479d9bf',
   '2026-08-10T00:00:00Z');

CREATE TABLE progress.learning_observations (
  observation_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  attempt_id uuid NOT NULL,
  correction_id uuid NOT NULL,
  target_type varchar(40) NOT NULL,
  target_id varchar(240) NOT NULL,
  facet_key varchar(160) NOT NULL,
  modality varchar(16) NOT NULL,
  operation varchar(24) NOT NULL,
  role varchar(16) NOT NULL,
  result varchar(24) NOT NULL,
  observation_value numeric(8,7) NOT NULL,
  correction_confidence numeric(5,4) NOT NULL,
  target_coverage numeric(5,4) NOT NULL,
  help_level varchar(4) NOT NULL,
  opportunity_id uuid NOT NULL,
  pedagogical_session_id varchar(240) NOT NULL,
  context_family_id varchar(240) NOT NULL,
  source_type varchar(24) NOT NULL,
  delay_band varchar(32) NOT NULL,
  transfer boolean NOT NULL,
  direct boolean NOT NULL,
  independence_weight numeric(5,4) NOT NULL,
  policy_revision_id uuid NOT NULL REFERENCES progress.policy_revisions(policy_revision_id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL,
  invalidated_at timestamptz,
  replacement_observation_id uuid,
  invalidation_reason varchar(120),
  CONSTRAINT fk_progress_observation_attempt FOREIGN KEY (profile_id,attempt_id)
    REFERENCES exercises.exercise_attempts(profile_id,attempt_id) ON DELETE RESTRICT,
  CONSTRAINT fk_progress_observation_correction FOREIGN KEY (profile_id,correction_id)
    REFERENCES exercises.exercise_corrections(profile_id,correction_id) ON DELETE RESTRICT,
  CONSTRAINT uq_progress_observation_profile UNIQUE (profile_id,observation_id),
  CONSTRAINT ck_progress_observation_uuid7 CHECK (
    progress.is_uuid7(observation_id) AND progress.is_uuid7(profile_id)
    AND progress.is_uuid7(attempt_id) AND progress.is_uuid7(correction_id)
    AND progress.is_uuid7(opportunity_id) AND progress.is_uuid7(policy_revision_id)
    AND (replacement_observation_id IS NULL OR progress.is_uuid7(replacement_observation_id))
  ),
  CONSTRAINT ck_progress_observation_shape CHECK (
    target_type IN ('skill','lexical_sense','lexical_form','grammar_structure','grammar_pattern','pronunciation_target')
    AND length(target_id)>=1 AND length(facet_key)>=1
    AND modality IN ('reading','listening','writing','speaking')
    AND operation IN ('recognize','recall','discriminate','transform','produce','interact','repair','transfer')
    AND role IN ('primary','secondary','support','distractor')
    AND result IN ('success','partial_success','failure','inconclusive')
    AND observation_value BETWEEN -1 AND 1
    AND correction_confidence BETWEEN 0 AND 1 AND target_coverage BETWEEN 0 AND 1
    AND help_level IN ('h0','h1','h2','h3','h4')
    AND source_type IN ('assessment','daily_sprint','foundations','free_practice','diagnostic','declaration','exposure')
    AND delay_band IN ('same_session','one_to_six_days','seven_days_or_more')
    AND independence_weight BETWEEN 0 AND 1
    AND ((invalidated_at IS NULL AND replacement_observation_id IS NULL AND invalidation_reason IS NULL)
      OR (invalidated_at IS NOT NULL AND invalidation_reason IS NOT NULL))
  )
);

CREATE TABLE progress.learning_evidence (
  evidence_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL,
  observation_id uuid NOT NULL,
  target_type varchar(40) NOT NULL,
  target_id varchar(240) NOT NULL,
  facet_key varchar(160) NOT NULL,
  modality varchar(16) NOT NULL,
  operation varchar(24) NOT NULL,
  evidence_score numeric(8,7) NOT NULL,
  evidence_mass numeric(8,7) NOT NULL,
  source_weight numeric(5,4) NOT NULL,
  independence_weight numeric(5,4) NOT NULL,
  opportunity_id uuid NOT NULL,
  pedagogical_session_id varchar(240) NOT NULL,
  context_family_id varchar(240) NOT NULL,
  delay_band varchar(32) NOT NULL,
  eligible boolean NOT NULL,
  direct boolean NOT NULL,
  transfer boolean NOT NULL,
  ineligibility_reasons varchar(120)[] NOT NULL,
  policy_revision_id uuid NOT NULL REFERENCES progress.policy_revisions(policy_revision_id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL,
  invalidated_at timestamptz,
  replacement_evidence_id uuid,
  CONSTRAINT fk_progress_evidence_observation FOREIGN KEY (profile_id,observation_id)
    REFERENCES progress.learning_observations(profile_id,observation_id) ON DELETE RESTRICT,
  CONSTRAINT uq_progress_evidence_observation UNIQUE (observation_id,policy_revision_id),
  CONSTRAINT uq_progress_evidence_profile UNIQUE (profile_id,evidence_id),
  CONSTRAINT ck_progress_evidence_uuid7 CHECK (
    progress.is_uuid7(evidence_id) AND progress.is_uuid7(profile_id)
    AND progress.is_uuid7(observation_id) AND progress.is_uuid7(opportunity_id)
    AND progress.is_uuid7(policy_revision_id)
    AND (replacement_evidence_id IS NULL OR progress.is_uuid7(replacement_evidence_id))
  ),
  CONSTRAINT ck_progress_evidence_shape CHECK (
    evidence_score BETWEEN 0 AND 1 AND evidence_mass BETWEEN 0 AND 1
    AND source_weight BETWEEN 0 AND 1 AND independence_weight BETWEEN 0 AND 1
    AND abs(evidence_mass - least(1,source_weight*independence_weight)) < 0.000001
    AND modality IN ('reading','listening','writing','speaking')
    AND delay_band IN ('same_session','one_to_six_days','seven_days_or_more')
    AND ((eligible AND evidence_mass > 0 AND cardinality(ineligibility_reasons)=0)
      OR (NOT eligible AND evidence_mass=0 AND cardinality(ineligibility_reasons)>0))
  )
);

CREATE TABLE progress.fact_invalidations (
  invalidation_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  fact_type varchar(24) NOT NULL,
  fact_id uuid NOT NULL,
  replacement_fact_id uuid,
  reason_code varchar(120) NOT NULL,
  invalidated_at timestamptz NOT NULL,
  source_event_id uuid NOT NULL REFERENCES platform.domain_events(event_id) ON DELETE RESTRICT,
  CONSTRAINT uq_progress_fact_invalidation UNIQUE (fact_type,fact_id),
  CONSTRAINT ck_progress_fact_invalidation_uuid7 CHECK (
    progress.is_uuid7(invalidation_id) AND progress.is_uuid7(profile_id)
    AND progress.is_uuid7(fact_id) AND progress.is_uuid7(source_event_id)
    AND (replacement_fact_id IS NULL OR progress.is_uuid7(replacement_fact_id))
  ),
  CONSTRAINT ck_progress_fact_invalidation_shape CHECK (
    fact_type IN ('observation','evidence') AND length(reason_code)>=1
  )
);

CREATE TABLE progress.mastery_projections (
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  target_type varchar(40) NOT NULL,
  target_id varchar(240) NOT NULL,
  facet_key varchar(160) NOT NULL,
  modality varchar(16) NOT NULL,
  operation varchar(24) NOT NULL,
  status varchar(24) NOT NULL,
  mastery_base numeric(8,7) NOT NULL,
  mastery_current numeric(8,7) NOT NULL,
  confidence numeric(8,7) NOT NULL,
  freshness numeric(8,7) NOT NULL,
  effective_mass numeric(12,7) NOT NULL,
  success_count integer NOT NULL,
  failure_count integer NOT NULL,
  context_count integer NOT NULL,
  session_count integer NOT NULL,
  delay_band_count integer NOT NULL,
  transfer_count integer NOT NULL,
  last_evidence_at timestamptz,
  next_verification_at timestamptz,
  policy_revision_id uuid NOT NULL REFERENCES progress.policy_revisions(policy_revision_id) ON DELETE RESTRICT,
  projection_version integer NOT NULL,
  last_event_id uuid,
  projection_fingerprint char(64) NOT NULL,
  computed_at timestamptz NOT NULL,
  PRIMARY KEY (profile_id,target_type,target_id,facet_key,modality,operation),
  CONSTRAINT ck_progress_mastery_uuid7 CHECK (
    progress.is_uuid7(profile_id) AND progress.is_uuid7(policy_revision_id)
    AND (last_event_id IS NULL OR progress.is_uuid7(last_event_id))
  ),
  CONSTRAINT ck_progress_mastery_shape CHECK (
    status IN ('non_observed','discovered','in_progress','reliable','mastered','review_due','not_evaluable')
    AND mastery_base BETWEEN 0 AND 1 AND mastery_current BETWEEN 0 AND 1
    AND confidence BETWEEN 0 AND 1 AND freshness BETWEEN 0 AND 1 AND effective_mass >= 0
    AND success_count>=0 AND failure_count>=0 AND context_count>=0 AND session_count>=0
    AND delay_band_count>=0 AND transfer_count>=0 AND projection_version>=1
    AND projection_fingerprint ~ '^[0-9a-f]{64}$'
  )
);
CREATE UNIQUE INDEX uq_progress_mastery_facet ON progress.mastery_projections
  (profile_id,target_type,target_id,facet_key,modality,operation);

CREATE TABLE progress.personal_sense_facets (
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  sense_id uuid NOT NULL,
  modality varchar(16) NOT NULL,
  operation varchar(24) NOT NULL,
  direction varchar(40) NOT NULL,
  mastery_status varchar(24) NOT NULL,
  score numeric(8,7) NOT NULL,
  confidence numeric(8,7) NOT NULL,
  freshness numeric(8,7) NOT NULL,
  evidence_count integer NOT NULL,
  contradiction_count integer NOT NULL,
  last_activity_at timestamptz,
  next_verification_at timestamptz,
  projection_version integer NOT NULL,
  policy_revision_id uuid NOT NULL REFERENCES progress.policy_revisions(policy_revision_id) ON DELETE RESTRICT,
  last_event_id uuid,
  PRIMARY KEY (profile_id,sense_id,modality,operation,direction),
  CONSTRAINT ck_progress_sense_facet_uuid7 CHECK (
    progress.is_uuid7(profile_id) AND progress.is_uuid7(sense_id)
    AND progress.is_uuid7(policy_revision_id)
    AND (last_event_id IS NULL OR progress.is_uuid7(last_event_id))
  ),
  CONSTRAINT ck_progress_sense_facet_shape CHECK (
    modality IN ('reading','listening','writing','speaking')
    AND mastery_status IN ('non_observed','discovered','in_progress','reliable','mastered','review_due','not_evaluable')
    AND score BETWEEN 0 AND 1 AND confidence BETWEEN 0 AND 1 AND freshness BETWEEN 0 AND 1
    AND evidence_count>=0 AND contradiction_count>=0 AND projection_version>=1
  )
);

CREATE TABLE progress.learning_needs (
  need_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  target_type varchar(40) NOT NULL,
  target_id varchar(240) NOT NULL,
  facet_key varchar(160) NOT NULL,
  status varchar(16) NOT NULL,
  urgency numeric(5,4) NOT NULL,
  opened_at timestamptz NOT NULL,
  planned_at timestamptz,
  resolved_at timestamptz,
  superseded_by_need_id uuid,
  resolution_policy_revision_id uuid REFERENCES progress.policy_revisions(policy_revision_id) ON DELETE RESTRICT,
  resolution_evidence_id uuid,
  version integer NOT NULL,
  CONSTRAINT uq_progress_need_profile UNIQUE (profile_id,need_id),
  CONSTRAINT ck_progress_need_uuid7 CHECK (
    progress.is_uuid7(need_id) AND progress.is_uuid7(profile_id)
    AND (superseded_by_need_id IS NULL OR progress.is_uuid7(superseded_by_need_id))
    AND (resolution_policy_revision_id IS NULL OR progress.is_uuid7(resolution_policy_revision_id))
    AND (resolution_evidence_id IS NULL OR progress.is_uuid7(resolution_evidence_id))
  ),
  CONSTRAINT ck_progress_need_shape CHECK (
    status IN ('open','planned','resolved','superseded') AND urgency BETWEEN 0 AND 1
    AND version>=1 AND (planned_at IS NULL OR planned_at>=opened_at)
    AND ((status='resolved')=(resolved_at IS NOT NULL AND resolution_policy_revision_id IS NOT NULL AND resolution_evidence_id IS NOT NULL))
    AND ((status='superseded')=(superseded_by_need_id IS NOT NULL))
  )
);
CREATE UNIQUE INDEX uq_progress_active_need ON progress.learning_needs
  (profile_id,target_type,target_id,facet_key) WHERE status IN ('open','planned');

CREATE TABLE progress.learning_need_causes (
  cause_id uuid PRIMARY KEY,
  need_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  cause_type varchar(80) NOT NULL,
  source_fact_id uuid NOT NULL,
  opened_at timestamptz NOT NULL,
  CONSTRAINT fk_progress_need_cause FOREIGN KEY (profile_id,need_id)
    REFERENCES progress.learning_needs(profile_id,need_id) ON DELETE RESTRICT,
  CONSTRAINT uq_progress_need_cause UNIQUE (need_id,cause_type,source_fact_id),
  CONSTRAINT ck_progress_need_cause_uuid7 CHECK (
    progress.is_uuid7(cause_id) AND progress.is_uuid7(need_id)
    AND progress.is_uuid7(profile_id) AND progress.is_uuid7(source_fact_id)
  )
);

CREATE TABLE progress.recommendations (
  recommendation_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  target_type varchar(40) NOT NULL,
  target_id varchar(240) NOT NULL,
  facet_key varchar(160) NOT NULL,
  need_id uuid,
  reason_code varchar(120) NOT NULL,
  reason_params jsonb NOT NULL,
  missing_evidence_spec jsonb NOT NULL,
  proposed_activity jsonb NOT NULL,
  priority numeric(8,7) NOT NULL,
  urgency numeric(5,4) NOT NULL,
  estimated_duration_ms integer NOT NULL,
  policy_revision_id uuid NOT NULL REFERENCES progress.policy_revisions(policy_revision_id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL,
  expires_at timestamptz,
  dismissed_at timestamptz,
  dismiss_reason varchar(120),
  CONSTRAINT ck_progress_recommendation_uuid7 CHECK (
    progress.is_uuid7(recommendation_id) AND progress.is_uuid7(profile_id)
    AND (need_id IS NULL OR progress.is_uuid7(need_id)) AND progress.is_uuid7(policy_revision_id)
  ),
  CONSTRAINT ck_progress_recommendation_shape CHECK (
    jsonb_typeof(reason_params)='object' AND jsonb_typeof(missing_evidence_spec)='object'
    AND jsonb_typeof(proposed_activity)='object' AND priority BETWEEN 0 AND 1
    AND urgency BETWEEN 0 AND 1 AND estimated_duration_ms>0
    AND (expires_at IS NULL OR expires_at>created_at)
    AND ((dismissed_at IS NULL AND dismiss_reason IS NULL) OR (dismissed_at IS NOT NULL AND dismiss_reason IS NOT NULL))
  )
);

CREATE TABLE progress.consumer_cursors (
  consumer_code varchar(120) NOT NULL,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  last_event_id uuid,
  last_occurred_at timestamptz,
  projection_fingerprint char(64) NOT NULL,
  version integer NOT NULL,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (consumer_code,profile_id),
  CONSTRAINT ck_progress_cursor_uuid7 CHECK (
    progress.is_uuid7(profile_id) AND (last_event_id IS NULL OR progress.is_uuid7(last_event_id))
  ),
  CONSTRAINT ck_progress_cursor_shape CHECK (
    length(consumer_code)>=1 AND projection_fingerprint ~ '^[0-9a-f]{64}$' AND version>=1
  )
);

CREATE INDEX ix_progress_observation_target ON progress.learning_observations
  (profile_id,target_type,target_id,facet_key,modality,created_at);
CREATE INDEX ix_progress_evidence_target ON progress.learning_evidence
  (profile_id,target_type,target_id,facet_key,modality,created_at);
CREATE INDEX ix_progress_opportunity ON progress.learning_evidence
  (profile_id,opportunity_id,target_type,target_id,facet_key,modality);
CREATE INDEX ix_progress_recommendations_active ON progress.recommendations
  (profile_id,priority DESC,created_at) WHERE dismissed_at IS NULL;

DO $guards$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'policy_revisions','learning_observations','learning_evidence',
    'fact_invalidations','learning_need_causes'
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON progress.%I FOR EACH ROW EXECUTE FUNCTION progress.guard_append_only()',
      'guard_' || table_name,table_name
    );
  END LOOP;
END
$guards$;

ALTER TABLE progress.policy_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE progress.policy_revisions FORCE ROW LEVEL SECURITY;
CREATE POLICY policy_revisions_read ON progress.policy_revisions FOR SELECT USING (true);
DO $rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'learning_observations','learning_evidence','fact_invalidations','mastery_projections',
    'personal_sense_facets','learning_needs','learning_need_causes','recommendations','consumer_cursors'
  ] LOOP
    EXECUTE format('ALTER TABLE progress.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE progress.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY %I ON progress.%I USING (progress.owns_profile(profile_id)) WITH CHECK (progress.owns_profile(profile_id))',
      table_name || '_owner',table_name
    );
  END LOOP;
END
$rls$;

GRANT USAGE ON SCHEMA progress TO polyglot_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA progress TO polyglot_runtime;
REVOKE DELETE ON ALL TABLES IN SCHEMA progress FROM polyglot_runtime;
GRANT INSERT ON progress.learning_observations,progress.learning_evidence,
  progress.fact_invalidations,progress.learning_need_causes TO polyglot_runtime;
GRANT SELECT,INSERT,UPDATE,DELETE ON progress.mastery_projections,progress.personal_sense_facets,
  progress.learning_needs,progress.recommendations,progress.consumer_cursors TO polyglot_runtime;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA progress TO polyglot_migration;
REVOKE ALL ON ALL TABLES IN SCHEMA progress FROM PUBLIC;
ALTER FUNCTION progress.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION progress.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION progress.owns_profile(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION progress.guard_append_only() OWNER TO polyglot_migration;
DO $owners$ DECLARE item record; BEGIN
  FOR item IN SELECT tablename FROM pg_tables WHERE schemaname='progress' LOOP
    EXECUTE format('ALTER TABLE progress.%I OWNER TO polyglot_migration',item.tablename);
  END LOOP;
END $owners$;
"""


DROP_DDL = r"""
DROP SCHEMA IF EXISTS progress CASCADE;
ALTER TABLE IF EXISTS planning.session_plan_blocks DROP COLUMN IF EXISTS target_refs;
"""


async def _execute(connection: Connection, sql: str) -> None:
    await connection.execute(sql)


def upgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, PROGRESS_DDL))


def downgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DROP_DDL))
