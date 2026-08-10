from __future__ import annotations

from polyglot.interfaces.http.app import create_app

COMMANDS = {
    ("post", "/api/v1/language-profiles/{profile_id}/vocabulary-lists", False),
    ("patch", "/api/v1/vocabulary-lists/{list_id}", True),
    ("post", "/api/v1/vocabulary-lists/{list_id}/members:batch", True),
    ("post", "/api/v1/vocabulary-lists/{list_id}:snapshot", True),
    ("post", "/api/v1/vocabulary-lists/{list_id}:clone", False),
    ("post", "/api/v1/vocabulary-lists:merge", False),
    (
        "post",
        "/api/v1/vocabulary-lists/{list_id}/snapshots/{snapshot_id}:publish",
        True,
    ),
    ("post", "/api/v1/shared-vocabulary-lists/{publication_id}:retire", True),
    ("post", "/api/v1/language-profiles/{profile_id}/imports", False),
    (
        "post",
        "/api/v1/imports/{import_id}/conflicts/{conflict_id}:resolve",
        True,
    ),
    ("post", "/api/v1/imports/{import_id}:commit", True),
    ("post", "/api/v1/imports/{import_id}:revert", True),
    ("post", "/api/v1/language-profiles/{profile_id}/exports", False),
}


def _parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["name"]: item
        for item in operation.get("parameters", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def test_exchange_commands_are_closed_authenticated_idempotent_and_versioned() -> None:
    document = create_app(test_mode=True).openapi()
    for method, route, versioned in COMMANDS:
        operation = document["paths"][route][method]
        parameters = _parameters(operation)
        assert operation["security"] == [{"SessionCookie": []}]
        assert {"Idempotency-Key", "Origin", "X-CSRF-Token"} <= parameters.keys()
        if versioned:
            assert parameters["If-Match"]["required"] is True
            assert "428" in operation["responses"]
        schema_ref = operation["requestBody"]["content"]["application/json"]["schema"]
        schema = document["components"]["schemas"][schema_ref["$ref"].rsplit("/", 1)[-1]]
        assert schema["additionalProperties"] is False


def test_exchange_queries_are_authenticated_and_bounded() -> None:
    document = create_app(test_mode=True).openapi()
    for route in (
        "/api/v1/vocabulary-lists",
        "/api/v1/vocabulary-lists/{id}",
        "/api/v1/shared-vocabulary-lists",
        "/api/v1/shared-vocabulary-lists/{id}",
        "/api/v1/imports/{id}",
        "/api/v1/exports/{id}",
    ):
        operation = document["paths"][route]["get"]
        assert operation["security"] == [{"SessionCookie": []}]
        assert {"401", "403", "422", "503"} <= operation["responses"].keys()
        assert not {name for name in _parameters(operation) if name.startswith("_")}
    list_parameters = _parameters(document["paths"]["/api/v1/vocabulary-lists"]["get"])
    assert list_parameters["limit"]["schema"]["maximum"] == 100


def test_commit_request_cannot_self_assert_catalogue_freshness() -> None:
    document = create_app(test_mode=True).openapi()
    operation = document["paths"]["/api/v1/imports/{import_id}:commit"]["post"]
    schema_ref = operation["requestBody"]["content"]["application/json"]["schema"]
    schema = document["components"]["schemas"][schema_ref["$ref"].rsplit("/", 1)[-1]]
    assert "current_catalogue_version" not in schema["properties"]
    assert "catalogue_version" not in schema["properties"]
