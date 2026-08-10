from polyglot.interfaces.http.app import create_app

COMMANDS = {
    ("post", "/api/v1/language-profiles/{profile_id}/daily-plans", False),
    ("post", "/api/v1/language-profiles/{profile_id}/free-practice-plans", False),
    ("post", "/api/v1/session-plans/{plan_id}:prepare", True),
    ("post", "/api/v1/session-plans/{plan_id}:cancel", True),
    ("post", "/api/v1/session-plans/{plan_id}/runs", False),
    ("post", "/api/v1/sprint-runs/{run_id}:interrupt", True),
    ("post", "/api/v1/sprint-runs/{run_id}:resume", True),
    ("post", "/api/v1/sprint-runs/{run_id}:stop", True),
    ("post", "/api/v1/sprint-runs/{run_id}:complete", True),
    ("post", "/api/v1/sprint-runs/{run_id}/blocks/{block_id}:skip", True),
    ("post", "/api/v1/sprint-runs/{run_id}/blocks/{block_id}:abandon", True),
}


def parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["name"]: item
        for item in operation.get("parameters", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def test_sprint_commands_are_authenticated_idempotent_closed_and_versioned() -> None:
    document = create_app(test_mode=True).openapi()

    for method, route, versioned in COMMANDS:
        operation = document["paths"][route][method]
        names = parameters(operation)
        assert operation["security"] == [{"SessionCookie": []}]
        assert {"Idempotency-Key", "Origin", "X-CSRF-Token"} <= names.keys()
        if versioned:
            assert names["If-Match"]["required"] is True
            assert "428" in operation["responses"]
        body = operation["requestBody"]["content"]["application/json"]["schema"]
        schema = document["components"]["schemas"][body["$ref"].rsplit("/", 1)[-1]]
        assert schema["additionalProperties"] is False


def test_sprint_queries_are_authenticated_and_versioned() -> None:
    document = create_app(test_mode=True).openapi()

    for route in ("/api/v1/session-plans/{id}", "/api/v1/sprint-runs/{id}"):
        operation = document["paths"][route]["get"]
        assert operation["security"] == [{"SessionCookie": []}]
        assert operation["responses"]["200"]["headers"]["ETag"]["schema"] == {"type": "string"}


def test_free_practice_request_exposes_bounded_context_without_enrollment() -> None:
    document = create_app(test_mode=True).openapi()
    operation = document["paths"]["/api/v1/language-profiles/{profile_id}/free-practice-plans"][
        "post"
    ]
    reference = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    schema = document["components"]["schemas"][reference.rsplit("/", 1)[-1]]

    assert "enrollment_id" not in schema["properties"]
    assert schema["properties"]["private_context"]["anyOf"][0]["maxLength"] == 4000
