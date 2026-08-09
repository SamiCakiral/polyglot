import os
import subprocess
import sys
import zipfile
from pathlib import Path


def test_installed_wheel_contains_contracts_and_runs_its_own_migrations(
    tmp_path: Path,
    database_url: str,
) -> None:
    backend = Path(__file__).resolve().parents[3]
    distribution = tmp_path / "dist"
    build = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(distribution)],
        cwd=backend,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    wheel = next(distribution.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    assert {
        "polyglot/migrations/alembic.ini",
        "polyglot/migrations/env.py",
        "polyglot/migrations/versions/0001_platform.py",
        "polyglot/platform/contracts/envelope.schema.json",
        "polyglot/platform/contracts/event-catalogue.yaml",
    } <= names

    target = tmp_path / "installed"
    install = subprocess.run(
        ["uv", "pip", "install", "--target", str(target), "--no-deps", str(wheel)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert install.returncode == 0, install.stdout + install.stderr
    environment = {
        **os.environ,
        "POLYGLOT_DATABASE_URL": database_url,
        "PYTHONPATH": str(target),
    }
    smoke = subprocess.run(
        [
            sys.executable,
            "-m",
            "polyglot.bootstrap.migrations",
            "round-trip",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
