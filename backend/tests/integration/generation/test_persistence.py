import json
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.interfaces.tools.deterministic import DeterministicToolHandlers
from polyglot.interfaces.tools.executor import ToolExecutor, ToolInvocation, ToolScope
from polyglot.modules.generation.application import RequestGenerationJob
from polyglot.modules.generation.persistence import SqlGenerationService
from polyglot.modules.generation.providers import ChatRequest, ChatResult
from polyglot.platform.errors import DomainError, ErrorCode

from .conftest import NOW


class Sequence:
    def __init__(self) -> None:
        self.value = 100

    def id(self) -> UUID:
        self.value += 1
        return UUID(f"019fec20-0000-7000-8000-{self.value:012x}")

    def new(self) -> UUID:
        return self.id()

    def now(self) -> datetime:
        self.value += 1
        return NOW + timedelta(milliseconds=self.value)


def service(factory: async_sessionmaker[AsyncSession]) -> SqlGenerationService:
    sequence = Sequence()
    return SqlGenerationService(
        factory,
        ToolExecutor(
            DeterministicToolHandlers(sequence.id).handlers(),
            now=sequence.now,
            provenance_id=sequence.id,
        ),
        clock=sequence,
        id_generator=sequence,
    )


class FakeProvider:
    code = "lm_studio"
    model = "qwen/qwen3.6-35b-a3b"

    def __init__(self, *, unavailable: bool = False) -> None:
        self.calls = 0
        self.unavailable = unavailable

    async def complete(self, request: ChatRequest) -> ChatResult:
        self.calls += 1
        if self.unavailable:
            raise DomainError(ErrorCode.PROVIDER_UNAVAILABLE, retryable=False)
        return ChatResult(
            json.dumps(
                {
                    "tool_name": "quality.report_ambiguity",
                    "tool_version": "1.0.0",
                    "input": {
                        "resource_ref": "exercise:treno",
                        "resource_revision_id": "it-v1",
                        "ambiguity_type": "wording",
                        "location": "prompt",
                        "description": "La consigne admet deux lectures.",
                        "candidate_interpretations": ["train", "entraînement"],
                    },
                }
            ),
            120,
            80,
        )


def draft_invocation(actor_id: UUID, sequence: Sequence | None = None) -> ToolInvocation:
    ids = sequence or Sequence()
    return ToolInvocation(
        "exercise.submit_draft",
        "1.0.0",
        ids.id(),
        actor_id,
        "author",
        ToolScope(),
        "tool-draft-1",
        None,
        {
            "pack_revision_id": "p",
            "primitive_id": "cloze",
            "blueprint_version": "1",
            "stimulus": {},
            "response_contract": {},
            "target_bindings": [],
            "accepted_answers_or_rubric": [],
            "hints": [],
            "difficulty_profile": {},
            "provenance_inputs": [],
        },
        ids.id(),
        None,
        {"security": "v1"},
    )


async def test_job_request_replays_and_cancels_once(
    runtime_factory: async_sessionmaker[AsyncSession], seeded_account: UUID
) -> None:
    app = service(runtime_factory)
    command = RequestGenerationJob(
        "exercise_draft",
        {"topic": "treno"},
        ("exercise.get_blueprint@1.0.0", "exercise.submit_draft@1.0.0"),
        "lm_studio",
        "qwen/qwen3.6-35b-a3b",
        "PROMPT_V1",
        1,
        1000,
        1000,
        100,
    )
    created = await app.request_job(seeded_account, command, idempotency_key="job-1")
    replay = await app.request_job(seeded_account, command, idempotency_key="job-1")
    assert replay.job_id == created.job_id

    cancelled = await app.cancel_job(
        seeded_account,
        created.job_id,
        expected_version=created.version,
        idempotency_key="cancel-1",
    )
    cancel_replay = await app.cancel_job(
        seeded_account,
        created.job_id,
        expected_version=created.version,
        idempotency_key="cancel-1",
    )
    assert cancelled.status == "cancelled"
    assert cancel_replay.version == cancelled.version


async def test_job_request_rejects_provider_or_model_substitution(
    runtime_factory: async_sessionmaker[AsyncSession], seeded_account: UUID
) -> None:
    app = service(runtime_factory)
    for provider, model in (
        ("remote", "qwen/qwen3.6-35b-a3b"),
        ("lm_studio", "another-model"),
    ):
        with pytest.raises(DomainError) as caught:
            await app.request_job(
                seeded_account,
                RequestGenerationJob(
                    "quality_report",
                    {"topic": "treno"},
                    ("quality.report_ambiguity@1.0.0",),
                    provider,
                    model,
                    "PROMPT_V1",
                    1,
                    1000,
                    1000,
                    100,
                ),
                idempotency_key=f"invalid-{provider}-{model}",
            )
        assert caught.value.code is ErrorCode.PROVIDER_UNAVAILABLE


async def test_tool_invocation_is_idempotent_and_only_persists_a_draft(
    runtime_factory: async_sessionmaker[AsyncSession], seeded_account: UUID
) -> None:
    app = service(runtime_factory)
    invocation = draft_invocation(seeded_account)
    result = await app.invoke_tool(invocation)
    replays = [await app.invoke_tool(invocation) for _ in range(100)]
    artifacts = await app.list_artifacts(seeded_account)

    assert all(replay.output == result.output for replay in replays)
    assert len(artifacts) == 1
    assert artifacts[0].status == "draft"
    assert artifacts[0].artifact_type == "exercise"
    assert "publish" not in artifacts[0].payload

    conflicting = ToolInvocation(
        invocation.tool_name,
        invocation.tool_version,
        UUID("019fec20-0000-7000-8000-000000009999"),
        invocation.actor_id,
        invocation.actor_role,
        invocation.scope,
        invocation.idempotency_key,
        invocation.expected_version,
        {**invocation.input, "primitive_id": "translation"},
        invocation.correlation_id,
        invocation.causation_id,
        invocation.policy_revisions,
    )
    with pytest.raises(DomainError) as caught:
        await app.invoke_tool(conflicting)
    assert caught.value.code is ErrorCode.IDEMPOTENCY_CONFLICT


async def test_worker_generates_one_controlled_artifact(
    runtime_factory: async_sessionmaker[AsyncSession], seeded_account: UUID
) -> None:
    app = service(runtime_factory)
    provider = FakeProvider()
    created = await app.request_job(
        seeded_account,
        RequestGenerationJob(
            "quality_report",
            {"topic": "treno"},
            ("quality.report_ambiguity@1.0.0",),
            provider.code,
            provider.model,
            "PROMPT_V1",
            1,
            1000,
            1000,
            100,
        ),
        idempotency_key="generated-quality-1",
    )

    processed = await app.process_next_job(provider)
    assert processed is not None
    assert processed.job_id == created.job_id
    assert processed.status == "succeeded"
    assert processed.attempt_count == 1
    assert processed.result_draft_id is not None
    assert provider.calls == 1
    artifacts = await app.list_artifacts(seeded_account)
    assert len(artifacts) == 1
    assert artifacts[0].artifact_type == "quality_report"


async def test_worker_records_provider_failure_without_retry(
    runtime_factory: async_sessionmaker[AsyncSession], seeded_account: UUID
) -> None:
    app = service(runtime_factory)
    provider = FakeProvider(unavailable=True)
    created = await app.request_job(
        seeded_account,
        RequestGenerationJob(
            "quality_report",
            {"topic": "treno"},
            ("quality.report_ambiguity@1.0.0",),
            provider.code,
            provider.model,
            "PROMPT_V1",
            1,
            1000,
            1000,
            100,
        ),
        idempotency_key="failed-quality-1",
    )

    failed = await app.process_next_job(provider)
    assert failed is not None
    assert failed.job_id == created.job_id
    assert failed.status == "failed"
    assert failed.error_code == "provider_unavailable"
    assert failed.attempt_count == 1
    assert await app.process_next_job(provider) is None
    assert provider.calls == 1
