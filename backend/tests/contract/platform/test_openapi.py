import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OPENAPI_PATH = ROOT / "contracts/openapi/v1.json"


def _parameter_names(operation: dict[str, object]) -> set[str]:
    return {
        parameter["name"]
        for parameter in operation.get("parameters", [])
        if isinstance(parameter, dict)
    }


def _parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        parameter["name"]: parameter
        for parameter in operation.get("parameters", [])
        if isinstance(parameter, dict) and isinstance(parameter.get("name"), str)
    }


def _assert_required_string_header(operation: dict[str, object], name: str) -> None:
    parameter = _parameters(operation)[name]
    assert parameter["in"] == "header"
    assert parameter["required"] is True
    schema = parameter["schema"]
    assert isinstance(schema, dict)
    assert schema.get("type") == "string"
    assert "anyOf" not in schema


def test_openapi_exports_the_implemented_w01_and_w02_surface() -> None:
    from polyglot.interfaces.http.app import create_app
    from polyglot.interfaces.http.export_openapi import validate_registry_compatibility

    document = create_app(test_mode=True).openapi()

    assert set(document["paths"]) == {
        "/api/v1/account/password",
        "/api/v1/account/preferences",
        "/api/v1/accounts",
        "/api/v1/authoring/content/{id}/history",
        "/api/v1/authoring/drafts",
        "/api/v1/authoring/drafts/{draft_id}",
        "/api/v1/authoring/drafts/{draft_id}:approve",
        "/api/v1/authoring/drafts/{draft_id}:publish",
        "/api/v1/authoring/drafts/{draft_id}:validate",
        "/api/v1/consents/{purpose}",
        "/api/v1/content/{content_id}/revisions/{revision_id}:retire",
        "/api/v1/catalogue/targets",
        "/api/v1/health/live",
        "/api/v1/health/ready",
        "/api/v1/language-packs",
        "/api/v1/language-profiles",
        "/api/v1/language-profiles/{id}",
        "/api/v1/language-profiles/{profile_id}",
        "/api/v1/language-profiles/{profile_id}/diagnostics",
        "/api/v1/language-profiles/{profile_id}/foundation-runs",
        "/api/v1/language-profiles/{profile_id}/goals",
        "/api/v1/language-profiles/{profile_id}:archive",
        "/api/v1/language-profiles/{profile_id}:pause",
        "/api/v1/language-profiles/{profile_id}:restore",
        "/api/v1/diagnostics/{id}",
        "/api/v1/diagnostics/{run_id}/responses",
        "/api/v1/diagnostics/{run_id}:complete",
        "/api/v1/foundation-runs/{id}",
        "/api/v1/foundation-runs/{run_id}:complete",
        "/api/v1/lexicon/search",
        "/api/v1/session",
        "/api/v1/validation-reports/{id}",
    }
    validate_registry_compatibility(document, ROOT / "contracts/registry")


def test_identity_openapi_models_security_headers_union_and_rfc9457() -> None:
    from polyglot.interfaces.http.app import create_app

    document = create_app(test_mode=True).openapi()
    paths = document["paths"]
    schemes = document["components"]["securitySchemes"]

    assert schemes["SessionCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "__Host-polyglot_session",
    }
    credentials_schema = paths["/api/v1/session"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    assert len(credentials_schema["oneOf"]) == 2
    assert credentials_schema["discriminator"]["propertyName"] == "provider_type"

    for method, route in (
        ("post", "/api/v1/accounts"),
        ("post", "/api/v1/session"),
        ("delete", "/api/v1/session"),
        ("put", "/api/v1/account/password"),
        ("patch", "/api/v1/account/preferences"),
        ("put", "/api/v1/consents/{purpose}"),
    ):
        _assert_required_string_header(paths[route][method], "Origin")
    for method, route in (
        ("delete", "/api/v1/session"),
        ("put", "/api/v1/account/password"),
        ("patch", "/api/v1/account/preferences"),
        ("put", "/api/v1/consents/{purpose}"),
    ):
        operation = paths[route][method]
        _assert_required_string_header(operation, "X-CSRF-Token")
        assert operation["security"] == [{"SessionCookie": []}]

    for method, route in (
        ("put", "/api/v1/account/password"),
        ("patch", "/api/v1/account/preferences"),
        ("put", "/api/v1/consents/{purpose}"),
    ):
        _assert_required_string_header(paths[route][method], "If-Match")

    assert _parameters(paths["/api/v1/session"]["delete"])["Idempotency-Key"][
        "required"
    ] is False
    assert _parameters(paths["/api/v1/account/preferences"]["patch"])[
        "Idempotency-Key"
    ]["required"] is False

    assert paths["/api/v1/session"]["get"]["security"] == [{"SessionCookie": []}]
    for status in ("401", "403", "409", "423", "429"):
        response = paths["/api/v1/account/password"]["put"]["responses"][status]
        assert "application/problem+json" in response["content"]
        schema = response["content"]["application/problem+json"]["schema"]
        assert schema["$ref"] == "#/components/schemas/ProblemResponse"


def test_registry_compatibility_rejects_missing_w02_operation_and_security_details() -> None:
    from polyglot.interfaces.http.app import create_app
    from polyglot.interfaces.http.export_openapi import validate_registry_compatibility

    document = create_app(test_mode=True).openapi()
    registry = ROOT / "contracts/registry"
    mutations = []

    missing_operation = deepcopy(document)
    del missing_operation["paths"]["/api/v1/session"]["delete"]
    mutations.append(missing_operation)

    missing_security = deepcopy(document)
    del missing_security["paths"]["/api/v1/session"]["get"]["security"]
    mutations.append(missing_security)

    missing_header = deepcopy(document)
    operation = missing_header["paths"]["/api/v1/account/password"]["put"]
    operation["parameters"] = [
        parameter for parameter in operation["parameters"] if parameter["name"] != "If-Match"
    ]
    mutations.append(missing_header)

    optional_header = deepcopy(document)
    operation = optional_header["paths"]["/api/v1/account/password"]["put"]
    _parameters(operation)["If-Match"]["required"] = False
    mutations.append(optional_header)

    for mutation in mutations:
        try:
            validate_registry_compatibility(mutation, registry)
        except ValueError:
            continue
        raise AssertionError("invalid W02 OpenAPI contract was accepted")


def test_committed_openapi_is_deterministic_and_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "polyglot.interfaces.http.export_openapi",
            "--check",
            str(OPENAPI_PATH),
        ],
        cwd=ROOT / "backend",
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    document = json.loads(OPENAPI_PATH.read_text())
    assert document["openapi"] == "3.1.0"
    assert document["info"]["title"] == "Polyglot V2 API"
