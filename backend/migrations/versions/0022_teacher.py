"""Add local teacher conversations and compensating actions.

Revision ID: 0022_teacher
Revises: 0021_practice_stacks
"""

# ruff: noqa: E501

from alembic import op
from asyncpg import Connection

revision = "0022_teacher"
down_revision = "0021_practice_stacks"
branch_labels = None
depends_on = None

DDL = r"""
CREATE SCHEMA teacher AUTHORIZATION polyglot_migration;

CREATE FUNCTION teacher.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
  SELECT value IS NOT NULL AND (get_byte(uuid_send(value),6) >> 4) = 7
$function$;
CREATE FUNCTION teacher.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE AS $function$
  SELECT NULLIF(current_setting('app.user_id',true),'')::uuid
$function$;
CREATE FUNCTION teacher.owns_profile(value uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog,language_profiles,teacher AS $function$
  SELECT EXISTS (
    SELECT 1 FROM language_profiles.learner_language_profiles profile
    WHERE profile.profile_id=value AND profile.account_id=teacher.current_user_id()
      AND profile.status <> 'deleted'
  )
$function$;
CREATE FUNCTION teacher.guard_append_only() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
  RAISE EXCEPTION 'teacher history is append-only' USING ERRCODE='55000';
END
$function$;

CREATE TABLE teacher.conversations (
  conversation_id uuid PRIMARY KEY,
  profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
  title varchar(160) NOT NULL,
  status varchar(20) NOT NULL DEFAULT 'active',
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT uq_teacher_conversation_profile UNIQUE(profile_id,conversation_id),
  CONSTRAINT ck_teacher_conversation_uuid7 CHECK (teacher.is_uuid7(conversation_id) AND teacher.is_uuid7(profile_id)),
  CONSTRAINT ck_teacher_conversation_shape CHECK (length(title) BETWEEN 1 AND 160 AND status IN ('active','archived') AND version >= 1 AND updated_at >= created_at)
);

CREATE TABLE teacher.messages (
  message_id uuid PRIMARY KEY,
  conversation_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  role varchar(16) NOT NULL,
  content text NOT NULL,
  provider_code varchar(40),
  model_code varchar(160),
  input_tokens integer NOT NULL DEFAULT 0,
  output_tokens integer NOT NULL DEFAULT 0,
  context_snapshot jsonb NOT NULL,
  created_at timestamptz NOT NULL,
  CONSTRAINT fk_teacher_message_conversation FOREIGN KEY(profile_id,conversation_id) REFERENCES teacher.conversations(profile_id,conversation_id) ON DELETE RESTRICT,
  CONSTRAINT uq_teacher_message_profile UNIQUE(profile_id,message_id),
  CONSTRAINT ck_teacher_message_uuid7 CHECK (teacher.is_uuid7(message_id) AND teacher.is_uuid7(conversation_id) AND teacher.is_uuid7(profile_id)),
  CONSTRAINT ck_teacher_message_shape CHECK (role IN ('user','assistant') AND length(content) BETWEEN 1 AND 12000 AND input_tokens >= 0 AND output_tokens >= 0 AND jsonb_typeof(context_snapshot)='object' AND ((role='assistant')=(provider_code IS NOT NULL AND model_code IS NOT NULL)))
);

CREATE TABLE teacher.actions (
  action_id uuid PRIMARY KEY,
  conversation_id uuid NOT NULL,
  message_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  action_type varchar(40) NOT NULL,
  status varchar(20) NOT NULL,
  payload jsonb NOT NULL,
  inverse_payload jsonb NOT NULL,
  version integer NOT NULL,
  applied_at timestamptz NOT NULL,
  reverted_at timestamptz,
  CONSTRAINT fk_teacher_action_conversation FOREIGN KEY(profile_id,conversation_id) REFERENCES teacher.conversations(profile_id,conversation_id) ON DELETE RESTRICT,
  CONSTRAINT fk_teacher_action_message FOREIGN KEY(profile_id,message_id) REFERENCES teacher.messages(profile_id,message_id) ON DELETE RESTRICT,
  CONSTRAINT uq_teacher_action_profile UNIQUE(profile_id,action_id),
  CONSTRAINT ck_teacher_action_uuid7 CHECK (teacher.is_uuid7(action_id) AND teacher.is_uuid7(conversation_id) AND teacher.is_uuid7(message_id) AND teacher.is_uuid7(profile_id)),
  CONSTRAINT ck_teacher_action_shape CHECK (action_type IN ('add_word_to_list','create_learning_debt','prepare_exercise','create_practice_preset','record_encounter') AND status IN ('applied','reverted') AND jsonb_typeof(payload)='object' AND jsonb_typeof(inverse_payload)='object' AND version >= 1 AND ((status='reverted')=(reverted_at IS NOT NULL)))
);

CREATE TABLE teacher.action_events (
  event_id uuid PRIMARY KEY,
  action_id uuid NOT NULL,
  conversation_id uuid NOT NULL,
  profile_id uuid NOT NULL,
  event_type varchar(40) NOT NULL,
  payload jsonb NOT NULL,
  occurred_at timestamptz NOT NULL,
  CONSTRAINT fk_teacher_action_event FOREIGN KEY(profile_id,action_id) REFERENCES teacher.actions(profile_id,action_id) ON DELETE RESTRICT,
  CONSTRAINT ck_teacher_action_event_uuid7 CHECK (teacher.is_uuid7(event_id) AND teacher.is_uuid7(action_id) AND teacher.is_uuid7(conversation_id) AND teacher.is_uuid7(profile_id)),
  CONSTRAINT ck_teacher_action_event_shape CHECK (event_type IN ('teacher_action_applied','teacher_action_reverted') AND jsonb_typeof(payload)='object')
);

CREATE TABLE teacher.command_receipts (
  receipt_id uuid PRIMARY KEY,
  actor_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
  command_type varchar(50) NOT NULL,
  idempotency_key varchar(255) NOT NULL,
  request_fingerprint char(64) NOT NULL,
  status varchar(16) NOT NULL,
  result_id uuid,
  created_at timestamptz NOT NULL,
  completed_at timestamptz,
  CONSTRAINT uq_teacher_command UNIQUE(actor_id,command_type,idempotency_key),
  CONSTRAINT ck_teacher_receipt_uuid7 CHECK (teacher.is_uuid7(receipt_id) AND teacher.is_uuid7(actor_id) AND (result_id IS NULL OR teacher.is_uuid7(result_id))),
  CONSTRAINT ck_teacher_receipt_shape CHECK (request_fingerprint ~ '^[0-9a-f]{64}$' AND status IN ('started','succeeded','failed') AND ((status='started')=(completed_at IS NULL)) AND ((status='succeeded')=(result_id IS NOT NULL)))
);

CREATE INDEX ix_teacher_conversations_profile ON teacher.conversations(profile_id,updated_at DESC);
CREATE INDEX ix_teacher_messages_conversation ON teacher.messages(conversation_id,created_at,message_id);
CREATE INDEX ix_teacher_actions_conversation ON teacher.actions(conversation_id,applied_at,action_id);
CREATE INDEX ix_teacher_action_events_action ON teacher.action_events(action_id,occurred_at);

CREATE TRIGGER teacher_messages_append_only BEFORE UPDATE OR DELETE ON teacher.messages FOR EACH ROW EXECUTE FUNCTION teacher.guard_append_only();
CREATE TRIGGER teacher_action_events_append_only BEFORE UPDATE OR DELETE ON teacher.action_events FOR EACH ROW EXECUTE FUNCTION teacher.guard_append_only();

DO $rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['conversations','messages','actions','action_events'] LOOP
    EXECUTE format('ALTER TABLE teacher.%I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE teacher.%I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format('CREATE POLICY %I ON teacher.%I USING (teacher.owns_profile(profile_id)) WITH CHECK (teacher.owns_profile(profile_id))',table_name || '_owner',table_name);
  END LOOP;
  ALTER TABLE teacher.command_receipts ENABLE ROW LEVEL SECURITY;
  ALTER TABLE teacher.command_receipts FORCE ROW LEVEL SECURITY;
  CREATE POLICY teacher_receipts_owner ON teacher.command_receipts USING (actor_id=teacher.current_user_id()) WITH CHECK (actor_id=teacher.current_user_id());
END
$rls$;

GRANT USAGE ON SCHEMA teacher TO polyglot_runtime;
GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA teacher TO polyglot_runtime;
GRANT UPDATE ON teacher.conversations,teacher.actions,teacher.command_receipts TO polyglot_runtime;
GRANT USAGE,CREATE ON SCHEMA teacher TO polyglot_migration;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA teacher TO polyglot_migration;
ALTER FUNCTION teacher.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION teacher.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION teacher.owns_profile(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION teacher.guard_append_only() OWNER TO polyglot_migration;
"""

DROP_DDL = "DROP SCHEMA IF EXISTS teacher CASCADE;"


async def _execute(connection: Connection, sql: str) -> None:
    await connection.execute(sql)


def upgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DDL))


def downgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DROP_DDL))
