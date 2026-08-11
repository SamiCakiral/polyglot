from __future__ import annotations

import json
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.generation.providers import ChatRequest, ChatResult
from polyglot.modules.teacher.persistence import SqlTeacherService
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.ids import Uuid7Generator
from tests.integration.curriculum.conftest import (
    ACCOUNT_ID,
    PROFILE_ID,
    seed_curriculum_dependencies,
)


class FakeTeacherProvider:
    code = "lm_studio"
    model = "qwen/qwen3.6-35b-a3b"

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    async def complete(self, request: ChatRequest) -> ChatResult:
        self.calls += 1
        assert request.model == self.model
        assert len(request.messages) == 2
        return ChatResult(self.response, 120, 40)


class UnavailableTeacherProvider(FakeTeacherProvider):
    async def complete(self, request: ChatRequest) -> ChatResult:
        self.calls += 1
        raise DomainError(ErrorCode.PROVIDER_UNAVAILABLE, retryable=False)


def new_id() -> UUID:
    return Uuid7Generator().new()


async def seed_profile(session: AsyncSession) -> None:
    await seed_curriculum_dependencies(session)
    await session.commit()


@pytest.mark.asyncio
async def test_teacher_history_actions_idempotence_and_compensation(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_profile(migration_session)
    provider = FakeTeacherProvider(
        json.dumps(
            {
                "reply": "Vorrei rend la demande plus polie.",
                "actions": [
                    {
                        "type": "create_learning_debt",
                        "payload": {"target": "vorrei", "reason": "à consolider"},
                    }
                ],
            }
        )
    )
    service = SqlTeacherService(runtime_factory, provider)
    conversation_id = new_id()
    created = await service.create_conversation(
        ACCOUNT_ID,
        PROFILE_ID,
        conversation_id,
        "Question de grammaire",
        idempotency_key="teacher-create",
    )

    answered = await service.send_message(
        ACCOUNT_ID,
        conversation_id,
        new_id(),
        "Comment demander poliment ?",
        {"route": "/today", "exercise_family": "grammar_toolbox"},
        expected_version=created.version,
        idempotency_key="teacher-send",
    )
    replayed = await service.send_message(
        ACCOUNT_ID,
        conversation_id,
        answered.messages[0].message_id,
        "Comment demander poliment ?",
        {"route": "/today", "exercise_family": "grammar_toolbox"},
        expected_version=created.version,
        idempotency_key="teacher-send",
    )

    assert provider.calls == 1
    assert len(answered.messages) == 2
    assert replayed == answered
    action = answered.messages[-1].actions[0]
    reverted = await service.revert_action(
        ACCOUNT_ID,
        action.action_id,
        expected_version=action.version,
        idempotency_key="teacher-revert",
    )
    assert reverted.status == "reverted"
    assert reverted.version == 2
    await migration_session.execute(
        text("SELECT set_config('app.user_id',:actor,true)"),
        {"actor": str(ACCOUNT_ID)},
    )
    event_types = tuple(
        (
            await migration_session.execute(
                text(
                    "SELECT event_type FROM teacher.action_events "
                    "WHERE action_id=:action ORDER BY occurred_at"
                ),
                {"action": action.action_id},
            )
        ).scalars()
    )
    assert event_types == ("teacher_action_applied", "teacher_action_reverted")


@pytest.mark.asyncio
async def test_teacher_provider_failure_is_visible_and_never_retried(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_profile(migration_session)
    provider = UnavailableTeacherProvider("")
    service = SqlTeacherService(runtime_factory, provider)
    conversation = await service.create_conversation(
        ACCOUNT_ID,
        PROFILE_ID,
        new_id(),
        "Panne locale",
        idempotency_key="teacher-failure-create",
    )

    with pytest.raises(DomainError) as unavailable:
        await service.send_message(
            ACCOUNT_ID,
            conversation.conversation_id,
            new_id(),
            "Explique-moi vorrei.",
            {"route": "/practice"},
            expected_version=conversation.version,
            idempotency_key="teacher-failure-send",
        )

    assert unavailable.value.code is ErrorCode.PROVIDER_UNAVAILABLE
    assert provider.calls == 1
    await migration_session.execute(
        text("SELECT set_config('app.user_id',:actor,true)"),
        {"actor": str(ACCOUNT_ID)},
    )
    receipt_status = await migration_session.scalar(
        text(
            "SELECT status FROM teacher.command_receipts "
            "WHERE command_type='teacher.send_message'"
        )
    )
    assert receipt_status == "failed"
