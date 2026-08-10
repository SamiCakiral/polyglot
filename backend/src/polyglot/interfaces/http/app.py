import os
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.types import Lifespan

from polyglot.bootstrap.database import (
    create_database_engine,
    create_session_factory,
    database_is_ready,
    database_url_from_environment,
)
from polyglot.bootstrap.object_storage import FilesystemObjectStorageProbe
from polyglot.interfaces.http.dependencies import ReadinessCheck, valid_correlation_id
from polyglot.interfaces.http.errors import register_error_handlers
from polyglot.interfaces.http.routes.identity import identity_router
from polyglot.modules.identity.application import IdentityApplicationService
from polyglot.modules.identity.domain import FakeOidcProvider, SessionSecrets
from polyglot.platform.ids import IdGenerator, Uuid7Generator


class LiveStatus(BaseModel):
    status: Literal["ok"]


class ReadyStatus(BaseModel):
    status: Literal["ready", "unavailable"]
    checks: dict[str, Literal["ready", "unavailable"]]


class DatabaseReadinessProbe:
    name = "database"

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def check(self) -> bool:
        return await database_is_ready(self._engine)


def _enabled_from_environment(name: str) -> bool:
    raw = os.environ.get(name, "true").lower()
    if raw not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return raw == "true"


def create_app(
    *,
    id_generator: IdGenerator | None = None,
    readiness_checks: Sequence[ReadinessCheck] = (),
    lifespan: Lifespan[FastAPI] | None = None,
    test_mode: bool = False,
    identity_service: IdentityApplicationService | None = None,
    allowed_origin: str = "https://polyglot.test",
) -> FastAPI:
    if not readiness_checks and not test_mode:
        raise ValueError("readiness checks are required outside test mode")
    generator = id_generator or Uuid7Generator()
    app = FastAPI(
        title="Polyglot V2 API",
        version="0.1.0",
        openapi_version="3.1.0",
        lifespan=lifespan,
    )
    register_error_handlers(app)
    app.include_router(
        identity_router(identity_service, allowed_origin=allowed_origin),
    )

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = valid_correlation_id(request.headers.get("X-Correlation-ID"))
        request.state.correlation_id = correlation_id or str(generator.new())
        request.state.request_id = str(generator.new())
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.get(
        "/api/v1/health/live",
        operation_id="health_live",
        response_model=LiveStatus,
    )
    async def health_live() -> LiveStatus:
        return LiveStatus(status="ok")

    @app.get(
        "/api/v1/health/ready",
        operation_id="health_ready",
        response_model=ReadyStatus,
        responses={503: {"model": ReadyStatus}},
    )
    async def health_ready() -> ReadyStatus | JSONResponse:
        results: dict[str, Literal["ready", "unavailable"]] = {}
        for check in readiness_checks:
            try:
                available = await check.check()
            except Exception:
                available = False
            results[check.name] = "ready" if available else "unavailable"
        if all(result == "ready" for result in results.values()):
            return ReadyStatus(status="ready", checks=results)
        payload = ReadyStatus(status="unavailable", checks=results)
        return JSONResponse(status_code=503, content=payload.model_dump())

    return app


def create_runtime_app() -> FastAPI:
    engine = create_database_engine(database_url_from_environment())
    session_factory = create_session_factory(engine)
    identity_service = IdentityApplicationService(
        session_factory,
        session_secrets=SessionSecrets.from_key(
            os.environ["POLYGLOT_SESSION_SECRET"].encode()
        ),
        oidc_provider=FakeOidcProvider({}),
        registration_enabled=_enabled_from_environment("POLYGLOT_REGISTRATION_ENABLED"),
        oidc_enabled=_enabled_from_environment("POLYGLOT_OIDC_ENABLED"),
    )
    object_storage = FilesystemObjectStorageProbe(
        Path(os.environ.get("POLYGLOT_OBJECT_STORAGE_PATH", ".local/object-storage"))
    )
    object_storage.prepare()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    return create_app(
        readiness_checks=(DatabaseReadinessProbe(engine), object_storage),
        lifespan=lifespan,
        identity_service=identity_service,
        allowed_origin=os.environ["POLYGLOT_ALLOWED_ORIGIN"],
    )
