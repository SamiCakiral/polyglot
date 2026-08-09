import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OPENAPI_PATH = ROOT / "contracts/openapi/v1.json"


def test_openapi_exports_only_the_implemented_w01_surface() -> None:
    from polyglot.interfaces.http.app import create_app
    from polyglot.interfaces.http.export_openapi import validate_registry_compatibility

    document = create_app(test_mode=True).openapi()

    assert set(document["paths"]) == {
        "/api/v1/health/live",
        "/api/v1/health/ready",
    }
    validate_registry_compatibility(document, ROOT / "contracts/registry")


def test_committed_openapi_is_deterministic_and_current() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "polyglot.interfaces.http.export_openapi",
            "--check",
            str(OPENAPI_PATH),
        ],
        cwd=ROOT / "backend",
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    document = json.loads(OPENAPI_PATH.read_text())
    assert document["openapi"] == "3.1.0"
    assert document["info"]["title"] == "Polyglot V2 API"
