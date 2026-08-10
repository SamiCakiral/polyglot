from polyglot.interfaces.http.app import create_app


def parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["name"]: item
        for item in operation.get("parameters", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def test_media_mutations_are_authenticated_closed_and_idempotent() -> None:
    document = create_app(test_mode=True).openapi()
    commands = (
        ("post", "/api/v1/media/uploads", False),
        ("post", "/api/v1/media/uploads/{upload_id}:complete", False),
        ("delete", "/api/v1/media/{media_id}", True),
        ("post", "/api/v1/media/tts/syntheses", False),
    )

    for method, path, versioned in commands:
        operation = document["paths"][path][method]
        names = parameters(operation)
        assert operation["security"] == [{"SessionCookie": []}]
        assert {"Idempotency-Key", "Origin", "X-CSRF-Token"} <= names.keys()
        if versioned:
            assert names["If-Match"]["required"] is True
            assert "428" in operation["responses"]
        if "requestBody" in operation:
            body = operation["requestBody"]["content"]["application/json"]["schema"]
            schema = document["components"]["schemas"][body["$ref"].rsplit("/", 1)[-1]]
            assert schema["additionalProperties"] is False


def test_signed_binary_routes_do_not_claim_session_authentication() -> None:
    document = create_app(test_mode=True).openapi()
    upload = document["paths"]["/api/v1/media/uploads/{upload_id}/content"]["put"]
    download = document["paths"]["/api/v1/media/{media_id}/content"]["get"]

    assert "security" not in upload
    assert "security" not in download
    for operation in (upload, download):
        token = parameters(operation)["token"]
        assert token["required"] is True
        assert token["in"] == "query"


def test_media_read_model_never_persists_or_exposes_storage_keys() -> None:
    document = create_app(test_mode=True).openapi()
    schema = document["components"]["schemas"]["MediaResponse"]

    assert "storage_key" not in schema["properties"]
    assert "public_url" not in schema["properties"]
    assert {"upload_url", "read_url", "url_expires_at"} <= schema["properties"].keys()
