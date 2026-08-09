from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch


async def test_runtime_readiness_checks_postgres_and_filesystem(
    database_url: str,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    from polyglot.interfaces.http.app import create_runtime_app

    object_storage_path = tmp_path / "objects"
    monkeypatch.setenv("POLYGLOT_DATABASE_URL", database_url)
    monkeypatch.setenv("POLYGLOT_OBJECT_STORAGE_PATH", str(object_storage_path))
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
