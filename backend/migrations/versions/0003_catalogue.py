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

CREATE FUNCTION catalogue.foundation_checksum_text(value text)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $function$
    SELECT '["string",' || to_json(value)::text || ']'
$function$;

CREATE FUNCTION catalogue.foundation_checksum_uuid(value uuid)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $function$
    SELECT '["uuid",' || to_json(value::text)::text || ']'
$function$;

CREATE FUNCTION catalogue.foundation_checksum_integer(value integer)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $function$
    SELECT '["integer",' || to_json(value::text)::text || ']'
$function$;

CREATE FUNCTION catalogue.foundation_checksum_decimal(value numeric)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $function$
    SELECT '["decimal",' || to_json(trim_scale(value)::text)::text || ']'
$function$;

CREATE FUNCTION catalogue.foundation_checksum_boolean(value boolean)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $function$
    SELECT '["boolean",' || lower(value::text) || ']'
$function$;

CREATE FUNCTION catalogue.foundation_checksum_text_array(values_ text[])
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $function$
    SELECT '["array",[' || COALESCE(
        string_agg(catalogue.foundation_checksum_text(item), ',' ORDER BY ordinal),
        ''
    ) || ']]'
    FROM unnest(values_) WITH ORDINALITY AS value(item, ordinal)
$function$;

CREATE FUNCTION catalogue.foundation_content_checksum(kind text, VARIADIC parts text[])
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $function$
    SELECT encode(
        sha256(convert_to(
            '["foundation-checksum-v2",' ||
            catalogue.foundation_checksum_text(kind) ||
            ',["array",[' || array_to_string(parts, ',') || ']]]',
            'UTF8'
        )),
        'hex'
    )
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
    CONSTRAINT ck_catalogue_skill_type_code CHECK (
        skill_type ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
        AND target_ref ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
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
    ),
    CONSTRAINT ck_catalogue_structure_code CHECK (
        structure_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
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
    CONSTRAINT ck_catalogue_pattern_code CHECK (
        pattern_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
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
    CONSTRAINT ck_catalogue_sense_code CHECK (
        sense_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
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

CREATE TABLE catalogue.foundation_definitions (
    foundation_id uuid PRIMARY KEY,
    foundation_code varchar(120) NOT NULL UNIQUE,
    CONSTRAINT ck_catalogue_foundation_uuid7 CHECK (catalogue.is_uuid7(foundation_id)),
    CONSTRAINT ck_catalogue_foundation_code CHECK (
        foundation_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
    )
);

CREATE TABLE catalogue.foundation_definition_revisions (
    foundation_revision_id uuid PRIMARY KEY,
    foundation_id uuid NOT NULL
        REFERENCES catalogue.foundation_definitions(foundation_id) ON DELETE RESTRICT,
    pack_revision_id uuid NOT NULL
        REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
    revision_no integer NOT NULL,
    status varchar(24) NOT NULL,
    checksum varchar(64) NOT NULL,
    CONSTRAINT ck_catalogue_foundation_revision_uuid7 CHECK (
        catalogue.is_uuid7(foundation_revision_id)
        AND catalogue.is_uuid7(foundation_id)
        AND catalogue.is_uuid7(pack_revision_id)
    ),
    CONSTRAINT ck_catalogue_foundation_revision_no CHECK (revision_no >= 1),
    CONSTRAINT ck_catalogue_foundation_revision_status CHECK (status = 'published'),
    CONSTRAINT ck_catalogue_foundation_revision_checksum CHECK (
        checksum ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT uq_catalogue_foundation_revision UNIQUE (foundation_id, revision_no),
    CONSTRAINT uq_catalogue_pack_foundation UNIQUE (pack_revision_id, foundation_id)
);

CREATE TABLE catalogue.foundation_reference_revisions (
    reference_revision_id uuid PRIMARY KEY,
    pack_revision_id uuid NOT NULL
        REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
    reference_code varchar(120) NOT NULL,
    reference_kind varchar(24) NOT NULL,
    status varchar(24) NOT NULL,
    checksum varchar(64) NOT NULL,
    CONSTRAINT ck_catalogue_foundation_reference_uuid7 CHECK (
        catalogue.is_uuid7(reference_revision_id)
        AND catalogue.is_uuid7(pack_revision_id)
    ),
    CONSTRAINT ck_catalogue_foundation_reference_shape CHECK (
        reference_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
        AND reference_kind IN ('target', 'facet', 'waiver_policy')
        AND status = 'published'
        AND checksum ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT uq_catalogue_foundation_reference_code UNIQUE (
        pack_revision_id, reference_code
    )
);

CREATE TABLE catalogue.foundation_block_revisions (
    block_revision_id uuid PRIMARY KEY,
    foundation_revision_id uuid NOT NULL
        REFERENCES catalogue.foundation_definition_revisions(foundation_revision_id)
        ON DELETE RESTRICT,
    pack_revision_id uuid NOT NULL
        REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
    block_code varchar(16) NOT NULL,
    ordinal integer NOT NULL,
    component_type varchar(64) NOT NULL,
    prerequisite_refs varchar(120)[] NOT NULL,
    modalities varchar(16)[] NOT NULL,
    backend_criteria varchar(120)[] NOT NULL,
    waiver_policy_ref varchar(120) NOT NULL,
    status varchar(24) NOT NULL,
    checksum varchar(64) NOT NULL,
    CONSTRAINT ck_catalogue_foundation_block_uuid7 CHECK (
        catalogue.is_uuid7(block_revision_id)
        AND catalogue.is_uuid7(foundation_revision_id)
        AND catalogue.is_uuid7(pack_revision_id)
    ),
    CONSTRAINT ck_catalogue_foundation_block_ordinal CHECK (ordinal BETWEEN 1 AND 5),
    CONSTRAINT ck_catalogue_foundation_block_status CHECK (status = 'published'),
    CONSTRAINT ck_catalogue_foundation_block_codes CHECK (
        block_code ~ '^F[1-5]$'
        AND component_type ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
        AND waiver_policy_ref ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
    ),
    CONSTRAINT ck_catalogue_foundation_block_shape CHECK (
        cardinality(modalities) >= 1
        AND modalities <@ ARRAY['reading', 'listening', 'writing', 'speaking']::varchar[]
        AND cardinality(backend_criteria) >= 1
        AND checksum ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT uq_catalogue_foundation_block_ordinal UNIQUE (foundation_revision_id, ordinal),
    CONSTRAINT uq_catalogue_foundation_block_code UNIQUE (foundation_revision_id, block_code)
);

CREATE TABLE catalogue.foundation_item_revisions (
    item_revision_id uuid PRIMARY KEY,
    block_revision_id uuid NOT NULL
        REFERENCES catalogue.foundation_block_revisions(block_revision_id) ON DELETE RESTRICT,
    pack_revision_id uuid NOT NULL
        REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
    item_code varchar(120) NOT NULL UNIQUE,
    ordinal integer NOT NULL,
    target_refs varchar(120)[] NOT NULL,
    response_kind varchar(16) NOT NULL,
    checker_kind varchar(32) NOT NULL,
    checker_values text[] NOT NULL,
    modalities varchar(16)[] NOT NULL,
    status varchar(24) NOT NULL,
    checksum varchar(64) NOT NULL,
    CONSTRAINT ck_catalogue_foundation_item_uuid7 CHECK (
        catalogue.is_uuid7(item_revision_id)
        AND catalogue.is_uuid7(block_revision_id)
        AND catalogue.is_uuid7(pack_revision_id)
    ),
    CONSTRAINT ck_catalogue_foundation_item_ordinal CHECK (ordinal >= 1),
    CONSTRAINT ck_catalogue_foundation_item_status CHECK (status = 'published'),
    CONSTRAINT ck_catalogue_foundation_item_shape CHECK (
        item_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
        AND cardinality(target_refs) >= 1
        AND response_kind = 'raw'
        AND checker_kind IN ('exact_choice', 'exact_reconstruction',
                             'normalized_alternatives', 'not_evaluable')
        AND ((checker_kind = 'not_evaluable' AND cardinality(checker_values) = 0)
             OR (checker_kind <> 'not_evaluable' AND cardinality(checker_values) >= 1))
        AND cardinality(modalities) >= 1
        AND modalities <@ ARRAY['reading', 'listening', 'writing', 'speaking']::varchar[]
        AND checksum ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT uq_catalogue_foundation_item_ordinal UNIQUE (block_revision_id, ordinal)
);

CREATE TABLE catalogue.foundation_gate_revisions (
    gate_revision_id uuid PRIMARY KEY,
    foundation_revision_id uuid NOT NULL UNIQUE
        REFERENCES catalogue.foundation_definition_revisions(foundation_revision_id)
        ON DELETE RESTRICT,
    pack_revision_id uuid NOT NULL
        REFERENCES catalogue.language_pack_revisions(pack_revision_id) ON DELETE RESTRICT,
    gate_code varchar(120) NOT NULL,
    blocking_target_refs varchar(120)[] NOT NULL,
    blocking_facet_refs varchar(120)[] NOT NULL,
    blocking_facet_minimum_status varchar(24) NOT NULL,
    coverage_threshold numeric(4, 3) NOT NULL,
    confidence_threshold numeric(4, 3) NOT NULL,
    minimum_distinct_sessions integer NOT NULL,
    delayed_control_block_code varchar(16) NOT NULL,
    delayed_control_hours integer NOT NULL,
    grapheme_sound_minimum integer NOT NULL,
    grapheme_sound_total integer NOT NULL,
    targeted_reading_minimum integer NOT NULL,
    targeted_reading_total integer NOT NULL,
    survival_exchange_minimum integer NOT NULL,
    survival_exchange_total integer NOT NULL,
    survival_exchange_without_reveal boolean NOT NULL,
    oral_policy varchar(64) NOT NULL,
    status varchar(24) NOT NULL,
    checksum varchar(64) NOT NULL,
    CONSTRAINT ck_catalogue_foundation_gate_uuid7 CHECK (
        catalogue.is_uuid7(gate_revision_id)
        AND catalogue.is_uuid7(foundation_revision_id)
        AND catalogue.is_uuid7(pack_revision_id)
    ),
    CONSTRAINT ck_catalogue_foundation_gate_shape CHECK (
        gate_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'
        AND cardinality(blocking_target_refs) >= 1
        AND blocking_facet_refs = ARRAY[
            'grapheme_sound_discrimination', 'controlled_reading',
            'greeting_recognition', 'functional_frame_choice', 'written_guided_repair'
        ]::varchar[]
        AND blocking_facet_minimum_status = 'reliable'
        AND coverage_threshold = 1.000 AND confidence_threshold = 0.600
        AND minimum_distinct_sessions = 2
        AND delayed_control_block_code = 'F1' AND delayed_control_hours = 24
        AND grapheme_sound_minimum = 8 AND grapheme_sound_total = 10
        AND targeted_reading_minimum = 8 AND targeted_reading_total = 10
        AND survival_exchange_minimum = 4 AND survival_exchange_total = 5
        AND survival_exchange_without_reveal IS TRUE
        AND oral_policy = 'not_evaluable_non_blocking'
        AND status = 'published'
        AND checksum ~ '^[0-9a-f]{64}$'
    )
);

CREATE FUNCTION catalogue.validate_foundation_checksum() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE
    expected_checksum text;
    definition_code varchar;
BEGIN
    CASE TG_TABLE_NAME
        WHEN 'foundation_definition_revisions' THEN
            SELECT foundation.foundation_code INTO definition_code
            FROM catalogue.foundation_definitions AS foundation
            WHERE foundation.foundation_id = NEW.foundation_id;
            expected_checksum := catalogue.foundation_content_checksum(
                'foundation_definition_v1',
                catalogue.foundation_checksum_uuid(NEW.foundation_revision_id),
                catalogue.foundation_checksum_uuid(NEW.foundation_id),
                catalogue.foundation_checksum_uuid(NEW.pack_revision_id),
                catalogue.foundation_checksum_text(definition_code),
                catalogue.foundation_checksum_integer(NEW.revision_no),
                catalogue.foundation_checksum_text(NEW.status)
            );
        WHEN 'foundation_reference_revisions' THEN
            expected_checksum := catalogue.foundation_content_checksum(
                'foundation_reference_v1',
                catalogue.foundation_checksum_uuid(NEW.reference_revision_id),
                catalogue.foundation_checksum_uuid(NEW.pack_revision_id),
                catalogue.foundation_checksum_text(NEW.reference_code),
                catalogue.foundation_checksum_text(NEW.reference_kind),
                catalogue.foundation_checksum_text(NEW.status)
            );
        WHEN 'foundation_block_revisions' THEN
            expected_checksum := catalogue.foundation_content_checksum(
                'foundation_block_v1',
                catalogue.foundation_checksum_uuid(NEW.block_revision_id),
                catalogue.foundation_checksum_uuid(NEW.foundation_revision_id),
                catalogue.foundation_checksum_uuid(NEW.pack_revision_id),
                catalogue.foundation_checksum_text(NEW.block_code),
                catalogue.foundation_checksum_integer(NEW.ordinal),
                catalogue.foundation_checksum_text(NEW.component_type),
                catalogue.foundation_checksum_text_array(NEW.prerequisite_refs),
                catalogue.foundation_checksum_text_array(NEW.modalities),
                catalogue.foundation_checksum_text_array(NEW.backend_criteria),
                catalogue.foundation_checksum_text(NEW.waiver_policy_ref),
                catalogue.foundation_checksum_text(NEW.status)
            );
        WHEN 'foundation_item_revisions' THEN
            expected_checksum := catalogue.foundation_content_checksum(
                'foundation_item_v1',
                catalogue.foundation_checksum_uuid(NEW.item_revision_id),
                catalogue.foundation_checksum_uuid(NEW.block_revision_id),
                catalogue.foundation_checksum_uuid(NEW.pack_revision_id),
                catalogue.foundation_checksum_text(NEW.item_code),
                catalogue.foundation_checksum_integer(NEW.ordinal),
                catalogue.foundation_checksum_text_array(NEW.target_refs),
                catalogue.foundation_checksum_text(NEW.response_kind),
                catalogue.foundation_checksum_text(NEW.checker_kind),
                catalogue.foundation_checksum_text_array(NEW.checker_values),
                catalogue.foundation_checksum_text_array(NEW.modalities),
                catalogue.foundation_checksum_text(NEW.status)
            );
        WHEN 'foundation_gate_revisions' THEN
            expected_checksum := catalogue.foundation_content_checksum(
                'foundation_gate_v1',
                catalogue.foundation_checksum_uuid(NEW.gate_revision_id),
                catalogue.foundation_checksum_uuid(NEW.foundation_revision_id),
                catalogue.foundation_checksum_uuid(NEW.pack_revision_id),
                catalogue.foundation_checksum_text(NEW.gate_code),
                catalogue.foundation_checksum_text_array(NEW.blocking_target_refs),
                catalogue.foundation_checksum_text_array(NEW.blocking_facet_refs),
                catalogue.foundation_checksum_text(NEW.blocking_facet_minimum_status),
                catalogue.foundation_checksum_decimal(NEW.coverage_threshold),
                catalogue.foundation_checksum_decimal(NEW.confidence_threshold),
                catalogue.foundation_checksum_integer(NEW.minimum_distinct_sessions),
                catalogue.foundation_checksum_text(NEW.delayed_control_block_code),
                catalogue.foundation_checksum_integer(NEW.delayed_control_hours),
                catalogue.foundation_checksum_integer(NEW.grapheme_sound_minimum),
                catalogue.foundation_checksum_integer(NEW.grapheme_sound_total),
                catalogue.foundation_checksum_integer(NEW.targeted_reading_minimum),
                catalogue.foundation_checksum_integer(NEW.targeted_reading_total),
                catalogue.foundation_checksum_integer(NEW.survival_exchange_minimum),
                catalogue.foundation_checksum_integer(NEW.survival_exchange_total),
                catalogue.foundation_checksum_boolean(NEW.survival_exchange_without_reveal),
                catalogue.foundation_checksum_text(NEW.oral_policy),
                catalogue.foundation_checksum_text(NEW.status)
            );
    END CASE;
    IF expected_checksum IS DISTINCT FROM NEW.checksum THEN
        RAISE EXCEPTION 'foundation checksum does not match content' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE TRIGGER validate_foundation_definition_checksum
BEFORE INSERT OR UPDATE ON catalogue.foundation_definition_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.validate_foundation_checksum();
CREATE TRIGGER validate_foundation_reference_checksum
BEFORE INSERT OR UPDATE ON catalogue.foundation_reference_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.validate_foundation_checksum();
CREATE TRIGGER validate_foundation_block_checksum
BEFORE INSERT OR UPDATE ON catalogue.foundation_block_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.validate_foundation_checksum();
CREATE TRIGGER validate_foundation_item_checksum
BEFORE INSERT OR UPDATE ON catalogue.foundation_item_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.validate_foundation_checksum();
CREATE TRIGGER validate_foundation_gate_checksum
BEFORE INSERT OR UPDATE ON catalogue.foundation_gate_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.validate_foundation_checksum();

CREATE FUNCTION catalogue.validate_foundation_references() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE
    parent_pack_revision_id uuid;
    requested_refs varchar[];
    requested_kind varchar;
    row_data jsonb := to_jsonb(NEW);
    waiver_policy_ref varchar;
    blocking_facet_refs varchar[];
BEGIN
    IF TG_TABLE_NAME = 'foundation_block_revisions' THEN
        SELECT pack_revision_id INTO parent_pack_revision_id
        FROM catalogue.foundation_definition_revisions
        WHERE foundation_revision_id = (row_data->>'foundation_revision_id')::uuid;
        requested_refs := ARRAY(
            SELECT jsonb_array_elements_text(row_data->'prerequisite_refs')
        );
        waiver_policy_ref := row_data->>'waiver_policy_ref';
        requested_kind := 'target';
    ELSIF TG_TABLE_NAME = 'foundation_item_revisions' THEN
        SELECT pack_revision_id INTO parent_pack_revision_id
        FROM catalogue.foundation_block_revisions
        WHERE block_revision_id = (row_data->>'block_revision_id')::uuid;
        requested_refs := ARRAY(
            SELECT jsonb_array_elements_text(row_data->'target_refs')
        );
        requested_kind := 'target';
    ELSE
        SELECT pack_revision_id INTO parent_pack_revision_id
        FROM catalogue.foundation_definition_revisions
        WHERE foundation_revision_id = (row_data->>'foundation_revision_id')::uuid;
        requested_refs := ARRAY(
            SELECT jsonb_array_elements_text(row_data->'blocking_target_refs')
        );
        blocking_facet_refs := ARRAY(
            SELECT jsonb_array_elements_text(row_data->'blocking_facet_refs')
        );
        requested_kind := 'target';
    END IF;
    IF parent_pack_revision_id IS DISTINCT FROM NEW.pack_revision_id THEN
        RAISE EXCEPTION 'foundation child does not match published pack' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM unnest(requested_refs) AS requested(reference_code)
        WHERE NOT EXISTS (
            SELECT 1 FROM catalogue.foundation_reference_revisions AS reference
            WHERE reference.pack_revision_id = NEW.pack_revision_id
              AND reference.reference_code = requested.reference_code
              AND reference.reference_kind = requested_kind
              AND reference.status = 'published'
        )
    ) THEN
        RAISE EXCEPTION 'foundation reference is not published' USING ERRCODE = '23503';
    END IF;
    IF TG_TABLE_NAME = 'foundation_block_revisions' AND NOT EXISTS (
        SELECT 1 FROM catalogue.foundation_reference_revisions AS reference
        WHERE reference.pack_revision_id = NEW.pack_revision_id
          AND reference.reference_code = waiver_policy_ref
          AND reference.reference_kind = 'waiver_policy'
          AND reference.status = 'published'
    ) THEN
        RAISE EXCEPTION 'foundation reference is not published' USING ERRCODE = '23503';
    END IF;
    IF TG_TABLE_NAME = 'foundation_gate_revisions' AND EXISTS (
        SELECT 1 FROM unnest(blocking_facet_refs) AS requested(reference_code)
        WHERE NOT EXISTS (
            SELECT 1 FROM catalogue.foundation_reference_revisions AS reference
            WHERE reference.pack_revision_id = NEW.pack_revision_id
              AND reference.reference_code = requested.reference_code
              AND reference.reference_kind = 'facet'
              AND reference.status = 'published'
        )
    ) THEN
        RAISE EXCEPTION 'foundation reference is not published' USING ERRCODE = '23503';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE TRIGGER validate_foundation_block_references
BEFORE INSERT OR UPDATE ON catalogue.foundation_block_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.validate_foundation_references();
CREATE TRIGGER validate_foundation_item_references
BEFORE INSERT OR UPDATE ON catalogue.foundation_item_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.validate_foundation_references();
CREATE TRIGGER validate_foundation_gate_references
BEFORE INSERT OR UPDATE ON catalogue.foundation_gate_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.validate_foundation_references();

CREATE FUNCTION catalogue.reject_late_foundation_insert() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE
    is_published boolean;
BEGIN
    IF TG_TABLE_NAME = 'foundation_definition_revisions' THEN
        SELECT EXISTS (
            SELECT 1 FROM catalogue.foundation_definition_revisions
            WHERE pack_revision_id = NEW.pack_revision_id AND status = 'published'
        ) INTO is_published;
    ELSIF TG_TABLE_NAME = 'foundation_reference_revisions' THEN
        SELECT EXISTS (
            SELECT 1 FROM catalogue.foundation_gate_revisions
            WHERE pack_revision_id = NEW.pack_revision_id AND status = 'published'
        ) INTO is_published;
    ELSIF TG_TABLE_NAME = 'foundation_block_revisions' THEN
        SELECT EXISTS (
            SELECT 1 FROM catalogue.foundation_gate_revisions
            WHERE foundation_revision_id = NEW.foundation_revision_id AND status = 'published'
        ) INTO is_published;
    ELSE
        SELECT EXISTS (
            SELECT 1 FROM catalogue.foundation_gate_revisions AS gate
            JOIN catalogue.foundation_block_revisions AS block
              ON block.foundation_revision_id = gate.foundation_revision_id
            WHERE block.block_revision_id = NEW.block_revision_id AND gate.status = 'published'
        ) INTO is_published;
    END IF;
    IF is_published THEN
        RAISE EXCEPTION 'published foundation is immutable' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE TRIGGER guard_late_foundation_definition
BEFORE INSERT ON catalogue.foundation_definition_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_late_foundation_insert();
CREATE TRIGGER guard_late_foundation_reference
BEFORE INSERT ON catalogue.foundation_reference_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_late_foundation_insert();
CREATE TRIGGER guard_late_foundation_block
BEFORE INSERT ON catalogue.foundation_block_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_late_foundation_insert();
CREATE TRIGGER guard_late_foundation_item
BEFORE INSERT ON catalogue.foundation_item_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_late_foundation_insert();

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
CREATE TRIGGER guard_published_foundation_revision
BEFORE UPDATE OR DELETE ON catalogue.foundation_definition_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_published_revision();
CREATE TRIGGER guard_published_foundation_reference
BEFORE UPDATE OR DELETE ON catalogue.foundation_reference_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_published_revision();
CREATE TRIGGER guard_published_foundation_block
BEFORE UPDATE OR DELETE ON catalogue.foundation_block_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_published_revision();
CREATE TRIGGER guard_published_foundation_item
BEFORE UPDATE OR DELETE ON catalogue.foundation_item_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_published_revision();
CREATE TRIGGER guard_published_foundation_gate
BEFORE UPDATE OR DELETE ON catalogue.foundation_gate_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.reject_published_revision();

CREATE FUNCTION catalogue.assert_published_revisions_immutable(revision_ids uuid[])
RETURNS void LANGUAGE plpgsql AS $function$
BEGIN
    IF EXISTS (
        SELECT 1 FROM (
            SELECT status FROM catalogue.language_pack_revisions
             WHERE pack_revision_id = ANY(revision_ids)
            UNION ALL
            SELECT status FROM catalogue.skill_revisions
             WHERE skill_revision_id = ANY(revision_ids)
            UNION ALL
            SELECT status FROM catalogue.grammar_structure_revisions
             WHERE structure_revision_id = ANY(revision_ids)
            UNION ALL
            SELECT status FROM catalogue.lexical_unit_revisions
             WHERE unit_revision_id = ANY(revision_ids)
            UNION ALL
            SELECT status FROM catalogue.lexical_sense_revisions
             WHERE sense_revision_id = ANY(revision_ids)
            UNION ALL
            SELECT status FROM catalogue.foundation_definition_revisions
             WHERE foundation_revision_id = ANY(revision_ids)
            UNION ALL
            SELECT status FROM catalogue.foundation_reference_revisions
             WHERE reference_revision_id = ANY(revision_ids)
            UNION ALL
            SELECT status FROM catalogue.foundation_block_revisions
             WHERE block_revision_id = ANY(revision_ids)
            UNION ALL
            SELECT status FROM catalogue.foundation_item_revisions
             WHERE item_revision_id = ANY(revision_ids)
            UNION ALL
            SELECT status FROM catalogue.foundation_gate_revisions
             WHERE gate_revision_id = ANY(revision_ids)
        ) AS revisions
        WHERE status = 'published'
    ) THEN
        RAISE EXCEPTION 'published revision is immutable' USING ERRCODE = '55000';
    END IF;
END;
$function$;

CREATE FUNCTION catalogue.guard_published_child() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE
    old_form_owner_id uuid;
    new_form_owner_id uuid;
    old_revisions uuid[];
    new_revisions uuid[];
BEGIN
    IF TG_TABLE_NAME = 'language_pack_support_varieties' THEN
        IF TG_OP <> 'INSERT' THEN
            old_revisions := ARRAY[OLD.pack_revision_id];
        END IF;
        IF TG_OP <> 'DELETE' THEN
            new_revisions := ARRAY[NEW.pack_revision_id];
        END IF;
    ELSIF TG_TABLE_NAME = 'grammar_patterns' THEN
        IF TG_OP <> 'INSERT' THEN
            old_revisions := ARRAY[OLD.structure_revision_id];
        END IF;
        IF TG_OP <> 'DELETE' THEN
            new_revisions := ARRAY[NEW.structure_revision_id];
        END IF;
    ELSIF TG_TABLE_NAME = 'form_analyses' THEN
        IF TG_OP <> 'INSERT' THEN
            old_revisions := ARRAY[OLD.unit_revision_id];
        END IF;
        IF TG_OP <> 'DELETE' THEN
            new_revisions := ARRAY[NEW.unit_revision_id];
        END IF;
    ELSIF TG_TABLE_NAME = 'form_realizations' THEN
        IF TG_OP <> 'INSERT' THEN
            SELECT unit_revision_id INTO old_form_owner_id
            FROM catalogue.form_analyses WHERE form_analysis_id = OLD.form_analysis_id;
            old_revisions := ARRAY[
                old_form_owner_id, OLD.unit_revision_id, OLD.sense_revision_id
            ];
        END IF;
        IF TG_OP <> 'DELETE' THEN
            SELECT unit_revision_id INTO new_form_owner_id
            FROM catalogue.form_analyses WHERE form_analysis_id = NEW.form_analysis_id;
            new_revisions := ARRAY[
                new_form_owner_id, NEW.unit_revision_id, NEW.sense_revision_id
            ];
        END IF;
    ELSIF TG_TABLE_NAME = 'expression_components' THEN
        IF TG_OP <> 'INSERT' THEN
            old_revisions := ARRAY[
                OLD.expression_unit_revision_id, OLD.component_unit_revision_id
            ];
        END IF;
        IF TG_OP <> 'DELETE' THEN
            new_revisions := ARRAY[
                NEW.expression_unit_revision_id, NEW.component_unit_revision_id
            ];
        END IF;
    ELSE
        RAISE EXCEPTION 'unknown catalogue child table %', TG_TABLE_NAME USING ERRCODE = 'XX000';
    END IF;
    IF TG_OP <> 'INSERT' THEN
        PERFORM catalogue.assert_published_revisions_immutable(old_revisions);
    END IF;
    IF TG_OP <> 'DELETE' THEN
        PERFORM catalogue.assert_published_revisions_immutable(new_revisions);
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$function$;

CREATE TRIGGER guard_published_pack_support_variety
BEFORE INSERT OR UPDATE OR DELETE ON catalogue.language_pack_support_varieties
FOR EACH ROW EXECUTE FUNCTION catalogue.guard_published_child();
CREATE TRIGGER guard_published_grammar_pattern
BEFORE INSERT OR UPDATE OR DELETE ON catalogue.grammar_patterns
FOR EACH ROW EXECUTE FUNCTION catalogue.guard_published_child();
CREATE TRIGGER guard_published_form_analysis
BEFORE INSERT OR UPDATE OR DELETE ON catalogue.form_analyses
FOR EACH ROW EXECUTE FUNCTION catalogue.guard_published_child();
CREATE TRIGGER guard_published_form_realization
BEFORE INSERT OR UPDATE OR DELETE ON catalogue.form_realizations
FOR EACH ROW EXECUTE FUNCTION catalogue.guard_published_child();
CREATE TRIGGER guard_published_expression_component
BEFORE INSERT OR UPDATE OR DELETE ON catalogue.expression_components
FOR EACH ROW EXECUTE FUNCTION catalogue.guard_published_child();

CREATE FUNCTION catalogue.validate_form_realization() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE
    analysis_unit_id uuid;
    analysis_pack_revision_id uuid;
    unit_lexical_unit_id uuid;
    sense_lexical_unit_id uuid;
    sense_pack_revision_id uuid;
BEGIN
    SELECT analysis.unit_revision_id, unit_revision.pack_revision_id,
           unit_revision.lexical_unit_id
      INTO analysis_unit_id, analysis_pack_revision_id, unit_lexical_unit_id
    FROM catalogue.form_analyses AS analysis
    JOIN catalogue.lexical_unit_revisions AS unit_revision
      ON unit_revision.unit_revision_id = analysis.unit_revision_id
    WHERE analysis.form_analysis_id = NEW.form_analysis_id;
    IF analysis_unit_id IS DISTINCT FROM NEW.unit_revision_id THEN
        RAISE EXCEPTION 'form realization must match its form analysis unit'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.sense_revision_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT sense.lexical_unit_id, sense_revision.pack_revision_id
      INTO sense_lexical_unit_id, sense_pack_revision_id
    FROM catalogue.lexical_sense_revisions AS sense_revision
    JOIN catalogue.lexical_senses AS sense ON sense.sense_id = sense_revision.sense_id
    WHERE sense_revision.sense_revision_id = NEW.sense_revision_id;
    IF sense_lexical_unit_id IS DISTINCT FROM unit_lexical_unit_id THEN
        RAISE EXCEPTION 'form realization sense must belong to its unit'
            USING ERRCODE = '23514';
    END IF;
    IF sense_pack_revision_id IS DISTINCT FROM analysis_pack_revision_id THEN
        RAISE EXCEPTION 'form realization references a different pack revision'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE FUNCTION catalogue.validate_expression_component() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE
    expression_type varchar;
    expression_pack_revision_id uuid;
    expression_variety_id uuid;
    component_pack_revision_id uuid;
    component_variety_id uuid;
BEGIN
    SELECT unit.unit_type, revision.pack_revision_id, unit.variety_id
      INTO expression_type, expression_pack_revision_id, expression_variety_id
    FROM catalogue.lexical_unit_revisions AS revision
    JOIN catalogue.lexical_units AS unit ON unit.lexical_unit_id = revision.lexical_unit_id
    WHERE revision.unit_revision_id = NEW.expression_unit_revision_id;
    IF expression_type IS DISTINCT FROM 'multiword_expression' THEN
        RAISE EXCEPTION 'expression components require a multiword expression root'
            USING ERRCODE = '23514';
    END IF;
    SELECT revision.pack_revision_id, unit.variety_id
      INTO component_pack_revision_id, component_variety_id
    FROM catalogue.lexical_unit_revisions AS revision
    JOIN catalogue.lexical_units AS unit ON unit.lexical_unit_id = revision.lexical_unit_id
    WHERE revision.unit_revision_id = NEW.component_unit_revision_id;
    IF expression_pack_revision_id IS DISTINCT FROM component_pack_revision_id
       OR expression_variety_id IS DISTINCT FROM component_variety_id THEN
        RAISE EXCEPTION 'expression components must share pack and variety'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

CREATE TRIGGER validate_form_realization
BEFORE INSERT OR UPDATE ON catalogue.form_realizations
FOR EACH ROW EXECUTE FUNCTION catalogue.validate_form_realization();
CREATE TRIGGER validate_expression_component
BEFORE INSERT OR UPDATE ON catalogue.expression_components
FOR EACH ROW EXECUTE FUNCTION catalogue.validate_expression_component();

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
DECLARE
    current_frontier uuid[] := ARRAY[NEW.to_skill_revision_id];
    next_frontier uuid[];
    visited uuid[] := ARRAY[NEW.to_skill_revision_id];
    depth integer := 0;
    max_depth constant integer := 64;
    max_nodes constant integer := 4096;
BEGIN
    IF NEW.edge_type <> 'required' THEN
        RETURN NEW;
    END IF;
    PERFORM pg_advisory_xact_lock(742910171);
    LOOP
        IF NEW.from_skill_revision_id = ANY(current_frontier) THEN
            RAISE EXCEPTION 'prerequisite_cycle' USING ERRCODE = '23514';
        END IF;
        SELECT COALESCE(array_agg(DISTINCT edge.to_skill_revision_id), ARRAY[]::uuid[])
          INTO next_frontier
        FROM catalogue.skill_prerequisite_edges AS edge
        WHERE edge.edge_type = 'required'
          AND edge.edge_id <> NEW.edge_id
          AND edge.from_skill_revision_id = ANY(current_frontier)
          AND NOT edge.to_skill_revision_id = ANY(visited);
        IF cardinality(next_frontier) = 0 THEN
            RETURN NEW;
        END IF;
        depth := depth + 1;
        IF depth > max_depth OR cardinality(visited) + cardinality(next_frontier) > max_nodes THEN
            RAISE EXCEPTION 'prerequisite_graph_limit' USING ERRCODE = '54000';
        END IF;
        visited := visited || next_frontier;
        current_frontier := next_frontier;
    END LOOP;
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

CREATE FUNCTION catalogue.validate_foundation_gate() RETURNS trigger
LANGUAGE plpgsql AS $function$
DECLARE
    definition_pack_revision_id uuid;
    definition_code varchar;
    ordered_codes varchar[];
BEGIN
    SELECT revision.pack_revision_id, definition.foundation_code
      INTO definition_pack_revision_id, definition_code
    FROM catalogue.foundation_definition_revisions AS revision
    JOIN catalogue.foundation_definitions AS definition
      ON definition.foundation_id = revision.foundation_id
    WHERE revision.foundation_revision_id = NEW.foundation_revision_id;
    IF definition_pack_revision_id IS DISTINCT FROM NEW.pack_revision_id
       OR definition_code IS DISTINCT FROM NEW.gate_code THEN
        RAISE EXCEPTION 'foundation gate does not match definition' USING ERRCODE = '23514';
    END IF;
    SELECT array_agg(block_code ORDER BY ordinal)
      INTO ordered_codes
    FROM catalogue.foundation_block_revisions
    WHERE foundation_revision_id = NEW.foundation_revision_id
      AND pack_revision_id = NEW.pack_revision_id
      AND status = 'published';
    IF ordered_codes IS DISTINCT FROM ARRAY['F1', 'F2', 'F3', 'F4', 'F5']::varchar[]
       OR (SELECT count(*) FROM catalogue.foundation_item_revisions AS item
           JOIN catalogue.foundation_block_revisions AS block
             ON block.block_revision_id = item.block_revision_id
           WHERE block.foundation_revision_id = NEW.foundation_revision_id
             AND item.pack_revision_id = NEW.pack_revision_id
             AND item.status = 'published') <> 10 THEN
        RAISE EXCEPTION 'foundation definition is incomplete' USING ERRCODE = '23514';
    END IF;
    IF cardinality(NEW.blocking_target_refs) <>
       (SELECT count(DISTINCT target_ref) FROM unnest(NEW.blocking_target_refs) AS target_ref)
       OR EXISTS (
        SELECT 1
        FROM unnest(NEW.blocking_target_refs) AS requested(target_ref)
        WHERE NOT EXISTS (
            SELECT 1
            FROM catalogue.foundation_item_revisions AS item
            JOIN catalogue.foundation_block_revisions AS block
              ON block.block_revision_id = item.block_revision_id
            CROSS JOIN unnest(item.target_refs) AS declared(target_ref)
            WHERE block.foundation_revision_id = NEW.foundation_revision_id
              AND item.pack_revision_id = NEW.pack_revision_id
              AND item.checker_kind <> 'not_evaluable'
              AND declared.target_ref = requested.target_ref
        )
    ) OR EXISTS (
        SELECT 1
        FROM catalogue.foundation_item_revisions AS item
        JOIN catalogue.foundation_block_revisions AS block
          ON block.block_revision_id = item.block_revision_id
        CROSS JOIN unnest(item.target_refs) AS declared(target_ref)
        WHERE block.foundation_revision_id = NEW.foundation_revision_id
          AND item.pack_revision_id = NEW.pack_revision_id
          AND item.checker_kind <> 'not_evaluable'
          AND NOT declared.target_ref = ANY(NEW.blocking_target_refs)
    ) THEN
        RAISE EXCEPTION 'foundation gate references missing target' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;
CREATE TRIGGER validate_foundation_gate
BEFORE INSERT OR UPDATE ON catalogue.foundation_gate_revisions
FOR EACH ROW EXECUTE FUNCTION catalogue.validate_foundation_gate();

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
ALTER FUNCTION catalogue.foundation_checksum_text(text) OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.foundation_checksum_uuid(uuid) OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.foundation_checksum_integer(integer) OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.foundation_checksum_decimal(numeric) OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.foundation_checksum_boolean(boolean) OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.foundation_checksum_text_array(text[]) OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.foundation_content_checksum(text, text[]) OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.validate_foundation_checksum() OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.validate_foundation_references() OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.reject_late_foundation_insert() OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.reject_published_revision() OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.assert_published_revisions_immutable(uuid[]) OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.guard_published_child() OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.validate_form_realization() OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.validate_expression_component() OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.guard_prerequisite_edge() OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.reject_required_prerequisite_cycle() OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.validate_pack_publication() OWNER TO polyglot_migration;
ALTER FUNCTION catalogue.validate_foundation_gate() OWNER TO polyglot_migration;
"""


async def _execute_catalogue_ddl(connection: Connection) -> None:
    await connection.execute(CATALOGUE_DDL)


def upgrade() -> None:
    op.get_bind().connection.run_async(_execute_catalogue_ddl)


def downgrade() -> None:
    op.execute("DROP SCHEMA catalogue CASCADE")
