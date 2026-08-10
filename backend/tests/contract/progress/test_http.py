from polyglot.interfaces.http.app import create_app


def test_progress_reads_are_authenticated_paginated_and_do_not_expose_global_score() -> None:
    document = create_app(test_mode=True).openapi()

    progress = document["paths"]["/api/v1/language-profiles/{id}/progress"]["get"]
    recommendations = document["paths"]["/api/v1/language-profiles/{id}/recommendations"]["get"]
    for operation in (progress, recommendations):
        assert operation["security"] == [{"SessionCookie": []}]
        parameters = {item["name"]: item for item in operation["parameters"]}
        assert parameters["cursor"]["required"] is False
        assert parameters["limit"]["required"] is False

    schema_ref = progress["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    schema = document["components"]["schemas"][schema_ref.rsplit("/", 1)[-1]]
    assert "modalities" in schema["properties"]
    assert "global_score" not in schema["properties"]
    assert schema["properties"]["has_global_score"]["type"] == "boolean"
