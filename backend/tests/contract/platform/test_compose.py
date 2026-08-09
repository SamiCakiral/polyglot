import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def compose_environment() -> dict[str, str]:
    return {
        **os.environ,
        "POLYGLOT_POSTGRES_PASSWORD": "contract-bootstrap-only",
        "POLYGLOT_MIGRATION_DB_PASSWORD": "contract-migration-only",
        "POLYGLOT_RUNTIME_DB_PASSWORD": "contract-runtime-only",
        "POLYGLOT_RETENTION_DB_PASSWORD": "contract-retention-only",
    }


def test_compose_uses_postgres_17_and_no_fake_object_storage_service() -> None:
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT,
        env=compose_environment(),
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
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT,
        env=compose_environment(),
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


def test_compose_bootstraps_and_exposes_only_dedicated_workload_logins() -> None:
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT,
        env=compose_environment(),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    configuration = json.loads(result.stdout)
    postgres = configuration["services"]["postgres"]
    assert postgres["environment"]["POSTGRES_USER"] == "polyglot_bootstrap"
    assert postgres["environment"]["POLYGLOT_MIGRATION_DB_PASSWORD"] == (
        "contract-migration-only"
    )
    assert postgres["environment"]["POLYGLOT_RUNTIME_DB_PASSWORD"] == (
        "contract-runtime-only"
    )
    assert postgres["environment"]["POLYGLOT_RETENTION_DB_PASSWORD"] == (
        "contract-retention-only"
    )
    assert any(
        volume["target"] == "/docker-entrypoint-initdb.d/10-polyglot-identities.sh"
        and volume["read_only"] is True
        for volume in postgres["volumes"]
    )
    assert "polyglot_runtime_login" in postgres["healthcheck"]["test"][-1]
    assert "polyglot_bootstrap" not in postgres["healthcheck"]["test"][-1]
    assert configuration["x-polyglot-database-urls"] == {
        "POLYGLOT_MIGRATION_DATABASE_URL": (
            "postgresql+asyncpg://polyglot_migration_login:"
            "contract-migration-only@127.0.0.1:55432/polyglot"
        ),
        "POLYGLOT_RETENTION_DATABASE_URL": (
            "postgresql+asyncpg://polyglot_retention_login:"
            "contract-retention-only@127.0.0.1:55432/polyglot"
        ),
        "POLYGLOT_DATABASE_URL": (
            "postgresql+asyncpg://polyglot_runtime_login:"
            "contract-runtime-only@127.0.0.1:55432/polyglot"
        ),
    }
