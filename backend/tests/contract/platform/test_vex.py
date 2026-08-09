import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
POSTGRES_IMAGE = (
    "postgres:17-alpine@sha256:"
    "742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193"
)
CVE = "CVE-2025-68121"


def test_postgres_cve_exception_is_digest_scoped_owned_and_expiring() -> None:
    vex_path = ROOT / "security/vex/postgres-17-alpine-CVE-2025-68121.json"
    vex = json.loads(vex_path.read_text())
    statement = vex["statements"][0]
    disposition = vex["x_polyglot"]
    recheck_on = date.fromisoformat(disposition["recheck_on"])
    expires_on = date.fromisoformat(disposition["expires_on"])

    assert statement["vulnerability"] == {"@id": CVE}
    assert statement["products"] == [{"@id": POSTGRES_IMAGE}]
    assert statement["status"] == "not_affected"
    assert statement["justification"] == "vulnerable_code_not_in_execute_path"
    assert disposition["image"] == POSTGRES_IMAGE
    assert disposition["component_path"] == "usr/local/bin/gosu"
    assert disposition["owner"] == "platform-security"
    assert "crypto/tls" in disposition["reachability"]
    assert disposition["reason"]
    assert date.today() <= recheck_on <= expires_on
    assert (expires_on - date.today()).days <= 90


def test_trivy_ignore_matches_vex_scope_and_is_wired_to_image_gate() -> None:
    ignore = json.loads((ROOT / ".trivyignore.yaml").read_text())
    vex = json.loads(
        (ROOT / "security/vex/postgres-17-alpine-CVE-2025-68121.json").read_text()
    )
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    entry = ignore["vulnerabilities"][0]

    assert entry["id"] == CVE
    assert entry["paths"] == ["usr/local/bin/gosu"]
    assert POSTGRES_IMAGE in entry["statement"]
    assert "platform-security" in entry["statement"]
    assert entry["expired_at"].endswith("Z")
    ignore_expiry = datetime.fromisoformat(entry["expired_at"].replace("Z", "+00:00"))
    assert ignore_expiry.date().isoformat() == vex["x_polyglot"]["expires_on"]
    assert "trivyignores: .trivyignore.yaml" in workflow
