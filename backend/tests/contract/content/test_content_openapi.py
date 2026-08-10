from pathlib import Path

from polyglot.interfaces.http.app import create_app
from polyglot.interfaces.http.export_openapi import validate_registry_compatibility

ROOT = Path(__file__).resolve().parents[4]


def _parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        parameter["name"]: parameter
        for parameter in operation.get("parameters", [])
        if isinstance(parameter, dict) and isinstance(parameter.get("name"), str)
    }


def test_openapi_exposes_ten_authenticated_w05_routes_with_transport_contracts() -> None:
    document = create_app(test_mode=True).openapi()
    paths = document["paths"]
    commands = {
        ("post", "/api/v1/authoring/drafts"): ("create_content_draft", False),
        ("patch", "/api/v1/authoring/drafts/{draft_id}"): (
            "revise_content_draft",
            True,
        ),
        ("post", "/api/v1/authoring/drafts/{draft_id}:validate"): (
            "validate_content_revision",
            True,
        ),
        ("post", "/api/v1/authoring/drafts/{draft_id}:approve"): (
            "approve_content_revision",
            True,
        ),
        ("post", "/api/v1/authoring/drafts/{draft_id}:publish"): (
            "publish_content_revision",
            True,
        ),
        ("post", "/api/v1/content/{content_id}/revisions/{revision_id}:retire"): (
            "retire_content_revision",
            True,
        ),
    }
    reads = {
        ("get", "/api/v1/authoring/drafts"): "list_content_drafts",
        ("get", "/api/v1/authoring/drafts/{draft_id}"): "get_content_draft",
        ("get", "/api/v1/authoring/content/{id}/history"): "get_content_history",
        ("get", "/api/v1/validation-reports/{id}"): "get_validation_report",
    }

    for (method, route), (operation_id, needs_version) in commands.items():
        operation = paths[route][method]
        parameters = _parameters(operation)
        assert operation["operationId"] == operation_id
        assert operation["security"] == [{"SessionCookie": []}]
        assert {"Origin", "X-CSRF-Token", "Idempotency-Key"} <= parameters.keys()
        assert all(parameters[name]["required"] is True for name in (
            "Origin",
            "X-CSRF-Token",
            "Idempotency-Key",
        ))
        assert ("If-Match" in parameters) is needs_version
        for status in ("401", "403", "409", "422", "503"):
            problem = operation["responses"][status]["content"][
                "application/problem+json"
            ]["schema"]
            assert problem["$ref"] == "#/components/schemas/ProblemResponse"

    for (method, route), operation_id in reads.items():
        operation = paths[route][method]
        assert operation["operationId"] == operation_id
        assert operation["security"] == [{"SessionCookie": []}]
        if route in {
            "/api/v1/authoring/drafts",
            "/api/v1/authoring/content/{id}/history",
        }:
            assert {"limit", "cursor"} <= _parameters(operation).keys()

    schemas = document["components"]["schemas"]
    for name in (
        "CreateContentDraftRequest",
        "ReviseContentDraftRequest",
        "ValidateContentRevisionRequest",
        "ApproveContentRevisionRequest",
        "PublishContentRevisionRequest",
        "ContentRevisionResponse",
        "ContentRevisionPageResponse",
        "ValidationReportResponse",
    ):
        assert schemas[name]["additionalProperties"] is False
    validate_registry_compatibility(document, ROOT / "contracts/registry")
