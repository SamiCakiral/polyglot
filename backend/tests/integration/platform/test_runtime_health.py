from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch


def test_database_environment_urls_are_closed_by_workload(
    monkeypatch: MonkeyPatch,
) -> None:
    from polyglot.bootstrap.database import (
        database_url_from_environment,
        retention_database_url_from_environment,
    )

    monkeypatch.setenv("POLYGLOT_DATABASE_URL", "postgresql+asyncpg://runtime")
    monkeypatch.setenv(
        "POLYGLOT_RETENTION_DATABASE_URL",
        "postgresql+asyncpg://retention",
    )

    assert database_url_from_environment() == "postgresql+asyncpg://runtime"
    assert retention_database_url_from_environment() == "postgresql+asyncpg://retention"


async def test_runtime_readiness_checks_postgres_and_filesystem(
    database_url: str,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    from polyglot.interfaces.http.app import create_runtime_app

    object_storage_path = tmp_path / "objects"
    monkeypatch.setenv("POLYGLOT_DATABASE_URL", database_url)
    monkeypatch.setenv("POLYGLOT_OBJECT_STORAGE_PATH", str(object_storage_path))
    monkeypatch.setenv("POLYGLOT_SESSION_SECRET", "runtime-health-fixture-key-32-bytes")
    monkeypatch.setenv(
        "POLYGLOT_MEDIA_SIGNING_SECRET", "runtime-media-signing-fixture-key-32-bytes"
    )
    monkeypatch.setenv("POLYGLOT_ALLOWED_ORIGIN", "https://polyglot.test")
    app: FastAPI = create_runtime_app()

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ready", "object_storage": "ready"},
    }
    assert object_storage_path.is_dir()
