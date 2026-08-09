import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast

from sqlalchemy import make_url

ROOT = Path(__file__).resolve().parents[4]

WORKLOAD_PASSWORDS = {
    "migration": "mig:r@tion/%#secret",
    "runtime": "run:t@ime/%#secret",
    "retention": "ret:ent@ion/%#secret",
}


def compose_environment(
    workload_passwords: dict[str, str] | None = None,
) -> dict[str, str]:
    passwords = workload_passwords or {
        "migration": "contract-migration-only",
        "runtime": "contract-runtime-only",
        "retention": "contract-retention-only",
    }
    return {
        **os.environ,
        "POLYGLOT_POSTGRES_PASSWORD": "contract-bootstrap-only",
        "POLYGLOT_MIGRATION_DB_PASSWORD": passwords["migration"],
        "POLYGLOT_RUNTIME_DB_PASSWORD": passwords["runtime"],
        "POLYGLOT_RETENTION_DB_PASSWORD": passwords["retention"],
    }


def render_compose(
    workload_passwords: dict[str, str] | None = None,
) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT,
        env=compose_environment(workload_passwords),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    return cast(dict[str, Any], json.loads(result.stdout))


def test_compose_uses_postgres_17_and_no_fake_object_storage_service() -> None:
    configuration = render_compose()
    assert set(configuration["services"]) == {"postgres"}
    image = configuration["services"]["postgres"]["image"]
    assert image.startswith("postgres:17-alpine@sha256:")
    assert len(image.rsplit("@sha256:", 1)[1]) == 64


def test_compose_declares_the_w01_filesystem_placeholder() -> None:
    configuration = render_compose()
    placeholder = configuration["x-polyglot-object-storage"]
    assert placeholder == {
        "mode": "filesystem-placeholder",
        "path": ".local/object-storage",
    }


def test_compose_bootstraps_and_exposes_only_dedicated_workload_logins() -> None:
    configuration = render_compose()
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
    assert "x-polyglot-database-urls" not in configuration
    assert configuration["x-polyglot-database-environment"] == {
        "POLYGLOT_DATABASE_DRIVERNAME": "postgresql+asyncpg",
        "POLYGLOT_DATABASE_HOST": "127.0.0.1",
        "POLYGLOT_DATABASE_NAME": "polyglot",
        "POLYGLOT_DATABASE_PORT": "55432",
        "POLYGLOT_MIGRATION_DATABASE_PASSWORD": "contract-migration-only",
        "POLYGLOT_MIGRATION_DATABASE_USERNAME": "polyglot_migration_login",
        "POLYGLOT_RETENTION_DATABASE_PASSWORD": "contract-retention-only",
        "POLYGLOT_RETENTION_DATABASE_USERNAME": "polyglot_retention_login",
        "POLYGLOT_RUNTIME_DATABASE_PASSWORD": "contract-runtime-only",
        "POLYGLOT_RUNTIME_DATABASE_USERNAME": "polyglot_runtime_login",
    }


def test_compose_database_components_round_trip_reserved_password_characters() -> None:
    from polyglot.bootstrap import database

    configuration = render_compose(WORKLOAD_PASSWORDS)
    assert "x-polyglot-database-urls" not in configuration
    environment = configuration["x-polyglot-database-environment"]
    assert hasattr(database, "workload_database_url_from_environment")
    build_url = database.workload_database_url_from_environment

    expected_usernames = {
        "migration": "polyglot_migration_login",
        "runtime": "polyglot_runtime_login",
        "retention": "polyglot_retention_login",
    }
    for workload, password in WORKLOAD_PASSWORDS.items():
        parsed = make_url(build_url(workload, environment))
        assert parsed.username == expected_usernames[workload]
        assert parsed.password == password
        assert parsed.host == "127.0.0.1"
        assert parsed.port == 55432
        assert parsed.database == "polyglot"
