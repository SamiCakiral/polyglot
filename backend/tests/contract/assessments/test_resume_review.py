from polyglot.interfaces.http.app import create_app

COMMANDS = {
    ("post", "/api/v1/language-profiles/{profile_id}/assessments", False),
    ("post", "/api/v1/assessments/{run_id}:start", True),
    ("patch", "/api/v1/assessments/{run_id}/responses/{item_id}", True),
    ("post", "/api/v1/assessments/{run_id}:pause", True),
    ("post", "/api/v1/assessments/{run_id}:resume", True),
    ("post", "/api/v1/assessments/{run_id}:submit", True),
    ("post", "/api/v1/assessments/{run_id}:resolve-review", True),
}


def parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["name"]: item
        for item in operation.get("parameters", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def test_assessment_commands_are_authenticated_idempotent_closed_and_versioned() -> None:
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


def test_assessment_read_model_is_frozen_versioned_and_never_exposes_solutions() -> None:
    document = create_app(test_mode=True).openapi()
    operation = document["paths"]["/api/v1/assessments/{id}"]["get"]

    assert operation["security"] == [{"SessionCookie": []}]
    assert operation["responses"]["200"]["headers"]["ETag"]["schema"] == {"type": "string"}
    item_schema = document["components"]["schemas"]["AssessmentItemResponse"]
    assert "prompt" in item_schema["properties"]
    assert "solution" not in item_schema["properties"]
    assert "accepted_answers" not in item_schema["properties"]


def test_four_modalities_and_not_evaluable_result_are_closed_contracts() -> None:
    document = create_app(test_mode=True).openapi()
    prepare = document["components"]["schemas"]["PrepareAssessmentRequest"]
    modality_ref = prepare["properties"]["modality"]["$ref"]
    modality = document["components"]["schemas"][modality_ref.rsplit("/", 1)[-1]]
    assert modality["enum"] == ["reading", "listening", "writing", "speaking"]

    result = document["components"]["schemas"]["AssessmentResultResponse"]
    assert {"status", "score", "band", "confidence", "coverage"} <= result["properties"].keys()
