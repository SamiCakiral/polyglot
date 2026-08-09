import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_compose_uses_postgres_17_and_no_fake_object_storage_service() -> None:
    environment = {
        **os.environ,
        "POLYGLOT_POSTGRES_PASSWORD": "contract-only",
    }
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    configuration = json.loads(result.stdout)
    assert set(configuration["services"]) == {"postgres"}
    image = configuration["services"]["postgres"]["image"]
    assert image.startswith("postgres:17-alpine@sha256:")
    assert len(image.rsplit("@sha256:", 1)[1]) == 64


def test_compose_declares_the_w01_filesystem_placeholder() -> None:
    environment = {
        **os.environ,
        "POLYGLOT_POSTGRES_PASSWORD": "contract-only",
    }
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    configuration = json.loads(result.stdout)
    placeholder = configuration["x-polyglot-object-storage"]
    assert placeholder == {
        "mode": "filesystem-placeholder",
        "path": ".local/object-storage",
    }
