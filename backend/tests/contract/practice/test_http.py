from polyglot.interfaces.http.app import create_app

COMMANDS = {
    ("post", "/api/v1/language-profiles/{profile_id}/practice-stacks"),
    ("post", "/api/v1/practice-stacks:combine"),
    ("post", "/api/v1/practice-stacks/{stack_id}:inject-next-sprint"),
    ("post", "/api/v1/language-profiles/{profile_id}/practice-presets"),
    ("post", "/api/v1/practice-presets/{preset_id}/runs"),
    ("post", "/api/v1/practice-runs/{run_id}:advance"),
    ("post", "/api/v1/practice-runs/{run_id}:interrupt"),
    ("post", "/api/v1/practice-runs/{run_id}:resume"),
    ("post", "/api/v1/practice-runs/{run_id}:abandon"),
}


def parameters(operation: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        item["name"]: item
        for item in operation.get("parameters", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def test_practice_commands_are_authenticated_idempotent_and_closed() -> None:
    document = create_app(test_mode=True).openapi()

    for method, route in COMMANDS:
        operation = document["paths"][route][method]
        names = parameters(operation)
        assert operation["security"] == [{"SessionCookie": []}]
        assert {"Idempotency-Key", "Origin", "X-CSRF-Token"} <= names.keys()
        assert all(
            names[name]["required"] is True
            for name in ("Idempotency-Key", "Origin", "X-CSRF-Token")
        )
        for status in ("401", "403", "409", "422", "503"):
            assert status in operation["responses"]


def test_run_mutations_require_expected_version() -> None:
    document = create_app(test_mode=True).openapi()
    for action in ("advance", "interrupt", "resume", "abandon"):
        operation = document["paths"][f"/api/v1/practice-runs/{{run_id}}:{action}"]["post"]
        assert parameters(operation)["If-Match"]["required"] is True
        assert "428" in operation["responses"]


def test_practice_reads_are_authenticated() -> None:
    document = create_app(test_mode=True).openapi()
    reads = (
        "/api/v1/language-profiles/{profile_id}/practice-stacks",
        "/api/v1/practice-stacks/{stack_id}",
        "/api/v1/language-profiles/{profile_id}/practice-presets",
        "/api/v1/practice-runs/{run_id}",
    )
    assert all(
        document["paths"][route]["get"]["security"] == [{"SessionCookie": []}] for route in reads
    )
