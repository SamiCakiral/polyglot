from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from polyglot.platform.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class TeacherActionView:
    action_id: UUID
    action_type: str
    status: str
    payload: dict[str, JsonValue]
    version: int
    applied_at: datetime
    reverted_at: datetime | None


@dataclass(frozen=True, slots=True)
class TeacherMessageView:
    message_id: UUID
    role: str
    content: str
    provider_code: str | None
    model_code: str | None
    created_at: datetime
    actions: tuple[TeacherActionView, ...]


@dataclass(frozen=True, slots=True)
class TeacherConversationView:
    conversation_id: UUID
    profile_id: UUID
    title: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    messages: tuple[TeacherMessageView, ...]


class TeacherService(Protocol):
    async def create_conversation(
        self,
        actor_id: UUID,
        profile_id: UUID,
        conversation_id: UUID,
        title: str,
        *,
        idempotency_key: str,
    ) -> TeacherConversationView: ...

    async def list_conversations(
        self, actor_id: UUID, profile_id: UUID
    ) -> tuple[TeacherConversationView, ...]: ...

    async def get_conversation(
        self, actor_id: UUID, conversation_id: UUID
    ) -> TeacherConversationView: ...

    async def send_message(
        self,
        actor_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        content: str,
        page_context: dict[str, JsonValue],
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> TeacherConversationView: ...

    async def revert_action(
        self,
        actor_id: UUID,
        action_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> TeacherActionView: ...
