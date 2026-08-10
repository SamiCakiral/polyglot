import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_w00_registry_declares_all_ten_w05_http_routes() -> None:
    commands = json.loads((ROOT / "contracts/registry/commands.yaml").read_text())["commands"]
    queries = json.loads((ROOT / "contracts/registry/queries.yaml").read_text())["queries"]

    registered = {(item["method"], item["route"]) for item in commands}
    registered.update(
        (item["method"], f"/api/v1{item['route']}") for item in queries
    )
    required = {
        ("POST", "/api/v1/authoring/drafts"),
        ("PATCH", "/api/v1/authoring/drafts/{draft_id}"),
        ("POST", "/api/v1/authoring/drafts/{draft_id}:validate"),
        ("POST", "/api/v1/authoring/drafts/{draft_id}:approve"),
        ("POST", "/api/v1/authoring/drafts/{draft_id}:publish"),
        ("POST", "/api/v1/content/{content_id}/revisions/{revision_id}:retire"),
        ("GET", "/api/v1/authoring/drafts"),
        ("GET", "/api/v1/authoring/drafts/{draft_id}"),
        ("GET", "/api/v1/authoring/content/{id}/history"),
        ("GET", "/api/v1/validation-reports/{id}"),
    }

    assert required <= registered
