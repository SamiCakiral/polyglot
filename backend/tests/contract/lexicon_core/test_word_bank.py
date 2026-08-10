from polyglot.interfaces.http.app import create_app


COMMANDS = {
    ("post", "/api/v1/language-profiles/{profile_id}/encounters"),
    ("post", "/api/v1/lexical-mentions/{mention_id}:resolve"),
    ("post", "/api/v1/language-profiles/{profile_id}/private-lexicon"),
    ("post", "/api/v1/lexical-senses/{sense_id}/personal-relations"),
    ("post", "/api/v1/personal-lexical-relations/{relation_id}:retract"),
    ("post", "/api/v1/language-profiles/{profile_id}/private-lexicon:merge"),
    ("post", "/api/v1/lexical-senses/{sense_id}:split-private"),
    ("delete", "/api/v1/lexical-encounters/{encounter_id}/private-context"),
    ("post", "/api/v1/attempts/{attempt_id}/lexical-gaps"),
    ("put", "/api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/declaration"),
    ("put", "/api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/preference"),
    ("put", "/api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/annotation"),
    ("delete", "/api/v1/lexical-annotations/{annotation_id}"),
}


def parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["name"]: item
        for item in operation.get("parameters", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def test_w06_commands_are_authenticated_idempotent_and_closed() -> None:
    document = create_app(test_mode=True).openapi()

    for method, route in COMMANDS:
        operation = document["paths"][route][method]
        names = parameters(operation)
        assert operation["security"] == [{"SessionCookie": []}]
        assert {"Idempotency-Key", "Origin", "X-CSRF-Token"} <= names.keys()
        assert all(names[name]["required"] is True for name in (
            "Idempotency-Key",
            "Origin",
            "X-CSRF-Token",
        ))
        for status in ("401", "403", "409", "422", "503"):
            assert status in operation["responses"]


def test_versioned_annotations_and_preferences_require_if_match() -> None:
    document = create_app(test_mode=True).openapi()
    versioned = (
        ("put", "/api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/preference"),
        ("put", "/api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/annotation"),
        ("delete", "/api/v1/lexical-annotations/{annotation_id}"),
    )
    for method, route in versioned:
        operation = document["paths"][route][method]
        assert parameters(operation)["If-Match"]["required"] is True
        assert "428" in operation["responses"]
        assert operation["responses"]["200"]["headers"]["ETag"]


def test_word_bank_reads_are_paginated_bounded_and_never_claim_absolute_coverage() -> None:
    document = create_app(test_mode=True).openapi()
    paths = document["paths"]
    reads = {
        "/api/v1/lexicon/search",
        "/api/v1/lexical-senses/{sense_id}",
        "/api/v1/language-profiles/{profile_id}/word-bank",
        "/api/v1/language-profiles/{profile_id}/lexical-annotations",
    }
    assert reads <= paths.keys()
    neighborhood = paths["/api/v1/lexical-senses/{sense_id}"]["get"]
    by_name = parameters(neighborhood)
    assert by_name["depth"]["schema"]["maximum"] == 2
    assert by_name["max_nodes"]["schema"]["maximum"] == 500
    assert by_name["edge_types"]["required"] is True
    overview_schema = document["components"]["schemas"]["WordBankOverviewResponse"]
    assert "language_percentage" not in overview_schema["properties"]
    assert {"limit", "cursor"} <= parameters(
        paths["/api/v1/language-profiles/{profile_id}/word-bank"]["get"]
    ).keys()
