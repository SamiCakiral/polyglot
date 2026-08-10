"""Persist versioned four-modality assessments.

Revision ID: 0014_assessments
Revises: 0013_progress
"""

# ruff: noqa: E501

from alembic import op
from asyncpg import Connection

revision = "0014_assessments"
down_revision = "0013_progress"
branch_labels = None
depends_on = None


ASSESSMENTS_DDL = r"""
CREATE SCHEMA assessments AUTHORIZATION polyglot_migration;

CREATE FUNCTION assessments.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
  SELECT value IS NOT NULL AND (get_byte(uuid_send(value),6) >> 4) = 7
$function$;
CREATE FUNCTION assessments.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE AS $function$
  SELECT NULLIF(current_setting('app.user_id',true),'')::uuid
$function$;
CREATE FUNCTION assessments.owns_profile(value uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,language_profiles,assessments AS $function$
  SELECT EXISTS (
    SELECT 1 FROM language_profiles.learner_language_profiles profile
    WHERE profile.profile_id=value AND profile.account_id=assessments.current_user_id()
      AND profile.status <> 'deleted'
  )
$function$;
CREATE FUNCTION assessments.guard_append_only() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
  RAISE EXCEPTION 'assessment fact is append-only' USING ERRCODE='55000';
END
$function$;

CREATE TABLE assessments.assessment_definitions (
  assessment_definition_id uuid PRIMARY KEY,
  definition_code varchar(120) NOT NULL UNIQUE,
  modality varchar(16) NOT NULL,
  current_revision_id uuid,
  status varchar(16) NOT NULL,
  version integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT ck_assessment_definition_uuid7 CHECK (assessments.is_uuid7(assessment_definition_id)),
  CONSTRAINT ck_assessment_definition_shape CHECK (
    modality IN ('reading','listening','writing','speaking')
    AND status IN ('draft','published','retired') AND version>=1 AND updated_at>=created_at
  )
);

CREATE TABLE assessments.assessment_definition_revisions (
  assessment_revision_id uuid PRIMARY KEY,
  assessment_definition_id uuid NOT NULL REFERENCES assessments.assessment_definitions(assessment_definition_id) ON DELETE RESTRICT,
  revision_no integer NOT NULL,
  status varchar(16) NOT NULL,
  protocol_code varchar(80) NOT NULL,
  coverage_matrix jsonb NOT NULL,
  difficulty_profile jsonb NOT NULL,
  time_limit_ms integer NOT NULL,
  pause_policy jsonb NOT NULL,
  security_rules jsonb NOT NULL,
  rubric_revision varchar(80),
  parallel_form_rules jsonb NOT NULL,
  protocol_fingerprint char(64) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_assessment_revision_no UNIQUE (assessment_definition_id,revision_no),
  CONSTRAINT uq_assessment_revision_owner UNIQUE (assessment_definition_id,assessment_revision_id),
  CONSTRAINT ck_assessment_revision_uuid7 CHECK (
    assessments.is_uuid7(assessment_revision_id) AND assessments.is_uuid7(assessment_definition_id)
  ),
  CONSTRAINT ck_assessment_revision_shape CHECK (
    revision_no>=1 AND status IN ('draft','published','retired') AND time_limit_ms>=60000
    AND jsonb_typeof(coverage_matrix)='object' AND jsonb_typeof(difficulty_profile)='object'
    AND jsonb_typeof(pause_policy)='object' AND jsonb_typeof(security_rules)='object'
    AND jsonb_typeof(parallel_form_rules)='object' AND protocol_fingerprint ~ '^[0-9a-f]{64}$'
  )
);
ALTER TABLE assessments.assessment_definitions ADD CONSTRAINT fk_assessment_current_revision
  FOREIGN KEY (assessment_definition_id,current_revision_id)
  REFERENCES assessments.assessment_definition_revisions(assessment_definition_id,assessment_revision_id) ON DELETE RESTRICT;

CREATE TABLE assessments.assessment_forms (
  form_id uuid PRIMARY KEY,
  assessment_revision_id uuid NOT NULL REFERENCES assessments.assessment_definition_revisions(assessment_revision_id) ON DELETE RESTRICT,
  form_code varchar(120) NOT NULL,
  status varchar(16) NOT NULL,
  current_band_weight smallint NOT NULL,
  lower_anchor_weight smallint NOT NULL,
  transfer_weight smallint NOT NULL,
  calibration_uncertainty numeric(6,5) NOT NULL,
  media_cost smallint NOT NULL,
  coverage_targets varchar(160)[] NOT NULL,
  required_capabilities varchar(80)[] NOT NULL,
  checksum char(64) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_assessment_form_code UNIQUE (assessment_revision_id,form_code),
  CONSTRAINT ck_assessment_form_uuid7 CHECK (
    assessments.is_uuid7(form_id) AND assessments.is_uuid7(assessment_revision_id)
  ),
  CONSTRAINT ck_assessment_form_shape CHECK (
    status IN ('draft','published','retired') AND current_band_weight=60
    AND lower_anchor_weight=20 AND transfer_weight=20
    AND calibration_uncertainty BETWEEN 0 AND 1 AND media_cost>=0
    AND cardinality(coverage_targets)>=1 AND checksum ~ '^[0-9a-f]{64}$'
  )
);

CREATE TABLE assessments.assessment_section_definitions (
  section_definition_id uuid PRIMARY KEY,
  form_id uuid NOT NULL REFERENCES assessments.assessment_forms(form_id) ON DELETE RESTRICT,
  ordinal smallint NOT NULL,
  section_type varchar(80) NOT NULL,
  weight numeric(7,6) NOT NULL,
  title varchar(160) NOT NULL,
  instructions text NOT NULL,
  CONSTRAINT uq_assessment_section_ordinal UNIQUE (form_id,ordinal),
  CONSTRAINT uq_assessment_section_owner UNIQUE (form_id,section_definition_id),
  CONSTRAINT ck_assessment_section_uuid7 CHECK (
    assessments.is_uuid7(section_definition_id) AND assessments.is_uuid7(form_id)
  ),
  CONSTRAINT ck_assessment_section_shape CHECK (
    ordinal>=1 AND weight>0 AND weight<=1 AND length(title)>=1 AND length(instructions)>=1
  )
);

CREATE TABLE assessments.assessment_items (
  item_id uuid PRIMARY KEY,
  section_definition_id uuid NOT NULL REFERENCES assessments.assessment_section_definitions(section_definition_id) ON DELETE RESTRICT,
  ordinal smallint NOT NULL,
  item_kind varchar(40) NOT NULL,
  answer_kind varchar(40) NOT NULL,
  correction_strategy varchar(40) NOT NULL,
  weight numeric(8,7) NOT NULL,
  difficulty_tier varchar(16) NOT NULL,
  coverage_targets varchar(160)[] NOT NULL,
  prompt_snapshot jsonb NOT NULL,
  solution_snapshot jsonb NOT NULL,
  media_ref varchar(240),
  max_plays smallint,
  defective boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL,
  CONSTRAINT uq_assessment_item_ordinal UNIQUE (section_definition_id,ordinal),
  CONSTRAINT ck_assessment_item_uuid7 CHECK (
    assessments.is_uuid7(item_id) AND assessments.is_uuid7(section_definition_id)
  ),
  CONSTRAINT ck_assessment_item_shape CHECK (
    ordinal>=1 AND weight>0 AND weight<=1
    AND difficulty_tier IN ('lower_anchor','current','transfer')
    AND cardinality(coverage_targets)>=1
    AND jsonb_typeof(prompt_snapshot)='object' AND jsonb_typeof(solution_snapshot)='object'
    AND ((media_ref IS NULL AND max_plays IS NULL) OR (media_ref IS NOT NULL AND max_plays>=1))
  )
);

CREATE TABLE assessments.assessment_runs (
  assessment_run_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  assessment_revision_id uuid NOT NULL REFERENCES assessments.assessment_definition_revisions(assessment_revision_id) ON DELETE RESTRICT,
  form_id uuid NOT NULL REFERENCES assessments.assessment_forms(form_id) ON DELETE RESTRICT,
  modality varchar(16) NOT NULL,
  status varchar(24) NOT NULL,
  target_snapshot jsonb NOT NULL,
  item_order uuid[] NOT NULL,
  form_snapshot jsonb NOT NULL,
  time_limit_ms integer NOT NULL,
  pause_allowed boolean NOT NULL,
  resume_window_ms integer NOT NULL,
  prepared_at timestamptz NOT NULL,
  started_at timestamptz,
  deadline_at timestamptz,
  paused_at timestamptz,
  remaining_time_ms integer,
  submitted_at timestamptz,
  completed_at timestamptz,
  integrity_incidents jsonb NOT NULL,
  version integer NOT NULL,
  idempotency_key varchar(255) NOT NULL,
  request_fingerprint char(64) NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_assessment_run_owner UNIQUE (profile_id,assessment_run_id),
  CONSTRAINT uq_assessment_prepare_idempotency UNIQUE (profile_id,idempotency_key),
  CONSTRAINT ck_assessment_run_uuid7 CHECK (
    assessments.is_uuid7(assessment_run_id) AND assessments.is_uuid7(profile_id)
    AND assessments.is_uuid7(assessment_revision_id) AND assessments.is_uuid7(form_id)
  ),
  CONSTRAINT ck_assessment_run_shape CHECK (
    modality IN ('reading','listening','writing','speaking')
    AND status IN ('prepared','in_progress','paused','submitted','expired','scoring','review_required','completed','cancelled')
    AND jsonb_typeof(target_snapshot)='object' AND cardinality(item_order)>=1
    AND jsonb_typeof(form_snapshot)='object' AND time_limit_ms>=60000
    AND resume_window_ms>=0 AND jsonb_typeof(integrity_incidents)='array'
    AND version>=1 AND request_fingerprint ~ '^[0-9a-f]{64}$' AND updated_at>=prepared_at
  )
);

CREATE TABLE assessments.assessment_section_runs (
  section_run_id uuid PRIMARY KEY,
  assessment_run_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  section_definition_id uuid NOT NULL REFERENCES assessments.assessment_section_definitions(section_definition_id) ON DELETE RESTRICT,
  status varchar(16) NOT NULL,
  started_at timestamptz,
  completed_at timestamptz,
  remaining_time_ms_at_pause integer,
  version integer NOT NULL,
  CONSTRAINT fk_assessment_section_run FOREIGN KEY (profile_id,assessment_run_id)
    REFERENCES assessments.assessment_runs(profile_id,assessment_run_id) ON DELETE RESTRICT,
  CONSTRAINT uq_assessment_section_run UNIQUE (assessment_run_id,section_definition_id),
  CONSTRAINT ck_assessment_section_run_uuid7 CHECK (
    assessments.is_uuid7(section_run_id) AND assessments.is_uuid7(assessment_run_id)
    AND assessments.is_uuid7(profile_id) AND assessments.is_uuid7(section_definition_id)
  ),
  CONSTRAINT ck_assessment_section_run_shape CHECK (
    status IN ('pending','in_progress','completed','skipped','expired') AND version>=1
  )
);

CREATE TABLE assessments.assessment_responses (
  response_id uuid PRIMARY KEY,
  assessment_run_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  item_id uuid NOT NULL REFERENCES assessments.assessment_items(item_id) ON DELETE RESTRICT,
  answer jsonb NOT NULL,
  version integer NOT NULL,
  saved_at timestamptz NOT NULL,
  submitted_at timestamptz,
  correction_payload jsonb,
  CONSTRAINT fk_assessment_response_run FOREIGN KEY (profile_id,assessment_run_id)
    REFERENCES assessments.assessment_runs(profile_id,assessment_run_id) ON DELETE RESTRICT,
  CONSTRAINT uq_assessment_response UNIQUE (assessment_run_id,item_id),
  CONSTRAINT ck_assessment_response_uuid7 CHECK (
    assessments.is_uuid7(response_id) AND assessments.is_uuid7(assessment_run_id)
    AND assessments.is_uuid7(profile_id) AND assessments.is_uuid7(item_id)
  ),
  CONSTRAINT ck_assessment_response_shape CHECK (
    jsonb_typeof(answer)='object' AND version>=1
    AND (correction_payload IS NULL OR jsonb_typeof(correction_payload)='object')
  )
);

CREATE FUNCTION assessments.guard_response_mutation() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE run_status text;
BEGIN
  SELECT status INTO run_status FROM assessments.assessment_runs
  WHERE assessment_run_id=OLD.assessment_run_id;
  IF run_status NOT IN ('in_progress','paused') THEN
    RAISE EXCEPTION 'submitted assessment response is immutable' USING ERRCODE='55000';
  END IF;
  RETURN NEW;
END
$function$;

CREATE TABLE assessments.assessment_results (
  result_id uuid PRIMARY KEY,
  assessment_run_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  modality varchar(16) NOT NULL,
  result_status varchar(24) NOT NULL,
  score numeric(8,7),
  band varchar(16),
  confidence numeric(8,7) NOT NULL,
  coverage numeric(8,7) NOT NULL,
  integrity_factor numeric(8,7) NOT NULL,
  limiting_criteria varchar(160)[] NOT NULL,
  policy_revision varchar(80) NOT NULL,
  score_payload jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_assessment_result_run FOREIGN KEY (profile_id,assessment_run_id)
    REFERENCES assessments.assessment_runs(profile_id,assessment_run_id) ON DELETE RESTRICT,
  CONSTRAINT uq_assessment_result UNIQUE (assessment_run_id),
  CONSTRAINT ck_assessment_result_uuid7 CHECK (
    assessments.is_uuid7(result_id) AND assessments.is_uuid7(assessment_run_id)
    AND assessments.is_uuid7(profile_id)
  ),
  CONSTRAINT ck_assessment_result_shape CHECK (
    modality IN ('reading','listening','writing','speaking')
    AND result_status IN ('valid','indicative','not_evaluable')
    AND confidence BETWEEN 0 AND 1 AND coverage BETWEEN 0 AND 1
    AND integrity_factor BETWEEN 0 AND 1 AND jsonb_typeof(score_payload)='object'
    AND ((result_status='not_evaluable' AND score IS NULL AND band IS NULL)
      OR (result_status<>'not_evaluable' AND score BETWEEN 0 AND 1
        AND band IN ('assess_b0','assess_b1','assess_b2','assess_b3','assess_b4')))
  )
);

CREATE TABLE assessments.assessment_evidence (
  assessment_evidence_id uuid PRIMARY KEY,
  result_id uuid NOT NULL REFERENCES assessments.assessment_results(result_id) ON DELETE RESTRICT,
  assessment_run_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  item_id uuid NOT NULL REFERENCES assessments.assessment_items(item_id) ON DELETE RESTRICT,
  observation_id uuid REFERENCES progress.learning_observations(observation_id) ON DELETE RESTRICT,
  modality varchar(16) NOT NULL,
  facet_key varchar(160) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_assessment_evidence_run FOREIGN KEY (profile_id,assessment_run_id)
    REFERENCES assessments.assessment_runs(profile_id,assessment_run_id) ON DELETE RESTRICT,
  CONSTRAINT uq_assessment_evidence UNIQUE (result_id,item_id,facet_key),
  CONSTRAINT ck_assessment_evidence_uuid7 CHECK (
    assessments.is_uuid7(assessment_evidence_id) AND assessments.is_uuid7(result_id)
    AND assessments.is_uuid7(assessment_run_id) AND assessments.is_uuid7(profile_id)
    AND assessments.is_uuid7(item_id)
    AND (observation_id IS NULL OR assessments.is_uuid7(observation_id))
  ),
  CONSTRAINT ck_assessment_evidence_shape CHECK (
    modality IN ('reading','listening','writing','speaking') AND length(facet_key)>=1
  )
);

CREATE TABLE assessments.assessment_reviews (
  review_id uuid PRIMARY KEY,
  assessment_run_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  reviewer_id uuid NOT NULL,
  rubric_revision varchar(80) NOT NULL,
  criterion_scores jsonb NOT NULL,
  annotations jsonb NOT NULL,
  qualified boolean NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_assessment_review_run FOREIGN KEY (profile_id,assessment_run_id)
    REFERENCES assessments.assessment_runs(profile_id,assessment_run_id) ON DELETE RESTRICT,
  CONSTRAINT uq_assessment_review UNIQUE (assessment_run_id),
  CONSTRAINT ck_assessment_review_uuid7 CHECK (
    assessments.is_uuid7(review_id) AND assessments.is_uuid7(assessment_run_id)
    AND assessments.is_uuid7(profile_id) AND assessments.is_uuid7(reviewer_id)
  ),
  CONSTRAINT ck_assessment_review_shape CHECK (
    jsonb_typeof(criterion_scores)='object' AND jsonb_typeof(annotations)='array'
  )
);

CREATE TABLE assessments.form_exposures (
  exposure_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  assessment_run_id uuid NOT NULL,
  form_id uuid NOT NULL REFERENCES assessments.assessment_forms(form_id) ON DELETE RESTRICT,
  item_ids uuid[] NOT NULL,
  exposed_at timestamptz NOT NULL,
  CONSTRAINT fk_assessment_exposure_run FOREIGN KEY (profile_id,assessment_run_id)
    REFERENCES assessments.assessment_runs(profile_id,assessment_run_id) ON DELETE RESTRICT,
  CONSTRAINT uq_assessment_exposure_run UNIQUE (assessment_run_id),
  CONSTRAINT ck_assessment_exposure_uuid7 CHECK (
    assessments.is_uuid7(exposure_id) AND assessments.is_uuid7(profile_id)
    AND assessments.is_uuid7(assessment_run_id) AND assessments.is_uuid7(form_id)
  ),
  CONSTRAINT ck_assessment_exposure_shape CHECK (cardinality(item_ids)>=1)
);

CREATE TRIGGER guard_assessment_response_update
  BEFORE UPDATE OR DELETE ON assessments.assessment_responses
  FOR EACH ROW EXECUTE FUNCTION assessments.guard_response_mutation();
DO $guards$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'assessment_definition_revisions','assessment_forms','assessment_section_definitions',
    'assessment_items','assessment_results','assessment_evidence','assessment_reviews','form_exposures'
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON assessments.%I FOR EACH ROW EXECUTE FUNCTION assessments.guard_append_only()',
      'guard_' || table_name,table_name
    );
  END LOOP;
END
$guards$;

DO $rls_public$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'assessment_definitions','assessment_definition_revisions','assessment_forms',
    'assessment_section_definitions','assessment_items'
  ] LOOP
    EXECUTE format('ALTER TABLE assessments.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE assessments.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format('CREATE POLICY %I ON assessments.%I FOR SELECT USING (true)',table_name || '_read',table_name);
    EXECUTE format(
      'CREATE POLICY %I ON assessments.%I TO polyglot_migration USING (true) WITH CHECK (true)',
      table_name || '_migration',table_name
    );
  END LOOP;
END
$rls_public$;
DO $rls_owner$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'assessment_runs','assessment_section_runs','assessment_responses','assessment_results',
    'assessment_evidence','assessment_reviews','form_exposures'
  ] LOOP
    EXECUTE format('ALTER TABLE assessments.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE assessments.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY %I ON assessments.%I USING (assessments.owns_profile(profile_id)) WITH CHECK (assessments.owns_profile(profile_id))',
      table_name || '_owner',table_name
    );
    EXECUTE format(
      'CREATE POLICY %I ON assessments.%I TO polyglot_migration USING (true) WITH CHECK (true)',
      table_name || '_migration',table_name
    );
  END LOOP;
END
$rls_owner$;

GRANT USAGE ON SCHEMA assessments TO polyglot_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA assessments TO polyglot_runtime;
GRANT INSERT,UPDATE ON assessments.assessment_runs,assessments.assessment_section_runs,
  assessments.assessment_responses TO polyglot_runtime;
GRANT INSERT ON assessments.assessment_results,assessments.assessment_evidence,
  assessments.assessment_reviews,assessments.form_exposures TO polyglot_runtime;
REVOKE DELETE ON ALL TABLES IN SCHEMA assessments FROM polyglot_runtime;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA assessments TO polyglot_migration;
REVOKE ALL ON ALL TABLES IN SCHEMA assessments FROM PUBLIC;

INSERT INTO assessments.assessment_definitions
  (assessment_definition_id,definition_code,modality,current_revision_id,status,version,created_at,updated_at)
VALUES
  ('019feb32-0000-7000-8000-000000001001','it.reading.v0','reading',NULL,'published',1,'2026-08-10T00:00:00Z','2026-08-10T00:00:00Z'),
  ('019feb32-0000-7000-8000-000000001002','it.listening.v0','listening',NULL,'published',1,'2026-08-10T00:00:00Z','2026-08-10T00:00:00Z'),
  ('019feb32-0000-7000-8000-000000001003','it.writing.v0','writing',NULL,'published',1,'2026-08-10T00:00:00Z','2026-08-10T00:00:00Z'),
  ('019feb32-0000-7000-8000-000000001004','it.speaking.v0','speaking',NULL,'published',1,'2026-08-10T00:00:00Z','2026-08-10T00:00:00Z');

INSERT INTO assessments.assessment_definition_revisions
  (assessment_revision_id,assessment_definition_id,revision_no,status,protocol_code,coverage_matrix,difficulty_profile,time_limit_ms,pause_policy,security_rules,rubric_revision,parallel_form_rules,protocol_fingerprint,created_at)
VALUES
  ('019feb32-0000-7000-8000-000000002001','019feb32-0000-7000-8000-000000001001',1,'published','READING_SCORE_V0','{"literal":0.25,"inference":0.30,"intention":0.20,"register":0.10,"vocabulary":0.10,"unknown_strategy":0.05}','{"current":0.6,"lower_anchor":0.2,"transfer":0.2}',1500000,'{"allowed":true,"resume_window_ms":86400000}','{"exposure_window_days":14}',NULL,'{"current":60,"lower_anchor":20,"transfer":20}','4b1fe65d53e448f4cf7df723e090a7492af2a46b93c771019804d35087736319','2026-08-10T00:00:00Z'),
  ('019feb32-0000-7000-8000-000000002002','019feb32-0000-7000-8000-000000001002',1,'published','LISTENING_SCORE_V0','{"global":0.20,"detail":0.25,"inference":0.25,"register":0.15,"perceptive_strategy":0.15}','{"current":0.6,"lower_anchor":0.2,"transfer":0.2}',1500000,'{"allowed":false,"resume_window_ms":0}','{"exposure_window_days":14,"transcript_hidden":true}',NULL,'{"current":60,"lower_anchor":20,"transfer":20}','8bc39a0a1662b7a76ebe11ad2200814172a5c4f5299954dd73bd87d804996a6f','2026-08-10T00:00:00Z'),
  ('019feb32-0000-7000-8000-000000002003','019feb32-0000-7000-8000-000000001003',1,'published','WRITING_RUBRIC_V0','{"task_achievement":0.25,"coherence":0.25,"grammar":0.20,"range":0.15,"lexis_register":0.15}','{"current":0.6,"lower_anchor":0.2,"transfer":0.2}',2400000,'{"allowed":true,"resume_window_ms":86400000}','{"exposure_window_days":14}','WRITING_RUBRIC_V0','{"current":60,"lower_anchor":20,"transfer":20}','44de6181960504f336766172472303507490d3a61e57d211f7282f2fd424e421','2026-08-10T00:00:00Z'),
  ('019feb32-0000-7000-8000-000000002004','019feb32-0000-7000-8000-000000001004',1,'published','SPEAKING_RUBRIC_V0','{"interaction":0.25,"intelligibility":0.25,"fluency":0.20,"grammar":0.15,"range_lexis_register":0.15}','{"current":0.6,"lower_anchor":0.2,"transfer":0.2}',1080000,'{"allowed":true,"resume_window_ms":86400000}','{"exposure_window_days":14,"recording_optional":true}','SPEAKING_RUBRIC_V0','{"current":60,"lower_anchor":20,"transfer":20}','08893255eae1fe1fc72d3200c948d33d86d94b4c60b706d433e18165c1003dbf','2026-08-10T00:00:00Z');

UPDATE assessments.assessment_definitions d SET current_revision_id=r.assessment_revision_id
FROM assessments.assessment_definition_revisions r
WHERE r.assessment_definition_id=d.assessment_definition_id;

INSERT INTO assessments.assessment_forms
  (form_id,assessment_revision_id,form_code,status,current_band_weight,lower_anchor_weight,transfer_weight,calibration_uncertainty,media_cost,coverage_targets,required_capabilities,checksum,created_at)
VALUES
  ('019feb32-0000-7000-8000-000000003001','019feb32-0000-7000-8000-000000002001','IT-READ-A','published',60,20,20,0.10,0,ARRAY['literal','inference','register'],ARRAY[]::varchar[],'210abcdfa68dc18230ff163ecd317a7d4c90317b86d70901b820ac63543fbc95','2026-08-10T00:00:00Z'),
  ('019feb32-0000-7000-8000-000000003002','019feb32-0000-7000-8000-000000002002','IT-LISTEN-A','published',60,20,20,0.10,1,ARRAY['global','detail','inference'],ARRAY['tts'],'315d44a38ed244308510391601ae33176835cc7f0122f782036815f666424e12','2026-08-10T00:00:00Z'),
  ('019feb32-0000-7000-8000-000000003003','019feb32-0000-7000-8000-000000002003','IT-WRITE-A','published',60,20,20,0.10,0,ARRAY['task_achievement','coherence','grammar'],ARRAY[]::varchar[],'61d4b58c1a89460cdad9c8f3096bd62063272edd136440096783090bcd06a3a6','2026-08-10T00:00:00Z'),
  ('019feb32-0000-7000-8000-000000003004','019feb32-0000-7000-8000-000000002004','IT-SPEAK-A','published',60,20,20,0.10,0,ARRAY['interaction','intelligibility','fluency'],ARRAY[]::varchar[],'b037861414ef479cb2762fc9f2afc59baca8f88414f5d46318458a0b367eac45','2026-08-10T00:00:00Z');

INSERT INTO assessments.assessment_section_definitions
  (section_definition_id,form_id,ordinal,section_type,weight,title,instructions)
VALUES
  ('019feb32-0000-7000-8000-000000004001','019feb32-0000-7000-8000-000000003001',1,'reading_comprehension',1,'Compréhension écrite','Lisez puis répondez sans aide externe.'),
  ('019feb32-0000-7000-8000-000000004002','019feb32-0000-7000-8000-000000003002',1,'listening_comprehension',1,'Compréhension orale','Écoutez chaque segment selon le nombre de lectures autorisé.'),
  ('019feb32-0000-7000-8000-000000004003','019feb32-0000-7000-8000-000000003003',1,'writing_production',1,'Expression écrite','Rédigez les deux productions en italien.'),
  ('019feb32-0000-7000-8000-000000004004','019feb32-0000-7000-8000-000000003004',1,'speaking_simulation',1,'Expression orale','Réalisez les quatre séquences puis auto-évaluez-vous.' );

INSERT INTO assessments.assessment_items
  (item_id,section_definition_id,ordinal,item_kind,answer_kind,correction_strategy,weight,difficulty_tier,coverage_targets,prompt_snapshot,solution_snapshot,media_ref,max_plays,defective,created_at)
SELECT
  ('019feb32-0000-7000-8000-' || lpad(to_hex(5000+n),12,'0'))::uuid,
  '019feb32-0000-7000-8000-000000004001'::uuid,n,'single_choice','single_choice','accepted_set',1.0/18,
  CASE WHEN n<=4 THEN 'lower_anchor' WHEN n<=14 THEN 'current' ELSE 'transfer' END,
  ARRAY[CASE WHEN n%3=0 THEN 'inference' WHEN n%3=1 THEN 'literal' ELSE 'register' END],
  jsonb_build_object('title','Un viaggio in Italia','body','Leggi il testo e scegli la risposta più precisa.','question','Domanda ' || n,'options',jsonb_build_array('A','B','C','D')),
  jsonb_build_object('accepted',jsonb_build_array('A'),'option_count',4),NULL,NULL,false,'2026-08-10T00:00:00Z'
FROM generate_series(1,18) n;

INSERT INTO assessments.assessment_items
  (item_id,section_definition_id,ordinal,item_kind,answer_kind,correction_strategy,weight,difficulty_tier,coverage_targets,prompt_snapshot,solution_snapshot,media_ref,max_plays,defective,created_at)
SELECT
  ('019feb32-0000-7000-8000-' || lpad(to_hex(6000+n),12,'0'))::uuid,
  '019feb32-0000-7000-8000-000000004002'::uuid,n,'listening_choice','single_choice','accepted_set',1.0/16,
  CASE WHEN n<=3 THEN 'lower_anchor' WHEN n<=13 THEN 'current' ELSE 'transfer' END,
  ARRAY[CASE WHEN n%3=0 THEN 'inference' WHEN n%3=1 THEN 'global' ELSE 'detail' END],
  jsonb_build_object('title','Ascolto ' || n,'question','Scegli la risposta corretta.','options',jsonb_build_array('A','B','C','D'),'transcript_hidden',true),
  jsonb_build_object('accepted',jsonb_build_array('A'),'option_count',4),
  'tts:it:assessment:listening:' || n,2,false,'2026-08-10T00:00:00Z'
FROM generate_series(1,16) n;

INSERT INTO assessments.assessment_items
  (item_id,section_definition_id,ordinal,item_kind,answer_kind,correction_strategy,weight,difficulty_tier,coverage_targets,prompt_snapshot,solution_snapshot,media_ref,max_plays,defective,created_at)
VALUES
  ('019feb32-0000-7000-8000-000000007001','019feb32-0000-7000-8000-000000004003',1,'functional_message','text','human_review',0.4,'current',ARRAY['task_achievement','coherence','grammar'],jsonb_build_object('title','Message pratique','body','Scrivi un messaggio per spostare un appuntamento e proponi una nuova ora.'),jsonb_build_object('rubric','WRITING_RUBRIC_V0'),NULL,NULL,false,'2026-08-10T00:00:00Z'),
  ('019feb32-0000-7000-8000-000000007002','019feb32-0000-7000-8000-000000004003',2,'sustained_writing','text','human_review',0.6,'transfer',ARRAY['task_achievement','coherence','grammar','range','lexis_register'],jsonb_build_object('title','Production développée','body','Racconta un imprevisto durante un viaggio e spiega come lo hai risolto.'),jsonb_build_object('rubric','WRITING_RUBRIC_V0'),NULL,NULL,false,'2026-08-10T00:00:00Z');

INSERT INTO assessments.assessment_items
  (item_id,section_definition_id,ordinal,item_kind,answer_kind,correction_strategy,weight,difficulty_tier,coverage_targets,prompt_snapshot,solution_snapshot,media_ref,max_plays,defective,created_at)
VALUES
  ('019feb32-0000-7000-8000-000000008001','019feb32-0000-7000-8000-000000004004',1,'targeted_reading','self_assessment','self_assessment',0.15,'lower_anchor',ARRAY['intelligibility'],jsonb_build_object('title','Lecture ciblée','body','Leggi ad alta voce: Gli amici scelgono un viaggio in giugno.'),jsonb_build_object('rubric','SPEAKING_RUBRIC_V0'),NULL,NULL,false,'2026-08-10T00:00:00Z'),
  ('019feb32-0000-7000-8000-000000008002','019feb32-0000-7000-8000-000000004004',2,'guided_answers','self_assessment','self_assessment',0.20,'current',ARRAY['interaction','fluency'],jsonb_build_object('title','Réponses guidées','body','Rispondi a tre domande sulla tua giornata.'),jsonb_build_object('rubric','SPEAKING_RUBRIC_V0'),NULL,NULL,false,'2026-08-10T00:00:00Z'),
  ('019feb32-0000-7000-8000-000000008003','019feb32-0000-7000-8000-000000004004',3,'prepared_monologue','self_assessment','self_assessment',0.25,'current',ARRAY['fluency','grammar','range_lexis_register'],jsonb_build_object('title','Monologue','body','Descrivi una città che vorresti visitare e spiega perché.'),jsonb_build_object('rubric','SPEAKING_RUBRIC_V0'),NULL,NULL,false,'2026-08-10T00:00:00Z'),
  ('019feb32-0000-7000-8000-000000008004','019feb32-0000-7000-8000-000000004004',4,'simulated_interaction','self_assessment','self_assessment',0.40,'transfer',ARRAY['interaction','intelligibility','fluency'],jsonb_build_object('title','Interaction simulée','body','Simula una conversazione per risolvere un errore di prenotazione.'),jsonb_build_object('rubric','SPEAKING_RUBRIC_V0'),NULL,NULL,false,'2026-08-10T00:00:00Z');

ALTER FUNCTION assessments.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION assessments.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION assessments.owns_profile(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION assessments.guard_append_only() OWNER TO polyglot_migration;
ALTER FUNCTION assessments.guard_response_mutation() OWNER TO polyglot_migration;
DO $owners$ DECLARE item record; BEGIN
  FOR item IN SELECT tablename FROM pg_tables WHERE schemaname='assessments' LOOP
    EXECUTE format('ALTER TABLE assessments.%I OWNER TO polyglot_migration',item.tablename);
  END LOOP;
END $owners$;
"""


DROP_DDL = "DROP SCHEMA IF EXISTS assessments CASCADE;"


async def _execute(connection: Connection, sql: str) -> None:
    await connection.execute(sql)


def upgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, ASSESSMENTS_DDL))


def downgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DROP_DDL))
