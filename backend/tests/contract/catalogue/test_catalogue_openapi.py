from copy import deepcopy
from pathlib import Path

import pytest

from polyglot.interfaces.http.app import create_app
from polyglot.interfaces.http.export_openapi import validate_registry_compatibility

ROOT = Path(__file__).resolve().parents[4]


def parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        parameter["name"]: parameter
        for parameter in operation.get("parameters", [])
        if isinstance(parameter, dict) and isinstance(parameter.get("name"), str)
    }


def test_openapi_exposes_all_required_w04_queries_and_parameters() -> None:
    document = create_app(test_mode=True).openapi()
    paths = document["paths"]

    assert paths["/api/v1/language-packs"]["get"]["operationId"] == "list_language_packs"
    assert paths["/api/v1/catalogue/targets"]["get"]["operationId"] == "list_catalogue_targets"
    assert paths["/api/v1/lexicon/search"]["get"]["operationId"] == "search_lexicon"
    assert parameters(paths["/api/v1/catalogue/targets"]["get"])["pack_code"][
        "required"
    ] is True
    lexicon_parameters = parameters(paths["/api/v1/lexicon/search"]["get"])
    assert lexicon_parameters["q"]["required"] is True
    assert lexicon_parameters["language_tag"]["required"] is True
    for route in ("/api/v1/language-packs", "/api/v1/catalogue/targets", "/api/v1/lexicon/search"):
        operation = paths[route]["get"]
        assert "security" not in operation
        problem = operation["responses"]["422"]["content"]["application/problem+json"]
        assert problem["schema"]["$ref"] == "#/components/schemas/ProblemResponse"
    validate_registry_compatibility(document, ROOT / "contracts/registry")


def test_language_pack_response_exposes_runtime_language_metadata() -> None:
    document = create_app(test_mode=True).openapi()
    schema = document["components"]["schemas"]["LanguagePackResponse"]

    assert set(schema["required"]) >= {
        "target_script_codes",
        "text_direction",
        "segmentation_policy_revision_id",
        "media_capabilities",
        "capability_manifest",
    }


def test_registry_compatibility_rejects_a_missing_w04_query() -> None:
    document = deepcopy(create_app(test_mode=True).openapi())
    del document["paths"]["/api/v1/lexicon/search"]

    with pytest.raises(ValueError, match="W04"):
        validate_registry_compatibility(document, ROOT / "contracts/registry")
