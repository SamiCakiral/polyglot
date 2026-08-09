import argparse
import json
import sys
from pathlib import Path
from typing import Any

from polyglot.interfaces.http.app import create_app

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})


def canonical_openapi() -> str:
    return json.dumps(
        create_app().openapi(),
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export deterministic Polyglot OpenAPI")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("path", type=Path)
    arguments = parser.parse_args(argv)
    document = create_app().openapi()
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
