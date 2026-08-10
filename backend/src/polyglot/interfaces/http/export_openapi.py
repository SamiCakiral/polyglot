import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from polyglot.interfaces.http.app import create_app

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
REQUIRED_W02_COMMANDS = frozenset(
    {
        "RegisterAccount",
        "AuthenticateSession",
        "RevokeSession",
        "ChangePassword",
        "UpdateUserPreferences",
        "UpdateConsent",
    }
)
REQUIRED_W02_HEADERS = {
    ("post", "/api/v1/accounts"): {"Origin", "Idempotency-Key"},
    ("post", "/api/v1/session"): {"Origin", "Idempotency-Key"},
    ("delete", "/api/v1/session"): {"Origin", "X-CSRF-Token", "Idempotency-Key"},
    ("put", "/api/v1/account/password"): {
        "Origin",
        "X-CSRF-Token",
        "If-Match",
        "Idempotency-Key",
    },
    ("patch", "/api/v1/account/preferences"): {
        "Origin",
        "X-CSRF-Token",
        "If-Match",
        "Idempotency-Key",
    },
    ("put", "/api/v1/consents/{purpose}"): {
        "Origin",
        "X-CSRF-Token",
        "If-Match",
        "Idempotency-Key",
    },
}
AUTHENTICATED_W02_OPERATIONS = frozenset(
    {
        ("get", "/api/v1/session"),
        ("delete", "/api/v1/session"),
        ("put", "/api/v1/account/password"),
        ("patch", "/api/v1/account/preferences"),
        ("put", "/api/v1/consents/{purpose}"),
    }
)


def _operation_id(command_name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", command_name).lower()


def _parameter_names(operation: dict[str, Any]) -> set[str]:
    return {
        parameter["name"]
        for parameter in operation.get("parameters", [])
        if isinstance(parameter, dict) and isinstance(parameter.get("name"), str)
    }


def canonical_openapi() -> str:
    return json.dumps(
        create_app(test_mode=True).openapi(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def validate_registry_compatibility(
    document: dict[str, Any],
    registry_directory: Path,
) -> None:
    commands = json.loads((registry_directory / "commands.yaml").read_text())["commands"]
    queries = json.loads((registry_directory / "queries.yaml").read_text())["queries"]
    registered = {
        (item["method"].lower(), item["route"])
        for item in commands
    }
    registered.update(
        (
            item["method"].lower(),
            item["route"]
            if item["route"].startswith("/api/v1/")
            else f"/api/v1{item['route']}",
        )
        for item in queries
    )
    operation_ids: set[str] = set()
    for route, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            operation_id = operation["operationId"]
            if operation_id in operation_ids:
                raise ValueError(f"duplicate OpenAPI operationId: {operation_id}")
            operation_ids.add(operation_id)
            if route.startswith("/api/v1/health/"):
                continue
            if (method, route) not in registered:
                raise ValueError(f"OpenAPI operation missing from W00 registry: {method} {route}")

    commands_by_name = {command["name"]: command for command in commands}
    for command_name in REQUIRED_W02_COMMANDS:
        command = commands_by_name.get(command_name)
        if command is None:
            raise ValueError(f"required W02 command missing from W00 registry: {command_name}")
        method = command["method"].lower()
        route = command["route"]
        operation = document.get("paths", {}).get(route, {}).get(method)
        if operation is None:
            raise ValueError(f"required W02 operation missing: {method} {route}")
        if operation.get("operationId") != _operation_id(command_name):
            raise ValueError(f"noncanonical W02 operationId: {method} {route}")
        required_headers = REQUIRED_W02_HEADERS[(method, route)]
        if not required_headers <= _parameter_names(operation):
            raise ValueError(f"required W02 headers missing: {method} {route}")

    session_query = document.get("paths", {}).get("/api/v1/session", {}).get("get")
    if session_query is None or session_query.get("operationId") != "get_current_session":
        raise ValueError("required W02 session query is missing or noncanonical")

    schemes = document.get("components", {}).get("securitySchemes", {})
    if schemes.get("SessionCookie") != {
        "type": "apiKey",
        "in": "cookie",
        "name": "__Host-polyglot_session",
    }:
        raise ValueError("required W02 session cookie security scheme is missing")
    for method, route in AUTHENTICATED_W02_OPERATIONS:
        operation = document["paths"][route][method]
        if operation.get("security") != [{"SessionCookie": []}]:
            raise ValueError(f"required W02 cookie security is missing: {method} {route}")
        for status in ("401", "403", "409", "423", "429"):
            content = operation.get("responses", {}).get(status, {}).get("content", {})
            problem = content.get("application/problem+json", {}).get("schema", {})
            if problem.get("$ref") != "#/components/schemas/ProblemResponse":
                raise ValueError(f"required W02 problem response is missing: {method} {route}")

    credentials = document["paths"]["/api/v1/session"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    if (
        len(credentials.get("oneOf", ())) != 2
        or credentials.get("discriminator", {}).get("propertyName") != "provider_type"
    ):
        raise ValueError("required W02 credential union is missing")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export deterministic Polyglot OpenAPI")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("path", type=Path)
    arguments = parser.parse_args(argv)
    document = create_app(test_mode=True).openapi()
    registry = Path(__file__).resolve().parents[5] / "contracts/registry"
    validate_registry_compatibility(document, registry)
    rendered = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.check:
        if not arguments.path.is_file() or arguments.path.read_text() != rendered:
            print(f"OpenAPI is not current: {arguments.path}", file=sys.stderr)
            return 1
        return 0
    arguments.path.parent.mkdir(parents=True, exist_ok=True)
    arguments.path.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
