from polyglot.interfaces.http.app import create_app


def test_account_language_contract_is_authenticated_and_idempotent() -> None:
    document = create_app(test_mode=True).openapi()
    collection = document["paths"]["/api/v1/account-languages"]

    assert collection["get"]["operationId"] == "list_account_languages"
    assert collection["post"]["operationId"] == "create_account_language"
    assert {item["name"] for item in collection["post"]["parameters"]} >= {
        "Idempotency-Key",
        "Origin",
        "X-CSRF-Token",
    }
    request_ref = collection["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    request = document["components"]["schemas"][request_ref.rsplit("/", 1)[1]]
    assert request["additionalProperties"] is False

    member = document["paths"]["/api/v1/account-languages/{language_id}"]
    archive = document["paths"]["/api/v1/account-languages/{language_id}:archive"]
    assert member["patch"]["operationId"] == "revise_account_language"
    assert archive["post"]["operationId"] == "archive_account_language"
    for operation in (member["patch"], archive["post"]):
        parameters = {item["name"] for item in operation["parameters"]}
        assert {"Idempotency-Key", "If-Match", "Origin", "X-CSRF-Token"} <= parameters
        assert operation["responses"]["200"]["headers"]["ETag"]["schema"] == {"type": "string"}
