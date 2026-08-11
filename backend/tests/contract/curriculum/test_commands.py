from polyglot.interfaces.http.app import create_app

COMMANDS = {
    ("post", "/api/v1/language-profiles/{profile_id}/module-enrollments", False),
    ("post", "/api/v1/module-enrollments/{id}:pause", True),
    ("post", "/api/v1/module-enrollments/{id}:complete", True),
}


def parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["name"]: item
        for item in operation.get("parameters", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def test_curriculum_commands_are_authenticated_idempotent_closed_and_versioned() -> None:
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


def test_curriculum_queries_are_authenticated_and_enrollment_is_versioned() -> None:
    document = create_app(test_mode=True).openapi()

    modules = document["paths"]["/api/v1/modules"]["get"]
    enrollment = document["paths"]["/api/v1/module-enrollments/{id}"]["get"]
    assert modules["security"] == [{"SessionCookie": []}]
    assert parameters(modules)["pack_revision_id"]["required"] is False
    module_schema = document["components"]["schemas"]["ModuleResponse"]
    assert "pack_revision_id" in module_schema["required"]
    assert enrollment["security"] == [{"SessionCookie": []}]
    assert enrollment["responses"]["200"]["headers"]["ETag"]["schema"] == {"type": "string"}


def test_completion_request_cannot_self_assert_exit_criteria() -> None:
    document = create_app(test_mode=True).openapi()
    operation = document["paths"]["/api/v1/module-enrollments/{id}:complete"]["post"]
    reference = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    schema = document["components"]["schemas"][reference.rsplit("/", 1)[-1]]

    assert set(schema["properties"]) == {"completed_at"}
