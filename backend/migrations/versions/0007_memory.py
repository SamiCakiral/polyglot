"""Create append-only memory scheduling facts.

Revision ID: 0007_memory
Revises: 0006_lexicon_core
"""

# ruff: noqa: E501

from alembic import op
from asyncpg import Connection

revision = "0007_memory"
down_revision = "0006_lexicon_core"
branch_labels = None
depends_on = None


MEMORY_DDL = r"""
CREATE SCHEMA memory;

CREATE FUNCTION memory.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
  SELECT value IS NOT NULL AND (get_byte(uuid_send(value), 6) >> 4) = 7
$function$;

CREATE FUNCTION memory.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE AS $function$
  SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
$function$;

CREATE FUNCTION memory.owns_profile(value uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, language_profiles, memory AS $function$
  SELECT EXISTS (
    SELECT 1 FROM language_profiles.learner_language_profiles profile
    WHERE profile.profile_id = value
      AND profile.account_id = memory.current_user_id()
      AND profile.status <> 'deleted'
  )
$function$;

CREATE TABLE memory.memory_prompts (
  prompt_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  target_ref uuid NOT NULL,
  target_revision_id uuid NOT NULL,
  direction varchar(80) NOT NULL,
  modality varchar(40) NOT NULL,
  operation varchar(80) NOT NULL,
  protocol_id varchar(120) NOT NULL,
  protocol_revision integer NOT NULL,
  rating_semantics_id varchar(120) NOT NULL,
  scheduler_policy_id uuid NOT NULL,
  scheduler_kind varchar(40) NOT NULL,
  scheduler_version varchar(40) NOT NULL,
  parameter_set_id varchar(120) NOT NULL,
  policy_revision integer NOT NULL,
  status varchar(24) NOT NULL,
  version integer NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  aggregate_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT ck_memory_prompt_uuid7 CHECK (
    memory.is_uuid7(prompt_id) AND memory.is_uuid7(profile_id)
    AND memory.is_uuid7(target_ref) AND memory.is_uuid7(target_revision_id)
    AND memory.is_uuid7(scheduler_policy_id)
  ),
  CONSTRAINT ck_memory_prompt_shape CHECK (
    protocol_revision >= 1 AND policy_revision >= 1 AND version >= 1
    AND status IN ('active','suspended','superseded','archived','deleted')
    AND updated_at >= created_at AND jsonb_typeof(aggregate_payload) = 'object'
  ),
  CONSTRAINT uq_memory_prompt_profile UNIQUE (profile_id, prompt_id)
);

CREATE TABLE memory.memory_schedule_states (
  prompt_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL,
  scheduler_kind varchar(40) NOT NULL,
  scheduler_version varchar(40) NOT NULL,
  parameter_set_id varchar(120) NOT NULL,
  policy_revision integer NOT NULL,
  state varchar(24) NOT NULL,
  difficulty numeric,
  stability numeric,
  desired_retention numeric(5,4) NOT NULL,
  last_review_at timestamptz,
  due_at timestamptz NOT NULL,
  reps integer NOT NULL,
  lapses integer NOT NULL,
  last_rating varchar(16),
  last_review_id uuid,
  projection_version integer NOT NULL,
  computed_at timestamptz NOT NULL,
  causal_checkpoint text NOT NULL,
  step integer,
  CONSTRAINT fk_memory_schedule_prompt FOREIGN KEY (profile_id,prompt_id)
    REFERENCES memory.memory_prompts(profile_id,prompt_id) ON DELETE RESTRICT,
  CONSTRAINT ck_memory_schedule_uuid7 CHECK (
    memory.is_uuid7(prompt_id) AND memory.is_uuid7(profile_id)
    AND (last_review_id IS NULL OR memory.is_uuid7(last_review_id))
  ),
  CONSTRAINT ck_memory_schedule_shape CHECK (
    policy_revision >= 1 AND projection_version >= 1
    AND state IN ('new','learning','review','relearning')
    AND desired_retention BETWEEN 0.80 AND 0.97
    AND reps >= 0 AND lapses >= 0 AND lapses <= reps
    AND (last_rating IS NULL OR last_rating IN ('again','hard','good','easy'))
  )
);
CREATE INDEX ix_memory_due
  ON memory.memory_schedule_states(profile_id,due_at,prompt_id);

CREATE TABLE memory.memory_reviews (
  review_id uuid PRIMARY KEY,
  prompt_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  opportunity_id uuid NOT NULL,
  reviewed_at timestamptz NOT NULL,
  previous_checkpoint text NOT NULL,
  payload jsonb NOT NULL,
  CONSTRAINT fk_memory_review_prompt FOREIGN KEY (profile_id,prompt_id)
    REFERENCES memory.memory_prompts(profile_id,prompt_id) ON DELETE RESTRICT,
  CONSTRAINT ck_memory_review_uuid7 CHECK (
    memory.is_uuid7(review_id) AND memory.is_uuid7(prompt_id)
    AND memory.is_uuid7(profile_id) AND memory.is_uuid7(opportunity_id)
  ),
  CONSTRAINT uq_memory_review_opportunity UNIQUE (prompt_id,opportunity_id)
);

CREATE TABLE memory.memory_schedule_resets (
  reset_id uuid PRIMARY KEY,
  prompt_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  reset_at timestamptz NOT NULL,
  previous_checkpoint text NOT NULL,
  payload jsonb NOT NULL,
  CONSTRAINT fk_memory_reset_prompt FOREIGN KEY (profile_id,prompt_id)
    REFERENCES memory.memory_prompts(profile_id,prompt_id) ON DELETE RESTRICT,
  CONSTRAINT ck_memory_reset_uuid7 CHECK (
    memory.is_uuid7(reset_id) AND memory.is_uuid7(prompt_id) AND memory.is_uuid7(profile_id)
  )
);

CREATE TABLE memory.memory_schedule_resumptions (
  resumption_id uuid PRIMARY KEY,
  prompt_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  resumed_at timestamptz NOT NULL,
  previous_checkpoint text NOT NULL,
  payload jsonb NOT NULL,
  CONSTRAINT fk_memory_resumption_prompt FOREIGN KEY (profile_id,prompt_id)
    REFERENCES memory.memory_prompts(profile_id,prompt_id) ON DELETE RESTRICT,
  CONSTRAINT ck_memory_resumption_uuid7 CHECK (
    memory.is_uuid7(resumption_id) AND memory.is_uuid7(prompt_id) AND memory.is_uuid7(profile_id)
  )
);

CREATE TABLE memory.memory_prompt_lineages (
  source_prompt_id uuid PRIMARY KEY,
  canonical_prompt_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  merged_at timestamptz NOT NULL,
  payload jsonb NOT NULL,
  CONSTRAINT fk_memory_lineage_prompt FOREIGN KEY (profile_id,canonical_prompt_id)
    REFERENCES memory.memory_prompts(profile_id,prompt_id) ON DELETE RESTRICT,
  CONSTRAINT ck_memory_lineage_uuid7 CHECK (
    memory.is_uuid7(source_prompt_id) AND memory.is_uuid7(canonical_prompt_id)
    AND memory.is_uuid7(profile_id) AND source_prompt_id <> canonical_prompt_id
  )
);

CREATE TABLE memory.memory_command_receipts (
  receipt_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  actor_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  command_type varchar(120) NOT NULL,
  idempotency_key varchar(255) NOT NULL,
  request_fingerprint char(64) NOT NULL,
  result_prompt_id uuid NOT NULL,
  result_payload jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT ck_memory_receipt_uuid7 CHECK (
    memory.is_uuid7(receipt_id) AND memory.is_uuid7(profile_id)
    AND memory.is_uuid7(actor_id) AND memory.is_uuid7(result_prompt_id)
  ),
  CONSTRAINT ck_memory_receipt_fingerprint CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
  CONSTRAINT uq_memory_receipt_scope UNIQUE (actor_id,command_type,idempotency_key)
);

CREATE FUNCTION memory.guard_append_only() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
  RAISE EXCEPTION 'memory fact is append-only' USING ERRCODE = '55000';
END
$function$;

CREATE TRIGGER memory_reviews_append_only BEFORE UPDATE OR DELETE ON memory.memory_reviews
FOR EACH ROW EXECUTE FUNCTION memory.guard_append_only();
CREATE TRIGGER memory_resets_append_only BEFORE UPDATE OR DELETE ON memory.memory_schedule_resets
FOR EACH ROW EXECUTE FUNCTION memory.guard_append_only();
CREATE TRIGGER memory_resumptions_append_only BEFORE UPDATE OR DELETE ON memory.memory_schedule_resumptions
FOR EACH ROW EXECUTE FUNCTION memory.guard_append_only();
CREATE TRIGGER memory_lineages_append_only BEFORE UPDATE OR DELETE ON memory.memory_prompt_lineages
FOR EACH ROW EXECUTE FUNCTION memory.guard_append_only();

DO $rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'memory_prompts','memory_schedule_states','memory_reviews',
    'memory_schedule_resets','memory_schedule_resumptions',
    'memory_prompt_lineages','memory_command_receipts'
  ] LOOP
    EXECUTE format('ALTER TABLE memory.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE memory.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON memory.%I USING (memory.owns_profile(profile_id)) WITH CHECK (memory.owns_profile(profile_id))',
      table_name || '_owner', table_name
    );
  END LOOP;
END
$rls$;

GRANT USAGE ON SCHEMA memory TO polyglot_runtime;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA memory TO polyglot_runtime;
GRANT UPDATE ON memory.memory_prompts, memory.memory_schedule_states,
  memory.memory_command_receipts TO polyglot_runtime;
GRANT USAGE, CREATE ON SCHEMA memory TO polyglot_migration;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA memory TO polyglot_migration;

ALTER FUNCTION memory.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION memory.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION memory.owns_profile(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION memory.guard_append_only() OWNER TO polyglot_migration;
"""

DROP_DDL = "DROP SCHEMA IF EXISTS memory CASCADE;"


async def _execute(connection: Connection, sql: str) -> None:
    await connection.execute(sql)


def upgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, MEMORY_DDL))


def downgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DROP_DDL))
