"""Create personal lexicon facts and Word Bank read foundations.

Revision ID: 0006_lexicon_core
Revises: 0005_content
"""

# ruff: noqa: E501

from alembic import op
from asyncpg import Connection

revision = "0006_lexicon_core"
down_revision = "0005_content"
branch_labels = None
depends_on = None


LEXICON_DDL = r"""
CREATE SCHEMA lexicon;

CREATE FUNCTION lexicon.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $function$
    SELECT value IS NOT NULL AND (get_byte(uuid_send(value), 6) >> 4) = 7
$function$;

CREATE FUNCTION lexicon.current_user_id() RETURNS uuid
LANGUAGE sql STABLE PARALLEL SAFE AS $function$
    SELECT NULLIF(current_setting('app.user_id', true), '')::uuid
$function$;

CREATE FUNCTION lexicon.owns_profile(value uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, language_profiles
AS $function$
    SELECT EXISTS (
        SELECT 1 FROM language_profiles.learner_language_profiles profile
        WHERE profile.profile_id = value
          AND profile.account_id = lexicon.current_user_id()
          AND profile.status <> 'deleted'
    )
$function$;

CREATE TABLE lexicon.lexical_reference_sets (
    reference_set_id uuid PRIMARY KEY,
    code varchar(120) NOT NULL,
    revision varchar(120) NOT NULL,
    label text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT ck_reference_set_uuid7 CHECK (lexicon.is_uuid7(reference_set_id)),
    CONSTRAINT uq_reference_set_revision UNIQUE (code, revision)
);

CREATE TABLE lexicon.lexical_reference_entries (
    reference_set_id uuid NOT NULL REFERENCES lexicon.lexical_reference_sets(reference_set_id) ON DELETE RESTRICT,
    sense_id uuid NOT NULL,
    ordinal integer NOT NULL,
    label text NOT NULL,
    definition text NOT NULL,
    PRIMARY KEY (reference_set_id, sense_id),
    CONSTRAINT uq_reference_entry_ordinal UNIQUE (reference_set_id, ordinal),
    CONSTRAINT ck_reference_entry_shape CHECK (
      lexicon.is_uuid7(reference_set_id) AND lexicon.is_uuid7(sense_id)
      AND ordinal >= 1 AND length(label) BETWEEN 1 AND 500
    )
);
CREATE INDEX ix_lexicon_reference_search
  ON lexicon.lexical_reference_entries(reference_set_id, label, sense_id);

CREATE TABLE lexicon.private_lexical_units (
    lexical_unit_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
    variety_id uuid NOT NULL,
    unit_type varchar(32) NOT NULL,
    lemma text NOT NULL,
    normalization_key text NOT NULL,
    components uuid[] NOT NULL DEFAULT '{}',
    provenance_ref text NOT NULL,
    merged_into_unit_id uuid,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL,
    CONSTRAINT ck_private_unit_uuid7 CHECK (
      lexicon.is_uuid7(lexical_unit_id) AND lexicon.is_uuid7(profile_id)
      AND lexicon.is_uuid7(variety_id)
    ),
    CONSTRAINT ck_private_unit_type CHECK (unit_type IN ('word','multiword_expression','proper_name','lexicalized_construction')),
    CONSTRAINT ck_private_unit_shape CHECK (
      length(lemma) BETWEEN 1 AND 500 AND length(normalization_key) BETWEEN 1 AND 500
      AND ((unit_type = 'multiword_expression' AND cardinality(components) >= 2)
        OR (unit_type <> 'multiword_expression' AND cardinality(components) = 0))
      AND version >= 1
    ),
    CONSTRAINT uq_private_unit_profile UNIQUE (profile_id, lexical_unit_id),
    CONSTRAINT fk_private_unit_merge_profile FOREIGN KEY (profile_id, merged_into_unit_id)
      REFERENCES lexicon.private_lexical_units(profile_id, lexical_unit_id) ON DELETE RESTRICT
);
CREATE INDEX ix_lexicon_private_unit_search
  ON lexicon.private_lexical_units(profile_id, normalization_key, lexical_unit_id);

CREATE TABLE lexicon.private_lexical_senses (
    sense_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
    lexical_unit_id uuid NOT NULL,
    sense_code varchar(120) NOT NULL,
    definition text NOT NULL,
    support_language_tag varchar(35),
    provenance_ref text NOT NULL,
    split_from_sense_id uuid,
    created_at timestamptz NOT NULL,
    CONSTRAINT ck_private_sense_uuid7 CHECK (
      lexicon.is_uuid7(sense_id) AND lexicon.is_uuid7(profile_id)
      AND lexicon.is_uuid7(lexical_unit_id)
    ),
    CONSTRAINT uq_private_sense_code UNIQUE (lexical_unit_id, sense_code),
    CONSTRAINT uq_private_sense_profile UNIQUE (profile_id, sense_id),
    CONSTRAINT fk_private_sense_unit_profile FOREIGN KEY (profile_id, lexical_unit_id)
      REFERENCES lexicon.private_lexical_units(profile_id, lexical_unit_id) ON DELETE RESTRICT
);

CREATE TABLE lexicon.lexical_encounters (
    encounter_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
    exact_surface text NOT NULL,
    source_type varchar(32) NOT NULL,
    source_ref text NOT NULL,
    source_revision_ref text NOT NULL,
    modality varchar(16) NOT NULL,
    lexical_role varchar(32) NOT NULL,
    operation varchar(32) NOT NULL,
    help_state varchar(32) NOT NULL,
    result_state varchar(32) NOT NULL,
    correction_ref text NOT NULL,
    correction_confidence numeric(5,4) NOT NULL,
    context_private text,
    context_fingerprint char(64) NOT NULL,
    context_retention varchar(32) NOT NULL,
    context_deleted_at timestamptz,
    occurred_at timestamptz NOT NULL,
    idempotency_key varchar(255) NOT NULL,
    request_fingerprint char(64) NOT NULL,
    CONSTRAINT ck_encounter_uuid7 CHECK (lexicon.is_uuid7(encounter_id) AND lexicon.is_uuid7(profile_id)),
    CONSTRAINT ck_encounter_modality CHECK (modality IN ('reading','listening','writing','speaking')),
    CONSTRAINT ck_encounter_confidence CHECK (correction_confidence BETWEEN 0 AND 1),
    CONSTRAINT ck_encounter_context_delete CHECK (
      (context_deleted_at IS NULL) OR (context_deleted_at >= occurred_at AND context_private IS NULL)
    ),
    CONSTRAINT uq_encounter_idempotency UNIQUE (profile_id, idempotency_key),
    CONSTRAINT uq_encounter_profile UNIQUE (profile_id, encounter_id)
);
CREATE INDEX ix_lexicon_encounters_profile_time
  ON lexicon.lexical_encounters(profile_id, occurred_at DESC, encounter_id DESC);
CREATE INDEX ix_lexicon_encounters_surface
  ON lexicon.lexical_encounters(profile_id, lower(exact_surface), encounter_id);

CREATE TABLE lexicon.lexical_mentions (
    mention_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
    encounter_id uuid NOT NULL,
    exact_surface text NOT NULL,
    form_analysis_id uuid,
    analysis_revision_ref text NOT NULL,
    ordinal integer NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT ck_mention_uuid7 CHECK (
      lexicon.is_uuid7(mention_id) AND lexicon.is_uuid7(profile_id)
      AND lexicon.is_uuid7(encounter_id) AND (form_analysis_id IS NULL OR lexicon.is_uuid7(form_analysis_id))
    ),
    CONSTRAINT ck_mention_ordinal CHECK (ordinal >= 1),
    CONSTRAINT uq_mention_encounter_ordinal UNIQUE (encounter_id, ordinal),
    CONSTRAINT uq_mention_profile UNIQUE (profile_id, mention_id),
    CONSTRAINT fk_mention_encounter_profile FOREIGN KEY (profile_id, encounter_id)
      REFERENCES lexicon.lexical_encounters(profile_id, encounter_id) ON DELETE RESTRICT
);
CREATE INDEX ix_lexicon_mentions_unresolved
  ON lexicon.lexical_mentions(profile_id, mention_id);

CREATE TABLE lexicon.mention_candidates (
    candidate_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
    mention_id uuid NOT NULL,
    sense_id uuid NOT NULL,
    sense_scope varchar(16) NOT NULL,
    confidence numeric(5,4) NOT NULL,
    source varchar(120) NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT ck_candidate_uuid7 CHECK (
      lexicon.is_uuid7(candidate_id) AND lexicon.is_uuid7(profile_id)
      AND lexicon.is_uuid7(mention_id) AND lexicon.is_uuid7(sense_id)
    ),
    CONSTRAINT ck_candidate_scope CHECK (sense_scope IN ('shared','private')),
    CONSTRAINT ck_candidate_confidence CHECK (confidence BETWEEN 0 AND 1),
    CONSTRAINT uq_candidate_mention_sense UNIQUE (mention_id, sense_id),
    CONSTRAINT uq_candidate_profile UNIQUE (profile_id, candidate_id),
    CONSTRAINT fk_candidate_mention_profile FOREIGN KEY (profile_id, mention_id)
      REFERENCES lexicon.lexical_mentions(profile_id, mention_id) ON DELETE RESTRICT
);

CREATE TABLE lexicon.mention_resolutions (
    resolution_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
    mention_id uuid NOT NULL,
    candidate_id uuid NOT NULL,
    sense_id uuid NOT NULL,
    resolver_type varchar(32) NOT NULL,
    confidence numeric(5,4) NOT NULL,
    supersedes_resolution_id uuid,
    created_at timestamptz NOT NULL,
    idempotency_key varchar(255) NOT NULL,
    request_fingerprint char(64) NOT NULL,
    CONSTRAINT ck_resolution_uuid7 CHECK (
      lexicon.is_uuid7(resolution_id) AND lexicon.is_uuid7(profile_id)
      AND lexicon.is_uuid7(mention_id) AND lexicon.is_uuid7(candidate_id)
      AND lexicon.is_uuid7(sense_id)
    ),
    CONSTRAINT ck_resolution_confidence CHECK (confidence BETWEEN 0 AND 1),
    CONSTRAINT uq_resolution_idempotency UNIQUE (profile_id, idempotency_key),
    CONSTRAINT uq_resolution_profile UNIQUE (profile_id, resolution_id),
    CONSTRAINT fk_resolution_mention_profile FOREIGN KEY (profile_id, mention_id)
      REFERENCES lexicon.lexical_mentions(profile_id, mention_id) ON DELETE RESTRICT,
    CONSTRAINT fk_resolution_candidate_profile FOREIGN KEY (profile_id, candidate_id)
      REFERENCES lexicon.mention_candidates(profile_id, candidate_id) ON DELETE RESTRICT,
    CONSTRAINT fk_resolution_supersedes_profile FOREIGN KEY (profile_id, supersedes_resolution_id)
      REFERENCES lexicon.mention_resolutions(profile_id, resolution_id) ON DELETE RESTRICT
);
CREATE INDEX ix_lexicon_resolution_current
  ON lexicon.mention_resolutions(profile_id, mention_id, created_at DESC, resolution_id DESC);

CREATE TABLE lexicon.personal_lexical_relations (
    relation_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
    source_sense_id uuid NOT NULL,
    target_sense_id uuid NOT NULL,
    relation_type varchar(32) NOT NULL,
    direction varchar(16) NOT NULL,
    provenance_ref text NOT NULL,
    confidence numeric(5,4) NOT NULL,
    created_at timestamptz NOT NULL,
    version integer NOT NULL DEFAULT 1,
    CONSTRAINT ck_relation_uuid7 CHECK (
      lexicon.is_uuid7(relation_id) AND lexicon.is_uuid7(profile_id)
      AND lexicon.is_uuid7(source_sense_id) AND lexicon.is_uuid7(target_sense_id)
    ),
    CONSTRAINT ck_relation_shape CHECK (
      source_sense_id <> target_sense_id AND direction IN ('directed','bidirectional')
      AND confidence BETWEEN 0 AND 1 AND version >= 1
    ),
    CONSTRAINT uq_relation_profile UNIQUE (profile_id, relation_id)
);
CREATE INDEX ix_lexicon_relations_source
  ON lexicon.personal_lexical_relations(profile_id, source_sense_id, relation_type, relation_id);
CREATE INDEX ix_lexicon_relations_target
  ON lexicon.personal_lexical_relations(profile_id, target_sense_id, relation_type, relation_id);

CREATE TABLE lexicon.lexical_relation_retractions (
    retraction_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
    relation_id uuid NOT NULL,
    reason text NOT NULL,
    retracted_at timestamptz NOT NULL,
    idempotency_key varchar(255) NOT NULL,
    request_fingerprint char(64) NOT NULL,
    CONSTRAINT ck_retraction_uuid7 CHECK (
      lexicon.is_uuid7(retraction_id) AND lexicon.is_uuid7(profile_id) AND lexicon.is_uuid7(relation_id)
    ),
    CONSTRAINT uq_retraction_relation UNIQUE (relation_id),
    CONSTRAINT uq_retraction_idempotency UNIQUE (profile_id, idempotency_key),
    CONSTRAINT fk_retraction_relation_profile FOREIGN KEY (profile_id, relation_id)
      REFERENCES lexicon.personal_lexical_relations(profile_id, relation_id) ON DELETE RESTRICT
);

CREATE TABLE lexicon.lexical_declarations (
    declaration_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
    sense_id uuid NOT NULL,
    familiarity varchar(32) NOT NULL,
    declared_at timestamptz NOT NULL,
    supersedes_declaration_id uuid,
    idempotency_key varchar(255) NOT NULL,
    request_fingerprint char(64) NOT NULL,
    CONSTRAINT ck_declaration_uuid7 CHECK (
      lexicon.is_uuid7(declaration_id) AND lexicon.is_uuid7(profile_id) AND lexicon.is_uuid7(sense_id)
    ),
    CONSTRAINT uq_declaration_idempotency UNIQUE (profile_id, idempotency_key),
    CONSTRAINT uq_declaration_profile UNIQUE (profile_id, declaration_id),
    CONSTRAINT fk_declaration_supersedes_profile FOREIGN KEY (profile_id, supersedes_declaration_id)
      REFERENCES lexicon.lexical_declarations(profile_id, declaration_id) ON DELETE RESTRICT
);

CREATE TABLE lexicon.lexical_preferences (
    preference_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
    sense_id uuid NOT NULL,
    preference varchar(16) NOT NULL,
    version integer NOT NULL,
    set_at timestamptz NOT NULL,
    idempotency_key varchar(255) NOT NULL,
    request_fingerprint char(64) NOT NULL,
    CONSTRAINT ck_preference_uuid7 CHECK (
      lexicon.is_uuid7(preference_id) AND lexicon.is_uuid7(profile_id) AND lexicon.is_uuid7(sense_id)
    ),
    CONSTRAINT ck_preference_value CHECK (preference IN ('normal','prioritize','ignore') AND version >= 1),
    CONSTRAINT uq_preference_profile_sense UNIQUE (profile_id, sense_id),
    CONSTRAINT uq_preference_idempotency UNIQUE (profile_id, idempotency_key)
);

CREATE TABLE lexicon.lexical_annotations (
    annotation_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
    sense_id uuid NOT NULL,
    version integer NOT NULL,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT ck_annotation_uuid7 CHECK (
      lexicon.is_uuid7(annotation_id) AND lexicon.is_uuid7(profile_id) AND lexicon.is_uuid7(sense_id)
    ),
    CONSTRAINT ck_annotation_version CHECK (version >= 1 AND updated_at >= created_at),
    CONSTRAINT uq_annotation_profile_sense UNIQUE (profile_id, sense_id),
    CONSTRAINT uq_annotation_profile UNIQUE (profile_id, annotation_id)
);
CREATE INDEX ix_lexicon_annotations_profile_sense
  ON lexicon.lexical_annotations(profile_id, sense_id, annotation_id);

CREATE TABLE lexicon.lexical_annotation_revisions (
    annotation_revision_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
    annotation_id uuid NOT NULL,
    version integer NOT NULL,
    body text NOT NULL,
    created_at timestamptz NOT NULL,
    idempotency_key varchar(255) NOT NULL,
    request_fingerprint char(64) NOT NULL,
    CONSTRAINT ck_annotation_revision_uuid7 CHECK (
      lexicon.is_uuid7(annotation_revision_id) AND lexicon.is_uuid7(profile_id)
      AND lexicon.is_uuid7(annotation_id)
    ),
    CONSTRAINT ck_annotation_revision_version CHECK (version >= 1),
    CONSTRAINT uq_annotation_revision UNIQUE (annotation_id, version),
    CONSTRAINT uq_annotation_revision_idempotency UNIQUE (profile_id, idempotency_key),
    CONSTRAINT fk_annotation_revision_profile FOREIGN KEY (profile_id, annotation_id)
      REFERENCES lexicon.lexical_annotations(profile_id, annotation_id) ON DELETE RESTRICT
);

CREATE TABLE lexicon.lexicon_command_receipts (
    receipt_id uuid PRIMARY KEY,
    profile_id uuid NOT NULL REFERENCES language_profiles.learner_language_profiles(profile_id) ON DELETE RESTRICT,
    command_name varchar(120) NOT NULL,
    idempotency_key varchar(255) NOT NULL,
    request_fingerprint char(64) NOT NULL,
    resource_id uuid NOT NULL,
    result_payload jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT ck_lexicon_receipt_uuid7 CHECK (
      lexicon.is_uuid7(receipt_id) AND lexicon.is_uuid7(profile_id) AND lexicon.is_uuid7(resource_id)
    ),
    CONSTRAINT uq_lexicon_receipt_key UNIQUE (profile_id, command_name, idempotency_key)
);

CREATE FUNCTION lexicon.guard_append_only() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
  RAISE EXCEPTION 'lexicon fact is append-only' USING ERRCODE = '55000';
END
$function$;

CREATE FUNCTION lexicon.guard_encounter_update() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
  IF OLD.context_deleted_at IS NULL
     AND NEW.context_deleted_at IS NOT NULL
     AND NEW.context_private IS NULL
     AND (to_jsonb(NEW) - ARRAY['context_private','context_deleted_at'])
         = (to_jsonb(OLD) - ARRAY['context_private','context_deleted_at']) THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'lexical encounter is append-only' USING ERRCODE = '55000';
END
$function$;

CREATE TRIGGER lexical_encounters_no_delete BEFORE DELETE ON lexicon.lexical_encounters
FOR EACH ROW EXECUTE FUNCTION lexicon.guard_append_only();
CREATE TRIGGER lexical_encounters_guard_update BEFORE UPDATE ON lexicon.lexical_encounters
FOR EACH ROW EXECUTE FUNCTION lexicon.guard_encounter_update();
CREATE TRIGGER lexical_mentions_append_only BEFORE UPDATE OR DELETE ON lexicon.lexical_mentions
FOR EACH ROW EXECUTE FUNCTION lexicon.guard_append_only();
CREATE TRIGGER mention_candidates_append_only BEFORE UPDATE OR DELETE ON lexicon.mention_candidates
FOR EACH ROW EXECUTE FUNCTION lexicon.guard_append_only();
CREATE TRIGGER mention_resolutions_append_only BEFORE UPDATE OR DELETE ON lexicon.mention_resolutions
FOR EACH ROW EXECUTE FUNCTION lexicon.guard_append_only();
CREATE TRIGGER lexical_declarations_append_only BEFORE UPDATE OR DELETE ON lexicon.lexical_declarations
FOR EACH ROW EXECUTE FUNCTION lexicon.guard_append_only();
CREATE TRIGGER annotation_revisions_append_only BEFORE UPDATE OR DELETE ON lexicon.lexical_annotation_revisions
FOR EACH ROW EXECUTE FUNCTION lexicon.guard_append_only();

DO $rls$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'private_lexical_units','private_lexical_senses','lexical_encounters','lexical_mentions',
    'mention_candidates','mention_resolutions','personal_lexical_relations',
    'lexical_relation_retractions','lexical_declarations','lexical_preferences',
    'lexical_annotations','lexical_annotation_revisions','lexicon_command_receipts'
  ] LOOP
    EXECUTE format('ALTER TABLE lexicon.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE lexicon.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON lexicon.%I USING (lexicon.owns_profile(profile_id)) WITH CHECK (lexicon.owns_profile(profile_id))',
      table_name || '_owner', table_name
    );
  END LOOP;
END
$rls$;

GRANT USAGE ON SCHEMA lexicon TO polyglot_runtime;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA lexicon TO polyglot_runtime;
GRANT USAGE ON SCHEMA lexicon TO polyglot_migration;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA lexicon TO polyglot_migration;

ALTER FUNCTION lexicon.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION lexicon.current_user_id() OWNER TO polyglot_migration;
ALTER FUNCTION lexicon.owns_profile(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION lexicon.guard_append_only() OWNER TO polyglot_migration;
ALTER FUNCTION lexicon.guard_encounter_update() OWNER TO polyglot_migration;
"""


DROP_DDL = r"""
DROP SCHEMA IF EXISTS lexicon CASCADE;
"""


async def _execute(connection: Connection, sql: str) -> None:
    await connection.execute(sql)


def upgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, LEXICON_DDL))


def downgrade() -> None:
    op.get_bind().connection.run_async(lambda connection: _execute(connection, DROP_DDL))
