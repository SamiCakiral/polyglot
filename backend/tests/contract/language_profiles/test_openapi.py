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
        "trial_ordinal",
    }
    assert complete["responses"]["200"]["headers"]["ETag"]["schema"] == {
        "type": "string"
    }
