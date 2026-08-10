from polyglot.interfaces.http.app import create_app

COMMANDS = {
    ("post", "/api/v1/language-profiles/{profile_id}/memory-prompts", False),
    ("post", "/api/v1/memory-prompts/{prompt_id}/reviews", True),
    ("post", "/api/v1/memory-prompts/{prompt_id}:suspend", True),
    ("post", "/api/v1/memory-prompts/{prompt_id}:resume", True),
    ("post", "/api/v1/memory-prompts/{prompt_id}:reset", True),
    ("post", "/api/v1/memory-prompts:merge", False),
    ("post", "/api/v1/memory-prompts/{prompt_id}:archive", True),
    ("post", "/api/v1/memory-prompts/{prompt_id}:restore", True),
    ("delete", "/api/v1/memory-prompts/{prompt_id}", True),
}


def parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["name"]: item
        for item in operation.get("parameters", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def test_memory_commands_are_authenticated_idempotent_closed_and_versioned() -> None:
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


def test_due_query_is_authenticated_stable_and_bounded() -> None:
    operation = create_app(test_mode=True).openapi()["paths"][
        "/api/v1/memory-prompts/due"
    ]["get"]
    names = parameters(operation)
    assert operation["security"] == [{"SessionCookie": []}]
    assert {"profile_id", "cutoff", "limit", "cursor"} <= names.keys()
    assert names["limit"]["schema"]["maximum"] == 100
    assert names["cutoff"]["required"] is True
    assert {"401", "403", "422", "503"} <= operation["responses"].keys()
