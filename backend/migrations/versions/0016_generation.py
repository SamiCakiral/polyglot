"""Persist deterministic authoring tools and generation jobs.

Revision ID: 0016_generation
Revises: 0015_media
"""

# ruff: noqa: E501

import hashlib
import json
from importlib.resources import files
from pathlib import Path

from alembic import op
from asyncpg import Connection

revision = "0016_generation"
down_revision = "0015_media"
branch_labels = None
depends_on = None

TOOLS = (
    ("profile.read_authorized", ("learner", "author"), "none", 10000),
    ("catalogue.list_targets", ("learner", "author", "reviewer", "support", "admin"), "none", 10000),
    ("lexicon.read_session_scope", ("learner", "author"), "none", 10000),
    ("exercise.get_blueprint", ("author", "reviewer", "worker"), "none", 10000),
    ("exercise.submit_draft", ("author",), "create_draft", 60000),
    ("content.validate_draft", ("author", "reviewer"), "create_validation_report", 30000),
    ("curriculum.submit_module_draft", ("author",), "create_module_draft", 60000),
    ("curriculum.submit_day_draft", ("author",), "create_day_draft", 60000),
    ("correction.submit_structured_draft", ("reviewer", "worker"), "create_correction_revision_draft", 30000),
    ("quality.report_ambiguity", ("learner", "author", "reviewer"), "create_quality_report", 30000),
    ("progress.explain_recommendation", ("learner", "support"), "none", 10000),
)

DDL = r"""
CREATE SCHEMA generation AUTHORIZATION polyglot_migration;

CREATE FUNCTION generation.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
  SELECT value IS NOT NULL AND (get_byte(uuid_send(value),6) >> 4) = 7
$function$;
CREATE FUNCTION generation.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE AS $function$
  SELECT NULLIF(current_setting('app.user_id',true),'')::uuid
$function$;
CREATE FUNCTION generation.guard_append_only() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
  RAISE EXCEPTION 'generation fact is append-only' USING ERRCODE='55000';
END
$function$;

CREATE TABLE generation.tool_revisions (
  tool_revision_id uuid PRIMARY KEY,
  tool_name varchar(120) NOT NULL,
  tool_version varchar(32) NOT NULL,
  allowed_roles varchar(32)[] NOT NULL,
  effect varchar(80) NOT NULL,
  input_schema jsonb NOT NULL,
  output_schema jsonb NOT NULL,
  timeout_ms integer NOT NULL,
  max_input_bytes integer NOT NULL,
  max_output_bytes integer NOT NULL,
  checksum char(64) NOT NULL,
  published_at timestamptz NOT NULL,
  CONSTRAINT uq_tool_revision UNIQUE (tool_name,tool_version),
  CONSTRAINT ck_tool_revision_uuid7 CHECK (generation.is_uuid7(tool_revision_id)),
  CONSTRAINT ck_tool_revision_shape CHECK (
    tool_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$' AND cardinality(allowed_roles)>=1
    AND effect IN ('none','create_draft','create_validation_report','create_module_draft',
      'create_day_draft','create_correction_revision_draft','create_quality_report')
    AND jsonb_typeof(input_schema)='object' AND jsonb_typeof(output_schema)='object'
    AND timeout_ms BETWEEN 1 AND 60000 AND max_input_bytes BETWEEN 1 AND 262144
    AND max_output_bytes BETWEEN 1 AND 1048576 AND checksum ~ '^[0-9a-f]{64}$'
  )
);

CREATE TABLE generation.generation_jobs (
  job_id uuid PRIMARY KEY REFERENCES platform.jobs(job_id) ON DELETE RESTRICT,
  owner_account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  task_type varchar(120) NOT NULL,
  task_input jsonb NOT NULL,
  tool_allowlist varchar(180)[] NOT NULL,
  provider_code varchar(120) NOT NULL,
  model_code varchar(160) NOT NULL,
  prompt_revision varchar(120) NOT NULL,
  max_attempts smallint NOT NULL,
  max_input_tokens integer NOT NULL,
  max_output_tokens integer NOT NULL,
  max_cost_micros bigint NOT NULL,
  result_draft_id uuid,
  created_at timestamptz NOT NULL,
  CONSTRAINT ck_generation_job_uuid7 CHECK (
    generation.is_uuid7(job_id) AND generation.is_uuid7(owner_account_id)
    AND (result_draft_id IS NULL OR generation.is_uuid7(result_draft_id))
  ),
  CONSTRAINT ck_generation_job_shape CHECK (
    jsonb_typeof(task_input)='object' AND cardinality(tool_allowlist)>=1
    AND max_attempts BETWEEN 1 AND 3 AND LEAST(max_input_tokens,max_output_tokens)>0
    AND max_cost_micros>0
  )
);

CREATE TABLE generation.generation_attempts (
  generation_attempt_id uuid PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES generation.generation_jobs(job_id) ON DELETE RESTRICT,
  owner_account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  attempt_no smallint NOT NULL,
  provider_code varchar(120) NOT NULL,
  model_code varchar(160) NOT NULL,
  prompt_revision varchar(120) NOT NULL,
  tool_versions varchar(180)[] NOT NULL,
  input_fingerprint char(64) NOT NULL,
  status varchar(24) NOT NULL,
  error_code varchar(120),
  input_tokens integer NOT NULL,
  output_tokens integer NOT NULL,
  cost_micros bigint NOT NULL,
  started_at timestamptz NOT NULL,
  finished_at timestamptz NOT NULL,
  CONSTRAINT uq_generation_attempt UNIQUE (job_id,attempt_no),
  CONSTRAINT ck_generation_attempt_uuid7 CHECK (
    generation.is_uuid7(generation_attempt_id) AND generation.is_uuid7(job_id)
    AND generation.is_uuid7(owner_account_id)
  ),
  CONSTRAINT ck_generation_attempt_shape CHECK (
    attempt_no>=1 AND cardinality(tool_versions)>=1
    AND input_fingerprint ~ '^[0-9a-f]{64}$'
    AND status IN ('succeeded','failed','cancelled')
    AND LEAST(input_tokens,output_tokens,cost_micros)>=0 AND finished_at>=started_at
  )
);

CREATE TABLE generation.tool_invocations (
  invocation_id uuid PRIMARY KEY,
  owner_account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  tool_revision_id uuid NOT NULL REFERENCES generation.tool_revisions(tool_revision_id) ON DELETE RESTRICT,
  tool_name varchar(120) NOT NULL,
  actor_role varchar(32) NOT NULL,
  scope jsonb NOT NULL,
  idempotency_key varchar(255) NOT NULL,
  request_fingerprint char(64) NOT NULL,
  input_payload jsonb NOT NULL,
  status varchar(24) NOT NULL,
  output_payload jsonb,
  error_payload jsonb,
  output_fingerprint char(64) NOT NULL,
  provenance_id uuid NOT NULL,
  correlation_id uuid NOT NULL,
  causation_id uuid,
  started_at timestamptz NOT NULL,
  finished_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  CONSTRAINT uq_tool_invocation_idempotency UNIQUE (owner_account_id,tool_name,idempotency_key),
  CONSTRAINT ck_tool_invocation_uuid7 CHECK (
    generation.is_uuid7(invocation_id) AND generation.is_uuid7(owner_account_id)
    AND generation.is_uuid7(tool_revision_id) AND generation.is_uuid7(provenance_id)
    AND generation.is_uuid7(correlation_id)
    AND (causation_id IS NULL OR generation.is_uuid7(causation_id))
  ),
  CONSTRAINT ck_tool_invocation_shape CHECK (
    jsonb_typeof(scope)='object' AND jsonb_typeof(input_payload)='object'
    AND status IN ('succeeded','rejected','failed')
    AND ((output_payload IS NULL)<>(error_payload IS NULL))
    AND request_fingerprint ~ '^[0-9a-f]{64}$' AND output_fingerprint ~ '^[0-9a-f]{64}$'
    AND finished_at>=started_at AND expires_at>finished_at
  )
);

CREATE TABLE generation.authoring_artifacts (
  artifact_id uuid PRIMARY KEY,
  owner_account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  source_invocation_id uuid NOT NULL REFERENCES generation.tool_invocations(invocation_id) ON DELETE RESTRICT,
  source_tool_name varchar(120) NOT NULL,
  artifact_type varchar(80) NOT NULL,
  status varchar(24) NOT NULL,
  payload jsonb NOT NULL,
  checksum char(64) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT ck_authoring_artifact_uuid7 CHECK (
    generation.is_uuid7(artifact_id) AND generation.is_uuid7(owner_account_id)
    AND generation.is_uuid7(source_invocation_id)
  ),
  CONSTRAINT ck_authoring_artifact_shape CHECK (
    artifact_type IN ('exercise','module','day','correction','validation_report','quality_report')
    AND status IN ('draft','human_required','open') AND jsonb_typeof(payload)='object'
    AND checksum ~ '^[0-9a-f]{64}$'
  )
);

CREATE TABLE generation.runner_transcripts (
  transcript_id uuid PRIMARY KEY,
  owner_account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  scenario_code varchar(120) NOT NULL,
  scenario_version integer NOT NULL,
  seed bigint NOT NULL,
  frozen_clock timestamptz NOT NULL,
  lines jsonb NOT NULL,
  checksum char(64) NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT ck_runner_transcript_uuid7 CHECK (
    generation.is_uuid7(transcript_id) AND generation.is_uuid7(owner_account_id)
  ),
  CONSTRAINT ck_runner_transcript_shape CHECK (
    scenario_version>=1 AND jsonb_typeof(lines)='array' AND checksum ~ '^[0-9a-f]{64}$'
  )
);

CREATE TRIGGER guard_generation_attempts BEFORE UPDATE OR DELETE
  ON generation.generation_attempts FOR EACH ROW EXECUTE FUNCTION generation.guard_append_only();
CREATE TRIGGER guard_tool_invocations BEFORE UPDATE OR DELETE
  ON generation.tool_invocations FOR EACH ROW EXECUTE FUNCTION generation.guard_append_only();
CREATE TRIGGER guard_authoring_artifacts BEFORE UPDATE OR DELETE
  ON generation.authoring_artifacts FOR EACH ROW EXECUTE FUNCTION generation.guard_append_only();
CREATE TRIGGER guard_runner_transcripts BEFORE UPDATE OR DELETE
  ON generation.runner_transcripts FOR EACH ROW EXECUTE FUNCTION generation.guard_append_only();

ALTER TABLE generation.tool_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE generation.tool_revisions FORCE ROW LEVEL SECURITY;
CREATE POLICY tool_revisions_read ON generation.tool_revisions FOR SELECT USING (true);
CREATE POLICY tool_revisions_migration ON generation.tool_revisions TO polyglot_migration USING (true) WITH CHECK (true);

DO $rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'generation_jobs','generation_attempts','tool_invocations','authoring_artifacts','runner_transcripts'
  ] LOOP
    EXECUTE format('ALTER TABLE generation.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE generation.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY %I ON generation.%I USING (owner_account_id=generation.current_user_id()) WITH CHECK (owner_account_id=generation.current_user_id())',
      table_name || '_owner',table_name
    );
    EXECUTE format('CREATE POLICY %I ON generation.%I TO polyglot_migration USING (true) WITH CHECK (true)',table_name || '_migration',table_name);
  END LOOP;
END $rls$;

GRANT USAGE ON SCHEMA generation TO polyglot_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA generation TO polyglot_runtime;
GRANT INSERT ON generation.generation_jobs,generation.generation_attempts,
  generation.tool_invocations,generation.authoring_artifacts,generation.runner_transcripts TO polyglot_runtime;
GRANT UPDATE ON generation.generation_jobs TO polyglot_runtime;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA generation TO polyglot_migration;
REVOKE DELETE,TRUNCATE ON ALL TABLES IN SCHEMA generation FROM polyglot_runtime;
REVOKE ALL ON ALL TABLES IN SCHEMA generation FROM PUBLIC;

ALTER FUNCTION generation.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION generation.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION generation.guard_append_only() OWNER TO polyglot_migration;
DO $owners$ DECLARE item record; BEGIN
  FOR item IN SELECT tablename FROM pg_tables WHERE schemaname='generation' LOOP
    EXECUTE format('ALTER TABLE generation.%I OWNER TO polyglot_migration',item.tablename);
  END LOOP;
END $owners$;
"""

DROP_DDL = "DROP SCHEMA IF EXISTS generation CASCADE;"


def _tool_rows() -> str:
    rows: list[str] = []

    def contract(name: str, kind: str) -> object:
        filename = f"{name}.{kind}.schema.json"
        packaged = files("polyglot.interfaces.tools").joinpath("contracts", filename)
        try:
            raw = packaged.read_text(encoding="utf-8")
        except FileNotFoundError:
            root = Path(__file__).resolve().parents[3]
            raw = (root / "contracts" / "tools" / filename).read_text()
        return json.loads(raw)

    for ordinal, (name, roles, effect, timeout_ms) in enumerate(TOOLS, start=1):
        schema = contract(name, "input")
        output = contract(name, "output")
        canonical = json.dumps(
            {
                "name": name,
                "version": "1.0.0",
                "roles": roles,
                "effect": effect,
                "input": schema,
                "output": output,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        checksum = hashlib.sha256(canonical.encode()).hexdigest()
        escaped_name = name.replace("'", "''")
        role_sql = ",".join(f"'{role}'" for role in roles)
        rows.append(
            "("
            f"'019fec16-0000-7000-8000-{ordinal:012x}','{escaped_name}','1.0.0',"
            f"ARRAY[{role_sql}],'{effect}','{json.dumps(schema)}'::jsonb,"
            f"'{json.dumps(output)}'::jsonb,{timeout_ms},262144,1048576,'{checksum}',"
            "'2026-08-10T00:00:00Z')"
        )
    return ",\n".join(rows)


async def _upgrade(connection: Connection) -> None:
    await connection.execute(DDL)
    await connection.execute(
        "INSERT INTO generation.tool_revisions "
        "(tool_revision_id,tool_name,tool_version,allowed_roles,effect,input_schema,output_schema,"
        "timeout_ms,max_input_bytes,max_output_bytes,checksum,published_at) VALUES "
        + _tool_rows()
    )


async def _downgrade(connection: Connection) -> None:
    await connection.execute(DROP_DDL)


def upgrade() -> None:
    op.get_bind().connection.run_async(_upgrade)


def downgrade() -> None:
    op.get_bind().connection.run_async(_downgrade)
