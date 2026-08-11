from polyglot.interfaces.http.app import create_app


def test_onboarding_contract_supports_entry_placement_and_user_choice() -> None:
    document = create_app(test_mode=True).openapi()
    paths = document["paths"]
    resource = paths["/api/v1/language-profiles/{profile_id}/onboarding"]
    placement = paths["/api/v1/language-profiles/{profile_id}/onboarding/placement"]
    choice = paths["/api/v1/language-profiles/{profile_id}/onboarding:choose"]

    assert resource["get"]["operationId"] == "get_onboarding_state"
    assert resource["put"]["operationId"] == "start_onboarding"
    assert placement["patch"]["operationId"] == "record_placement_profile"
    assert choice["post"]["operationId"] == "choose_placement"

    for operation in (resource["put"], placement["patch"], choice["post"]):
        parameters = {item["name"] for item in operation["parameters"]}
        assert {"Idempotency-Key", "Origin", "X-CSRF-Token"} <= parameters
        assert operation["responses"]["200"]["headers"]["ETag"]["schema"] == {"type": "string"}
    for operation in (placement["patch"], choice["post"]):
        assert "If-Match" in {item["name"] for item in operation["parameters"]}

    response_schema = document["components"]["schemas"]["OnboardingResponse"]
    assert response_schema["properties"]["can_train"]["type"] == "boolean"
    assert response_schema["properties"]["skill_profile"]["type"] == "array"
