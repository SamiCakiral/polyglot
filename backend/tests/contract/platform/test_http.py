from pathlib import Path
from uuid import UUID

from httpx import ASGITransport, AsyncClient


class ReadinessStub:
    def __init__(self, name: str, result: bool) -> None:
        self.name = name
        self.result = result

    async def check(self) -> bool:
        return self.result


async def get(app: object, path: str, headers: dict[str, str] | None = None) -> object:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.get(path, headers=headers)


async def request(app: object, method: str, path: str) -> object:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path)


async def test_liveness_returns_a_generated_correlation_id() -> None:
    from polyglot.interfaces.http.app import create_app

    response = await get(create_app(test_mode=True), "/api/v1/health/live")

    correlation_id = UUID(response.headers["X-Correlation-ID"])
    assert response.status_code == 200
    assert correlation_id.version == 7
    assert response.json() == {"status": "ok"}


async def test_valid_correlation_id_is_preserved_in_problem_details() -> None:
    from polyglot.interfaces.http.app import create_app

    correlation_id = "019fe680-5d40-7001-8203-040506070809"
    response = await get(
        create_app(test_mode=True),
        "/api/v1/does-not-exist",
        headers={"X-Correlation-ID": correlation_id},
    )

    problem = response.json()
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["X-Correlation-ID"] == correlation_id
    assert problem["type"] == "https://polyglot.example/problems/not-found"
    assert problem["status"] == 404
    assert problem["code"] == "not_found"
    assert problem["message_key"] == "errors.not_found"
    assert problem["instance"] == "/api/v1/does-not-exist"
    assert problem["correlation_id"] == correlation_id
    assert UUID(problem["request_id"]).version == 7


async def test_invalid_correlation_id_is_replaced() -> None:
    from polyglot.interfaces.http.app import create_app

    response = await get(
        create_app(test_mode=True),
        "/api/v1/does-not-exist",
        headers={"X-Correlation-ID": "not-an-id"},
    )

    generated = response.headers["X-Correlation-ID"]
    assert generated != "not-an-id"
    assert UUID(generated).version == 7
    assert response.json()["correlation_id"] == generated


async def test_readiness_reports_each_required_local_dependency() -> None:
    from polyglot.interfaces.http.app import create_app

    checks = (
        ReadinessStub("database", True),
        ReadinessStub("object_storage", True),
    )
    response = await get(create_app(readiness_checks=checks), "/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ready", "object_storage": "ready"},
    }


async def test_readiness_is_unavailable_when_the_filesystem_placeholder_is_missing() -> None:
    from polyglot.interfaces.http.app import create_app

    checks = (
        ReadinessStub("database", True),
        ReadinessStub("object_storage", False),
    )
    response = await get(create_app(readiness_checks=checks), "/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "ready", "object_storage": "unavailable"},
    }


async def test_filesystem_object_storage_placeholder_has_an_explicit_health_check(
    tmp_path: Path,
) -> None:
    from polyglot.bootstrap.object_storage import FilesystemObjectStorageProbe

    path = tmp_path / "objects"
    probe = FilesystemObjectStorageProbe(path)

    assert await probe.check() is False
    probe.prepare()
    assert await probe.check() is True


async def test_domain_validation_and_unexpected_errors_use_problem_details() -> None:
    from polyglot.interfaces.http.app import create_app
    from polyglot.platform.errors import DomainError, ErrorCode

    app = create_app(test_mode=True)

    @app.get("/api/v1/test/domain", include_in_schema=False)
    async def domain_failure() -> None:
        raise DomainError(ErrorCode.RATE_LIMITED)

    @app.get("/api/v1/test/validation", include_in_schema=False)
    async def validation_failure(count: int) -> None:
        del count

    @app.get("/api/v1/test/unexpected", include_in_schema=False)
    async def unexpected_failure() -> None:
        raise RuntimeError("private stack detail")

    cases = [
        ("GET", "/api/v1/test/domain", 429, "rate_limited"),
        ("GET", "/api/v1/test/validation?count=bad", 422, "validation_failed"),
        ("GET", "/api/v1/test/unexpected", 500, "internal_error"),
    ]
    for method, path, status, code in cases:
        response = await request(app, method, path)
        problem = response.json()
        assert response.status_code == status
        assert response.headers["content-type"] == "application/problem+json"
        assert problem["status"] == status
        assert problem["code"] == code
        assert problem["message_key"] == f"errors.{code}"
        assert problem["correlation_id"] == response.headers["X-Correlation-ID"]
        assert "private stack detail" not in str(problem)


async def test_method_not_allowed_preserves_405_in_a_closed_problem_mapping() -> None:
    from polyglot.interfaces.http.app import create_app

    response = await request(
        create_app(test_mode=True),
        "POST",
        "/api/v1/health/live",
    )

    assert response.status_code == 405
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == 405
    assert response.json()["code"] == "validation_failed"


def test_generic_app_factory_requires_readiness_checks_outside_test_mode() -> None:
    from polyglot.interfaces.http.app import create_app

    try:
        create_app()
    except ValueError as error:
        assert str(error) == "readiness checks are required outside test mode"
    else:
        raise AssertionError("create_app accepted an empty production readiness set")
