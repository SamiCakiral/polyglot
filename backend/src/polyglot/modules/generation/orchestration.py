from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from polyglot.interfaces.tools.registry import TOOL_REGISTRY
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue

GENERATION_TOOL_EXAMPLES: dict[str, dict[str, JsonValue]] = {
    "exercise.submit_draft": {
        "pack_revision_id": "use task_input.pack_revision_id",
        "primitive_id": "EX-COMP-03",
        "blueprint_version": 1,
        "stimulus": ["Breve testo italiano coerente con il brief."],
        "response_contract": "free_text",
        "target_bindings": ["skill:reading", "lexicon:travel"],
        "accepted_answers_or_rubric": ["Réponse correcte et fidèle au stimulus."],
        "hints": ["Un indice bref sans donner la réponse."],
        "difficulty_profile": "beginner",
        "provenance_inputs": ["task_input.brief"],
    },
    "curriculum.submit_module_draft": {
        "pack_revision_id": "use task_input.pack_revision_id",
        "module": "arrival_in_italy",
        "audience": "beginner",
        "objectives": ["Comprendre et produire des échanges simples."],
        "prerequisites": [],
        "exit_policy": "Complete the planned days and required checks.",
        "day_draft_refs": [],
        "length": "3_days",
        "context": "Situations variées cohérentes avec le brief.",
        "provenance": "task_input.brief",
    },
    "curriculum.submit_day_draft": {
        "module_draft_id": "use task_input.module_draft_id when provided",
        "ordinal": 1,
        "arc": "discovery_practice_recall",
        "context": "Une scène cohérente avec le brief.",
        "objectives": ["Un objectif observable."],
        "novelty": "Une structure ou un groupe lexical nouveau.",
        "reviews": ["Un acquis antérieur à rappeler."],
        "next_day_needs": ["Une trace à réactiver le lendemain."],
        "lists": ["Liste de vocabulaire de séance."],
        "compositions": ["Plan de sprint 30 minutes."],
        "provenance": "task_input.brief",
        "expected_version": 1,
    },
    "quality.report_ambiguity": {
        "resource_ref": "use task_input.resource_ref when provided",
        "resource_revision_id": "use task_input.resource_revision_id when provided",
        "ambiguity_type": "instruction",
        "location": "prompt",
        "description": "Description factuelle de l'ambiguïté.",
        "candidate_interpretations": ["Première interprétation", "Seconde interprétation"],
        "private_context_consent": False,
    },
}


@dataclass(frozen=True, slots=True)
class GenerationPlan:
    tool_name: str
    tool_version: str
    input: dict[str, JsonValue]


def build_generation_messages(
    *,
    task_type: str,
    task_input: dict[str, JsonValue],
    tool_allowlist: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    tools: list[dict[str, JsonValue]] = []
    for allowed in tool_allowlist:
        name, separator, version = allowed.partition("@")
        definition = TOOL_REGISTRY.get(name)
        if not separator or definition is None or version != definition.version:
            raise DomainError(ErrorCode.TOOL_NOT_ALLOWED)
        tools.append(
            {
                "example_input": GENERATION_TOOL_EXAMPLES.get(name),
                "reference": allowed,
                "name": name,
                "version": version,
                "required_input_fields": cast(list[JsonValue], sorted(definition.required)),
                "optional_input_fields": cast(list[JsonValue], sorted(definition.optional)),
            }
        )
    system = (
        "Plan exactly one controlled Polyglot authoring operation. "
        "Return only one JSON object with exactly tool_name, tool_version and input; "
        "one ```json fenced block is accepted but no prose is allowed. "
        "The input must contain exactly the selected fields and preserve every JSON type "
        "shown by example_input. Use matching task_input values instead of inventing IDs. "
        "Allowed tools: "
        + json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    user = json.dumps(
        {"task_input": task_input, "task_type": task_type},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (("system", system), ("user", user))


def parse_generation_plan(
    message: str,
    tool_allowlist: tuple[str, ...],
) -> GenerationPlan:
    candidate = message.strip()
    if candidate.startswith("```json\n") and candidate.endswith("```"):
        candidate = candidate[len("```json\n") : -len("```")].strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID) from error
    if not isinstance(payload, dict) or set(payload) != {"tool_name", "tool_version", "input"}:
        raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID)
    name = payload.get("tool_name")
    version = payload.get("tool_version")
    tool_input = payload.get("input")
    if (
        not isinstance(name, str)
        or not isinstance(version, str)
        or not isinstance(tool_input, dict)
    ):
        raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID)
    if f"{name}@{version}" not in tool_allowlist:
        raise DomainError(ErrorCode.TOOL_NOT_ALLOWED)
    definition = TOOL_REGISTRY.get(name)
    if definition is None or definition.version != version:
        raise DomainError(ErrorCode.TOOL_NOT_ALLOWED)
    if not definition.required <= set(tool_input) or not set(tool_input) <= (
        definition.required | definition.optional
    ):
        raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID)
    return GenerationPlan(name, version, cast(dict[str, JsonValue], tool_input))
