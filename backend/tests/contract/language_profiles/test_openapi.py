"""Machine-readable W03 HTTP contract remains explicit and closed."""

from polyglot.interfaces.http.app import create_app


def test_foundation_openapi_exposes_versioned_complete_workflow() -> None:
    document = create_app(test_mode=True).openapi()
    start = document["paths"]["/api/v1/language-profiles/{profile_id}/foundation-runs"][
        "post"
    ]
    complete = document["paths"]["/api/v1/foundation-runs/{run_id}:complete"]["post"]

    assert "201" in start["responses"]
    assert {item["name"] for item in start["parameters"]} >= {
        "Idempotency-Key",
        "If-Match",
        "Origin",
        "X-CSRF-Token",
    }
    assert {item["name"] for item in complete["parameters"]} >= {
        "Idempotency-Key",
        "If-Match",
        "Origin",
        "X-CSRF-Token",
    }
    request_schema = complete["requestBody"]["content"]["application/json"]["schema"]
    request_model = document["components"]["schemas"][request_schema["$ref"].rsplit("/", 1)[1]]
    assert set(request_model["properties"]) == {"answers"}
    assert request_model["additionalProperties"] is False
    answer_schema = document["components"]["schemas"]["FoundationAnswerRequest"]
    assert set(answer_schema["required"]) == {
        "answer",
        "item_revision_id",
    }
    assert complete["responses"]["200"]["headers"]["ETag"]["schema"] == {
        "type": "string"
    }


def test_every_w03_existing_resource_command_requires_if_match_and_documents_428() -> None:
    document = create_app(test_mode=True).openapi()
    operations = (
        ("/api/v1/language-profiles/{profile_id}/goals", "patch"),
        ("/api/v1/language-profiles/{profile_id}/diagnostics", "post"),
        ("/api/v1/diagnostics/{run_id}/responses", "post"),
        ("/api/v1/diagnostics/{run_id}:complete", "post"),
        ("/api/v1/language-profiles/{profile_id}/foundation-runs", "post"),
        ("/api/v1/foundation-runs/{run_id}:complete", "post"),
        ("/api/v1/language-profiles/{profile_id}:pause", "post"),
        ("/api/v1/language-profiles/{profile_id}:archive", "post"),
        ("/api/v1/language-profiles/{profile_id}:restore", "post"),
        ("/api/v1/language-profiles/{profile_id}", "delete"),
    )
    for path, method in operations:
        operation = document["paths"][path][method]
        if_match = next(item for item in operation["parameters"] if item["name"] == "If-Match")
        assert if_match["required"] is True, (path, method, if_match)
        assert if_match["schema"] == {"type": "string", "title": "If-Match"}
        assert "428" in operation["responses"], (path, method)


def test_every_w03_resource_transition_documents_and_returns_an_etag() -> None:
    document = create_app(test_mode=True).openapi()
    for path, method in (
        ("/api/v1/language-profiles/{profile_id}:pause", "post"),
        ("/api/v1/language-profiles/{profile_id}:archive", "post"),
        ("/api/v1/language-profiles/{profile_id}:restore", "post"),
        ("/api/v1/language-profiles/{profile_id}", "delete"),
    ):
        response = document["paths"][path][method]["responses"]["200"]
        assert response["headers"]["ETag"]["schema"] == {"type": "string"}
