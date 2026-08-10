"""Create persistent exercise definitions, attempts, and corrections.

Revision ID: 0009_exercises
Revises: 0008_exchange
"""

# ruff: noqa: E501

from alembic import op
from asyncpg import Connection

revision = "0009_exercises"
down_revision = "0008_exchange"
branch_labels = None
depends_on = None


EXERCISES_DDL = r"""
CREATE SCHEMA exercises AUTHORIZATION polyglot_migration;

CREATE FUNCTION exercises.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
  SELECT value IS NOT NULL AND (get_byte(uuid_send(value),6) >> 4) = 7
$function$;
CREATE FUNCTION exercises.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE AS $function$
  SELECT NULLIF(current_setting('app.user_id',true),'')::uuid
$function$;
CREATE FUNCTION exercises.owns_profile(value uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,language_profiles,exercises AS $function$
  SELECT EXISTS (
    SELECT 1 FROM language_profiles.learner_language_profiles profile
    WHERE profile.profile_id=value AND profile.account_id=exercises.current_user_id()
      AND profile.status <> 'deleted'
  )
$function$;
CREATE FUNCTION exercises.has_role(roles text[]) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,identity,exercises AS $function$
  SELECT EXISTS (
    SELECT 1 FROM identity.account_roles role_grant
    WHERE role_grant.account_id=exercises.current_user_id()
      AND role_grant.role=ANY(roles) AND role_grant.revoked_at IS NULL
  )
$function$;
CREATE FUNCTION exercises.guard_append_only() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
  RAISE EXCEPTION 'exercise fact is append-only' USING ERRCODE='55000';
END
$function$;
CREATE FUNCTION exercises.guard_attempt_answer() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
  IF OLD.raw_answer IS NOT NULL AND ROW(
    NEW.answer_kind,NEW.raw_answer,NEW.input_method,NEW.input_locale,
    NEW.submitted_at,NEW.normalization_policy_revision_id,NEW.normalized_answer,
    NEW.idempotency_key,NEW.request_fingerprint
  ) IS DISTINCT FROM ROW(
    OLD.answer_kind,OLD.raw_answer,OLD.input_method,OLD.input_locale,
    OLD.submitted_at,OLD.normalization_policy_revision_id,OLD.normalized_answer,
    OLD.idempotency_key,OLD.request_fingerprint
  ) THEN
    RAISE EXCEPTION 'submitted exercise answer is immutable' USING ERRCODE='55000';
  END IF;
  RETURN NEW;
END
$function$;
CREATE FUNCTION exercises.guard_correction_current() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
  IF TG_OP='UPDATE' AND OLD.is_current AND NOT NEW.is_current
     AND ROW(
       NEW.correction_id,NEW.attempt_id,NEW.profile_id,NEW.revision_no,NEW.verdict,
       NEW.confidence,NEW.target_coverage,NEW.strategy,NEW.rubric_revision_id,
       NEW.proposed_answer,NEW.alternatives,NEW.explanation,NEW.error_codes,
       NEW.criterion_scores,NEW.provenance_id,NEW.requires_review,
       NEW.supersedes_correction_id,NEW.result_payload,NEW.created_at
     ) IS NOT DISTINCT FROM ROW(
       OLD.correction_id,OLD.attempt_id,OLD.profile_id,OLD.revision_no,OLD.verdict,
       OLD.confidence,OLD.target_coverage,OLD.strategy,OLD.rubric_revision_id,
       OLD.proposed_answer,OLD.alternatives,OLD.explanation,OLD.error_codes,
       OLD.criterion_scores,OLD.provenance_id,OLD.requires_review,
       OLD.supersedes_correction_id,OLD.result_payload,OLD.created_at
     ) THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'exercise correction is immutable except current closure' USING ERRCODE='55000';
END
$function$;

CREATE TABLE exercises.exercise_definitions (
  definition_id uuid PRIMARY KEY,
  definition_code varchar(120) NOT NULL UNIQUE,
  current_revision_id uuid,
  status varchar(24) NOT NULL,
  version integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT ck_exercise_definition_uuid7 CHECK (exercises.is_uuid7(definition_id)),
  CONSTRAINT ck_exercise_definition_shape CHECK (
    definition_code ~ '^[a-z][a-z0-9_.-]{2,119}$'
    AND status IN ('draft','published','retired') AND version >= 1 AND updated_at >= created_at
  )
);

CREATE TABLE exercises.exercise_definition_revisions (
  definition_revision_id uuid PRIMARY KEY,
  definition_id uuid NOT NULL REFERENCES exercises.exercise_definitions(definition_id) ON DELETE RESTRICT,
  revision_no integer NOT NULL,
  schema_version integer NOT NULL,
  primitive_id varchar(40) NOT NULL,
  status varchar(24) NOT NULL,
  response_kinds jsonb NOT NULL,
  language_certification_ids jsonb NOT NULL,
  modes jsonb NOT NULL,
  target_weights jsonb NOT NULL,
  response_contract jsonb NOT NULL,
  stimulus_contract jsonb NOT NULL,
  target_contract jsonb NOT NULL,
  difficulty_profile jsonb NOT NULL,
  prerequisite_skill_revision_ids jsonb NOT NULL,
  correction_policy_id varchar(160) NOT NULL,
  hint_policy_id varchar(160) NOT NULL,
  observation_policy_id varchar(160) NOT NULL,
  accessibility_features jsonb NOT NULL,
  min_duration_ms integer NOT NULL,
  p50_duration_ms integer NOT NULL,
  p80_duration_ms integer NOT NULL,
  example_revision_ids jsonb NOT NULL,
  provenance_id uuid NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_exercise_definition_revision UNIQUE (definition_id,revision_no),
  CONSTRAINT uq_exercise_definition_revision_owner UNIQUE (definition_id,definition_revision_id),
  CONSTRAINT ck_exercise_definition_revision_uuid7 CHECK (
    exercises.is_uuid7(definition_revision_id) AND exercises.is_uuid7(definition_id)
    AND exercises.is_uuid7(provenance_id)
  ),
  CONSTRAINT ck_exercise_definition_revision_shape CHECK (
    revision_no >= 1 AND schema_version >= 1
    AND status IN ('draft','validated','approved','published','retired','rejected')
    AND primitive_id ~ '^EX-[A-Z]+-[0-9]{2}$'
    AND jsonb_typeof(response_kinds)='array' AND jsonb_array_length(response_kinds) >= 1
    AND jsonb_typeof(language_certification_ids)='array'
    AND jsonb_typeof(modes)='array' AND jsonb_typeof(target_weights)='array'
    AND jsonb_typeof(accessibility_features)='array'
    AND jsonb_typeof(response_contract)='object'
    AND jsonb_typeof(stimulus_contract)='object'
    AND jsonb_typeof(target_contract)='array'
    AND jsonb_typeof(difficulty_profile)='object'
    AND jsonb_typeof(prerequisite_skill_revision_ids)='array'
    AND jsonb_typeof(example_revision_ids)='array'
    AND min_duration_ms >= 0 AND p50_duration_ms >= min_duration_ms
    AND p80_duration_ms >= p50_duration_ms
  )
);
ALTER TABLE exercises.exercise_definitions ADD CONSTRAINT fk_exercise_definition_current
  FOREIGN KEY (definition_id,current_revision_id)
  REFERENCES exercises.exercise_definition_revisions(definition_id,definition_revision_id)
  ON DELETE RESTRICT;

CREATE TABLE exercises.exercise_language_certifications (
  certification_id uuid PRIMARY KEY,
  definition_revision_id uuid NOT NULL REFERENCES exercises.exercise_definition_revisions(definition_revision_id) ON DELETE RESTRICT,
  language_pack_revision_id uuid NOT NULL,
  status varchar(24) NOT NULL,
  validated_at timestamptz,
  validator_revision_ids jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_exercise_language_certification UNIQUE (definition_revision_id,language_pack_revision_id),
  CONSTRAINT ck_exercise_language_certification_uuid7 CHECK (
    exercises.is_uuid7(certification_id) AND exercises.is_uuid7(definition_revision_id)
    AND exercises.is_uuid7(language_pack_revision_id)
  ),
  CONSTRAINT ck_exercise_language_certification_shape CHECK (
    status IN ('draft','validated','rejected','retired')
    AND jsonb_typeof(validator_revision_ids)='array'
    AND ((status='validated') = (validated_at IS NOT NULL))
  )
);

CREATE TABLE exercises.exercise_instances (
  instance_id uuid PRIMARY KEY,
  standalone_profile_id uuid REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  definition_revision_id uuid NOT NULL REFERENCES exercises.exercise_definition_revisions(definition_revision_id) ON DELETE RESTRICT,
  language_pack_revision_id uuid NOT NULL,
  seed bigint NOT NULL,
  stimulus_revision_ids jsonb NOT NULL,
  session_plan_revision_id uuid,
  target_bindings jsonb NOT NULL,
  lexical_bindings jsonb NOT NULL,
  grammar_bindings jsonb NOT NULL,
  accepted_answer_set_revision_id uuid,
  rubric_revision_id uuid,
  available_from timestamptz,
  expires_at timestamptz,
  provenance_id uuid NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT ck_exercise_instance_uuid7 CHECK (
    exercises.is_uuid7(instance_id)
    AND (standalone_profile_id IS NULL OR exercises.is_uuid7(standalone_profile_id))
    AND exercises.is_uuid7(definition_revision_id)
    AND exercises.is_uuid7(language_pack_revision_id)
    AND (session_plan_revision_id IS NULL OR exercises.is_uuid7(session_plan_revision_id))
    AND (accepted_answer_set_revision_id IS NULL OR exercises.is_uuid7(accepted_answer_set_revision_id))
    AND (rubric_revision_id IS NULL OR exercises.is_uuid7(rubric_revision_id))
    AND exercises.is_uuid7(provenance_id)
  ),
  CONSTRAINT ck_exercise_instance_shape CHECK (
    jsonb_typeof(stimulus_revision_ids)='array'
    AND jsonb_array_length(stimulus_revision_ids) >= 1
    AND jsonb_typeof(target_bindings)='array'
    AND jsonb_typeof(lexical_bindings)='array'
    AND jsonb_typeof(grammar_bindings)='array'
    AND (expires_at IS NULL OR available_from IS NULL OR expires_at > available_from)
    AND ((session_plan_revision_id IS NULL) = (standalone_profile_id IS NOT NULL))
  )
);

CREATE TABLE exercises.exercise_attempts (
  attempt_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  instance_id uuid NOT NULL REFERENCES exercises.exercise_instances(instance_id) ON DELETE RESTRICT,
  attempt_no integer NOT NULL,
  status varchar(24) NOT NULL,
  terminal_reason varchar(40) NOT NULL,
  answer_kind varchar(32),
  raw_answer jsonb,
  input_method varchar(80),
  input_locale varchar(40),
  submitted_at timestamptz,
  active_duration_ms bigint NOT NULL DEFAULT 0,
  normalization_policy_revision_id uuid,
  normalized_answer jsonb,
  idempotency_key varchar(200),
  request_fingerprint char(64),
  corrected_at timestamptz,
  aggregate_payload jsonb NOT NULL,
  version integer NOT NULL,
  started_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  correction_reviewed_at timestamptz,
  CONSTRAINT uq_exercise_attempt_no UNIQUE (instance_id,profile_id,attempt_no),
  CONSTRAINT uq_exercise_attempt_profile UNIQUE (profile_id,attempt_id),
  CONSTRAINT ck_exercise_attempt_uuid7 CHECK (
    exercises.is_uuid7(attempt_id) AND exercises.is_uuid7(profile_id)
    AND exercises.is_uuid7(instance_id)
    AND (normalization_policy_revision_id IS NULL OR exercises.is_uuid7(normalization_policy_revision_id))
  ),
  CONSTRAINT ck_exercise_attempt_shape CHECK (
    attempt_no >= 1 AND version >= 1 AND active_duration_ms >= 0 AND updated_at >= started_at
    AND status IN ('draft','submitted','correcting','corrected','not_evaluable')
    AND (answer_kind IS NULL OR answer_kind IN (
      'acknowledgement','single_choice','graded_choice','selection','pairing','grouping',
      'ordered_items','cells','spans','tokens','text','short_text','audio_ref','self_grade',
      'self_assessment','no_answer'
    ))
    AND terminal_reason IN ('none','correction_unavailable','correction_ambiguous','answer_invalid','user_cancelled')
    AND ((status='not_evaluable') = (terminal_reason <> 'none'))
    AND (request_fingerprint IS NULL OR request_fingerprint ~ '^[0-9a-f]{64}$')
    AND ((raw_answer IS NULL AND answer_kind IS NULL AND input_method IS NULL AND input_locale IS NULL AND submitted_at IS NULL)
      OR (raw_answer IS NOT NULL AND answer_kind IS NOT NULL AND input_method IS NOT NULL AND input_locale IS NOT NULL
        AND submitted_at IS NOT NULL AND idempotency_key IS NOT NULL AND request_fingerprint IS NOT NULL))
    AND (normalized_answer IS NULL OR normalization_policy_revision_id IS NOT NULL)
    AND (corrected_at IS NULL OR status IN ('corrected','not_evaluable'))
  )
);
CREATE UNIQUE INDEX uq_exercise_open_attempt
  ON exercises.exercise_attempts(profile_id,instance_id)
  WHERE status IN ('draft','submitted','correcting');

CREATE TABLE exercises.attempt_drafts (
  attempt_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL,
  draft_payload jsonb NOT NULL,
  version integer NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT fk_attempt_draft_attempt FOREIGN KEY (profile_id,attempt_id)
    REFERENCES exercises.exercise_attempts(profile_id,attempt_id) ON DELETE RESTRICT,
  CONSTRAINT ck_attempt_draft_uuid7 CHECK (
    exercises.is_uuid7(attempt_id) AND exercises.is_uuid7(profile_id)
  ),
  CONSTRAINT ck_attempt_draft_shape CHECK (jsonb_typeof(draft_payload)='object' AND version >= 1)
);

CREATE TABLE exercises.exercise_hint_uses (
  hint_use_id uuid PRIMARY KEY,
  attempt_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  sequence_no integer NOT NULL,
  hint_definition_revision_id uuid NOT NULL,
  level varchar(4) NOT NULL,
  reason text NOT NULL,
  answer_state_checksum char(64) NOT NULL,
  effect_policy_revision_id uuid NOT NULL,
  shown_at timestamptz NOT NULL,
  CONSTRAINT fk_exercise_hint_attempt FOREIGN KEY (profile_id,attempt_id)
    REFERENCES exercises.exercise_attempts(profile_id,attempt_id) ON DELETE RESTRICT,
  CONSTRAINT uq_exercise_hint_sequence UNIQUE (attempt_id,sequence_no),
  CONSTRAINT ck_exercise_hint_uuid7 CHECK (
    exercises.is_uuid7(hint_use_id) AND exercises.is_uuid7(attempt_id)
    AND exercises.is_uuid7(profile_id)
    AND exercises.is_uuid7(hint_definition_revision_id)
    AND exercises.is_uuid7(effect_policy_revision_id)
  ),
  CONSTRAINT ck_exercise_hint_shape CHECK (
    sequence_no >= 1 AND level IN ('h0','h1','h2','h3','h4') AND length(reason) >= 1
    AND answer_state_checksum ~ '^[0-9a-f]{64}$'
  )
);

CREATE TABLE exercises.attempt_media_events (
  media_event_id uuid PRIMARY KEY,
  attempt_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  sequence_no integer NOT NULL,
  media_revision_id uuid NOT NULL,
  event_type varchar(24) NOT NULL,
  position_ms bigint,
  playback_rate numeric(5,2),
  segment_id uuid,
  occurred_at timestamptz NOT NULL,
  CONSTRAINT fk_attempt_media_event_attempt FOREIGN KEY (profile_id,attempt_id)
    REFERENCES exercises.exercise_attempts(profile_id,attempt_id) ON DELETE RESTRICT,
  CONSTRAINT uq_attempt_media_event_sequence UNIQUE (attempt_id,sequence_no),
  CONSTRAINT ck_attempt_media_event_uuid7 CHECK (
    exercises.is_uuid7(media_event_id) AND exercises.is_uuid7(attempt_id)
    AND exercises.is_uuid7(profile_id) AND exercises.is_uuid7(media_revision_id)
    AND (segment_id IS NULL OR exercises.is_uuid7(segment_id))
  ),
  CONSTRAINT ck_attempt_media_event_shape CHECK (
    sequence_no >= 1 AND event_type IN ('play','pause','seek','speed','transcript')
    AND (position_ms IS NULL OR position_ms >= 0)
    AND (playback_rate IS NULL OR playback_rate BETWEEN 0.25 AND 4.00)
  )
);

CREATE TABLE exercises.exercise_corrections (
  correction_id uuid PRIMARY KEY,
  attempt_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  revision_no integer NOT NULL,
  verdict varchar(32) NOT NULL,
  confidence numeric(5,4) NOT NULL,
  target_coverage numeric(5,4) NOT NULL,
  strategy varchar(80) NOT NULL,
  rubric_revision_id uuid,
  proposed_answer jsonb,
  alternatives jsonb NOT NULL,
  explanation text NOT NULL,
  error_codes jsonb NOT NULL,
  criterion_scores jsonb NOT NULL,
  provenance_id uuid NOT NULL,
  requires_review boolean NOT NULL,
  supersedes_correction_id uuid,
  is_current boolean NOT NULL,
  result_payload jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_exercise_correction_attempt FOREIGN KEY (profile_id,attempt_id)
    REFERENCES exercises.exercise_attempts(profile_id,attempt_id) ON DELETE RESTRICT,
  CONSTRAINT uq_exercise_correction_revision UNIQUE (attempt_id,revision_no),
  CONSTRAINT uq_exercise_correction_profile UNIQUE (profile_id,correction_id),
  CONSTRAINT ck_exercise_correction_uuid7 CHECK (
    exercises.is_uuid7(correction_id) AND exercises.is_uuid7(attempt_id)
    AND exercises.is_uuid7(profile_id)
    AND (rubric_revision_id IS NULL OR exercises.is_uuid7(rubric_revision_id))
    AND exercises.is_uuid7(provenance_id)
    AND (supersedes_correction_id IS NULL OR exercises.is_uuid7(supersedes_correction_id))
  ),
  CONSTRAINT ck_exercise_correction_shape CHECK (
    revision_no >= 1 AND verdict IN ('correct','partially_correct','incorrect','ambiguous','invalid_answer','not_evaluable')
    AND confidence BETWEEN 0 AND 1 AND target_coverage BETWEEN 0 AND 1
    AND jsonb_typeof(alternatives)='array' AND jsonb_typeof(error_codes)='array'
    AND jsonb_typeof(criterion_scores)='object' AND length(explanation) >= 1
    AND jsonb_typeof(result_payload)='object'
  )
);
ALTER TABLE exercises.exercise_corrections ADD CONSTRAINT fk_exercise_correction_supersedes
  FOREIGN KEY (profile_id,supersedes_correction_id)
  REFERENCES exercises.exercise_corrections(profile_id,correction_id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX uq_exercise_current_correction
  ON exercises.exercise_corrections(attempt_id) WHERE is_current;

CREATE TABLE exercises.correction_cases (
  case_id uuid PRIMARY KEY,
  attempt_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  status varchar(24) NOT NULL,
  opened_by_account_id uuid NOT NULL,
  reason_code varchar(80) NOT NULL,
  user_comment text,
  opened_at timestamptz NOT NULL,
  resolved_at timestamptz,
  resolution_correction_id uuid,
  current_review_no integer NOT NULL DEFAULT 0,
  version integer NOT NULL,
  CONSTRAINT fk_correction_case_attempt FOREIGN KEY (profile_id,attempt_id)
    REFERENCES exercises.exercise_attempts(profile_id,attempt_id) ON DELETE RESTRICT,
  CONSTRAINT uq_open_correction_case UNIQUE (attempt_id),
  CONSTRAINT uq_correction_case_profile UNIQUE (profile_id,case_id),
  CONSTRAINT ck_correction_case_uuid7 CHECK (
    exercises.is_uuid7(case_id) AND exercises.is_uuid7(attempt_id)
    AND exercises.is_uuid7(profile_id) AND exercises.is_uuid7(opened_by_account_id)
    AND (resolution_correction_id IS NULL OR exercises.is_uuid7(resolution_correction_id))
  ),
  CONSTRAINT ck_correction_case_shape CHECK (
    status IN ('closed','contested','review_pending','resolved') AND version >= 1
    AND current_review_no >= 0 AND length(reason_code) >= 1
    AND ((status='resolved') = (resolved_at IS NOT NULL AND resolution_correction_id IS NOT NULL))
  )
);
ALTER TABLE exercises.correction_cases ADD CONSTRAINT fk_correction_case_resolution
  FOREIGN KEY (profile_id,resolution_correction_id)
  REFERENCES exercises.exercise_corrections(profile_id,correction_id) ON DELETE RESTRICT;

CREATE TABLE exercises.correction_case_reviews (
  case_review_id uuid PRIMARY KEY,
  case_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  review_no integer NOT NULL,
  reviewer_actor_id uuid NOT NULL,
  decision varchar(40) NOT NULL,
  rationale text NOT NULL,
  correction_id uuid,
  reviewed_at timestamptz NOT NULL,
  CONSTRAINT fk_correction_case_review FOREIGN KEY (profile_id,case_id)
    REFERENCES exercises.correction_cases(profile_id,case_id) ON DELETE RESTRICT,
  CONSTRAINT fk_correction_case_review_correction FOREIGN KEY (profile_id,correction_id)
    REFERENCES exercises.exercise_corrections(profile_id,correction_id) ON DELETE RESTRICT,
  CONSTRAINT uq_correction_case_review UNIQUE (case_id,review_no),
  CONSTRAINT ck_correction_case_review_uuid7 CHECK (
    exercises.is_uuid7(case_review_id) AND exercises.is_uuid7(case_id)
    AND exercises.is_uuid7(profile_id) AND exercises.is_uuid7(reviewer_actor_id)
    AND (correction_id IS NULL OR exercises.is_uuid7(correction_id))
  ),
  CONSTRAINT ck_correction_case_review_shape CHECK (
    review_no >= 1 AND decision IN ('uphold','replace','not_evaluable')
    AND length(rationale) >= 1
  )
);

CREATE TABLE exercises.exercise_block_runs (
  block_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  sprint_run_id uuid NOT NULL,
  required boolean NOT NULL,
  status varchar(24) NOT NULL,
  reason text,
  aggregate_payload jsonb NOT NULL,
  version integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_exercise_block_profile UNIQUE (profile_id,block_id),
  CONSTRAINT ck_exercise_block_uuid7 CHECK (
    exercises.is_uuid7(block_id) AND exercises.is_uuid7(profile_id)
    AND exercises.is_uuid7(sprint_run_id)
  ),
  CONSTRAINT ck_exercise_block_shape CHECK (
    status IN ('pending','available','in_progress','completed','skipped','abandoned','unavailable')
    AND version >= 1 AND updated_at >= created_at AND jsonb_typeof(aggregate_payload)='object'
  )
);

CREATE TABLE exercises.exercise_command_receipts (
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
  CONSTRAINT uq_exercise_command_receipt UNIQUE (actor_id,command_type,idempotency_key),
  CONSTRAINT ck_exercise_command_receipt_uuid7 CHECK (
    exercises.is_uuid7(receipt_id) AND exercises.is_uuid7(profile_id)
    AND exercises.is_uuid7(actor_id) AND exercises.is_uuid7(result_id)
  ),
  CONSTRAINT ck_exercise_command_receipt_shape CHECK (
    request_fingerprint ~ '^[0-9a-f]{64}$' AND result_version >= 1
    AND result_type IN ('attempt','correction_case','exercise_block')
    AND jsonb_typeof(result_payload)='object'
    AND octet_length(result_payload::text) <= 65536
  )
);

CREATE INDEX ix_exercise_attempt_profile ON exercises.exercise_attempts(profile_id,status,updated_at,attempt_id);
CREATE INDEX ix_exercise_instance_standalone_profile
  ON exercises.exercise_instances(standalone_profile_id,created_at,instance_id)
  WHERE standalone_profile_id IS NOT NULL;
CREATE INDEX ix_exercise_block_profile ON exercises.exercise_block_runs(profile_id,status,updated_at,block_id);

DO $guards$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'exercise_definition_revisions','exercise_language_certifications',
    'exercise_instances','exercise_hint_uses','attempt_media_events',
    'correction_case_reviews','exercise_command_receipts'
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON exercises.%I FOR EACH ROW EXECUTE FUNCTION exercises.guard_append_only()',
      'guard_' || table_name,table_name
    );
  END LOOP;
END
$guards$;

CREATE TRIGGER guard_exercise_correction_current
  BEFORE UPDATE OR DELETE ON exercises.exercise_corrections
  FOR EACH ROW EXECUTE FUNCTION exercises.guard_correction_current();

CREATE TRIGGER guard_exercise_attempt_answer
  BEFORE UPDATE ON exercises.exercise_attempts
  FOR EACH ROW EXECUTE FUNCTION exercises.guard_attempt_answer();

ALTER TABLE exercises.exercise_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE exercises.exercise_instances FORCE ROW LEVEL SECURITY;
CREATE POLICY exercise_instances_read ON exercises.exercise_instances
  FOR SELECT USING (
    standalone_profile_id IS NULL OR exercises.owns_profile(standalone_profile_id)
    OR exercises.has_role(ARRAY['worker','reviewer','admin'])
  );
CREATE POLICY exercise_instances_write ON exercises.exercise_instances
  FOR INSERT WITH CHECK (
    standalone_profile_id IS NOT NULL AND exercises.owns_profile(standalone_profile_id)
  );

DO $rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'exercise_attempts','attempt_drafts','exercise_hint_uses','attempt_media_events',
    'exercise_corrections','correction_cases','correction_case_reviews','exercise_block_runs',
    'exercise_command_receipts'
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

CREATE POLICY exercise_attempts_operator ON exercises.exercise_attempts
  FOR ALL USING (exercises.has_role(ARRAY['worker','reviewer','admin']))
  WITH CHECK (exercises.has_role(ARRAY['worker','reviewer','admin']));
CREATE POLICY exercise_corrections_operator ON exercises.exercise_corrections
  FOR ALL USING (exercises.has_role(ARRAY['worker','reviewer','admin']))
  WITH CHECK (exercises.has_role(ARRAY['worker','reviewer','admin']));
CREATE POLICY correction_cases_reviewer ON exercises.correction_cases
  FOR ALL USING (exercises.has_role(ARRAY['reviewer','admin']))
  WITH CHECK (exercises.has_role(ARRAY['reviewer','admin']));
CREATE POLICY correction_case_reviews_reviewer ON exercises.correction_case_reviews
  FOR ALL USING (exercises.has_role(ARRAY['reviewer','admin']))
  WITH CHECK (exercises.has_role(ARRAY['reviewer','admin']));
CREATE POLICY exercise_command_receipts_operator ON exercises.exercise_command_receipts
  FOR ALL USING (exercises.has_role(ARRAY['worker','reviewer','admin']))
  WITH CHECK (exercises.has_role(ARRAY['worker','reviewer','admin']));

GRANT USAGE ON SCHEMA exercises TO polyglot_runtime;
GRANT SELECT ON exercises.exercise_definitions,exercises.exercise_definition_revisions,
  exercises.exercise_language_certifications TO polyglot_runtime;
GRANT SELECT,INSERT ON exercises.exercise_instances,exercises.exercise_hint_uses,
  exercises.attempt_media_events,exercises.exercise_corrections,
  exercises.correction_case_reviews TO polyglot_runtime;
GRANT UPDATE(is_current) ON exercises.exercise_corrections TO polyglot_runtime;
GRANT SELECT,INSERT,UPDATE ON exercises.exercise_attempts,exercises.attempt_drafts,
  exercises.correction_cases,exercises.exercise_block_runs TO polyglot_runtime;
GRANT SELECT,INSERT ON exercises.exercise_command_receipts TO polyglot_runtime;
GRANT USAGE,CREATE ON SCHEMA exercises TO polyglot_migration;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA exercises TO polyglot_migration;
REVOKE ALL ON SCHEMA exercises FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA exercises FROM PUBLIC;
ALTER SCHEMA exercises OWNER TO polyglot_migration;
DO $owners$ DECLARE item record; BEGIN
  FOR item IN SELECT tablename FROM pg_tables WHERE schemaname='exercises' LOOP
    EXECUTE format('ALTER TABLE exercises.%I OWNER TO polyglot_migration',item.tablename);
  END LOOP;
END $owners$;
ALTER FUNCTION exercises.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION exercises.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION exercises.owns_profile(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION exercises.has_role(text[]) OWNER TO polyglot_migration;
ALTER FUNCTION exercises.guard_append_only() OWNER TO polyglot_migration;
ALTER FUNCTION exercises.guard_attempt_answer() OWNER TO polyglot_migration;
ALTER FUNCTION exercises.guard_correction_current() OWNER TO polyglot_migration;
"""

DROP_DDL = r"""
DROP SCHEMA IF EXISTS exercises CASCADE;
"""


async def _execute(connection: Connection, sql: str) -> None:
    await connection.execute(sql)


def upgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, EXERCISES_DDL))


def downgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DROP_DDL))
