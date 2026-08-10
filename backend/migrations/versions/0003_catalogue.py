"""Create the revisioned shared language catalogue.

Revision ID: 0003_catalogue
Revises: 0002_identity
"""

from alembic import op
from asyncpg import Connection

revision = "0003_catalogue"
down_revision = "0002_identity"
branch_labels = None
depends_on = None


CATALOGUE_DDL = r"""
CREATE SCHEMA catalogue;

CREATE FUNCTION catalogue.is_uuid7(value uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $function$
    SELECT value IS NOT NULL AND (get_byte(uuid_send(value), 6) >> 4) = 7
$function$;

CREATE TABLE catalogue.language_varieties (
    variety_id uuid PRIMARY KEY,
    language_tag varchar(35) NOT NULL UNIQUE,
    region_code varchar(8),
    script_codes varchar(16)[] NOT NULL,
    text_direction varchar(3) NOT NULL,
    segmentation_policy_revision_id uuid NOT NULL,
    media_capabilities jsonb NOT NULL,
    normalization_policy_revision_id uuid NOT NULL,
    CONSTRAINT ck_catalogue_variety_uuid7 CHECK (
        catalogue.is_uuid7(variety_id)
        AND catalogue.is_uuid7(segmentation_policy_revision_id)
        AND catalogue.is_uuid7(normalization_policy_revision_id)
    ),
    CONSTRAINT ck_catalogue_language_tag CHECK (
        language_tag ~ '^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})+$'
    ),
    CONSTRAINT ck_catalogue_variety_scripts CHECK (cardinality(script_codes) >= 1),
    CONSTRAINT ck_catalogue_text_direction CHECK (text_direction IN ('ltr', 'rtl')),
    CONSTRAINT ck_catalogue_media_capabilities CHECK (
        jsonb_typeof(media_capabilities) = 'object'
        AND media_capabilities->>'schema_version' = '1'
    )
);

CREATE TABLE catalogue.language_packs (
    pack_id uuid PRIMARY KEY,
    pack_code varchar(120) NOT NULL UNIQUE,
    CONSTRAINT ck_catalogue_pack_uuid7 CHECK (catalogue.is_uuid7(pack_id)),
    CONSTRAINT ck_catalogue_pack_code CHECK (
        pack_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
    )
);

CREATE TABLE catalogue.language_pack_revisions (
    pack_revision_id uuid PRIMARY KEY,
    pack_id uuid NOT NULL REFERENCES catalogue.language_packs(pack_id) ON DELETE RESTRICT,
    revision_no integer NOT NULL,
    target_variety_id uuid NOT NULL
        REFERENCES catalogue.language_varieties(variety_id) ON DELETE RESTRICT,
    status varchar(24) NOT NULL,
    engine_min_version varchar(32) NOT NULL,
    engine_max_version varchar(32) NOT NULL,
    capability_manifest jsonb NOT NULL,
    checksum_manifest jsonb NOT NULL,
    license_refs varchar(255)[] NOT NULL,
    provenance_id uuid NOT NULL
        REFERENCES platform.provenance_records(provenance_id) ON DELETE RESTRICT,
    published_at timestamptz,
    CONSTRAINT ck_catalogue_pack_revision_uuid7 CHECK (
        catalogue.is_uuid7(pack_revision_id)
        AND catalogue.is_uuid7(pack_id)
        AND catalogue.is_uuid7(target_variety_id)
        AND catalogue.is_uuid7(provenance_id)
    ),
    CONSTRAINT ck_catalogue_pack_revision_no CHECK (revision_no >= 1),
    CONSTRAINT ck_catalogue_pack_revision_status CHECK (
        status IN ('draft', 'validating', 'validated', 'approved', 'published',
                   'retired', 'superseded', 'rejected', 'abandoned')
    ),
    CONSTRAINT ck_catalogue_pack_publication_shape CHECK (
        (status = 'published') = (published_at IS NOT NULL)
    ),
    CONSTRAINT ck_catalogue_pack_manifests CHECK (
        jsonb_typeof(capability_manifest) = 'object'
        AND capability_manifest->>'schema_version' = '1'
        AND jsonb_typeof(checksum_manifest) = 'object'
        AND checksum_manifest <> '{}'::jsonb
        AND cardinality(license_refs) >= 1
    ),
    CONSTRAINT uq_catalogue_pack_revision UNIQUE (pack_id, revision_no)
);

CREATE TABLE catalogue.language_pack_support_varieties (
    pack_revision_id uuid NOT NULL
        REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
    variety_id uuid NOT NULL
        REFERENCES catalogue.language_varieties(variety_id) ON DELETE RESTRICT,
    PRIMARY KEY (pack_revision_id, variety_id)
);

CREATE TABLE catalogue.language_pack_publications (
    publication_id uuid PRIMARY KEY,
    pack_id uuid NOT NULL REFERENCES catalogue.language_packs(pack_id) ON DELETE RESTRICT,
    pack_revision_id uuid NOT NULL UNIQUE
        REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
    channel varchar(40) NOT NULL,
    compatibility_range varchar(120) NOT NULL,
    published_at timestamptz NOT NULL,
    retired_at timestamptz,
    CONSTRAINT ck_catalogue_publication_uuid7 CHECK (
        catalogue.is_uuid7(publication_id)
        AND catalogue.is_uuid7(pack_id)
        AND catalogue.is_uuid7(pack_revision_id)
    ),
    CONSTRAINT ck_catalogue_publication_channel CHECK (
        channel ~ '^[a-z][a-z0-9_]{2,39}$'
    ),
    CONSTRAINT ck_catalogue_publication_retirement CHECK (
        retired_at IS NULL OR retired_at >= published_at
    )
);
CREATE UNIQUE INDEX uq_catalogue_active_pack_publication
    ON catalogue.language_pack_publications (pack_id, channel, compatibility_range)
    WHERE retired_at IS NULL;

CREATE TABLE catalogue.skills (
    skill_id uuid PRIMARY KEY,
    skill_code varchar(120) NOT NULL UNIQUE,
    CONSTRAINT ck_catalogue_skill_uuid7 CHECK (catalogue.is_uuid7(skill_id)),
    CONSTRAINT ck_catalogue_skill_code CHECK (
        skill_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
    )
);

CREATE TABLE catalogue.skill_revisions (
    skill_revision_id uuid PRIMARY KEY,
    skill_id uuid NOT NULL REFERENCES catalogue.skills(skill_id) ON DELETE RESTRICT,
    pack_revision_id uuid NOT NULL
        REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
    revision_no integer NOT NULL,
    skill_type varchar(64) NOT NULL,
    modality varchar(16) NOT NULL,
    operation varchar(16) NOT NULL,
    target_ref varchar(120) NOT NULL,
    scope jsonb NOT NULL,
    evidence_protocol_ids uuid[] NOT NULL,
    load_profile jsonb NOT NULL,
    status varchar(24) NOT NULL,
    provenance_id uuid NOT NULL
        REFERENCES platform.provenance_records(provenance_id) ON DELETE RESTRICT,
    CONSTRAINT ck_catalogue_skill_revision_uuid7 CHECK (
        catalogue.is_uuid7(skill_revision_id)
        AND catalogue.is_uuid7(skill_id)
        AND catalogue.is_uuid7(pack_revision_id)
        AND catalogue.is_uuid7(provenance_id)
    ),
    CONSTRAINT ck_catalogue_skill_revision_no CHECK (revision_no >= 1),
    CONSTRAINT ck_catalogue_skill_revision_status CHECK (
        status IN ('draft', 'validating', 'validated', 'approved', 'published',
                   'retired', 'superseded', 'rejected', 'abandoned')
    ),
    CONSTRAINT ck_catalogue_skill_modality CHECK (
        modality IN ('reading', 'listening', 'writing', 'speaking')
    ),
    CONSTRAINT ck_catalogue_skill_operation CHECK (
        operation IN ('recognize', 'recall', 'discriminate', 'transform',
                      'produce', 'interact', 'repair', 'transfer')
    ),
    CONSTRAINT ck_catalogue_skill_json CHECK (
        jsonb_typeof(scope) = 'object' AND jsonb_typeof(load_profile) = 'object'
    ),
    CONSTRAINT uq_catalogue_skill_revision UNIQUE (skill_id, revision_no)
);
CREATE INDEX ix_catalogue_skill_revisions_pack_status
    ON catalogue.skill_revisions (pack_revision_id, status, skill_revision_id);

CREATE TABLE catalogue.skill_prerequisite_edges (
    edge_id uuid PRIMARY KEY,
    from_skill_revision_id uuid NOT NULL
        REFERENCES catalogue.skill_revisions(skill_revision_id) ON DELETE RESTRICT,
    to_skill_revision_id uuid NOT NULL
        REFERENCES catalogue.skill_revisions(skill_revision_id) ON DELETE RESTRICT,
    edge_type varchar(16) NOT NULL,
    provenance_id uuid NOT NULL
        REFERENCES platform.provenance_records(provenance_id) ON DELETE RESTRICT,
    CONSTRAINT ck_catalogue_edge_uuid7 CHECK (
        catalogue.is_uuid7(edge_id)
        AND catalogue.is_uuid7(from_skill_revision_id)
        AND catalogue.is_uuid7(to_skill_revision_id)
        AND catalogue.is_uuid7(provenance_id)
    ),
    CONSTRAINT ck_catalogue_edge_type CHECK (
        edge_type IN ('required', 'recommended', 'contrast', 'transfer')
    ),
    CONSTRAINT ck_catalogue_edge_distinct CHECK (
        from_skill_revision_id <> to_skill_revision_id
    ),
    CONSTRAINT uq_catalogue_edge UNIQUE (
        from_skill_revision_id, to_skill_revision_id, edge_type
    )
);
CREATE INDEX ix_catalogue_edges_to_skill
    ON catalogue.skill_prerequisite_edges (to_skill_revision_id, edge_type);

CREATE TABLE catalogue.grammar_structures (
    structure_id uuid PRIMARY KEY,
    structure_code varchar(120) NOT NULL UNIQUE,
    function_skill_id uuid NOT NULL
        REFERENCES catalogue.skills(skill_id) ON DELETE RESTRICT,
    CONSTRAINT ck_catalogue_structure_uuid7 CHECK (
        catalogue.is_uuid7(structure_id) AND catalogue.is_uuid7(function_skill_id)
    )
);

CREATE TABLE catalogue.grammar_structure_revisions (
    structure_revision_id uuid PRIMARY KEY,
    structure_id uuid NOT NULL
        REFERENCES catalogue.grammar_structures(structure_id) ON DELETE RESTRICT,
    pack_revision_id uuid NOT NULL
        REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
    revision_no integer NOT NULL,
    constraints jsonb NOT NULL,
    contrasts jsonb NOT NULL,
    typical_errors jsonb NOT NULL,
    variants jsonb NOT NULL,
    status varchar(24) NOT NULL,
    provenance_id uuid NOT NULL
        REFERENCES platform.provenance_records(provenance_id) ON DELETE RESTRICT,
    CONSTRAINT ck_catalogue_structure_revision_uuid7 CHECK (
        catalogue.is_uuid7(structure_revision_id)
        AND catalogue.is_uuid7(structure_id)
        AND catalogue.is_uuid7(pack_revision_id)
        AND catalogue.is_uuid7(provenance_id)
    ),
    CONSTRAINT ck_catalogue_structure_revision_no CHECK (revision_no >= 1),
    CONSTRAINT ck_catalogue_structure_revision_status CHECK (
        status IN ('draft', 'validating', 'validated', 'approved', 'published',
                   'retired', 'superseded', 'rejected', 'abandoned')
    ),
    CONSTRAINT ck_catalogue_structure_json CHECK (
        jsonb_typeof(constraints) = 'object'
        AND jsonb_typeof(contrasts) = 'array'
        AND jsonb_typeof(typical_errors) = 'array'
        AND jsonb_typeof(variants) = 'array'
    ),
    CONSTRAINT uq_catalogue_structure_revision UNIQUE (structure_id, revision_no)
);

CREATE TABLE catalogue.grammar_patterns (
    pattern_id uuid PRIMARY KEY,
    structure_revision_id uuid NOT NULL
        REFERENCES catalogue.grammar_structure_revisions(structure_revision_id)
        ON DELETE RESTRICT,
    pattern_code varchar(120) NOT NULL,
    template text NOT NULL,
    slots jsonb NOT NULL,
    instantiation_rules jsonb NOT NULL,
    examples text[] NOT NULL,
    counterexamples text[] NOT NULL,
    CONSTRAINT ck_catalogue_pattern_uuid7 CHECK (catalogue.is_uuid7(pattern_id)),
    CONSTRAINT ck_catalogue_pattern_json CHECK (
        jsonb_typeof(slots) = 'array' AND jsonb_typeof(instantiation_rules) = 'object'
    ),
    CONSTRAINT uq_catalogue_pattern UNIQUE (structure_revision_id, pattern_code)
);

CREATE TABLE catalogue.lexical_units (
    lexical_unit_id uuid PRIMARY KEY,
    variety_id uuid NOT NULL
        REFERENCES catalogue.language_varieties(variety_id) ON DELETE RESTRICT,
    unit_type varchar(32) NOT NULL,
    visibility varchar(16) NOT NULL,
    owner_profile_id uuid,
    CONSTRAINT ck_catalogue_lexical_unit_uuid7 CHECK (
        catalogue.is_uuid7(lexical_unit_id) AND catalogue.is_uuid7(variety_id)
    ),
    CONSTRAINT ck_catalogue_lexical_unit_type CHECK (
        unit_type IN ('word', 'multiword_expression', 'proper_name',
                      'lexicalized_construction')
    ),
    CONSTRAINT ck_catalogue_lexical_visibility CHECK (
        visibility = 'shared' AND owner_profile_id IS NULL
    )
);

CREATE TABLE catalogue.lexical_unit_revisions (
    unit_revision_id uuid PRIMARY KEY,
    lexical_unit_id uuid NOT NULL
        REFERENCES catalogue.lexical_units(lexical_unit_id) ON DELETE RESTRICT,
    pack_revision_id uuid NOT NULL
        REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
    revision_no integer NOT NULL,
    lemma text NOT NULL,
    part_of_speech varchar(64) NOT NULL,
    register varchar(64),
    status varchar(24) NOT NULL,
    provenance_id uuid NOT NULL
        REFERENCES platform.provenance_records(provenance_id) ON DELETE RESTRICT,
    CONSTRAINT ck_catalogue_unit_revision_uuid7 CHECK (
        catalogue.is_uuid7(unit_revision_id)
        AND catalogue.is_uuid7(lexical_unit_id)
        AND catalogue.is_uuid7(pack_revision_id)
        AND catalogue.is_uuid7(provenance_id)
    ),
    CONSTRAINT ck_catalogue_unit_revision_no CHECK (revision_no >= 1),
    CONSTRAINT ck_catalogue_unit_revision_status CHECK (
        status IN ('draft', 'validating', 'validated', 'approved', 'published',
                   'retired', 'superseded', 'rejected', 'abandoned')
    ),
    CONSTRAINT ck_catalogue_lemma CHECK (length(lemma) BETWEEN 1 AND 500),
    CONSTRAINT uq_catalogue_unit_revision UNIQUE (lexical_unit_id, revision_no)
);

CREATE TABLE catalogue.lexical_senses (
    sense_id uuid PRIMARY KEY,
    lexical_unit_id uuid NOT NULL
        REFERENCES catalogue.lexical_units(lexical_unit_id) ON DELETE RESTRICT,
    sense_code varchar(120) NOT NULL,
    CONSTRAINT ck_catalogue_sense_uuid7 CHECK (
        catalogue.is_uuid7(sense_id) AND catalogue.is_uuid7(lexical_unit_id)
    ),
    CONSTRAINT uq_catalogue_sense_code UNIQUE (lexical_unit_id, sense_code)
);

CREATE TABLE catalogue.lexical_sense_revisions (
    sense_revision_id uuid PRIMARY KEY,
    sense_id uuid NOT NULL
        REFERENCES catalogue.lexical_senses(sense_id) ON DELETE RESTRICT,
    pack_revision_id uuid NOT NULL
        REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
    revision_no integer NOT NULL,
    definition text NOT NULL,
    domains varchar(120)[] NOT NULL,
    register varchar(64),
    status varchar(24) NOT NULL,
    provenance_id uuid NOT NULL
        REFERENCES platform.provenance_records(provenance_id) ON DELETE RESTRICT,
    CONSTRAINT ck_catalogue_sense_revision_uuid7 CHECK (
        catalogue.is_uuid7(sense_revision_id)
        AND catalogue.is_uuid7(sense_id)
        AND catalogue.is_uuid7(pack_revision_id)
        AND catalogue.is_uuid7(provenance_id)
    ),
    CONSTRAINT ck_catalogue_sense_revision_no CHECK (revision_no >= 1),
    CONSTRAINT ck_catalogue_sense_revision_status CHECK (
        status IN ('draft', 'validating', 'validated', 'approved', 'published',
                   'retired', 'superseded', 'rejected', 'abandoned')
    ),
    CONSTRAINT ck_catalogue_definition CHECK (length(definition) BETWEEN 1 AND 2000),
    CONSTRAINT uq_catalogue_sense_revision UNIQUE (sense_id, revision_no)
);

CREATE TABLE catalogue.form_analyses (
    form_analysis_id uuid PRIMARY KEY,
    unit_revision_id uuid NOT NULL
        REFERENCES catalogue.lexical_unit_revisions(unit_revision_id) ON DELETE RESTRICT,
    surface text NOT NULL,
    morphological_features jsonb NOT NULL,
    pronunciation_refs uuid[] NOT NULL,
    normalization_key text NOT NULL,
    CONSTRAINT ck_catalogue_form_uuid7 CHECK (catalogue.is_uuid7(form_analysis_id)),
    CONSTRAINT ck_catalogue_form_surface CHECK (
        length(surface) BETWEEN 1 AND 500 AND length(normalization_key) BETWEEN 1 AND 500
    ),
    CONSTRAINT ck_catalogue_form_features CHECK (
        jsonb_typeof(morphological_features) = 'object'
    ),
    CONSTRAINT uq_catalogue_form_analysis UNIQUE (
        unit_revision_id, surface, morphological_features
    )
);
CREATE INDEX ix_catalogue_form_normalization
    ON catalogue.form_analyses (normalization_key, form_analysis_id);

CREATE TABLE catalogue.form_realizations (
    realization_id uuid PRIMARY KEY,
    form_analysis_id uuid NOT NULL
        REFERENCES catalogue.form_analyses(form_analysis_id) ON DELETE RESTRICT,
    unit_revision_id uuid NOT NULL
        REFERENCES catalogue.lexical_unit_revisions(unit_revision_id) ON DELETE RESTRICT,
    sense_revision_id uuid
        REFERENCES catalogue.lexical_sense_revisions(sense_revision_id) ON DELETE RESTRICT,
    CONSTRAINT ck_catalogue_realization_uuid7 CHECK (
        catalogue.is_uuid7(realization_id)
        AND catalogue.is_uuid7(form_analysis_id)
        AND catalogue.is_uuid7(unit_revision_id)
        AND (sense_revision_id IS NULL OR catalogue.is_uuid7(sense_revision_id))
    ),
    CONSTRAINT uq_catalogue_form_realization UNIQUE (
        form_analysis_id, unit_revision_id, sense_revision_id
    )
);

CREATE TABLE catalogue.expression_components (
    expression_unit_revision_id uuid NOT NULL
        REFERENCES catalogue.lexical_unit_revisions(unit_revision_id) ON DELETE RESTRICT,
    component_unit_revision_id uuid NOT NULL
        REFERENCES catalogue.lexical_unit_revisions(unit_revision_id) ON DELETE RESTRICT,
    position integer NOT NULL,
    CONSTRAINT ck_catalogue_expression_distinct CHECK (
        expression_unit_revision_id <> component_unit_revision_id
    ),
    CONSTRAINT ck_catalogue_expression_position CHECK (position >= 1),
    PRIMARY KEY (expression_unit_revision_id, component_unit_revision_id),
    CONSTRAINT uq_catalogue_expression_position UNIQUE (
        expression_unit_revision_id, position
    )
);

CREATE FUNCTION catalogue.reject_published_revision() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
    IF OLD.status = 'published' THEN
        RAISE EXCEPTION 'published revision is immutable' USING ERRCODE = '55000';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$function$;

CREATE TRIGGER guard_published_pack_revision
BEFORE UPDATE OR DELETE ON catalogue.language_pack_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_published_revision();
CREATE TRIGGER guard_published_skill_revision
BEFORE UPDATE OR DELETE ON catalogue.skill_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_published_revision();
CREATE TRIGGER guard_published_structure_revision
BEFORE UPDATE OR DELETE ON catalogue.grammar_structure_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_published_revision();
CREATE TRIGGER guard_published_unit_revision
BEFORE UPDATE OR DELETE ON catalogue.lexical_unit_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_published_revision();
CREATE TRIGGER guard_published_sense_revision
BEFORE UPDATE OR DELETE ON catalogue.lexical_sense_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_published_revision();

CREATE FUNCTION catalogue.guard_prerequisite_edge() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE
    parent_status varchar;
BEGIN
    SELECT status INTO parent_status
    FROM catalogue.skill_revisions
    WHERE skill_revision_id IN (
        CASE WHEN TG_OP = 'DELETE' THEN OLD.from_skill_revision_id
             ELSE NEW.from_skill_revision_id END,
        CASE WHEN TG_OP = 'DELETE' THEN OLD.to_skill_revision_id
             ELSE NEW.to_skill_revision_id END
    )
    ORDER BY CASE WHEN status = 'published' THEN 0 ELSE 1 END
    LIMIT 1;
    IF parent_status = 'published' THEN
        RAISE EXCEPTION 'published revision is immutable' USING ERRCODE = '55000';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$function$;

CREATE FUNCTION catalogue.reject_required_prerequisite_cycle() RETURNS trigger
LANGUAGE plpgsql AS $function$
BEGIN
    IF NEW.edge_type <> 'required' THEN
        RETURN NEW;
    END IF;
    IF NEW.from_skill_revision_id = NEW.to_skill_revision_id OR EXISTS (
        WITH RECURSIVE reachable(skill_revision_id) AS (
            SELECT NEW.to_skill_revision_id
            UNION
            SELECT edge.to_skill_revision_id
            FROM catalogue.skill_prerequisite_edges AS edge
            JOIN reachable
              ON reachable.skill_revision_id = edge.from_skill_revision_id
            WHERE edge.edge_type = 'required'
              AND edge.edge_id <> NEW.edge_id
        )
        SELECT 1 FROM reachable
        WHERE skill_revision_id = NEW.from_skill_revision_id
    ) THEN
        RAISE EXCEPTION 'prerequisite_cycle' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE TRIGGER guard_published_prerequisite_edge
BEFORE INSERT OR UPDATE OR DELETE ON catalogue.skill_prerequisite_edges
FOR EACH ROW EXECUTE FUNCTION catalogue.guard_prerequisite_edge();
CREATE TRIGGER guard_required_prerequisite_cycle
BEFORE INSERT OR UPDATE ON catalogue.skill_prerequisite_edges
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_required_prerequisite_cycle();

CREATE FUNCTION catalogue.validate_pack_publication() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE
    revision_pack_id uuid;
    revision_status varchar;
    revision_published_at timestamptz;
BEGIN
    SELECT pack_id, status, published_at
      INTO revision_pack_id, revision_status, revision_published_at
    FROM catalogue.language_pack_revisions
    WHERE pack_revision_id = NEW.pack_revision_id;
    IF revision_pack_id <> NEW.pack_id OR revision_status <> 'published'
       OR revision_published_at <> NEW.published_at THEN
        RAISE EXCEPTION 'publication_not_active' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
CREATE TRIGGER validate_pack_publication
BEFORE INSERT OR UPDATE ON catalogue.language_pack_publications
FOR EACH ROW EXECUTE FUNCTION catalogue.validate_pack_publication();

REVOKE ALL ON SCHEMA catalogue FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA catalogue TO polyglot_migration;
GRANT USAGE ON SCHEMA catalogue TO polyglot_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA catalogue
    TO polyglot_migration;
GRANT SELECT ON ALL TABLES IN SCHEMA catalogue TO polyglot_runtime;

ALTER SCHEMA catalogue OWNER TO polyglot_migration;
DO $owners$
DECLARE item record;
BEGIN
    FOR item IN SELECT tablename FROM pg_tables WHERE schemaname = 'catalogue' LOOP
        EXECUTE format('ALTER TABLE catalogue.%I OWNER TO polyglot_migration', item.tablename);
    END LOOP;
END;
$owners$;
ALTER FUNCTION catalogue.is_uuid7(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.reject_published_revision() OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.guard_prerequisite_edge() OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.reject_required_prerequisite_cycle() OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.validate_pack_publication() OWNER TO polyglot_migration;
"""


async def _execute_catalogue_ddl(connection: Connection) -> None:
    await connection.execute(CATALOGUE_DDL)


def upgrade() -> None:
    op.get_bind().connection.run_async(_execute_catalogue_ddl)


def downgrade() -> None:
    op.execute("DROP SCHEMA catalogue CASCADE")
