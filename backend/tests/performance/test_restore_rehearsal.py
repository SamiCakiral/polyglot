"""Black-box checks for the W19L local restore rehearsal."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "restore-rehearsal.sh"
FIXTURE = ROOT / "fixtures" / "canonical" / "FX-OPS"


def run_rehearsal(
    *args: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    values = os.environ.copy()
    if environment is not None:
        values.update(environment)
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=ROOT,
        env=values,
        text=True,
        capture_output=True,
        check=False,
    )


def object_directories(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source-objects"
    target = tmp_path / "target-objects"
    shutil.copytree(FIXTURE / "objects", source)
    target.mkdir()
    return source, target


def report_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_help_describes_required_connection_inputs() -> None:
    result = run_rehearsal("--help")

    assert result.returncode == 0
    assert "--source-dsn" in result.stdout
    assert "--target-dsn" in result.stdout
    assert "--fixture FX-OPS" in result.stdout


def test_rejects_identical_source_and_target_before_running_tools(tmp_path: Path) -> None:
    source_objects, target_objects = object_directories(tmp_path)
    report = tmp_path / "same-target.json"
    dsn = "postgresql://fixture@127.0.0.1:55432/polyglot"

    result = run_rehearsal(
        "--fixture",
        "FX-OPS",
        "--source-dsn",
        dsn,
        "--target-dsn",
        dsn,
        "--source-objects",
        str(source_objects),
        "--target-objects",
        str(target_objects),
        "--report",
        str(report),
    )

    payload = report_payload(report)
    assert result.returncode != 0
    assert payload["status"] == "FAIL"
    assert any(
        check["name"] == "source_target_distinct" and check["status"] == "FAIL"
        for check in payload["checks"]
    )


def test_rejects_equivalent_source_and_target_database_with_different_dsn_text(
    tmp_path: Path,
) -> None:
    source_objects, target_objects = object_directories(tmp_path)
    report = tmp_path / "equivalent-target.json"

    result = run_rehearsal(
        "--fixture",
        "FX-OPS",
        "--source-dsn",
        "postgresql://source-operator@127.0.0.1:55432/polyglot",
        "--target-dsn",
        "postgres://target-operator@127.0.0.1:55432/polyglot",
        "--source-objects",
        str(source_objects),
        "--target-objects",
        str(target_objects),
        "--report",
        str(report),
        "--pg-dump-bin",
        "missing-w19-pg-dump",
    )

    payload = report_payload(report)
    assert result.returncode != 0
    assert payload["status"] == "FAIL"
    assert any(
        check["name"] == "source_target_distinct" and check["status"] == "FAIL"
        for check in payload["checks"]
    )


def test_failure_report_redacts_dsn_credentials(tmp_path: Path) -> None:
    source_objects, target_objects = object_directories(tmp_path)
    report = tmp_path / "redacted.json"
    secret_sentinel = "not-a-real-secret-but-must-be-redacted"

    result = run_rehearsal(
        "--fixture",
        "FX-OPS",
        "--source-dsn",
        f"postgresql://fixture:{secret_sentinel}@127.0.0.1:55432/source",
        "--target-dsn",
        "postgresql://fixture@127.0.0.1:55433/target",
        "--source-objects",
        str(source_objects),
        "--target-objects",
        str(target_objects),
        "--report",
        str(report),
        "--pg-dump-bin",
        "missing-w19-pg-dump",
    )

    rendered_report = report.read_text(encoding="utf-8")
    payload = report_payload(report)
    assert result.returncode != 0
    assert payload["status"] == "PARTIAL"
    assert secret_sentinel not in rendered_report
    assert secret_sentinel not in result.stdout
    assert secret_sentinel not in result.stderr


def test_real_rehearsal_restores_fixture_into_disposable_database_and_object_directory(
    tmp_path: Path,
) -> None:
    if os.environ.get("W19_REAL_TEST") != "1":
        pytest.skip("set W19_REAL_TEST=1 to run disposable PostgreSQL rehearsal")
    if shutil.which("docker") is None or shutil.which("uv") is None:
        pytest.skip("Docker and uv are required for the disposable PostgreSQL rehearsal")

    source_name = f"w19-source-{os.getpid()}-{time.time_ns()}"
    target_name = f"w19-target-{os.getpid()}-{time.time_ns()}"
    source_objects, target_objects = object_directories(tmp_path)
    work_root = tmp_path / "work"
    work_root.mkdir()
    source = start_postgres(source_name, work_root)
    target = start_postgres(target_name, work_root)
    try:
        create_migration_roles(source[0])
        migrate_source_database(source[1])
        seed_fixture(source[0])
        wrappers = create_postgres_tool_wrappers(
            tmp_path,
            source_name,
            target_name,
            source[1],
            target[1],
            work_root,
        )
        report = tmp_path / "successful-rehearsal.json"

        result = run_rehearsal(
            "--fixture",
            "FX-OPS",
            "--source-dsn",
            source[1],
            "--target-dsn",
            target[1],
            "--source-objects",
            str(source_objects),
            "--target-objects",
            str(target_objects),
            "--report",
            str(report),
            environment={
                "TMPDIR": str(work_root),
                "PG_DUMP_BIN": str(wrappers / "pg_dump"),
                "PG_RESTORE_BIN": str(wrappers / "pg_restore"),
                "PSQL_BIN": str(wrappers / "psql"),
            },
        )

        payload = report_payload(report)
        assert result.returncode == 0, result.stderr
        assert payload["status"] == "PASS"
        target_object = target_objects / "private" / "fx-ops-private-object.txt"
        source_object = source_objects / "private" / "fx-ops-private-object.txt"
        assert target_object.read_text(encoding="utf-8") == source_object.read_text(
            encoding="utf-8"
        )
        assert all(check["status"] == "PASS" for check in payload["checks"])
    finally:
        subprocess.run(["docker", "rm", "--force", source_name, target_name], check=False)


def start_postgres(name: str, work_root: Path) -> tuple[str, str]:
    subprocess.run(
        [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--name",
            name,
            "--volume",
            f"{work_root}:/work",
            "--publish",
            "127.0.0.1::5432",
            "--env",
            "POSTGRES_DB=polyglot",
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "postgres:17-alpine@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    for _ in range(60):
        ready = subprocess.run(
            [
                "docker",
                "exec",
                name,
                "pg_isready",
                "--username",
                "postgres",
                "--dbname",
                "polyglot",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if ready.returncode == 0:
            port_output = subprocess.check_output(
                ["docker", "port", name, "5432/tcp"], text=True
            ).strip()
            port = port_output.rsplit(":", 1)[1]
            dsn = f"postgresql://postgres@127.0.0.1:{port}/polyglot"
            return name, dsn
        time.sleep(0.5)
    raise AssertionError(f"PostgreSQL container {name} did not become ready")


def create_migration_roles(container: str) -> None:
    for role in ("polyglot_migration", "polyglot_runtime", "polyglot_retention"):
        subprocess.run(
            [
                "docker",
                "exec",
                container,
                "psql",
                "--username",
                "postgres",
                "--dbname",
                "polyglot",
                "--command",
                f"CREATE ROLE {role}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )


def migrate_source_database(dsn: str) -> None:
    environment = os.environ.copy()
    environment["POLYGLOT_MIGRATION_DATABASE_URL"] = dsn.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def seed_fixture(container: str) -> None:
    with (FIXTURE / "seed.sql").open("rb") as seed:
        subprocess.run(
            [
                "docker",
                "exec",
                "--interactive",
                container,
                "psql",
                "--username",
                "postgres",
                "--dbname",
                "polyglot",
                "--set",
                "ON_ERROR_STOP=1",
            ],
            stdin=seed,
            check=True,
            capture_output=True,
        )


def create_postgres_tool_wrappers(
    tmp_path: Path,
    source_name: str,
    target_name: str,
    source_dsn: str,
    target_dsn: str,
    work_root: Path,
) -> Path:
    wrappers = tmp_path / "bin"
    wrappers.mkdir()
    source_port = source_dsn.rsplit(":", 1)[1].split("/", 1)[0]
    target_port = target_dsn.rsplit(":", 1)[1].split("/", 1)[0]
    common = f"""#!/usr/bin/env bash
set -euo pipefail
source_port={source_port!r}
target_port={target_port!r}
source_name={source_name!r}
target_name={target_name!r}
work_root={str(work_root)!r}
translate_path() {{
  printf '/work/%s' "${{1#"$work_root"/}}"
}}
"""
    (wrappers / "pg_dump").write_text(
        common
        + """
arguments=()
for argument in "$@"; do
  case "$argument" in
    --file="$work_root"/*) arguments+=("--file=$(translate_path "${argument#--file=}")") ;;
    *":$source_port/"*) arguments+=("postgresql://postgres@localhost/polyglot") ;;
    *) arguments+=("$argument") ;;
  esac
done
exec docker exec "$source_name" pg_dump "${arguments[@]}"
""",
        encoding="utf-8",
    )
    (wrappers / "pg_restore").write_text(
        common
        + """
arguments=()
for argument in "$@"; do
  case "$argument" in
    "$work_root"/*) arguments+=("$(translate_path "$argument")") ;;
    *":$target_port/"*) arguments+=("postgresql://postgres@localhost/polyglot") ;;
    *) arguments+=("$argument") ;;
  esac
done
exec docker exec "$target_name" pg_restore "${arguments[@]}"
""",
        encoding="utf-8",
    )
    (wrappers / "psql").write_text(
        common
        + """
container=""
arguments=()
local_dsn="postgresql://postgres@localhost/polyglot"
if [[ "$1" == "--version" ]]; then
  exec docker exec "$source_name" psql "$@"
fi
for argument in "$@"; do
  case "$argument" in
    *":$source_port/"*) container="$source_name"; arguments+=("$local_dsn") ;;
    *":$target_port/"*) container="$target_name"; arguments+=("$local_dsn") ;;
    *) arguments+=("$argument") ;;
  esac
done
test -n "$container"
exec docker exec "$container" psql "${arguments[@]}"
""",
        encoding="utf-8",
    )
    for wrapper in wrappers.iterdir():
        wrapper.chmod(0o755)
    return wrappers
