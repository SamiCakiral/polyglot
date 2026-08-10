from polyglot.interfaces.http.app import create_app


def parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["name"]: item
        for item in operation.get("parameters", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def test_generation_commands_are_authenticated_closed_and_idempotent() -> None:
    document = create_app(test_mode=True).openapi()
    commands = (
        ("post", "/api/v1/generation-jobs", False),
        ("post", "/api/v1/generation-jobs/{job_id}:cancel", True),
        ("post", "/api/v1/tools/{tool_name}:invoke", False),
    )
    for method, path, versioned in commands:
        operation = document["paths"][path][method]
        names = parameters(operation)
        assert operation["security"] == [{"SessionCookie": []}]
        assert {"Idempotency-Key", "Origin", "X-CSRF-Token"} <= names.keys()
        if versioned:
            assert names["If-Match"]["required"] is True
        if "requestBody" in operation:
            body = operation["requestBody"]["content"]["application/json"]["schema"]
            schema = document["components"]["schemas"][body["$ref"].rsplit("/", 1)[-1]]
            assert schema["additionalProperties"] is False


def test_tool_result_has_no_publish_or_mastery_field() -> None:
    document = create_app(test_mode=True).openapi()
    operation = document["paths"]["/api/v1/tools/{tool_name}:invoke"]["post"]
    response = operation["responses"]["200"]["content"]["application/json"]["schema"]
    schema = document["components"]["schemas"][response["$ref"].rsplit("/", 1)[-1]]
    assert "publish" not in schema["properties"]
    assert "mastery" not in schema["properties"]


def test_job_query_is_owner_authenticated() -> None:
    document = create_app(test_mode=True).openapi()
    operation = document["paths"]["/api/v1/jobs/{id}"]["get"]
    assert operation["security"] == [{"SessionCookie": []}]


def test_tool_catalogue_is_authenticated_and_machine_readable() -> None:
    document = create_app(test_mode=True).openapi()
    operation = document["paths"]["/api/v1/tools"]["get"]
    assert operation["security"] == [{"SessionCookie": []}]
    response = operation["responses"]["200"]["content"]["application/json"]["schema"]
    definition = document["components"]["schemas"][
        response["items"]["$ref"].rsplit("/", 1)[-1]
    ]
    assert {"input_schema", "output_schema", "effect", "roles"} <= definition[
        "properties"
    ].keys()
