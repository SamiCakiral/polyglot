from polyglot.interfaces.http.app import create_app

COMMANDS = {
    ("post", "/api/v1/exercise-instances/{instance_id}/attempts", False),
    ("patch", "/api/v1/attempts/{attempt_id}/draft", True),
    ("post", "/api/v1/attempts/{attempt_id}/hints", True),
    ("post", "/api/v1/attempts/{attempt_id}:submit", True),
    ("post", "/api/v1/attempts/{attempt_id}:self-assess", True),
    ("post", "/api/v1/attempts/{attempt_id}/correction-case", True),
    ("post", "/api/v1/attempts/{attempt_id}:mark-correction-read", True),
    ("post", "/api/v1/correction-cases/{case_id}:resolve", True),
}

QUERIES = {
    ("get", "/api/v1/exercise-instances/{id}"),
    ("get", "/api/v1/attempts/{id}"),
    ("get", "/api/v1/correction-cases/{id}"),
}


def parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["name"]: item
        for item in operation.get("parameters", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def test_exercise_commands_are_authenticated_idempotent_closed_and_versioned() -> None:
    document = create_app(test_mode=True).openapi()

    for method, route, versioned in COMMANDS:
        operation = document["paths"][route][method]
        names = parameters(operation)
        assert operation["security"] == [{"SessionCookie": []}]
        assert {"Idempotency-Key", "Origin", "X-CSRF-Token"} <= names.keys()
        if versioned:
            assert names["If-Match"]["required"] is True
            assert "428" in operation["responses"]
        for status in ("401", "403", "409", "422", "503"):
            assert status in operation["responses"]
        body = operation.get("requestBody", {})
        if body:
            schema = body["content"]["application/json"]["schema"]
            assert schema.get("additionalProperties") is not True


def test_exercise_queries_are_authenticated() -> None:
    document = create_app(test_mode=True).openapi()

    for method, route in QUERIES:
        operation = document["paths"][route][method]
        assert operation["security"] == [{"SessionCookie": []}]
        assert {"401", "403", "422", "503"} <= operation["responses"].keys()


def test_answer_request_is_a_closed_discriminated_contract() -> None:
    document = create_app(test_mode=True).openapi()
    operation = document["paths"]["/api/v1/attempts/{attempt_id}:submit"]["post"]
    reference = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    schema = document["components"]["schemas"][reference.rsplit("/", 1)[-1]]

    assert schema["additionalProperties"] is False
    assert {"kind", "raw_value", "input_method", "input_locale", "submitted_at"} <= set(
        schema["properties"]
    )
