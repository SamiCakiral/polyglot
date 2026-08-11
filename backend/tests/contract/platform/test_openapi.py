import json
import os
import re
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


def test_openapi_exports_the_implemented_w01_through_w16_surface() -> None:
    from polyglot.interfaces.http.app import create_app
    from polyglot.interfaces.http.export_openapi import validate_registry_compatibility

    document = create_app(test_mode=True).openapi()

    assert set(document["paths"]) == {
        "/api/v1/account/password",
        "/api/v1/account/preferences",
        "/api/v1/account-languages",
        "/api/v1/account-languages/{language_id}",
        "/api/v1/account-languages/{language_id}:archive",
            "/api/v1/assessments/{id}",
            "/api/v1/assessments/{run_id}/responses/{item_id}",
            "/api/v1/assessments/{run_id}:pause",
            "/api/v1/assessments/{run_id}:resolve-review",
            "/api/v1/assessments/{run_id}:resume",
            "/api/v1/assessments/{run_id}:start",
            "/api/v1/assessments/{run_id}:submit",
            "/api/v1/accounts",
            "/api/v1/attempts/{attempt_id}/correction-case",
            "/api/v1/attempts/{attempt_id}/draft",
            "/api/v1/attempts/{attempt_id}/hints",
            "/api/v1/attempts/{attempt_id}/lexical-gaps",
            "/api/v1/attempts/{attempt_id}:mark-correction-read",
                "/api/v1/attempts/{attempt_id}:evaluate",
                "/api/v1/attempts/{attempt_id}:submit",
                "/api/v1/attempts/{attempt_id}:self-assess",
            "/api/v1/attempts/{id}",
            "/api/v1/authoring-artifacts",
            "/api/v1/authoring-artifacts/{artifact_id}",
            "/api/v1/authoring/content/{id}/history",
        "/api/v1/authoring/drafts",
        "/api/v1/authoring/drafts/{draft_id}",
        "/api/v1/authoring/drafts/{draft_id}:approve",
        "/api/v1/authoring/drafts/{draft_id}:publish",
        "/api/v1/authoring/drafts/{draft_id}:validate",
        "/api/v1/consents/{purpose}",
            "/api/v1/content/{content_id}/revisions/{revision_id}:retire",
            "/api/v1/correction-cases/{case_id}:resolve",
            "/api/v1/correction-cases/{id}",
        "/api/v1/catalogue/targets",
        "/api/v1/health/live",
        "/api/v1/health/ready",
        "/api/v1/generation-jobs",
        "/api/v1/generation-jobs/{job_id}:cancel",
        "/api/v1/jobs/{id}",
            "/api/v1/language-packs",
            "/api/v1/language-packs/{pack_revision_id}/foundation-manifest",
            "/api/v1/language-packs/{pack_revision_id}/grammar-functions",
            "/api/v1/language-packs/{pack_revision_id}/placement-manifest",
        "/api/v1/language-profiles",
        "/api/v1/language-profiles/{id}",
        "/api/v1/language-profiles/{id}/progress",
        "/api/v1/language-profiles/{id}/recommendations",
        "/api/v1/language-profiles/{profile_id}",
        "/api/v1/language-profiles/{profile_id}/assessment-capabilities",
        "/api/v1/language-profiles/{profile_id}/assessments",
        "/api/v1/language-profiles/{profile_id}/diagnostics",
        "/api/v1/language-profiles/{profile_id}/daily-plans",
        "/api/v1/language-profiles/{profile_id}/encounters",
        "/api/v1/language-profiles/{profile_id}/foundation-runs",
            "/api/v1/language-profiles/{profile_id}/free-practice-plans",
            "/api/v1/language-profiles/{profile_id}/practice-presets",
            "/api/v1/language-profiles/{profile_id}/practice-stacks",
            "/api/v1/language-profiles/{profile_id}/teacher-conversations",
        "/api/v1/language-profiles/{profile_id}/goals",
        "/api/v1/language-profiles/{profile_id}/lexical-annotations",
        "/api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/annotation",
        "/api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/declaration",
            "/api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/preference",
        "/api/v1/language-profiles/{profile_id}/memory-prompts",
        "/api/v1/language-profiles/{profile_id}/module-enrollments",
        "/api/v1/language-profiles/{profile_id}/onboarding",
        "/api/v1/language-profiles/{profile_id}/onboarding/placement",
        "/api/v1/language-profiles/{profile_id}/onboarding:choose",
        "/api/v1/language-profiles/{profile_id}/imports",
        "/api/v1/language-profiles/{profile_id}/private-lexicon",
        "/api/v1/language-profiles/{profile_id}/private-lexicon:merge",
        "/api/v1/language-profiles/{profile_id}/exports",
        "/api/v1/language-profiles/{profile_id}/vocabulary-lists",
        "/api/v1/language-profiles/{profile_id}/word-bank",
        "/api/v1/language-profiles/{profile_id}:archive",
        "/api/v1/language-profiles/{profile_id}:pause",
        "/api/v1/language-profiles/{profile_id}:restore",
        "/api/v1/diagnostics/{id}",
        "/api/v1/diagnostics/{run_id}/responses",
            "/api/v1/diagnostics/{run_id}:complete",
            "/api/v1/exercise-instances/{id}",
            "/api/v1/exercise-instances/{instance_id}/attempts",
        "/api/v1/foundation-runs/{id}",
        "/api/v1/foundation-runs/{run_id}:complete",
        "/api/v1/lexical-annotations/{annotation_id}",
        "/api/v1/lexical-encounters/{encounter_id}/private-context",
        "/api/v1/lexical-mentions/{mention_id}:resolve",
        "/api/v1/lexical-senses/{sense_id}",
        "/api/v1/lexical-senses/{sense_id}/personal-relations",
        "/api/v1/lexical-senses/{sense_id}:split-private",
            "/api/v1/lexicon/search",
            "/api/v1/memory-prompts/due",
            "/api/v1/memory-prompts:merge",
            "/api/v1/memory-prompts/{prompt_id}",
            "/api/v1/memory-prompts/{prompt_id}/reviews",
            "/api/v1/memory-prompts/{prompt_id}:archive",
            "/api/v1/memory-prompts/{prompt_id}:reset",
            "/api/v1/memory-prompts/{prompt_id}:restore",
            "/api/v1/memory-prompts/{prompt_id}:resume",
        "/api/v1/memory-prompts/{prompt_id}:suspend",
        "/api/v1/media/tts/capabilities",
        "/api/v1/media/tts/syntheses",
        "/api/v1/media/uploads",
        "/api/v1/media/uploads/{upload_id}/content",
        "/api/v1/media/uploads/{upload_id}:complete",
        "/api/v1/media/{media_id}",
        "/api/v1/media/{media_id}/content",
        "/api/v1/module-enrollments/{id}",
        "/api/v1/module-enrollments/{id}:complete",
        "/api/v1/module-enrollments/{id}:pause",
        "/api/v1/modules",
        "/api/v1/imports/{id}",
            "/api/v1/imports/{import_id}/conflicts/{conflict_id}:resolve",
            "/api/v1/imports/{import_id}/preview",
        "/api/v1/imports/{import_id}:commit",
        "/api/v1/imports/{import_id}:revert",
            "/api/v1/personal-lexical-relations/{relation_id}:retract",
            "/api/v1/practice-presets/{preset_id}/runs",
            "/api/v1/practice-runs/{run_id}",
            "/api/v1/practice-runs/{run_id}:abandon",
            "/api/v1/practice-runs/{run_id}:advance",
            "/api/v1/practice-runs/{run_id}:interrupt",
            "/api/v1/practice-runs/{run_id}:resume",
            "/api/v1/practice-stacks/{stack_id}",
            "/api/v1/practice-stacks/{stack_id}:inject-next-sprint",
            "/api/v1/practice-stacks:combine",
        "/api/v1/session",
        "/api/v1/session-plans/{id}",
        "/api/v1/session-plans/{plan_id}/runs",
        "/api/v1/session-plans/{plan_id}:cancel",
        "/api/v1/session-plans/{plan_id}:prepare",
        "/api/v1/sprint-runs/{id}",
        "/api/v1/sprint-runs/{run_id}/blocks/{block_id}:abandon",
        "/api/v1/sprint-runs/{run_id}/blocks/{block_id}:skip",
        "/api/v1/sprint-runs/{run_id}:complete",
        "/api/v1/sprint-runs/{run_id}:interrupt",
        "/api/v1/sprint-runs/{run_id}:resume",
        "/api/v1/sprint-runs/{run_id}:stop",
        "/api/v1/teacher-actions/{action_id}:revert",
        "/api/v1/teacher-conversations/{conversation_id}",
        "/api/v1/teacher-conversations/{conversation_id}/messages",
        "/api/v1/tools/{tool_name}:invoke",
        "/api/v1/tools",
        "/api/v1/exports/{id}",
        "/api/v1/shared-vocabulary-lists",
        "/api/v1/shared-vocabulary-lists/{id}",
        "/api/v1/shared-vocabulary-lists/{publication_id}:retire",
        "/api/v1/validation-reports/{id}",
        "/api/v1/vocabulary-lists",
        "/api/v1/vocabulary-lists/{id}",
        "/api/v1/vocabulary-lists/{list_id}",
            "/api/v1/vocabulary-lists/{list_id}/members:batch",
            "/api/v1/vocabulary-lists/{list_id}/preview",
        "/api/v1/vocabulary-lists/{list_id}/snapshots/{snapshot_id}:publish",
        "/api/v1/vocabulary-lists/{list_id}:clone",
        "/api/v1/vocabulary-lists/{list_id}:snapshot",
        "/api/v1/vocabulary-lists:merge",
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
        env={**os.environ, "PYTHONPATH": str(ROOT / "backend" / "src")},
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    document = json.loads(OPENAPI_PATH.read_text())
    assert document["openapi"] == "3.1.0"
    assert document["info"]["title"] == "Polyglot V2 API"


def test_every_declared_url_variable_is_a_required_path_parameter() -> None:
    from polyglot.interfaces.http.app import create_app

    document = create_app(test_mode=True).openapi()
    for route, path_item in document["paths"].items():
        expected = set(re.findall(r"\{([^}]+)\}", route))
        for method, operation in path_item.items():
            if method == "parameters":
                continue
            parameters = {
                parameter["name"]: parameter
                for parameter in operation.get("parameters", [])
                if parameter.get("in") == "path"
            }
            assert set(parameters) == expected, f"{method.upper()} {route}"
            assert all(parameter["required"] is True for parameter in parameters.values())
