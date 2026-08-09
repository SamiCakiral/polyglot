#!/usr/bin/env python3
"""Validate the W00 JSON-syntax YAML contract registry without dependencies."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REQUIRED_REGISTRY_FILES = ("enums.yaml", "commands.yaml", "queries.yaml", "errors.yaml")
REQUIRED_EVENT_FILES = ("envelope.schema.json", "event-catalogue.yaml")
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


def load_json_yaml(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        raise ValueError(f"missing file: {path}")
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON-syntax YAML: {path}: {error.msg}")


def require_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def validate_enums(registry: Path) -> dict[str, set[str]]:
    document = require_object(load_json_yaml(registry / "enums.yaml"), "enums.yaml")
    enums = require_object(document.get("enums"), "enums")
    validated: dict[str, set[str]] = {}
    for enum_name, values in enums.items():
        if not isinstance(enum_name, str) or not NAME_PATTERN.fullmatch(enum_name):
            raise ValueError(f"invalid enum name: {enum_name}")
        members = require_list(values, f"enum {enum_name}")
        if not members:
            raise ValueError(f"empty enum: {enum_name}")
        value_set: set[str] = set()
        for member in members:
            if not isinstance(member, str) or not NAME_PATTERN.fullmatch(member):
                raise ValueError(f"invalid enum value: {enum_name}.{member}")
            if member in value_set:
                raise ValueError(f"duplicate enum value: {enum_name}.{member}")
            value_set.add(member)
        validated[enum_name] = value_set
    return validated


def validate_commands(registry: Path, enums: dict[str, set[str]]) -> set[str]:
    document = require_object(load_json_yaml(registry / "commands.yaml"), "commands.yaml")
    commands = require_list(document.get("commands"), "commands")
    routes: set[tuple[str, str]] = set()
    events: set[str] = set()
    for command in commands:
        item = require_object(command, "command")
        name = item.get("name")
        method = item.get("method")
        route = item.get("route")
        if not isinstance(name, str) or not name:
            raise ValueError("command missing name")
        if method not in {"POST", "PATCH", "PUT", "DELETE"}:
            raise ValueError(f"invalid command method: {name}")
        if not isinstance(route, str) or not route.startswith("/api/v1/"):
            raise ValueError(f"invalid command route: {name}")
        route_key = (method, route)
        if route_key in routes:
            raise ValueError(f"duplicate route: {method} {route}")
        routes.add(route_key)
        if item.get("idempotency") not in {"required", "supported", "n/a"}:
            raise ValueError(f"invalid idempotency: {name}")
        for event in require_list(item.get("events"), f"command events: {name}"):
            if not isinstance(event, str) or not NAME_PATTERN.fullmatch(event):
                raise ValueError(f"invalid command event: {name}")
            events.add(event)
        enum_values = item.get("enum_values", {})
        enum_values = require_object(enum_values, f"enum values: {name}")
        for enum_name, values in enum_values.items():
            if enum_name not in enums:
                raise ValueError(f"unknown enum: {enum_name}")
            for value in require_list(values, f"enum values: {enum_name}"):
                if value not in enums[enum_name]:
                    raise ValueError(f"unknown enum value: {enum_name}.{value}")
    return events


def validate_queries(registry: Path) -> None:
    document = require_object(load_json_yaml(registry / "queries.yaml"), "queries.yaml")
    queries = require_list(document.get("queries"), "queries")
    routes: set[str] = set()
    for query in queries:
        item = require_object(query, "query")
        if item.get("method") != "GET":
            raise ValueError("query method must be GET")
        route = item.get("route")
        if not isinstance(route, str) or not route.startswith("/"):
            raise ValueError("query missing route")
        if route in routes:
            raise ValueError(f"duplicate query route: {route}")
        routes.add(route)


def validate_errors(registry: Path) -> None:
    document = require_object(load_json_yaml(registry / "errors.yaml"), "errors.yaml")
    errors = require_list(document.get("errors"), "errors")
    known: set[str] = set()
    for error in errors:
        if not isinstance(error, str) or not NAME_PATTERN.fullmatch(error):
            raise ValueError(f"invalid error: {error}")
        if error in known:
            raise ValueError(f"duplicate error: {error}")
        known.add(error)


def validate_events(contracts: Path, command_events: set[str]) -> None:
    schema = require_object(load_json_yaml(contracts / "events" / "envelope.schema.json"), "event envelope")
    required = require_list(schema.get("required"), "event envelope required")
    for field in ("event_id", "event_type", "schema_version"):
        if field not in required:
            raise ValueError(f"event envelope missing required field: {field}")
    catalogue = require_object(load_json_yaml(contracts / "events" / "event-catalogue.yaml"), "event catalogue")
    entries = require_list(catalogue.get("events"), "event catalogue events")
    known: set[str] = set()
    for entry in entries:
        item = require_object(entry, "event")
        event_type = item.get("event_type")
        if not isinstance(event_type, str) or not NAME_PATTERN.fullmatch(event_type):
            raise ValueError("event missing event_type")
        if "schema_version" not in item:
            raise ValueError(f"event missing schema_version: {event_type}")
        if not isinstance(item["schema_version"], int) or item["schema_version"] < 1:
            raise ValueError(f"invalid event schema_version: {event_type}")
        if event_type in known:
            raise ValueError(f"duplicate event: {event_type}")
        known.add(event_type)
    missing = command_events - known
    if missing:
        raise ValueError(f"command event missing from catalogue: {sorted(missing)[0]}")


def validate_tools(contracts: Path) -> None:
    document = require_object(load_json_yaml(contracts / "tools" / "manifest.yaml"), "tool manifest")
    tools = require_list(document.get("tools"), "tools")
    names: set[str] = set()
    for tool in tools:
        item = require_object(tool, "tool")
        name = item.get("tool_name")
        if not isinstance(name, str) or not TOOL_NAME_PATTERN.fullmatch(name):
            raise ValueError(f"invalid tool name: {name}")
        if name in names:
            raise ValueError(f"duplicate tool: {name}")
        names.add(name)
        limits = item.get("limits")
        if not isinstance(limits, dict) or not limits:
            raise ValueError(f"tool limits missing: {name}")
        if item.get("side_effect") not in {"none", "create_draft", "create_validation_report", "create_module_draft", "create_day_draft", "create_correction_revision_draft", "create_quality_report"}:
            raise ValueError(f"invalid tool side effect: {name}")
        for schema_key in ("input_schema", "output_schema"):
            schema_name = item.get(schema_key)
            if not isinstance(schema_name, str) or not schema_name.endswith(".schema.json"):
                raise ValueError(f"tool missing {schema_key}: {name}")
            schema = contracts / "tools" / schema_name
            if not schema.is_file():
                raise ValueError(f"tool schema missing: {name}.{schema_key}")
            require_object(load_json_yaml(schema), f"tool schema: {schema_name}")


def validate(registry: Path, tests: Path) -> None:
    contracts = registry.parent
    for relative_path in REQUIRED_REGISTRY_FILES:
        if not (registry / relative_path).is_file():
            raise ValueError(f"missing file: {registry / relative_path}")
    for relative_path in REQUIRED_EVENT_FILES:
        if not (contracts / "events" / relative_path).is_file():
            raise ValueError(f"missing file: {contracts / 'events' / relative_path}")
    if not (contracts / "tools" / "manifest.yaml").is_file():
        raise ValueError(f"missing file: {contracts / 'tools' / 'manifest.yaml'}")
    enums = validate_enums(registry)
    command_events = validate_commands(registry, enums)
    validate_queries(registry)
    validate_errors(registry)
    validate_events(contracts, command_events)
    validate_tools(contracts)
    fixture_schema = contracts / "fixtures" / "manifest.schema.json"
    if fixture_schema.exists():
        require_object(load_json_yaml(fixture_schema), "fixture manifest schema")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: validate_contract_registry.py REGISTRY_DIR TESTS_DIR", file=sys.stderr)
        return 2
    try:
        validate(Path(argv[1]), Path(argv[2]))
    except ValueError as error:
        print(f"ERROR: {error}")
        return 1
    print("contract registry valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
