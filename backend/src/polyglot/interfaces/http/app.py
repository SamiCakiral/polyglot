import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager, suppress
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
from polyglot.interfaces.http.routes.account_languages import account_languages_router
from polyglot.interfaces.http.routes.assessments import assessments_router
from polyglot.interfaces.http.routes.catalogue import catalogue_router
from polyglot.interfaces.http.routes.content import content_router
from polyglot.interfaces.http.routes.curriculum import curriculum_router
from polyglot.interfaces.http.routes.exchange import ExchangeService, exchange_router
from polyglot.interfaces.http.routes.exercises import exercises_router
from polyglot.interfaces.http.routes.generation import generation_router
from polyglot.interfaces.http.routes.identity import identity_router
from polyglot.interfaces.http.routes.language_profiles import language_profiles_router
from polyglot.interfaces.http.routes.media import media_router
from polyglot.interfaces.http.routes.memory import MemoryService, memory_router
from polyglot.interfaces.http.routes.onboarding import onboarding_router
from polyglot.interfaces.http.routes.progress import ProgressService, progress_router
from polyglot.interfaces.http.routes.sprints import sprints_router
from polyglot.interfaces.http.routes.word_bank import (
    SqlWordBankService,
    WordBankService,
    word_bank_router,
)
from polyglot.modules.assessments.application import AssessmentApplicationService
from polyglot.modules.catalogue.core.service import CatalogueApplicationService, CatalogueReader
from polyglot.modules.content.application import ContentApplicationService
from polyglot.modules.curriculum.application import CurriculumApplicationService
from polyglot.modules.exercises.core.application import ExerciseApplicationService
from polyglot.modules.generation.application import GenerationApplicationService
from polyglot.modules.identity.application import IdentityApplicationService
from polyglot.modules.identity.domain import FakeOidcProvider, SessionSecrets
from polyglot.modules.identity.language_persistence import AccountLanguageApplicationService
from polyglot.modules.language_profiles.application import LanguageProfileApplicationService
from polyglot.modules.language_profiles.onboarding_persistence import OnboardingApplicationService
from polyglot.modules.media.application import MediaApplicationService
from polyglot.modules.sprints.application import SprintApplicationService
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.observability import configure_local_logging


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
    account_language_service: AccountLanguageApplicationService | None = None,
    language_profile_service: LanguageProfileApplicationService | None = None,
    onboarding_service: OnboardingApplicationService | None = None,
    catalogue_service: CatalogueReader | None = None,
    content_service: ContentApplicationService | None = None,
    word_bank_service: WordBankService | None = None,
    memory_service: MemoryService | None = None,
    exchange_service: ExchangeService | None = None,
    exercise_service: ExerciseApplicationService | None = None,
    curriculum_service: CurriculumApplicationService | None = None,
    sprint_service: SprintApplicationService | None = None,
    progress_service: ProgressService | None = None,
    assessment_service: AssessmentApplicationService | None = None,
    media_service: MediaApplicationService | None = None,
    generation_service: GenerationApplicationService | None = None,
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
    app.include_router(catalogue_router(catalogue_service))
    app.include_router(
        content_router(
            content_service,
            identity_service,
            allowed_origin=allowed_origin,
        )
    )
    app.include_router(
        identity_router(identity_service, allowed_origin=allowed_origin),
    )
    app.include_router(
        account_languages_router(
            account_language_service,
            identity_service,
            allowed_origin=allowed_origin,
        )
    )
    app.include_router(
        language_profiles_router(
            language_profile_service,
            identity_service,
            allowed_origin=allowed_origin,
        )
    )
    app.include_router(
        onboarding_router(
            onboarding_service,
            identity_service,
            allowed_origin=allowed_origin,
        )
    )
    app.include_router(
        word_bank_router(
            word_bank_service,
            identity_service,
            allowed_origin=allowed_origin,
        )
    )
    app.include_router(
        memory_router(
            memory_service,
            identity_service,
            allowed_origin=allowed_origin,
        )
    )
    app.include_router(
        exchange_router(
            exchange_service,
            identity_service,
            allowed_origin=allowed_origin,
        )
    )
    app.include_router(
        exercises_router(
            exercise_service,
            identity_service,
            allowed_origin=allowed_origin,
        )
    )
    app.include_router(
        curriculum_router(
            curriculum_service,
            identity_service,
            allowed_origin=allowed_origin,
        )
    )
    app.include_router(
        sprints_router(
            sprint_service,
            identity_service,
            allowed_origin=allowed_origin,
        )
    )
    app.include_router(progress_router(progress_service, identity_service))
    app.include_router(
        assessments_router(
            assessment_service,
            identity_service,
            allowed_origin=allowed_origin,
        )
    )
    app.include_router(
        media_router(
            media_service,
            identity_service,
            allowed_origin=allowed_origin,
        )
    )
    app.include_router(
        generation_router(
            generation_service,
            identity_service,
            allowed_origin=allowed_origin,
        )
    )
    http_logger = logging.getLogger("polyglot.http")

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = time.perf_counter()
        correlation_id = valid_correlation_id(request.headers.get("X-Correlation-ID"))
        request.state.correlation_id = correlation_id or str(generator.new())
        request.state.request_id = str(generator.new())
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        response.headers["X-Request-ID"] = request.state.request_id
        http_logger.info(
            "request_completed",
            extra={
                "request_id": request.state.request_id,
                "correlation_id": request.state.correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )
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
    configure_local_logging()
    logger = logging.getLogger("polyglot.generation")
    engine = create_database_engine(database_url_from_environment())
    session_factory = create_session_factory(engine)
    identity_service = IdentityApplicationService(
        session_factory,
        session_secrets=SessionSecrets.from_key(os.environ["POLYGLOT_SESSION_SECRET"].encode()),
        oidc_provider=FakeOidcProvider({}),
        registration_enabled=_enabled_from_environment("POLYGLOT_REGISTRATION_ENABLED"),
        oidc_enabled=_enabled_from_environment("POLYGLOT_OIDC_ENABLED"),
    )
    account_language_service = AccountLanguageApplicationService(session_factory)
    catalogue_service = CatalogueApplicationService(session_factory)
    content_service = ContentApplicationService(session_factory)
    language_profile_service = LanguageProfileApplicationService(
        session_factory, catalogue_reader=catalogue_service
    )
    onboarding_service = OnboardingApplicationService(session_factory)
    word_bank_service = SqlWordBankService(session_factory)
    from polyglot.modules.lexicon.memory.persistence import SqlMemoryService
    from polyglot.modules.lexicon.memory.providers.fsrs_v6 import FsrsV6Scheduler

    memory_service = SqlMemoryService(session_factory, FsrsV6Scheduler())
    from polyglot.interfaces.tasks.dispatcher import LocalOutboxDispatcher
    from polyglot.interfaces.tasks.progress import LocalLearningEventPublisher
    from polyglot.interfaces.tools.deterministic import DeterministicToolHandlers
    from polyglot.interfaces.tools.executor import ToolExecutor
    from polyglot.modules.assessments.persistence import SqlAssessmentService
    from polyglot.modules.curriculum.persistence import SqlCurriculumService
    from polyglot.modules.exercises.core.persistence import SqlExerciseService
    from polyglot.modules.generation.persistence import SqlGenerationService
    from polyglot.modules.generation.providers import LmStudioChatProvider
    from polyglot.modules.lexicon.exchange.persistence import SqlExchangeService
    from polyglot.modules.media.persistence import SqlMediaService
    from polyglot.modules.media.ports import MacOSTtsPort, TtsAvailability, TtsVoice
    from polyglot.modules.media.storage import FilesystemObjectStorage, LocalSignedUrlSigner
    from polyglot.modules.progress.application import SqlProgressQueryService
    from polyglot.modules.progress.persistence import SqlProgressRepository
    from polyglot.modules.sprints.persistence import SqlSprintService
    from polyglot.platform.clock import SystemClock

    exchange_service = SqlExchangeService(session_factory)
    exercise_service = SqlExerciseService(session_factory)
    curriculum_service = SqlCurriculumService(session_factory)
    sprint_service = SqlSprintService(session_factory)
    progress_service = SqlProgressQueryService(session_factory)
    progress_dispatcher = LocalOutboxDispatcher(
        session_factory=session_factory,
        publisher=LocalLearningEventPublisher(
            session_factory,
            SqlProgressRepository(session_factory),
        ),
        clock=SystemClock(),
        worker_id="polyglot-local-progress",
        destination="learning-events",
    )
    assessment_service = SqlAssessmentService(session_factory)
    object_storage = FilesystemObjectStorageProbe(
        Path(os.environ.get("POLYGLOT_OBJECT_STORAGE_PATH", ".local/object-storage"))
    )
    object_storage.prepare()
    media_service = SqlMediaService(
        session_factory,
        FilesystemObjectStorage(object_storage.path),
        LocalSignedUrlSigner(os.environ["POLYGLOT_MEDIA_SIGNING_SECRET"].encode()),
        MacOSTtsPort(
            voices=(
                TtsVoice("Alice", "it-IT", TtsAvailability.AVAILABLE, "local-v1"),
                TtsVoice("Kyoko", "ja-JP", TtsAvailability.AVAILABLE, "local-v1"),
            ),
            cache_dir=object_storage.path / "tts-cache",
        ),
    )
    generation_ids = Uuid7Generator()
    generation_service = SqlGenerationService(
        session_factory,
        ToolExecutor(
            DeterministicToolHandlers(generation_ids.new).handlers(),
            now=SystemClock().now,
            provenance_id=generation_ids.new,
        ),
        id_generator=generation_ids,
    )
    generation_provider = LmStudioChatProvider(
        base_url=os.environ.get("POLYGLOT_LM_STUDIO_URL", "http://127.0.0.1:1234"),
        model="qwen/qwen3.6-35b-a3b",
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async def dispatch_progress() -> None:
            while True:
                await progress_dispatcher.run_once()
                await asyncio.sleep(0.5)

        async def dispatch_generation() -> None:
            while True:
                try:
                    await generation_service.process_next_job(generation_provider)
                except Exception:
                    logger.exception("generation worker cycle failed")
                await asyncio.sleep(1)

        progress_task = asyncio.create_task(dispatch_progress())
        generation_task = asyncio.create_task(dispatch_generation())
        try:
            yield
        finally:
            for task in (progress_task, generation_task):
                task.cancel()
            for task in (progress_task, generation_task):
                with suppress(asyncio.CancelledError):
                    await task
            await engine.dispose()

    return create_app(
        readiness_checks=(DatabaseReadinessProbe(engine), object_storage),
        lifespan=lifespan,
        identity_service=identity_service,
        account_language_service=account_language_service,
        catalogue_service=catalogue_service,
        content_service=content_service,
        language_profile_service=language_profile_service,
        onboarding_service=onboarding_service,
        word_bank_service=word_bank_service,
        memory_service=memory_service,
        exchange_service=exchange_service,
        exercise_service=exercise_service,
        curriculum_service=curriculum_service,
        sprint_service=sprint_service,
        progress_service=progress_service,
        assessment_service=assessment_service,
        media_service=media_service,
        generation_service=generation_service,
        allowed_origin=os.environ["POLYGLOT_ALLOWED_ORIGIN"],
    )
