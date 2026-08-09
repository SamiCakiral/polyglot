#!/usr/bin/env python3
"""Validate the dependency-free W00 contract registry and fixtures."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


NAME = re.compile(r"^[a-z][a-z0-9_]*$")
TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
MARKDOWN_LINK = re.compile(r"\[[^]]*\]\(([^)]+)\)")
REQUIRED_REGISTRY = ("enums.yaml", "commands.yaml", "queries.yaml", "errors.yaml")
REQUIRED_EVENTS = ("envelope.schema.json", "event-catalogue.yaml")
SIDE_EFFECTS = {
    "none",
    "create_draft",
    "create_validation_report",
    "create_module_draft",
    "create_day_draft",
    "create_correction_revision_draft",
    "create_quality_report",
}


def load(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as error:
        raise ValueError(f"missing file: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON-syntax YAML: {path}: {error.msg}") from error


def obj(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def string_set(values: object, label: str) -> set[str]:
    result: set[str] = set()
    for value in array(values, label):
        if not isinstance(value, str) or not NAME.fullmatch(value):
            raise ValueError(f"invalid {label}: {value}")
        if value in result:
            raise ValueError(f"duplicate {label}: {value}")
        result.add(value)
    return result


def validate_schema_shape(schema: object, label: str) -> None:
    item = obj(schema, label)
    if "$schema" in item and not isinstance(item["$schema"], str):
        raise ValueError(f"invalid schema declaration: {label}")
    schema_type = item.get("type")
    if schema_type not in {"object", "array", "string", "integer", "number", "boolean"}:
        raise ValueError(f"schema missing concrete type: {label}")
    if schema_type == "object":
        if item.get("additionalProperties") is not False:
            raise ValueError(f"schema object not closed: {label}")
        properties = obj(item.get("properties", {}), f"schema properties: {label}")
        required = array(item.get("required", []), f"schema required: {label}")
        for name in required:
            if not isinstance(name, str) or name not in properties:
                raise ValueError(f"schema required property missing: {label}.{name}")
        for name, child in properties.items():
            validate_schema_shape(child, f"{label}.{name}")
    if schema_type == "array":
        validate_schema_shape(item.get("items"), f"{label}[]")
        if not isinstance(item.get("maxItems"), int) or item["maxItems"] < 0:
            raise ValueError(f"schema array missing maxItems: {label}")
    if schema_type == "string" and not isinstance(item.get("maxLength"), int):
        raise ValueError(f"schema string missing maxLength: {label}")
    if schema_type in {"integer", "number"}:
        if "minimum" not in item or "maximum" not in item:
            raise ValueError(f"schema number missing bounds: {label}")


def validate_instance(value: object, schema: object, path: str) -> None:
    item = obj(schema, path)
    schema_type = item["type"]
    type_ok = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }[schema_type]
    if not type_ok:
        raise ValueError(f"{path}: expected {schema_type}")
    if "enum" in item and value not in item["enum"]:
        raise ValueError(f"{path}: value outside enum")
    if schema_type == "object":
        properties = obj(item.get("properties", {}), f"properties {path}")
        for key in value:
            if key not in properties:
                raise ValueError(f"{path}: additional property: {key}")
        for key in array(item.get("required", []), f"required {path}"):
            if key not in value:
                raise ValueError(f"{path}: missing required property: {key}")
        for key, child in properties.items():
            if key in value:
                validate_instance(value[key], child, f"{path}.{key}")
    elif schema_type == "array":
        if len(value) > item["maxItems"]:
            raise ValueError(f"{path}: exceeds maxItems")
        for index, child in enumerate(value):
            validate_instance(child, item["items"], f"{path}[{index}]")
    elif schema_type == "string":
        if len(value) > item["maxLength"]:
            raise ValueError(f"{path}: exceeds maxLength")
        if "minLength" in item and len(value) < item["minLength"]:
            raise ValueError(f"{path}: below minLength")
    elif schema_type in {"integer", "number"}:
        if value < item["minimum"] or value > item["maximum"]:
            raise ValueError(f"{path}: outside numeric bounds")


def validate_registry(registry: Path, tests: Path) -> tuple[Path, dict[str, object]]:
    contracts = registry.parent
    for name in REQUIRED_REGISTRY:
        if not (registry / name).is_file():
            raise ValueError(f"missing file: {registry / name}")
    for name in REQUIRED_EVENTS:
        if not (contracts / "events" / name).is_file():
            raise ValueError(f"missing file: {contracts / 'events' / name}")
    enums_document = obj(load(registry / "enums.yaml"), "enums")
    enums = obj(enums_document.get("enums"), "enums")
    known_enums = {name: string_set(values, f"enum value: {name}") for name, values in enums.items()}
    known_errors = string_set(obj(load(registry / "errors.yaml"), "errors").get("errors"), "error")
    commands = array(obj(load(registry / "commands.yaml"), "commands").get("commands"), "commands")
    routes: set[tuple[str, str]] = set()
    command_names: set[str] = set()
    command_events: set[str] = set()
    for command in commands:
        item = obj(command, "command")
        name, method, route = item.get("name"), item.get("method"), item.get("route")
        if not isinstance(name, str) or not name or name in command_names:
            raise ValueError(f"duplicate or missing command name: {name}")
        command_names.add(name)
        if method not in {"POST", "PATCH", "PUT", "DELETE"} or not isinstance(route, str) or not route.startswith("/api/v1/"):
            raise ValueError(f"invalid command route: {name}")
        if (method, route) in routes:
            raise ValueError(f"duplicate route: {method} {route}")
        routes.add((method, route))
        if item.get("idempotency") not in {"required", "supported", "n/a"}:
            raise ValueError(f"invalid idempotency: {name}")
        for event in array(item.get("events"), f"command events: {name}"):
            if not isinstance(event, str) or not NAME.fullmatch(event):
                raise ValueError(f"invalid command event: {name}")
            command_events.add(event)
        for error in array(item.get("errors", []), f"command errors: {name}"):
            if error not in known_errors:
                raise ValueError(f"unknown command error: {name}.{error}")
        for enum_name, values in obj(item.get("enum_values", {}), f"enum values: {name}").items():
            if enum_name not in known_enums:
                raise ValueError(f"unknown enum: {enum_name}")
            for value in array(values, f"enum values: {enum_name}"):
                if value not in known_enums[enum_name]:
                    raise ValueError(f"unknown enum value: {enum_name}.{value}")
    queries = obj(load(registry / "queries.yaml"), "queries")
    query_routes = set()
    for query in array(queries.get("queries"), "queries"):
        item = obj(query, "query")
        if item.get("method") != "GET" or not isinstance(item.get("route"), str):
            raise ValueError("invalid query")
        if item["route"] in query_routes:
            raise ValueError(f"duplicate query route: {item['route']}")
        query_routes.add(item["route"])
    envelope = obj(load(contracts / "events" / "envelope.schema.json"), "event envelope")
    for field in ("event_id", "event_type", "schema_version"):
        if field not in array(envelope.get("required"), "event envelope required"):
            raise ValueError(f"event envelope missing required field: {field}")
    catalogue = array(obj(load(contracts / "events" / "event-catalogue.yaml"), "event catalogue").get("events"), "events")
    known_events = set()
    for event in catalogue:
        item = obj(event, "event")
        event_type = item.get("event_type")
        if not isinstance(event_type, str) or not NAME.fullmatch(event_type):
            raise ValueError("event missing event_type")
        if not isinstance(item.get("schema_version"), int) or item["schema_version"] < 1:
            raise ValueError(f"event missing schema_version: {event_type}")
        if event_type in known_events:
            raise ValueError(f"duplicate event: {event_type}")
        known_events.add(event_type)
    missing_events = command_events - known_events
    if missing_events:
        raise ValueError(f"command event missing from catalogue: {sorted(missing_events)[0]}")
    manifest = obj(load(contracts / "tools" / "manifest.yaml"), "tool manifest")
    common_limits = manifest.get("common_limits")
    if not isinstance(common_limits, dict):
        raise ValueError("missing common tool limits")
    if common_limits != {
        "max_input_bytes": 262144,
        "max_output_bytes": 1048576,
        "max_free_text_characters": 20000,
    }:
        raise ValueError("common tool limits mismatch")
    if set(array(manifest.get("forbidden_effects"), "forbidden effects")) != {
        "approve",
        "publish",
        "retire",
        "award_mastery",
        "modify_fsrs_schedule",
    }:
        raise ValueError("forbidden tool effects mismatch")
    tools = array(manifest.get("tools"), "tools")
    tool_names = set()
    tool_schemas: dict[str, tuple[dict[str, object], dict[str, object]]] = {}
    for tool in tools:
        item = obj(tool, "tool")
        name = item.get("tool_name")
        if not isinstance(name, str) or not TOOL_NAME.fullmatch(name) or name in tool_names:
            raise ValueError(f"invalid or duplicate tool: {name}")
        tool_names.add(name)
        if item.get("side_effect") not in SIDE_EFFECTS:
            raise ValueError(f"invalid tool side effect: {name}")
        limits = item.get("limits")
        if not isinstance(limits, dict) or not limits:
            raise ValueError(f"tool limits missing: {name}")
        for error in array(item.get("errors", []), f"tool errors: {name}"):
            if error not in known_errors:
                raise ValueError(f"unknown tool error: {name}.{error}")
        schema_pair = []
        for key in ("input_schema", "output_schema"):
            filename = item.get(key)
            if not isinstance(filename, str) or not filename.endswith(".schema.json"):
                raise ValueError(f"tool missing {key}: {name}")
            schema = obj(load(contracts / "tools" / filename), f"tool schema: {filename}")
            validate_schema_shape(schema, filename)
            schema_pair.append(schema)
        tool_schemas[name] = (schema_pair[0], schema_pair[1])
    snapshot = obj(load(tests / "fixtures" / "canonical-sets.json"), "canonical sets")
    expected_commands = set(array(snapshot.get("command_names"), "canonical commands"))
    expected_queries = set(array(snapshot.get("query_names"), "canonical queries"))
    expected_tools = set(array(snapshot.get("tool_names"), "canonical tools"))
    expected_errors = set(array(snapshot.get("errors"), "canonical errors"))
    if command_names != expected_commands:
        raise ValueError("canonical command set mismatch")
    command_mappings = [
        {key: item.get(key) for key in ("name", "method", "route", "idempotency")}
        for item in commands
    ]
    if command_mappings != array(snapshot.get("command_mappings"), "canonical command mappings"):
        raise ValueError("canonical command mapping mismatch")
    if [
        {"method": item.get("method"), "route": item.get("route")}
        for item in array(queries.get("queries"), "queries")
    ] != array(snapshot.get("query_mappings"), "canonical query mappings"):
        raise ValueError("canonical query mapping mismatch")
    if set(queries.get("application_query_names", [])) != expected_queries:
        raise ValueError("canonical query set mismatch")
    if tool_names != expected_tools:
        raise ValueError("canonical tool set mismatch")
    if known_errors != expected_errors:
        raise ValueError("canonical error set mismatch")
    return contracts, {"tools": tool_schemas, "manifest": manifest}


def validate_tool_fixtures(tests: Path, tool_schemas: dict[str, tuple[dict[str, object], dict[str, object]]]) -> int:
    valid = 0
    for kind in ("positive", "negative"):
        for fixture_path in sorted((tests / "fixtures" / "tools" / kind).glob("*.json")):
            fixture = obj(load(fixture_path), f"fixture {fixture_path.name}")
            name = fixture.get("tool_name")
            if name not in tool_schemas or fixture.get("kind") != kind:
                raise ValueError(f"invalid tool fixture: {fixture_path}")
            input_schema, output_schema = tool_schemas[name]
            if kind == "positive":
                validate_instance(fixture.get("input"), input_schema, f"{fixture_path.name}.input")
                validate_instance(fixture.get("output"), output_schema, f"{fixture_path.name}.output")
            else:
                try:
                    validate_instance(fixture.get("input"), input_schema, f"{fixture_path.name}.input")
                    validate_instance(fixture.get("output"), output_schema, f"{fixture_path.name}.output")
                except ValueError as error:
                    if fixture.get("expected_error") not in str(error):
                        raise
                else:
                    raise ValueError(f"negative fixture accepted: {fixture_path.name}")
            valid += 1
    if valid != len(tool_schemas) * 2:
        raise ValueError(f"tool fixture count mismatch: {valid}")
    errors = set(array(obj(load(tests.parent / "registry" / "errors.yaml"), "errors").get("errors"), "errors"))
    meta_cases = array(load(tests / "fixtures" / "tools" / "meta-cases.json"), "tool meta cases")
    expected_cases = {"idempotency_conflict", "role_denial", "stale_reference", "size_limit", "timeout", "forbidden_effect"}
    if {item.get("case") for item in meta_cases if isinstance(item, dict)} != expected_cases:
        raise ValueError("tool meta case set mismatch")
    for case in meta_cases:
        item = obj(case, "tool meta case")
        if item.get("tool_name") not in tool_schemas or item.get("expected_error") not in errors:
            raise ValueError(f"invalid tool meta case: {item.get('case')}")
        if obj(item.get("expected_output"), "tool meta output") != {"status": "error", "error": item["expected_error"]} or item.get("expected_effect") != "none":
            raise ValueError(f"unsafe tool meta case: {item.get('case')}")
    return valid


def check_doc_links(root: Path) -> None:
    for path in [root / "README.md", root / "CONTRIBUTING.md", *sorted((root / "docs").rglob("*.md"))]:
        if not path.exists():
            continue
        for target in MARKDOWN_LINK.findall(path.read_text()):
            if target.startswith(("http://", "https://", "#")):
                continue
            destination = target.split("#", 1)[0]
            if destination and not (path.parent / destination).exists():
                raise ValueError(f"broken documentation link: {path.relative_to(root)} -> {target}")


def check_artifacts(root: Path) -> None:
    tracked = subprocess.run(["git", "ls-files"], cwd=root, text=True, capture_output=True, check=True).stdout.splitlines()
    forbidden = ("app/", "tests/", "card_sets/", "pillar_content/", ".env", "venv/", ".venv/")
    for path in tracked:
        if path in {"config.py", "run.py", "requirements.txt", ".env.example"} or path.startswith(forbidden) or path.endswith((".db", ".sqlite", ".sqlite3")):
            raise ValueError(f"forbidden tracked V1/private artifact: {path}")
    ignored = subprocess.run(["git", "status", "--porcelain", "--ignored", "--untracked-files=all"], cwd=root, text=True, capture_output=True, check=True).stdout.splitlines()
    for line in ignored:
        if not line.startswith(("??", "!!")):
            continue
        path = line[3:]
        if path.startswith("contracts/tests/__pycache__/") or path in {
            ".superpowers/sdd/.gitignore",
            ".superpowers/sdd/27-plan-implementation-detaille/task-W00-brief.md",
            ".superpowers/sdd/27-plan-implementation-detaille/task-W00-report.md",
            ".superpowers/sdd/27-plan-implementation-detaille/task-W00-rereview-1.md",
            ".superpowers/sdd/27-plan-implementation-detaille/task-W00-rereview-2.md",
            ".superpowers/sdd/27-plan-implementation-detaille/task-W00-review.md",
            ".superpowers/sdd/27-plan-implementation-detaille/progress.md",
        }:
            continue
        if path.startswith(("app/", "tests/", ".env", "venv/", ".venv/", "card_sets/", "pillar_content/")) or path.endswith((".db", ".sqlite", ".sqlite3")):
            raise ValueError(f"forbidden untracked private artifact: {path}")
        raise ValueError(f"forbidden untracked private artifact: {path}")


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: validate_contract_registry.py REGISTRY_DIR TESTS_DIR [--validate-tool-fixtures] [--check-doc-links] [--check-artifacts]", file=sys.stderr)
        return 2
    flags = set(argv[3:])
    if flags - {"--validate-tool-fixtures", "--check-doc-links", "--check-artifacts"}:
        print("ERROR: unknown flag")
        return 2
    try:
        contracts, state = validate_registry(Path(argv[1]), Path(argv[2]))
        if "--validate-tool-fixtures" in flags:
            print(f"{validate_tool_fixtures(Path(argv[2]), state['tools'])} tool fixtures valid")
        if "--check-doc-links" in flags:
            check_doc_links(contracts.parent)
            print("documentation links valid")
        if "--check-artifacts" in flags:
            check_artifacts(contracts.parent)
            print("artifact boundary valid")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}")
        return 1
    print("contract registry valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
