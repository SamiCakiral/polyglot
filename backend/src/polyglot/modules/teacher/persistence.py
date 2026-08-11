# ruff: noqa: E501
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.generation.providers import ChatProvider, ChatRequest
from polyglot.modules.teacher.application import (
    TeacherActionView,
    TeacherConversationView,
    TeacherMessageView,
)
from polyglot.modules.teacher.orchestration import parse_teacher_reply, teacher_system_prompt
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.json_types import JsonValue


class SqlTeacherService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        provider: ChatProvider,
        *,
        ids: IdGenerator | None = None,
    ) -> None:
        self._sessions = session_factory
        self._provider = provider
        self._ids = ids or Uuid7Generator()

    async def create_conversation(
        self,
        actor_id: UUID,
        profile_id: UUID,
        conversation_id: UUID,
        title: str,
        *,
        idempotency_key: str,
    ) -> TeacherConversationView:
        title = title.strip()
        if not title or len(title) > 160:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        fingerprint = canonical_json_fingerprint(
            {"profile_id": str(profile_id), "conversation_id": str(conversation_id), "title": title}
        )
        now = datetime.now(UTC)
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            await self._assert_owner(session, actor_id, profile_id)
            replay = await self._reserve(
                session,
                actor_id,
                "teacher.create_conversation",
                idempotency_key,
                fingerprint,
                now,
            )
            if replay is not None:
                view = await self._read_conversation(session, replay)
                if view is None:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return view
            await session.execute(
                text(
                    "INSERT INTO teacher.conversations "
                    "(conversation_id,profile_id,title,status,version,created_at,updated_at) "
                    "VALUES (:id,:profile,:title,'active',1,:now,:now)"
                ),
                {"id": conversation_id, "profile": profile_id, "title": title, "now": now},
            )
            await self._complete_receipt(
                session,
                actor_id,
                "teacher.create_conversation",
                idempotency_key,
                conversation_id,
                now,
            )
            await session.commit()
            view = await self._read_owned(actor_id, conversation_id)
            if view is None:
                raise DomainError(ErrorCode.INTERNAL_ERROR)
            return view

    async def list_conversations(
        self, actor_id: UUID, profile_id: UUID
    ) -> tuple[TeacherConversationView, ...]:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            await self._assert_owner(session, actor_id, profile_id)
            ids = tuple(
                cast(
                    UUID,
                    value,
                )
                for value in (
                    await session.execute(
                        text(
                            "SELECT conversation_id FROM teacher.conversations "
                            "WHERE profile_id=:profile ORDER BY updated_at DESC LIMIT 50"
                        ),
                        {"profile": profile_id},
                    )
                ).scalars()
            )
            views = [await self._read_conversation(session, value) for value in ids]
            return tuple(value for value in views if value is not None)

    async def get_conversation(
        self, actor_id: UUID, conversation_id: UUID
    ) -> TeacherConversationView:
        view = await self._read_owned(actor_id, conversation_id)
        if view is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        return view

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
    ) -> TeacherConversationView:
        content = content.strip()
        if not content or len(content) > 6000 or len(json.dumps(page_context).encode()) > 8000:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        fingerprint = canonical_json_fingerprint(
            {
                "conversation_id": str(conversation_id),
                "message_id": str(message_id),
                "content": content,
                "page_context": page_context,
                "expected_version": expected_version,
            }
        )
        now = datetime.now(UTC)
        context_snapshot: dict[str, JsonValue]
        prompt_payload: dict[str, JsonValue]
        profile_id: UUID
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            conversation = (
                (
                    await session.execute(
                        text(
                            "SELECT conversation_id,profile_id,version FROM teacher.conversations "
                            "WHERE conversation_id=:id AND status='active' FOR UPDATE"
                        ),
                        {"id": conversation_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if conversation is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            profile_id = UUID(str(conversation["profile_id"]))
            replay = await self._reserve(
                session,
                actor_id,
                "teacher.send_message",
                idempotency_key,
                fingerprint,
                now,
            )
            if replay is not None:
                view = await self._read_conversation(session, conversation_id)
                if view is None:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return view
            if int(conversation["version"]) != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            context_snapshot = await self._context_snapshot(
                session, actor_id, profile_id, page_context
            )
            history = await self._recent_history(session, conversation_id)
            prompt_payload = {
                "context": context_snapshot,
                "recent_messages": history,
                "learner_message": content,
            }
            await session.execute(
                text(
                    "INSERT INTO teacher.messages "
                    "(message_id,conversation_id,profile_id,role,content,provider_code,model_code,"
                    "input_tokens,output_tokens,context_snapshot,created_at) VALUES "
                    "(:message,:conversation,:profile,'user',:content,NULL,NULL,0,0,CAST(:context AS jsonb),:now)"
                ),
                {
                    "message": message_id,
                    "conversation": conversation_id,
                    "profile": profile_id,
                    "content": content,
                    "context": json.dumps(context_snapshot, ensure_ascii=False),
                    "now": now,
                },
            )
            await session.execute(
                text(
                    "UPDATE teacher.conversations SET version=version+1,updated_at=:now "
                    "WHERE conversation_id=:id"
                ),
                {"id": conversation_id, "now": now},
            )
            await session.commit()

        try:
            result = await self._provider.complete(
                ChatRequest(
                    model=self._provider.model,
                    messages=(
                        ("system", teacher_system_prompt()),
                        (
                            "user",
                            json.dumps(prompt_payload, ensure_ascii=False, separators=(",", ":")),
                        ),
                    ),
                    max_output_tokens=4096,
                )
            )
            parsed = parse_teacher_reply(result.message)
        except Exception:
            await self._fail_receipt(
                actor_id, "teacher.send_message", idempotency_key, datetime.now(UTC)
            )
            raise

        assistant_id = self._ids.new()
        completed_at = datetime.now(UTC)
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            await session.execute(
                text(
                    "INSERT INTO teacher.messages "
                    "(message_id,conversation_id,profile_id,role,content,provider_code,model_code,"
                    "input_tokens,output_tokens,context_snapshot,created_at) VALUES "
                    "(:message,:conversation,:profile,'assistant',:content,:provider,:model,:input,:output,"
                    "CAST(:context AS jsonb),:now)"
                ),
                {
                    "message": assistant_id,
                    "conversation": conversation_id,
                    "profile": profile_id,
                    "content": parsed.reply,
                    "provider": self._provider.code,
                    "model": self._provider.model,
                    "input": result.input_tokens,
                    "output": result.output_tokens,
                    "context": json.dumps(context_snapshot, ensure_ascii=False),
                    "now": completed_at,
                },
            )
            for proposed in parsed.actions:
                action_id = self._ids.new()
                inverse = {"action_id": str(action_id), "operation": "revert"}
                await session.execute(
                    text(
                        "INSERT INTO teacher.actions "
                        "(action_id,conversation_id,message_id,profile_id,action_type,status,payload,"
                        "inverse_payload,version,applied_at) VALUES "
                        "(:action,:conversation,:message,:profile,:type,'applied',CAST(:payload AS jsonb),"
                        "CAST(:inverse AS jsonb),1,:now)"
                    ),
                    {
                        "action": action_id,
                        "conversation": conversation_id,
                        "message": assistant_id,
                        "profile": profile_id,
                        "type": proposed.action_type,
                        "payload": json.dumps(proposed.payload, ensure_ascii=False),
                        "inverse": json.dumps(inverse),
                        "now": completed_at,
                    },
                )
                await self._insert_action_event(
                    session,
                    action_id,
                    conversation_id,
                    profile_id,
                    "teacher_action_applied",
                    proposed.payload,
                    completed_at,
                )
            await self._complete_receipt(
                session,
                actor_id,
                "teacher.send_message",
                idempotency_key,
                assistant_id,
                completed_at,
            )
            await session.commit()
        view = await self._read_owned(actor_id, conversation_id)
        if view is None:
            raise DomainError(ErrorCode.INTERNAL_ERROR)
        return view

    async def revert_action(
        self,
        actor_id: UUID,
        action_id: UUID,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> TeacherActionView:
        fingerprint = canonical_json_fingerprint(
            {"action_id": str(action_id), "expected_version": expected_version}
        )
        now = datetime.now(UTC)
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            row = (
                (
                    await session.execute(
                        text("SELECT * FROM teacher.actions WHERE action_id=:id FOR UPDATE"),
                        {"id": action_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if int(row["version"]) != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if str(row["status"]) != "applied":
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            replay = await self._reserve(
                session,
                actor_id,
                "teacher.revert_action",
                idempotency_key,
                fingerprint,
                now,
            )
            if replay is None:
                await session.execute(
                    text(
                        "UPDATE teacher.actions SET status='reverted',reverted_at=:now,version=version+1 "
                        "WHERE action_id=:id"
                    ),
                    {"id": action_id, "now": now},
                )
                await self._insert_action_event(
                    session,
                    action_id,
                    UUID(str(row["conversation_id"])),
                    UUID(str(row["profile_id"])),
                    "teacher_action_reverted",
                    cast(dict[str, JsonValue], row["inverse_payload"]),
                    now,
                )
                await self._complete_receipt(
                    session,
                    actor_id,
                    "teacher.revert_action",
                    idempotency_key,
                    action_id,
                    now,
                )
                await session.commit()
                await self._set_actor(session, actor_id)
            updated = (
                (
                    await session.execute(
                        text("SELECT * FROM teacher.actions WHERE action_id=:id"), {"id": action_id}
                    )
                )
                .mappings()
                .one()
            )
            return self._action_view(updated)

    async def _read_owned(
        self, actor_id: UUID, conversation_id: UUID
    ) -> TeacherConversationView | None:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            return await self._read_conversation(session, conversation_id)

    async def _read_conversation(
        self, session: AsyncSession, conversation_id: UUID
    ) -> TeacherConversationView | None:
        row = (
            (
                await session.execute(
                    text("SELECT * FROM teacher.conversations WHERE conversation_id=:id"),
                    {"id": conversation_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        message_rows = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM teacher.messages WHERE conversation_id=:id "
                        "ORDER BY created_at,message_id LIMIT 200"
                    ),
                    {"id": conversation_id},
                )
            )
            .mappings()
            .all()
        )
        action_rows = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM teacher.actions WHERE conversation_id=:id "
                        "ORDER BY applied_at,action_id"
                    ),
                    {"id": conversation_id},
                )
            )
            .mappings()
            .all()
        )
        actions_by_message: dict[UUID, list[TeacherActionView]] = {}
        for action in action_rows:
            actions_by_message.setdefault(UUID(str(action["message_id"])), []).append(
                self._action_view(action)
            )
        messages = tuple(
            TeacherMessageView(
                message_id=UUID(str(message["message_id"])),
                role=str(message["role"]),
                content=str(message["content"]),
                provider_code=(
                    None if message["provider_code"] is None else str(message["provider_code"])
                ),
                model_code=(None if message["model_code"] is None else str(message["model_code"])),
                created_at=cast(datetime, message["created_at"]),
                actions=tuple(actions_by_message.get(UUID(str(message["message_id"])), [])),
            )
            for message in message_rows
        )
        return TeacherConversationView(
            conversation_id=UUID(str(row["conversation_id"])),
            profile_id=UUID(str(row["profile_id"])),
            title=str(row["title"]),
            status=str(row["status"]),
            version=int(row["version"]),
            created_at=cast(datetime, row["created_at"]),
            updated_at=cast(datetime, row["updated_at"]),
            messages=messages,
        )

    async def _context_snapshot(
        self,
        session: AsyncSession,
        actor_id: UUID,
        profile_id: UUID,
        page_context: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        profile = (
            (
                await session.execute(
                    text(
                        "SELECT target.language_tag AS target_language,support.language_tag AS support_language,"
                        "profile.goals,profile.interests,onboarding.detected_band "
                        "FROM language_profiles.learner_language_profiles profile "
                        "JOIN catalogue.language_varieties target ON target.variety_id=profile.target_variety_id "
                        "JOIN catalogue.language_varieties support ON support.variety_id=profile.native_variety_id "
                        "LEFT JOIN language_profiles.onboarding_states onboarding USING(profile_id) "
                        "WHERE profile.profile_id=:profile AND profile.account_id=:actor"
                    ),
                    {"profile": profile_id, "actor": actor_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if profile is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        known = (
            (
                await session.execute(
                    text(
                        "SELECT variety.language_tag,language.relationship,language.self_assessed_band "
                        "FROM identity.account_languages language JOIN catalogue.language_varieties variety "
                        "ON variety.variety_id=language.variety_id WHERE language.account_id=:actor "
                        "AND language.archived_at IS NULL ORDER BY language.relationship,variety.language_tag"
                    ),
                    {"actor": actor_id},
                )
            )
            .mappings()
            .all()
        )
        module_code = await session.scalar(
            text(
                "SELECT module.module_code FROM curriculum.module_enrollments enrollment "
                "JOIN curriculum.module_revisions revision USING(module_revision_id) "
                "JOIN curriculum.learning_modules module USING(module_id) "
                "WHERE enrollment.profile_id=:profile AND enrollment.status='active' LIMIT 1"
            ),
            {"profile": profile_id},
        )
        known_payload: list[JsonValue] = [
            {
                "language_tag": str(item["language_tag"]),
                "relationship": str(item["relationship"]),
                "band": str(item["self_assessed_band"]),
            }
            for item in known
        ]
        return {
            "profile_id": str(profile_id),
            "target_language": str(profile["target_language"]),
            "support_language": str(profile["support_language"]),
            "known_languages": known_payload,
            "detected_band": None
            if profile["detected_band"] is None
            else str(profile["detected_band"]),
            "goals": cast(list[JsonValue], profile["goals"]),
            "interests": cast(list[JsonValue], profile["interests"]),
            "active_module": None if module_code is None else str(module_code),
            "page": page_context,
        }

    @staticmethod
    async def _recent_history(session: AsyncSession, conversation_id: UUID) -> list[JsonValue]:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT role,content FROM teacher.messages WHERE conversation_id=:id "
                        "ORDER BY created_at DESC,message_id DESC LIMIT 12"
                    ),
                    {"id": conversation_id},
                )
            )
            .mappings()
            .all()
        )
        return [
            {"role": str(row["role"]), "content": str(row["content"])[:3000]}
            for row in reversed(rows)
        ]

    async def _reserve(
        self,
        session: AsyncSession,
        actor_id: UUID,
        command_type: str,
        idempotency_key: str,
        fingerprint: str,
        now: datetime,
    ) -> UUID | None:
        inserted = await session.scalar(
            text(
                "INSERT INTO teacher.command_receipts "
                "(receipt_id,actor_id,command_type,idempotency_key,request_fingerprint,status,created_at) "
                "VALUES (:receipt,:actor,:type,:key,:fingerprint,'started',:now) "
                "ON CONFLICT (actor_id,command_type,idempotency_key) DO NOTHING RETURNING receipt_id"
            ),
            {
                "receipt": self._ids.new(),
                "actor": actor_id,
                "type": command_type,
                "key": idempotency_key,
                "fingerprint": fingerprint,
                "now": now,
            },
        )
        if inserted is not None:
            return None
        row = (
            (
                await session.execute(
                    text(
                        "SELECT request_fingerprint,status,result_id FROM teacher.command_receipts "
                        "WHERE actor_id=:actor AND command_type=:type AND idempotency_key=:key"
                    ),
                    {"actor": actor_id, "type": command_type, "key": idempotency_key},
                )
            )
            .mappings()
            .one()
        )
        if row["request_fingerprint"] != fingerprint or row["status"] != "succeeded":
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return UUID(str(row["result_id"]))

    @staticmethod
    async def _complete_receipt(
        session: AsyncSession,
        actor_id: UUID,
        command_type: str,
        idempotency_key: str,
        result_id: UUID,
        now: datetime,
    ) -> None:
        await session.execute(
            text(
                "UPDATE teacher.command_receipts SET status='succeeded',result_id=:result,"
                "completed_at=:now WHERE actor_id=:actor AND command_type=:type AND idempotency_key=:key"
            ),
            {
                "result": result_id,
                "now": now,
                "actor": actor_id,
                "type": command_type,
                "key": idempotency_key,
            },
        )

    async def _fail_receipt(
        self, actor_id: UUID, command_type: str, idempotency_key: str, now: datetime
    ) -> None:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            await session.execute(
                text(
                    "UPDATE teacher.command_receipts SET status='failed',completed_at=:now "
                    "WHERE actor_id=:actor AND command_type=:type AND idempotency_key=:key"
                ),
                {"now": now, "actor": actor_id, "type": command_type, "key": idempotency_key},
            )
            await session.commit()

    async def _insert_action_event(
        self,
        session: AsyncSession,
        action_id: UUID,
        conversation_id: UUID,
        profile_id: UUID,
        event_type: str,
        payload: dict[str, JsonValue],
        now: datetime,
    ) -> None:
        await session.execute(
            text(
                "INSERT INTO teacher.action_events "
                "(event_id,action_id,conversation_id,profile_id,event_type,payload,occurred_at) "
                "VALUES (:event,:action,:conversation,:profile,:type,CAST(:payload AS jsonb),:now)"
            ),
            {
                "event": self._ids.new(),
                "action": action_id,
                "conversation": conversation_id,
                "profile": profile_id,
                "type": event_type,
                "payload": json.dumps(payload, ensure_ascii=False),
                "now": now,
            },
        )

    @staticmethod
    async def _set_actor(session: AsyncSession, actor_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"), {"actor": str(actor_id)}
        )

    @staticmethod
    async def _assert_owner(session: AsyncSession, actor_id: UUID, profile_id: UUID) -> None:
        owned = await session.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM language_profiles.learner_language_profiles "
                "WHERE profile_id=:profile AND account_id=:actor AND status <> 'deleted')"
            ),
            {"profile": profile_id, "actor": actor_id},
        )
        if owned is not True:
            raise DomainError(ErrorCode.NOT_FOUND)

    @staticmethod
    def _action_view(row: RowMapping) -> TeacherActionView:
        return TeacherActionView(
            action_id=UUID(str(row["action_id"])),
            action_type=str(row["action_type"]),
            status=str(row["status"]),
            payload=cast(dict[str, JsonValue], row["payload"]),
            version=int(row["version"]),
            applied_at=cast(datetime, row["applied_at"]),
            reverted_at=cast(datetime | None, row["reverted_at"]),
        )
