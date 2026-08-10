from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from polyglot.platform.json_types import JsonValue

SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
DEFAULT_MAX_INPUT_BYTES = 256 * 1024
DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024

_OUTPUT_CONTRACTS: Final[dict[str, tuple[frozenset[str], frozenset[str]]]] = {
    "profile.read_authorized": (
        frozenset({"profile_id", "field_groups", "pseudonymized", "cutoff"}),
        frozenset(),
    ),
    "catalogue.list_targets": (
        frozenset({"targets", "next_cursor", "stable"}),
        frozenset(),
    ),
    "lexicon.read_session_scope": (
        frozenset({"senses", "snapshot_id"}),
        frozenset(),
    ),
    "exercise.get_blueprint": (
        frozenset(
            {
                "primitive_id",
                "contract_version",
                "correction_strategies",
                "publish_capability",
            }
        ),
        frozenset(),
    ),
    "exercise.submit_draft": (
        frozenset(
            {
                "draft_id",
                "draft_type",
                "revision",
                "status",
                "findings",
                "checksum",
                "publish_capability",
                "mastery_capability",
            }
        ),
        frozenset(),
    ),
    "content.validate_draft": (
        frozenset(
            {"validation_report_id", "decision", "findings", "report_truncated"}
        ),
        frozenset(),
    ),
    "curriculum.submit_module_draft": (
        frozenset(
            {
                "draft_id",
                "draft_type",
                "revision",
                "status",
                "findings",
                "checksum",
                "publish_capability",
                "mastery_capability",
            }
        ),
        frozenset(),
    ),
    "curriculum.submit_day_draft": (
        frozenset(
            {
                "draft_id",
                "draft_type",
                "revision",
                "status",
                "findings",
                "checksum",
                "publish_capability",
                "mastery_capability",
            }
        ),
        frozenset(),
    ),
    "correction.submit_structured_draft": (
        frozenset(
            {
                "draft_id",
                "draft_type",
                "revision",
                "status",
                "findings",
                "checksum",
                "publish_capability",
                "mastery_capability",
            }
        ),
        frozenset(),
    ),
    "quality.report_ambiguity": (
        frozenset(
            {
                "quality_report_id",
                "status",
                "visibility",
                "deduplication_fingerprint",
            }
        ),
        frozenset(),
    ),
    "progress.explain_recommendation": (
        frozenset({"recommendation_id", "reason_codes", "facts", "alternatives"}),
        frozenset(),
    ),
}


class ToolEffect(StrEnum):
    NONE = "none"
    CREATE_DRAFT = "create_draft"
    CREATE_VALIDATION_REPORT = "create_validation_report"
    CREATE_MODULE_DRAFT = "create_module_draft"
    CREATE_DAY_DRAFT = "create_day_draft"
    CREATE_CORRECTION_DRAFT = "create_correction_revision_draft"
    CREATE_QUALITY_REPORT = "create_quality_report"


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    version: str
    roles: frozenset[str]
    effect: ToolEffect
    required: frozenset[str]
    optional: frozenset[str]
    timeout_ms: int
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES

    @property
    def mutating(self) -> bool:
        return self.effect is not ToolEffect.NONE

    def input_schema(self) -> dict[str, JsonValue]:
        properties: dict[str, JsonValue] = {
            key: {} for key in sorted(self.required | self.optional)
        }
        required: list[JsonValue] = list(sorted(self.required))
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": required,
            "properties": properties,
        }

    def output_schema(self) -> dict[str, JsonValue]:
        required_fields, optional_fields = _OUTPUT_CONTRACTS[self.name]
        properties: dict[str, JsonValue] = {
            key: {} for key in sorted(required_fields | optional_fields)
        }
        required: list[JsonValue] = list(sorted(required_fields))
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": required,
            "properties": properties,
        }

    @property
    def output_fields(self) -> tuple[frozenset[str], frozenset[str]]:
        return _OUTPUT_CONTRACTS[self.name]


def _tool(
    name: str,
    roles: tuple[str, ...],
    effect: ToolEffect,
    required: tuple[str, ...],
    optional: tuple[str, ...] = (),
    *,
    timeout_ms: int = 10_000,
) -> ToolDefinition:
    return ToolDefinition(
        name,
        "1.0.0",
        frozenset(roles),
        effect,
        frozenset(required),
        frozenset(optional),
        timeout_ms,
    )


TOOL_DEFINITIONS: Final[tuple[ToolDefinition, ...]] = (
    _tool(
        "profile.read_authorized",
        ("learner", "author"),
        ToolEffect.NONE,
        ("profile_id", "purpose", "field_groups"),
    ),
    _tool(
        "catalogue.list_targets",
        ("learner", "author", "reviewer", "support", "admin"),
        ToolEffect.NONE,
        ("pack_revision_id",),
        ("target_types", "modality", "operation", "prerequisite_of", "status", "cursor", "limit"),
    ),
    _tool(
        "lexicon.read_session_scope",
        ("learner", "author"),
        ToolEffect.NONE,
        ("profile_id", "planning_snapshot_id", "roles", "target_refs", "list_snapshot_ids"),
        ("max_senses",),
    ),
    _tool(
        "exercise.get_blueprint",
        ("author", "reviewer", "worker"),
        ToolEffect.NONE,
        ("primitive_id", "primitive_contract_version", "language_pack_revision_id", "mode"),
        ("accessibility_capabilities",),
    ),
    _tool(
        "exercise.submit_draft",
        ("author",),
        ToolEffect.CREATE_DRAFT,
        (
            "pack_revision_id",
            "primitive_id",
            "blueprint_version",
            "stimulus",
            "response_contract",
            "target_bindings",
            "accepted_answers_or_rubric",
            "hints",
            "difficulty_profile",
            "provenance_inputs",
        ),
        ("reserved_draft_id",),
        timeout_ms=60_000,
    ),
    _tool(
        "content.validate_draft",
        ("author", "reviewer"),
        ToolEffect.CREATE_VALIDATION_REPORT,
        (
            "draft_revision_id",
            "validator_profile_id",
            "validator_revision_ids",
            "requested_checks",
            "seed",
        ),
        timeout_ms=30_000,
    ),
    _tool(
        "curriculum.submit_module_draft",
        ("author",),
        ToolEffect.CREATE_MODULE_DRAFT,
        (
            "pack_revision_id",
            "module_identity",
            "audience",
            "objectives",
            "prerequisites",
            "exit_policy",
            "day_draft_refs",
            "min_days",
            "max_days",
            "context",
            "provenance",
        ),
        timeout_ms=60_000,
    ),
    _tool(
        "curriculum.submit_day_draft",
        ("author",),
        ToolEffect.CREATE_DAY_DRAFT,
        (
            "module_draft_id",
            "ordinal",
            "arc",
            "context",
            "objectives",
            "novelties",
            "recalls",
            "delayed_needs",
            "lists",
            "compositions",
            "provenance",
        ),
        timeout_ms=60_000,
    ),
    _tool(
        "correction.submit_structured_draft",
        ("reviewer", "worker"),
        ToolEffect.CREATE_CORRECTION_DRAFT,
        (
            "attempt_id",
            "attempt_version",
            "strategy",
            "verdict",
            "criterion_scores",
            "error_codes",
            "proposed_answer",
            "alternatives",
            "explanation_codes",
            "confidence",
            "target_observations",
            "provenance",
        ),
        timeout_ms=30_000,
    ),
    _tool(
        "quality.report_ambiguity",
        ("learner", "author", "reviewer"),
        ToolEffect.CREATE_QUALITY_REPORT,
        (
            "resource_ref",
            "resource_revision_id",
            "ambiguity_type",
            "location",
            "description",
            "candidate_interpretations",
        ),
        ("private_context", "private_context_consented"),
        timeout_ms=30_000,
    ),
    _tool(
        "progress.explain_recommendation",
        ("learner", "support"),
        ToolEffect.NONE,
        ("profile_id", "recommendation_id", "as_of_projection_version", "detail_level"),
    ),
)

TOOL_REGISTRY: Final[dict[str, ToolDefinition]] = {
    definition.name: definition for definition in TOOL_DEFINITIONS
}
