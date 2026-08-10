import base64
import json
import unicodedata
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.modules.catalogue.core.domain import (
    ContentRevisionStatus,
    FoundationCheckerKind,
    PublishedFoundationBlock,
    PublishedFoundationCatalogue,
    PublishedFoundationDefinition,
    PublishedFoundationGate,
    PublishedFoundationItem,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue
from polyglot.platform.persistence.models import metadata

language_varieties = Table(
    "language_varieties",
    metadata,
    Column("variety_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("language_tag", String(35), nullable=False, unique=True),
    Column("region_code", String(8)),
    Column("script_codes", ARRAY(String(16)), nullable=False),
    Column("text_direction", String(3), nullable=False),
    Column("segmentation_policy_revision_id", PG_UUID(as_uuid=True), nullable=False),
    Column("media_capabilities", JSONB, nullable=False),
    Column("normalization_policy_revision_id", PG_UUID(as_uuid=True), nullable=False),
    CheckConstraint(
        "catalogue.is_uuid7(variety_id) "
        "AND catalogue.is_uuid7(segmentation_policy_revision_id) "
        "AND catalogue.is_uuid7(normalization_policy_revision_id)",
        name="ck_catalogue_variety_uuid7",
    ),
    CheckConstraint(
        "language_tag ~ '^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})+$'",
        name="ck_catalogue_language_tag",
    ),
    CheckConstraint(
        "cardinality(script_codes) >= 1",
        name="ck_catalogue_variety_scripts",
    ),
    CheckConstraint(
        "text_direction IN ('ltr', 'rtl')",
        name="ck_catalogue_text_direction",
    ),
    CheckConstraint(
        "jsonb_typeof(media_capabilities) = 'object' "
        "AND media_capabilities->>'schema_version' = '1'",
        name="ck_catalogue_media_capabilities",
    ),
    schema="catalogue",
)

language_packs = Table(
    "language_packs",
    metadata,
    Column("pack_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("pack_code", String(120), nullable=False, unique=True),
    CheckConstraint("catalogue.is_uuid7(pack_id)", name="ck_catalogue_pack_uuid7"),
    CheckConstraint(
        "pack_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'",
        name="ck_catalogue_pack_code",
    ),
    schema="catalogue",
)

language_pack_revisions = Table(
    "language_pack_revisions",
    metadata,
    Column("pack_revision_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "pack_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_packs.pack_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("revision_no", Integer, nullable=False),
    Column(
        "target_variety_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_varieties.variety_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("status", String(24), nullable=False),
    Column("engine_min_version", String(32), nullable=False),
    Column("engine_max_version", String(32), nullable=False),
    Column("capability_manifest", JSONB, nullable=False),
    Column("checksum_manifest", JSONB, nullable=False),
    Column("license_refs", ARRAY(String(255)), nullable=False),
    Column(
        "provenance_id",
        PG_UUID(as_uuid=True),
        ForeignKey("platform.provenance_records.provenance_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("published_at", DateTime(timezone=True)),
    CheckConstraint(
        "catalogue.is_uuid7(pack_revision_id) AND catalogue.is_uuid7(pack_id) "
        "AND catalogue.is_uuid7(target_variety_id) AND catalogue.is_uuid7(provenance_id)",
        name="ck_catalogue_pack_revision_uuid7",
    ),
    CheckConstraint("revision_no >= 1", name="ck_catalogue_pack_revision_no"),
    CheckConstraint(
        "status IN ('draft', 'validating', 'validated', 'approved', 'published', "
        "'retired', 'superseded', 'rejected', 'abandoned')",
        name="ck_catalogue_pack_revision_status",
    ),
    CheckConstraint(
        "(status = 'published') = (published_at IS NOT NULL)",
        name="ck_catalogue_pack_publication_shape",
    ),
    CheckConstraint(
        "jsonb_typeof(capability_manifest) = 'object' "
        "AND capability_manifest->>'schema_version' = '1' "
        "AND jsonb_typeof(checksum_manifest) = 'object' "
        "AND checksum_manifest <> '{}'::jsonb AND cardinality(license_refs) >= 1",
        name="ck_catalogue_pack_manifests",
    ),
    UniqueConstraint("pack_id", "revision_no", name="uq_catalogue_pack_revision"),
    schema="catalogue",
)

language_pack_support_varieties = Table(
    "language_pack_support_varieties",
    metadata,
    Column(
        "pack_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_pack_revisions.pack_revision_id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column(
        "variety_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_varieties.variety_id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    schema="catalogue",
)

language_pack_publications = Table(
    "language_pack_publications",
    metadata,
    Column("publication_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "pack_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_packs.pack_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "pack_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_pack_revisions.pack_revision_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    ),
    Column("channel", String(40), nullable=False),
    Column("compatibility_range", String(120), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=False),
    Column("retired_at", DateTime(timezone=True)),
    CheckConstraint(
        "catalogue.is_uuid7(publication_id) AND catalogue.is_uuid7(pack_id) "
        "AND catalogue.is_uuid7(pack_revision_id)",
        name="ck_catalogue_publication_uuid7",
    ),
    CheckConstraint(
        "channel ~ '^[a-z][a-z0-9_]{2,39}$'",
        name="ck_catalogue_publication_channel",
    ),
    CheckConstraint(
        "retired_at IS NULL OR retired_at >= published_at",
        name="ck_catalogue_publication_retirement",
    ),
    schema="catalogue",
)
Index(
    "uq_catalogue_active_pack_publication",
    language_pack_publications.c.pack_id,
    language_pack_publications.c.channel,
    language_pack_publications.c.compatibility_range,
    unique=True,
    postgresql_where=language_pack_publications.c.retired_at.is_(None),
)

skills = Table(
    "skills",
    metadata,
    Column("skill_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("skill_code", String(120), nullable=False, unique=True),
    CheckConstraint("catalogue.is_uuid7(skill_id)", name="ck_catalogue_skill_uuid7"),
    CheckConstraint(
        "skill_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'",
        name="ck_catalogue_skill_code",
    ),
    schema="catalogue",
)

skill_revisions = Table(
    "skill_revisions",
    metadata,
    Column("skill_revision_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "skill_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.skills.skill_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "pack_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_pack_revisions.pack_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("revision_no", Integer, nullable=False),
    Column("skill_type", String(64), nullable=False),
    Column("modality", String(16), nullable=False),
    Column("operation", String(16), nullable=False),
    Column("target_ref", String(120), nullable=False),
    Column("scope", JSONB, nullable=False),
    Column("evidence_protocol_ids", ARRAY(PG_UUID(as_uuid=True)), nullable=False),
    Column("load_profile", JSONB, nullable=False),
    Column("status", String(24), nullable=False),
    Column(
        "provenance_id",
        PG_UUID(as_uuid=True),
        ForeignKey("platform.provenance_records.provenance_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    CheckConstraint(
        "catalogue.is_uuid7(skill_revision_id) AND catalogue.is_uuid7(skill_id) "
        "AND catalogue.is_uuid7(pack_revision_id) AND catalogue.is_uuid7(provenance_id)",
        name="ck_catalogue_skill_revision_uuid7",
    ),
    CheckConstraint("revision_no >= 1", name="ck_catalogue_skill_revision_no"),
    CheckConstraint(
        "status IN ('draft', 'validating', 'validated', 'approved', 'published', "
        "'retired', 'superseded', 'rejected', 'abandoned')",
        name="ck_catalogue_skill_revision_status",
    ),
    CheckConstraint(
        "modality IN ('reading', 'listening', 'writing', 'speaking')",
        name="ck_catalogue_skill_modality",
    ),
    CheckConstraint(
        "operation IN ('recognize', 'recall', 'discriminate', 'transform', "
        "'produce', 'interact', 'repair', 'transfer')",
        name="ck_catalogue_skill_operation",
    ),
    CheckConstraint(
        "skill_type ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$' "
        "AND target_ref ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'",
        name="ck_catalogue_skill_type_code",
    ),
    CheckConstraint(
        "jsonb_typeof(scope) = 'object' AND jsonb_typeof(load_profile) = 'object'",
        name="ck_catalogue_skill_json",
    ),
    UniqueConstraint("skill_id", "revision_no", name="uq_catalogue_skill_revision"),
    schema="catalogue",
)
Index(
    "ix_catalogue_skill_revisions_pack_status",
    skill_revisions.c.pack_revision_id,
    skill_revisions.c.status,
    skill_revisions.c.skill_revision_id,
)

skill_prerequisite_edges = Table(
    "skill_prerequisite_edges",
    metadata,
    Column("edge_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "from_skill_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.skill_revisions.skill_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "to_skill_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.skill_revisions.skill_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("edge_type", String(16), nullable=False),
    Column(
        "provenance_id",
        PG_UUID(as_uuid=True),
        ForeignKey("platform.provenance_records.provenance_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    CheckConstraint(
        "catalogue.is_uuid7(edge_id) AND catalogue.is_uuid7(from_skill_revision_id) "
        "AND catalogue.is_uuid7(to_skill_revision_id) AND catalogue.is_uuid7(provenance_id)",
        name="ck_catalogue_edge_uuid7",
    ),
    CheckConstraint(
        "edge_type IN ('required', 'recommended', 'contrast', 'transfer')",
        name="ck_catalogue_edge_type",
    ),
    CheckConstraint(
        "from_skill_revision_id <> to_skill_revision_id",
        name="ck_catalogue_edge_distinct",
    ),
    UniqueConstraint(
        "from_skill_revision_id",
        "to_skill_revision_id",
        "edge_type",
        name="uq_catalogue_edge",
    ),
    schema="catalogue",
)
Index(
    "ix_catalogue_edges_to_skill",
    skill_prerequisite_edges.c.to_skill_revision_id,
    skill_prerequisite_edges.c.edge_type,
)

grammar_structures = Table(
    "grammar_structures",
    metadata,
    Column("structure_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("structure_code", String(120), nullable=False, unique=True),
    Column(
        "function_skill_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.skills.skill_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    CheckConstraint(
        "catalogue.is_uuid7(structure_id) AND catalogue.is_uuid7(function_skill_id)",
        name="ck_catalogue_structure_uuid7",
    ),
    CheckConstraint(
        "structure_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'",
        name="ck_catalogue_structure_code",
    ),
    schema="catalogue",
)

grammar_structure_revisions = Table(
    "grammar_structure_revisions",
    metadata,
    Column("structure_revision_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "structure_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.grammar_structures.structure_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "pack_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_pack_revisions.pack_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("revision_no", Integer, nullable=False),
    Column("constraints", JSONB, nullable=False),
    Column("contrasts", JSONB, nullable=False),
    Column("typical_errors", JSONB, nullable=False),
    Column("variants", JSONB, nullable=False),
    Column("status", String(24), nullable=False),
    Column(
        "provenance_id",
        PG_UUID(as_uuid=True),
        ForeignKey("platform.provenance_records.provenance_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    CheckConstraint(
        "catalogue.is_uuid7(structure_revision_id) "
        "AND catalogue.is_uuid7(structure_id) "
        "AND catalogue.is_uuid7(pack_revision_id) "
        "AND catalogue.is_uuid7(provenance_id)",
        name="ck_catalogue_structure_revision_uuid7",
    ),
    CheckConstraint("revision_no >= 1", name="ck_catalogue_structure_revision_no"),
    CheckConstraint(
        "status IN ('draft', 'validating', 'validated', 'approved', 'published', "
        "'retired', 'superseded', 'rejected', 'abandoned')",
        name="ck_catalogue_structure_revision_status",
    ),
    CheckConstraint(
        "jsonb_typeof(constraints) = 'object' AND jsonb_typeof(contrasts) = 'array' "
        "AND jsonb_typeof(typical_errors) = 'array' "
        "AND jsonb_typeof(variants) = 'array'",
        name="ck_catalogue_structure_json",
    ),
    UniqueConstraint(
        "structure_id",
        "revision_no",
        name="uq_catalogue_structure_revision",
    ),
    schema="catalogue",
)

grammar_patterns = Table(
    "grammar_patterns",
    metadata,
    Column("pattern_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "structure_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey(
            "catalogue.grammar_structure_revisions.structure_revision_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    ),
    Column("pattern_code", String(120), nullable=False),
    Column("template", Text, nullable=False),
    Column("slots", JSONB, nullable=False),
    Column("instantiation_rules", JSONB, nullable=False),
    Column("examples", ARRAY(Text), nullable=False),
    Column("counterexamples", ARRAY(Text), nullable=False),
    CheckConstraint(
        "catalogue.is_uuid7(pattern_id)",
        name="ck_catalogue_pattern_uuid7",
    ),
    CheckConstraint(
        "jsonb_typeof(slots) = 'array' AND jsonb_typeof(instantiation_rules) = 'object'",
        name="ck_catalogue_pattern_json",
    ),
    CheckConstraint(
        "pattern_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'",
        name="ck_catalogue_pattern_code",
    ),
    UniqueConstraint(
        "structure_revision_id",
        "pattern_code",
        name="uq_catalogue_pattern",
    ),
    schema="catalogue",
)

lexical_units = Table(
    "lexical_units",
    metadata,
    Column("lexical_unit_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "variety_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_varieties.variety_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("unit_type", String(32), nullable=False),
    Column("visibility", String(16), nullable=False),
    Column("owner_profile_id", PG_UUID(as_uuid=True)),
    CheckConstraint(
        "catalogue.is_uuid7(lexical_unit_id) AND catalogue.is_uuid7(variety_id)",
        name="ck_catalogue_lexical_unit_uuid7",
    ),
    CheckConstraint(
        "unit_type IN ('word', 'multiword_expression', 'proper_name', 'lexicalized_construction')",
        name="ck_catalogue_lexical_unit_type",
    ),
    CheckConstraint(
        "visibility = 'shared' AND owner_profile_id IS NULL",
        name="ck_catalogue_lexical_visibility",
    ),
    schema="catalogue",
)

lexical_unit_revisions = Table(
    "lexical_unit_revisions",
    metadata,
    Column("unit_revision_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "lexical_unit_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.lexical_units.lexical_unit_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "pack_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_pack_revisions.pack_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("revision_no", Integer, nullable=False),
    Column("lemma", Text, nullable=False),
    Column("part_of_speech", String(64), nullable=False),
    Column("register", String(64)),
    Column("status", String(24), nullable=False),
    Column(
        "provenance_id",
        PG_UUID(as_uuid=True),
        ForeignKey("platform.provenance_records.provenance_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    CheckConstraint(
        "catalogue.is_uuid7(unit_revision_id) "
        "AND catalogue.is_uuid7(lexical_unit_id) "
        "AND catalogue.is_uuid7(pack_revision_id) "
        "AND catalogue.is_uuid7(provenance_id)",
        name="ck_catalogue_unit_revision_uuid7",
    ),
    CheckConstraint("revision_no >= 1", name="ck_catalogue_unit_revision_no"),
    CheckConstraint(
        "status IN ('draft', 'validating', 'validated', 'approved', 'published', "
        "'retired', 'superseded', 'rejected', 'abandoned')",
        name="ck_catalogue_unit_revision_status",
    ),
    CheckConstraint(
        "length(lemma) BETWEEN 1 AND 500",
        name="ck_catalogue_lemma",
    ),
    UniqueConstraint(
        "lexical_unit_id",
        "revision_no",
        name="uq_catalogue_unit_revision",
    ),
    schema="catalogue",
)

lexical_senses = Table(
    "lexical_senses",
    metadata,
    Column("sense_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "lexical_unit_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.lexical_units.lexical_unit_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("sense_code", String(120), nullable=False),
    CheckConstraint(
        "catalogue.is_uuid7(sense_id) AND catalogue.is_uuid7(lexical_unit_id)",
        name="ck_catalogue_sense_uuid7",
    ),
    CheckConstraint(
        "sense_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'",
        name="ck_catalogue_sense_code",
    ),
    UniqueConstraint("lexical_unit_id", "sense_code", name="uq_catalogue_sense_code"),
    schema="catalogue",
)

lexical_sense_revisions = Table(
    "lexical_sense_revisions",
    metadata,
    Column("sense_revision_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "sense_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.lexical_senses.sense_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "pack_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_pack_revisions.pack_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("revision_no", Integer, nullable=False),
    Column("definition", Text, nullable=False),
    Column("domains", ARRAY(String(120)), nullable=False),
    Column("register", String(64)),
    Column("status", String(24), nullable=False),
    Column(
        "provenance_id",
        PG_UUID(as_uuid=True),
        ForeignKey("platform.provenance_records.provenance_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    CheckConstraint(
        "catalogue.is_uuid7(sense_revision_id) AND catalogue.is_uuid7(sense_id) "
        "AND catalogue.is_uuid7(pack_revision_id) AND catalogue.is_uuid7(provenance_id)",
        name="ck_catalogue_sense_revision_uuid7",
    ),
    CheckConstraint("revision_no >= 1", name="ck_catalogue_sense_revision_no"),
    CheckConstraint(
        "status IN ('draft', 'validating', 'validated', 'approved', 'published', "
        "'retired', 'superseded', 'rejected', 'abandoned')",
        name="ck_catalogue_sense_revision_status",
    ),
    CheckConstraint(
        "length(definition) BETWEEN 1 AND 2000",
        name="ck_catalogue_definition",
    ),
    UniqueConstraint("sense_id", "revision_no", name="uq_catalogue_sense_revision"),
    schema="catalogue",
)

form_analyses = Table(
    "form_analyses",
    metadata,
    Column("form_analysis_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "unit_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.lexical_unit_revisions.unit_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("surface", Text, nullable=False),
    Column("morphological_features", JSONB, nullable=False),
    Column("pronunciation_refs", ARRAY(PG_UUID(as_uuid=True)), nullable=False),
    Column("normalization_key", Text, nullable=False),
    CheckConstraint(
        "catalogue.is_uuid7(form_analysis_id)",
        name="ck_catalogue_form_uuid7",
    ),
    CheckConstraint(
        "length(surface) BETWEEN 1 AND 500 AND length(normalization_key) BETWEEN 1 AND 500",
        name="ck_catalogue_form_surface",
    ),
    CheckConstraint(
        "jsonb_typeof(morphological_features) = 'object'",
        name="ck_catalogue_form_features",
    ),
    UniqueConstraint(
        "unit_revision_id",
        "surface",
        "morphological_features",
        name="uq_catalogue_form_analysis",
    ),
    schema="catalogue",
)
Index(
    "ix_catalogue_form_normalization",
    form_analyses.c.normalization_key,
    form_analyses.c.form_analysis_id,
)

form_realizations = Table(
    "form_realizations",
    metadata,
    Column("realization_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "form_analysis_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.form_analyses.form_analysis_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "unit_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.lexical_unit_revisions.unit_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "sense_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.lexical_sense_revisions.sense_revision_id", ondelete="RESTRICT"),
    ),
    CheckConstraint(
        "catalogue.is_uuid7(realization_id) AND catalogue.is_uuid7(form_analysis_id) "
        "AND catalogue.is_uuid7(unit_revision_id) "
        "AND (sense_revision_id IS NULL OR catalogue.is_uuid7(sense_revision_id))",
        name="ck_catalogue_realization_uuid7",
    ),
    UniqueConstraint(
        "form_analysis_id",
        "unit_revision_id",
        "sense_revision_id",
        name="uq_catalogue_form_realization",
    ),
    schema="catalogue",
)

expression_components = Table(
    "expression_components",
    metadata,
    Column(
        "expression_unit_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.lexical_unit_revisions.unit_revision_id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column(
        "component_unit_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.lexical_unit_revisions.unit_revision_id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column("position", Integer, nullable=False),
    CheckConstraint(
        "expression_unit_revision_id <> component_unit_revision_id",
        name="ck_catalogue_expression_distinct",
    ),
    CheckConstraint(
        "position >= 1",
        name="ck_catalogue_expression_position",
    ),
    UniqueConstraint(
        "expression_unit_revision_id",
        "position",
        name="uq_catalogue_expression_position",
    ),
    schema="catalogue",
)

foundation_definitions = Table(
    "foundation_definitions",
    metadata,
    Column("foundation_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("foundation_code", String(120), nullable=False, unique=True),
    CheckConstraint("catalogue.is_uuid7(foundation_id)", name="ck_catalogue_foundation_uuid7"),
    CheckConstraint(
        "foundation_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'",
        name="ck_catalogue_foundation_code",
    ),
    schema="catalogue",
)

foundation_definition_revisions = Table(
    "foundation_definition_revisions",
    metadata,
    Column("foundation_revision_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "foundation_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.foundation_definitions.foundation_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "pack_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_pack_revisions.pack_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("revision_no", Integer, nullable=False),
    Column("status", String(24), nullable=False),
    Column("checksum", String(64), nullable=False),
    CheckConstraint(
        "catalogue.is_uuid7(foundation_revision_id) AND catalogue.is_uuid7(foundation_id) "
        "AND catalogue.is_uuid7(pack_revision_id)",
        name="ck_catalogue_foundation_revision_uuid7",
    ),
    CheckConstraint("revision_no >= 1", name="ck_catalogue_foundation_revision_no"),
    CheckConstraint("status = 'published'", name="ck_catalogue_foundation_revision_status"),
    CheckConstraint(
        "checksum ~ '^[0-9a-f]{64}$'", name="ck_catalogue_foundation_revision_checksum"
    ),
    UniqueConstraint("foundation_id", "revision_no", name="uq_catalogue_foundation_revision"),
    UniqueConstraint("pack_revision_id", "foundation_id", name="uq_catalogue_pack_foundation"),
    schema="catalogue",
)

foundation_block_revisions = Table(
    "foundation_block_revisions",
    metadata,
    Column("block_revision_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "foundation_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey(
            "catalogue.foundation_definition_revisions.foundation_revision_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    ),
    Column(
        "pack_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_pack_revisions.pack_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("block_code", String(16), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("component_type", String(64), nullable=False),
    Column("prerequisite_refs", ARRAY(String(120)), nullable=False),
    Column("modalities", ARRAY(String(16)), nullable=False),
    Column("backend_criteria", JSONB, nullable=False),
    Column("waiver_policy_ref", String(120), nullable=False),
    Column("status", String(24), nullable=False),
    Column("checksum", String(64), nullable=False),
    CheckConstraint(
        "catalogue.is_uuid7(block_revision_id) AND catalogue.is_uuid7(foundation_revision_id) "
        "AND catalogue.is_uuid7(pack_revision_id)",
        name="ck_catalogue_foundation_block_uuid7",
    ),
    CheckConstraint("ordinal BETWEEN 1 AND 5", name="ck_catalogue_foundation_block_ordinal"),
    CheckConstraint("status = 'published'", name="ck_catalogue_foundation_block_status"),
    CheckConstraint(
        "block_code ~ '^F[1-5]$' AND component_type ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$' "
        "AND waiver_policy_ref ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$'",
        name="ck_catalogue_foundation_block_codes",
    ),
    CheckConstraint(
        "cardinality(modalities) >= 1 AND modalities <@ ARRAY['reading', 'listening', "
        "'writing', 'speaking']::varchar[] AND jsonb_typeof(backend_criteria) = 'array' "
        "AND jsonb_array_length(backend_criteria) >= 1 AND checksum ~ '^[0-9a-f]{64}$'",
        name="ck_catalogue_foundation_block_shape",
    ),
    UniqueConstraint(
        "foundation_revision_id", "ordinal", name="uq_catalogue_foundation_block_ordinal"
    ),
    UniqueConstraint(
        "foundation_revision_id", "block_code", name="uq_catalogue_foundation_block_code"
    ),
    schema="catalogue",
)

foundation_item_revisions = Table(
    "foundation_item_revisions",
    metadata,
    Column("item_revision_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "block_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.foundation_block_revisions.block_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "pack_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_pack_revisions.pack_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("item_code", String(120), nullable=False, unique=True),
    Column("ordinal", Integer, nullable=False),
    Column("target_refs", ARRAY(String(120)), nullable=False),
    Column("response_kind", String(16), nullable=False),
    Column("checker_kind", String(32), nullable=False),
    Column("checker_values", ARRAY(Text), nullable=False),
    Column("modalities", ARRAY(String(16)), nullable=False),
    Column("status", String(24), nullable=False),
    Column("checksum", String(64), nullable=False),
    CheckConstraint(
        "catalogue.is_uuid7(item_revision_id) AND catalogue.is_uuid7(block_revision_id) "
        "AND catalogue.is_uuid7(pack_revision_id)",
        name="ck_catalogue_foundation_item_uuid7",
    ),
    CheckConstraint("ordinal >= 1", name="ck_catalogue_foundation_item_ordinal"),
    CheckConstraint("status = 'published'", name="ck_catalogue_foundation_item_status"),
    CheckConstraint(
        "item_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$' "
        "AND cardinality(target_refs) >= 1 "
        "AND response_kind = 'raw' "
        "AND checker_kind IN ('exact_choice', 'exact_reconstruction', "
        "'normalized_alternatives', 'not_evaluable') "
        "AND ((checker_kind = 'not_evaluable' AND cardinality(checker_values) = 0) "
        "OR (checker_kind <> 'not_evaluable' AND cardinality(checker_values) >= 1)) "
        "AND cardinality(modalities) >= 1 "
        "AND modalities <@ ARRAY['reading', 'listening', 'writing', 'speaking']::varchar[] "
        "AND checksum ~ '^[0-9a-f]{64}$'",
        name="ck_catalogue_foundation_item_shape",
    ),
    UniqueConstraint("block_revision_id", "ordinal", name="uq_catalogue_foundation_item_ordinal"),
    schema="catalogue",
)

foundation_gate_revisions = Table(
    "foundation_gate_revisions",
    metadata,
    Column("gate_revision_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "foundation_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey(
            "catalogue.foundation_definition_revisions.foundation_revision_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        unique=True,
    ),
    Column(
        "pack_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_pack_revisions.pack_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("gate_code", String(120), nullable=False),
    Column("blocking_target_refs", ARRAY(String(120)), nullable=False),
    Column("blocking_facet_refs", ARRAY(String(120)), nullable=False),
    Column("coverage_threshold", Numeric(4, 3), nullable=False),
    Column("confidence_threshold", Numeric(4, 3), nullable=False),
    Column("minimum_distinct_sessions", Integer, nullable=False),
    Column("delayed_control_hours", Integer, nullable=False),
    Column("grapheme_sound_minimum", Integer, nullable=False),
    Column("grapheme_sound_total", Integer, nullable=False),
    Column("targeted_reading_minimum", Integer, nullable=False),
    Column("targeted_reading_total", Integer, nullable=False),
    Column("survival_exchange_minimum", Integer, nullable=False),
    Column("survival_exchange_total", Integer, nullable=False),
    Column("oral_policy", String(64), nullable=False),
    Column("status", String(24), nullable=False),
    Column("checksum", String(64), nullable=False),
    CheckConstraint(
        "catalogue.is_uuid7(gate_revision_id) AND catalogue.is_uuid7(foundation_revision_id) "
        "AND catalogue.is_uuid7(pack_revision_id)",
        name="ck_catalogue_foundation_gate_uuid7",
    ),
    CheckConstraint(
        "gate_code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$' "
        "AND cardinality(blocking_target_refs) >= 1 AND cardinality(blocking_facet_refs) >= 1 "
        "AND coverage_threshold::numeric > 0 AND coverage_threshold::numeric <= 1 "
        "AND confidence_threshold::numeric > 0 AND confidence_threshold::numeric <= 1 "
        "AND minimum_distinct_sessions >= 2 AND delayed_control_hours >= 24 "
        "AND grapheme_sound_minimum BETWEEN 1 AND grapheme_sound_total "
        "AND targeted_reading_minimum BETWEEN 1 AND targeted_reading_total "
        "AND survival_exchange_minimum BETWEEN 1 AND survival_exchange_total "
        "AND oral_policy = 'not_evaluable_non_blocking' "
        "AND status = 'published' AND checksum ~ '^[0-9a-f]{64}$'",
        name="ck_catalogue_foundation_gate_shape",
    ),
    schema="catalogue",
)


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: tuple[T, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class LanguagePackSummary:
    pack_id: UUID
    pack_revision_id: UUID
    pack_code: str
    revision_no: int
    target_language_tag: str
    support_language_tags: tuple[str, ...]
    channel: str
    compatibility_range: str


@dataclass(frozen=True, slots=True)
class CatalogueTarget:
    skill_id: UUID
    skill_revision_id: UUID
    skill_code: str
    skill_type: str
    modality: str
    operation: str
    target_ref: str
    required_prerequisite_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LexicalAnalysisSummary:
    form_analysis_id: UUID
    unit_revision_id: UUID
    lemma: str
    unit_type: str
    part_of_speech: str
    morphological_features: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class LexicalSenseSummary:
    sense_id: UUID
    sense_revision_id: UUID
    sense_code: str
    definition: str


@dataclass(frozen=True, slots=True)
class LexiconSearchItem:
    surface: str
    analysis: LexicalAnalysisSummary
    senses: tuple[LexicalSenseSummary, ...]


def normalize_search_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold().strip()


def _encode_cursor(kind: str, values: tuple[str, ...]) -> str:
    payload = json.dumps([kind, *values], ensure_ascii=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str | None, kind: str, size: int) -> tuple[str, ...] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DomainError(ErrorCode.CURSOR_INVALID) from error
    if (
        not isinstance(payload, list)
        or len(payload) != size + 1
        or payload[0] != kind
        or not all(isinstance(value, str) for value in payload[1:])
    ):
        raise DomainError(ErrorCode.CURSOR_INVALID)
    return tuple(payload[1:])


class SqlCatalogueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_language_packs(
        self,
        *,
        limit: int,
        cursor: str | None,
    ) -> Page[LanguagePackSummary]:
        after = _decode_cursor(cursor, "language_packs", 2)
        rows = (
            (
                await self._session.execute(
                    text(
                        "SELECT pack.pack_id, revision.pack_revision_id, pack.pack_code, "
                        "revision.revision_no, target.language_tag AS target_language_tag, "
                        "array_agg(support.language_tag ORDER BY support.language_tag) "
                        "AS support_language_tags, publication.channel, "
                        "publication.compatibility_range "
                        "FROM catalogue.language_pack_publications AS publication "
                        "JOIN catalogue.language_packs AS pack "
                        "ON pack.pack_id = publication.pack_id "
                        "JOIN catalogue.language_pack_revisions AS revision "
                        "ON revision.pack_revision_id = publication.pack_revision_id "
                        "JOIN catalogue.language_varieties AS target "
                        "ON target.variety_id = revision.target_variety_id "
                        "JOIN catalogue.language_pack_support_varieties AS member "
                        "ON member.pack_revision_id = revision.pack_revision_id "
                        "JOIN catalogue.language_varieties AS support "
                        "ON support.variety_id = member.variety_id "
                        "WHERE publication.retired_at IS NULL AND revision.status = 'published' "
                        "AND (CAST(:after_code AS varchar) IS NULL "
                        "OR (pack.pack_code, revision.pack_revision_id) "
                        "> (CAST(:after_code AS varchar), CAST(:after_id AS uuid))) "
                        "GROUP BY pack.pack_id, revision.pack_revision_id, target.language_tag, "
                        "publication.channel, publication.compatibility_range "
                        "ORDER BY pack.pack_code, revision.pack_revision_id LIMIT :query_limit"
                    ),
                    {
                        "after_code": None if after is None else after[0],
                        "after_id": None if after is None else after[1],
                        "query_limit": limit + 1,
                    },
                )
            )
            .mappings()
            .all()
        )
        visible = rows[:limit]
        items = tuple(
            LanguagePackSummary(
                pack_id=row["pack_id"],
                pack_revision_id=row["pack_revision_id"],
                pack_code=row["pack_code"],
                revision_no=row["revision_no"],
                target_language_tag=row["target_language_tag"],
                support_language_tags=tuple(row["support_language_tags"]),
                channel=row["channel"],
                compatibility_range=row["compatibility_range"],
            )
            for row in visible
        )
        next_cursor = None
        if len(rows) > limit:
            last = visible[-1]
            next_cursor = _encode_cursor(
                "language_packs",
                (last["pack_code"], str(last["pack_revision_id"])),
            )
        return Page(items, next_cursor)

    async def list_targets(
        self,
        *,
        pack_code: str,
        limit: int,
        cursor: str | None,
    ) -> Page[CatalogueTarget]:
        after = _decode_cursor(cursor, "catalogue_targets", 2)
        rows = (
            (
                await self._session.execute(
                    text(
                        "SELECT skill.skill_id, revision.skill_revision_id, skill.skill_code, "
                        "revision.skill_type, revision.modality, revision.operation, "
                        "revision.target_ref, COALESCE(array_agg(prerequisite.skill_code "
                        "ORDER BY prerequisite.skill_code) FILTER "
                        "(WHERE edge.edge_type = 'required'), ARRAY[]::varchar[]) "
                        "AS prerequisite_codes "
                        "FROM catalogue.language_pack_publications AS publication "
                        "JOIN catalogue.language_packs AS pack "
                        "ON pack.pack_id = publication.pack_id "
                        "JOIN catalogue.skill_revisions AS revision "
                        "ON revision.pack_revision_id = publication.pack_revision_id "
                        "JOIN catalogue.skills AS skill ON skill.skill_id = revision.skill_id "
                        "LEFT JOIN catalogue.skill_prerequisite_edges AS edge "
                        "ON edge.to_skill_revision_id = revision.skill_revision_id "
                        "AND edge.edge_type = 'required' "
                        "LEFT JOIN catalogue.skill_revisions AS prerequisite_revision "
                        "ON prerequisite_revision.skill_revision_id = edge.from_skill_revision_id "
                        "LEFT JOIN catalogue.skills AS prerequisite "
                        "ON prerequisite.skill_id = prerequisite_revision.skill_id "
                        "WHERE publication.retired_at IS NULL AND revision.status = 'published' "
                        "AND pack.pack_code = :pack_code "
                        "AND (CAST(:after_code AS varchar) IS NULL "
                        "OR (skill.skill_code, revision.skill_revision_id) "
                        "> (CAST(:after_code AS varchar), CAST(:after_id AS uuid))) "
                        "GROUP BY skill.skill_id, revision.skill_revision_id "
                        "ORDER BY skill.skill_code, revision.skill_revision_id LIMIT :query_limit"
                    ),
                    {
                        "pack_code": pack_code,
                        "after_code": None if after is None else after[0],
                        "after_id": None if after is None else after[1],
                        "query_limit": limit + 1,
                    },
                )
            )
            .mappings()
            .all()
        )
        visible = rows[:limit]
        items = tuple(
            CatalogueTarget(
                skill_id=row["skill_id"],
                skill_revision_id=row["skill_revision_id"],
                skill_code=row["skill_code"],
                skill_type=row["skill_type"],
                modality=row["modality"],
                operation=row["operation"],
                target_ref=row["target_ref"],
                required_prerequisite_codes=tuple(row["prerequisite_codes"]),
            )
            for row in visible
        )
        next_cursor = None
        if len(rows) > limit:
            last = visible[-1]
            next_cursor = _encode_cursor(
                "catalogue_targets",
                (last["skill_code"], str(last["skill_revision_id"])),
            )
        return Page(items, next_cursor)

    async def search_lexicon(
        self,
        *,
        query: str,
        language_tag: str,
        limit: int,
        cursor: str | None,
    ) -> Page[LexiconSearchItem]:
        after = _decode_cursor(cursor, "lexicon_search", 2)
        rows = (
            (
                await self._session.execute(
                    text(
                        "WITH matching_forms AS ("
                        "SELECT DISTINCT form.surface, form.form_analysis_id, "
                        "form.unit_revision_id, "
                        "form.morphological_features, unit_revision.lemma, unit.unit_type, "
                        "unit_revision.part_of_speech "
                        "FROM catalogue.form_analyses AS form "
                        "JOIN catalogue.lexical_unit_revisions AS unit_revision "
                        "ON unit_revision.unit_revision_id = form.unit_revision_id "
                        "JOIN catalogue.lexical_units AS unit "
                        "ON unit.lexical_unit_id = unit_revision.lexical_unit_id "
                        "JOIN catalogue.language_varieties AS variety "
                        "ON variety.variety_id = unit.variety_id "
                        "JOIN catalogue.language_pack_publications AS publication "
                        "ON publication.pack_revision_id = unit_revision.pack_revision_id "
                        "JOIN catalogue.form_realizations AS realization "
                        "ON realization.form_analysis_id = form.form_analysis_id "
                        "JOIN catalogue.lexical_sense_revisions AS sense_revision "
                        "ON sense_revision.sense_revision_id = realization.sense_revision_id "
                        "WHERE publication.retired_at IS NULL "
                        "AND unit_revision.status = 'published' "
                        "AND sense_revision.status = 'published' "
                        "AND variety.language_tag = :language_tag "
                        "AND form.normalization_key = :query"
                        "), paged_forms AS ("
                        "SELECT * FROM matching_forms "
                        "WHERE (CAST(:after_surface AS text) IS NULL "
                        "OR (surface, form_analysis_id) > "
                        "(CAST(:after_surface AS text), CAST(:after_id AS uuid))) "
                        "ORDER BY surface, form_analysis_id LIMIT :query_limit"
                        ") "
                        "SELECT form.surface, form.form_analysis_id, form.unit_revision_id, "
                        "form.morphological_features, form.lemma, form.unit_type, "
                        "form.part_of_speech, sense.sense_id, sense_revision.sense_revision_id, "
                        "sense.sense_code, sense_revision.definition "
                        "FROM paged_forms AS form "
                        "JOIN catalogue.form_realizations AS realization "
                        "ON realization.form_analysis_id = form.form_analysis_id "
                        "JOIN catalogue.lexical_sense_revisions AS sense_revision "
                        "ON sense_revision.sense_revision_id = realization.sense_revision_id "
                        "JOIN catalogue.lexical_senses AS sense "
                        "ON sense.sense_id = sense_revision.sense_id "
                        "ORDER BY form.surface, form.form_analysis_id, sense.sense_code"
                    ),
                    {
                        "language_tag": language_tag,
                        "query": normalize_search_key(query),
                        "after_surface": None if after is None else after[0],
                        "after_id": None if after is None else after[1],
                        "query_limit": limit + 1,
                    },
                )
            )
            .mappings()
            .all()
        )
        grouped: list[LexiconSearchItem] = []
        for row in rows:
            key = (row["surface"], str(row["form_analysis_id"]))
            sense = LexicalSenseSummary(
                sense_id=row["sense_id"],
                sense_revision_id=row["sense_revision_id"],
                sense_code=row["sense_code"],
                definition=row["definition"],
            )
            if (
                grouped
                and (
                    grouped[-1].surface,
                    str(grouped[-1].analysis.form_analysis_id),
                )
                == key
            ):
                previous = grouped[-1]
                grouped[-1] = LexiconSearchItem(
                    surface=previous.surface,
                    analysis=previous.analysis,
                    senses=(*previous.senses, sense),
                )
                continue
            grouped.append(
                LexiconSearchItem(
                    surface=row["surface"],
                    analysis=LexicalAnalysisSummary(
                        form_analysis_id=row["form_analysis_id"],
                        unit_revision_id=row["unit_revision_id"],
                        lemma=row["lemma"],
                        unit_type=row["unit_type"],
                        part_of_speech=row["part_of_speech"],
                        morphological_features=cast(
                            dict[str, JsonValue], row["morphological_features"]
                        ),
                    ),
                    senses=(sense,),
                )
            )
        visible = grouped[:limit]
        next_cursor = None
        if len(grouped) > limit:
            last = visible[-1]
            next_cursor = _encode_cursor(
                "lexicon_search",
                (last.surface, str(last.analysis.form_analysis_id)),
            )
        return Page(tuple(visible), next_cursor)

    async def read_foundations(
        self,
        *,
        pack_revision_id: UUID,
    ) -> PublishedFoundationCatalogue | None:
        definitions = (
            (
                await self._session.execute(
                    text(
                        "SELECT definition.foundation_id, revision.foundation_revision_id, "
                        "revision.pack_revision_id, definition.foundation_code, "
                        "revision.revision_no, "
                        "revision.status, revision.checksum "
                        "FROM catalogue.foundation_definition_revisions AS revision "
                        "JOIN catalogue.foundation_definitions AS definition "
                        "ON definition.foundation_id = revision.foundation_id "
                        "WHERE revision.pack_revision_id = :pack_revision_id "
                        "AND revision.status = 'published' "
                        "ORDER BY definition.foundation_code, "
                        "revision.foundation_revision_id LIMIT 2"
                    ),
                    {"pack_revision_id": pack_revision_id},
                )
            )
            .mappings()
            .all()
        )
        if len(definitions) != 1:
            return None
        definition = definitions[0]
        blocks = (
            (
                await self._session.execute(
                    text(
                        "SELECT block_revision_id, foundation_revision_id, "
                        "pack_revision_id, block_code, "
                        "ordinal, component_type, prerequisite_refs, modalities, backend_criteria, "
                        "waiver_policy_ref, status, checksum "
                        "FROM catalogue.foundation_block_revisions "
                        "WHERE foundation_revision_id = :foundation_revision_id "
                        "AND pack_revision_id = :pack_revision_id AND status = 'published' "
                        "ORDER BY ordinal, block_revision_id LIMIT 6"
                    ),
                    {
                        "foundation_revision_id": definition["foundation_revision_id"],
                        "pack_revision_id": pack_revision_id,
                    },
                )
            )
            .mappings()
            .all()
        )
        if len(blocks) != 5:
            return None
        items = (
            (
                await self._session.execute(
                    text(
                        "SELECT item_revision_id, block_revision_id, pack_revision_id, "
                        "item_code, ordinal, target_refs, response_kind, checker_kind, "
                        "checker_values, modalities, status, checksum "
                        "FROM catalogue.foundation_item_revisions "
                        "WHERE block_revision_id = ANY(CAST(:block_revision_ids AS uuid[])) "
                        "AND pack_revision_id = :pack_revision_id AND status = 'published' "
                        "ORDER BY block_revision_id, ordinal, item_revision_id LIMIT 16"
                    ),
                    {
                        "block_revision_ids": [item["block_revision_id"] for item in blocks],
                        "pack_revision_id": pack_revision_id,
                    },
                )
            )
            .mappings()
            .all()
        )
        if len(items) != 10:
            return None
        gates = (
            (
                await self._session.execute(
                    text(
                        "SELECT gate_revision_id, foundation_revision_id, pack_revision_id, "
                        "gate_code, blocking_target_refs, blocking_facet_refs, coverage_threshold, "
                        "confidence_threshold, "
                        "minimum_distinct_sessions, delayed_control_hours, grapheme_sound_minimum, "
                        "grapheme_sound_total, targeted_reading_minimum, targeted_reading_total, "
                        "survival_exchange_minimum, survival_exchange_total, oral_policy, "
                        "status, checksum "
                        "FROM catalogue.foundation_gate_revisions "
                        "WHERE foundation_revision_id = :foundation_revision_id "
                        "AND pack_revision_id = :pack_revision_id AND status = 'published' "
                        "ORDER BY gate_revision_id LIMIT 2"
                    ),
                    {
                        "foundation_revision_id": definition["foundation_revision_id"],
                        "pack_revision_id": pack_revision_id,
                    },
                )
            )
            .mappings()
            .all()
        )
        if len(gates) != 1:
            return None

        items_by_block: dict[UUID, list[PublishedFoundationItem]] = {}
        for item in items:
            published_item = PublishedFoundationItem(
                item_revision_id=item["item_revision_id"],
                block_revision_id=item["block_revision_id"],
                pack_revision_id=item["pack_revision_id"],
                item_code=item["item_code"],
                ordinal=item["ordinal"],
                target_refs=tuple(item["target_refs"]),
                response_kind=item["response_kind"],
                checker_kind=FoundationCheckerKind(item["checker_kind"]),
                checker_values=tuple(item["checker_values"]),
                modalities=tuple(item["modalities"]),
                status=ContentRevisionStatus(item["status"]),
                checksum=item["checksum"],
            )
            items_by_block.setdefault(published_item.block_revision_id, []).append(published_item)
        try:
            published_blocks = tuple(
                PublishedFoundationBlock(
                    block_revision_id=item["block_revision_id"],
                    foundation_revision_id=item["foundation_revision_id"],
                    pack_revision_id=item["pack_revision_id"],
                    block_code=item["block_code"],
                    ordinal=item["ordinal"],
                    component_type=item["component_type"],
                    prerequisite_refs=tuple(item["prerequisite_refs"]),
                    items=tuple(items_by_block.get(item["block_revision_id"], ())),
                    modalities=tuple(item["modalities"]),
                    backend_criteria=tuple(cast(list[str], item["backend_criteria"])),
                    waiver_policy_ref=item["waiver_policy_ref"],
                    status=ContentRevisionStatus(item["status"]),
                    checksum=item["checksum"],
                )
                for item in blocks
            )
            gate = gates[0]
            published_gate = PublishedFoundationGate(
                gate_revision_id=gate["gate_revision_id"],
                foundation_revision_id=gate["foundation_revision_id"],
                pack_revision_id=gate["pack_revision_id"],
                gate_code=gate["gate_code"],
                blocking_target_refs=tuple(gate["blocking_target_refs"]),
                blocking_facet_refs=tuple(gate["blocking_facet_refs"]),
                coverage_threshold=float(gate["coverage_threshold"]),
                confidence_threshold=float(gate["confidence_threshold"]),
                minimum_distinct_sessions=gate["minimum_distinct_sessions"],
                delayed_control_hours=gate["delayed_control_hours"],
                grapheme_sound_minimum=gate["grapheme_sound_minimum"],
                grapheme_sound_total=gate["grapheme_sound_total"],
                targeted_reading_minimum=gate["targeted_reading_minimum"],
                targeted_reading_total=gate["targeted_reading_total"],
                survival_exchange_minimum=gate["survival_exchange_minimum"],
                survival_exchange_total=gate["survival_exchange_total"],
                oral_policy=gate["oral_policy"],
                status=ContentRevisionStatus(gate["status"]),
                checksum=gate["checksum"],
            )
            return PublishedFoundationCatalogue(
                definition=PublishedFoundationDefinition(
                    foundation_id=definition["foundation_id"],
                    foundation_revision_id=definition["foundation_revision_id"],
                    pack_revision_id=definition["pack_revision_id"],
                    foundation_code=definition["foundation_code"],
                    revision_no=definition["revision_no"],
                    blocks=published_blocks,
                    gate=published_gate,
                    status=ContentRevisionStatus(definition["status"]),
                    checksum=definition["checksum"],
                )
            )
        except (KeyError, TypeError, ValueError, DomainError):
            return None
