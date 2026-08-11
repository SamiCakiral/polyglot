from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from polyglot.interfaces.tools.registry import TOOL_REGISTRY
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue


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
                "reference": allowed,
                "name": name,
                "version": version,
                "required_input_fields": cast(
                    list[JsonValue], sorted(definition.required)
                ),
                "optional_input_fields": cast(
                    list[JsonValue], sorted(definition.optional)
                ),
            }
        )
    system = (
        "Plan exactly one controlled Polyglot authoring operation. "
        "Return only a JSON object with exactly tool_name, tool_version and input. "
        "The input must satisfy the selected closed contract. Allowed tools: "
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
    try:
        payload = json.loads(message)
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
