from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Final, cast

from polyglot.platform.json_types import JsonValue

SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
DEFAULT_MAX_INPUT_BYTES = 256 * 1024
DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024


@cache
def _contract_schema(tool_name: str, kind: str) -> dict[str, JsonValue]:
    filename = f"{tool_name}.{kind}.schema.json"
    packaged = files(__package__).joinpath("contracts", filename)
    try:
        raw = packaged.read_text(encoding="utf-8")
    except FileNotFoundError:
        raw = (Path(__file__).resolve().parents[5] / "contracts" / "tools" / filename).read_text()
    return cast(dict[str, JsonValue], json.loads(raw))


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
        return _contract_schema(self.name, "input")

    def output_schema(self) -> dict[str, JsonValue]:
        return _contract_schema(self.name, "output")

    @property
    def output_fields(self) -> tuple[frozenset[str], frozenset[str]]:
        schema = self.output_schema()
        required = frozenset(cast(list[str], schema["required"]))
        properties = frozenset(cast(dict[str, JsonValue], schema["properties"]))
        return required, properties - required


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
        (
            "profile_id",
            "planning_snapshot_id",
            "roles",
            "target_refs",
            "list_snapshot_ids",
            "max_senses",
        ),
    ),
    _tool(
        "exercise.get_blueprint",
        ("author", "reviewer", "worker"),
        ToolEffect.NONE,
        (
            "primitive_id",
            "primitive_contract_version",
            "language_pack_revision_id",
            "mode",
            "accessibility_capabilities",
        ),
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
            "module",
            "audience",
            "objectives",
            "prerequisites",
            "exit_policy",
            "day_draft_refs",
            "length",
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
            "novelty",
            "reviews",
            "next_day_needs",
            "lists",
            "compositions",
            "provenance",
            "expected_version",
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
            "private_context_consent",
        ),
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
