from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.practice.application import (
    CreatePracticePreset,
    CreatePracticeStack,
    PracticePresetView,
    PracticeRunView,
    PracticeStackView,
    StackInjectionView,
)
from polyglot.modules.practice.domain import (
    PracticeDirection,
    PracticeMode,
    PracticeStackKind,
    StackMember,
    build_run_snapshot,
    combine_stack_members,
    practice_stack_checksum,
    validate_preset,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator


class SqlPracticeService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        ids: IdGenerator | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._ids = ids or Uuid7Generator()

    async def _set_actor(self, session: AsyncSession, actor_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"),
            {"actor": str(actor_id)},
        )

    async def _assert_owner(self, session: AsyncSession, actor_id: UUID, profile_id: UUID) -> None:
        owned = await session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles "
                "WHERE profile_id=:profile AND account_id=:actor AND status <> 'deleted')"
            ),
            {"profile": profile_id, "actor": actor_id},
        )
        if owned is not True:
            raise DomainError(ErrorCode.NOT_FOUND)

    async def _replay(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        command_type: str,
        idempotency_key: str,
        fingerprint: str,
    ) -> UUID | None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
            {"scope": f"{actor_id}:{command_type}:{idempotency_key}"},
        )
        row = (
            (
                await session.execute(
                    text(
                        "SELECT request_fingerprint,status,result_ref "
                        "FROM platform.command_receipts "
                        "WHERE actor_id=:actor AND command_type=:command AND idempotency_key=:key"
                    ),
                    {"actor": actor_id, "command": command_type, "key": idempotency_key},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        if row["request_fingerprint"] != fingerprint or row["status"] != "succeeded":
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return UUID(str(row["result_ref"]))

    async def _record_command(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        profile_id: UUID,
        command_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        aggregate_version: int,
        idempotency_key: str,
        fingerprint: str,
        at: datetime,
        event_type: str,
    ) -> None:
        command_id = self._ids.new()
        await session.execute(
            text(
                "INSERT INTO platform.command_receipts "
                "(command_id,command_type,actor_id,aggregate_type,aggregate_id,idempotency_key,"
                "request_fingerprint,expected_version,received_at,result_ref,result_payload,"
                "status,expires_at) "
                "VALUES (:id,:command,:actor,:aggregate_type,:aggregate,:key,:fingerprint,NULL,:at,"
                ":aggregate,jsonb_build_object('resource_id',CAST(:resource AS text),"
                "'version',CAST(:version AS integer)),'succeeded',:expires)"
            ),
            {
                "id": command_id,
                "command": command_type,
                "actor": actor_id,
                "aggregate_type": aggregate_type,
                "aggregate": aggregate_id,
                "resource": str(aggregate_id),
                "key": idempotency_key,
                "fingerprint": fingerprint,
                "at": at,
                "version": aggregate_version,
                "expires": at + timedelta(days=30),
            },
        )
        event_id = self._ids.new()
        await session.execute(
            text(
                "INSERT INTO platform.domain_events "
                "(event_id,event_type,schema_version,aggregate_type,aggregate_id,aggregate_version,"
                "actor_type,actor_id,profile_id,occurred_at,recorded_at,correlation_id,causation_id,"
                "command_id,privacy_class,policy_versions,payload,expires_at,"
                "subject_type,subject_id) "
                "VALUES (:event,:event_type,1,:aggregate_type,:aggregate,:version,'account',:actor,"
                ":profile,:at,:at,:event,NULL,:command,'personal',CAST(:policies AS jsonb),"
                "CAST(:payload AS jsonb),:expires,'profile',:profile)"
            ),
            {
                "event": event_id,
                "event_type": event_type,
                "aggregate_type": aggregate_type,
                "aggregate": aggregate_id,
                "version": aggregate_version,
                "actor": actor_id,
                "profile": profile_id,
                "at": at,
                "command": command_id,
                "policies": json.dumps({"practice": "v1"}),
                "payload": json.dumps({"resource_id": str(aggregate_id)}),
                "expires": at + timedelta(days=3650),
            },
        )
        await session.execute(
            text(
                "INSERT INTO platform.outbox_messages "
                "(outbox_id,event_id,destination,created_at,attempt_count) "
                "VALUES (:outbox,:event,'learning-events',:at,0)"
            ),
            {"outbox": self._ids.new(), "event": event_id, "at": at},
        )

    async def _validate_pack(
        self, session: AsyncSession, profile_id: UUID, pack_revision_id: UUID
    ) -> None:
        valid = await session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles profile "
                "JOIN catalogue.language_pack_revisions revision "
                "ON revision.pack_revision_id=:pack "
                "WHERE profile.profile_id=:profile "
                "AND profile.target_variety_id=revision.target_variety_id)"
            ),
            {"profile": profile_id, "pack": pack_revision_id},
        )
        if valid is not True:
            raise DomainError(ErrorCode.VALIDATION_FAILED)

    async def _validate_members(
        self,
        session: AsyncSession,
        pack_revision_id: UUID,
        members: tuple[StackMember, ...],
    ) -> None:
        if not members:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        valid_count = await session.scalar(
            text(
                "SELECT count(*) FROM unnest(CAST(:senses AS uuid[]),"
                "CAST(:revisions AS uuid[])) pair(sense_id,sense_revision_id) "
                "JOIN catalogue.lexical_sense_revisions revision "
                "ON revision.sense_revision_id=pair.sense_revision_id "
                "AND revision.sense_id=pair.sense_id "
                "WHERE revision.pack_revision_id=:pack AND revision.status='published'"
            ),
            {
                "senses": [item.sense_id for item in members],
                "revisions": [item.sense_revision_id for item in members],
                "pack": pack_revision_id,
            },
        )
        if int(valid_count or 0) != len(members):
            raise DomainError(ErrorCode.VALIDATION_FAILED)

    async def _members_from_list_snapshot(
        self, session: AsyncSession, profile_id: UUID, snapshot_id: UUID
    ) -> tuple[UUID, tuple[StackMember, ...]]:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT sense_revision.pack_revision_id,sense_revision.sense_id,"
                        "sense_revision.sense_revision_id,unit_revision.lemma,sense_revision.definition,"
                        "member.role FROM lexicon.list_snapshot_members member "
                        "JOIN catalogue.lexical_sense_revisions sense_revision "
                        "ON sense_revision.sense_revision_id=member.sense_revision_id "
                        "JOIN catalogue.lexical_senses sense "
                        "ON sense.sense_id=sense_revision.sense_id "
                        "JOIN LATERAL (SELECT revision.lemma "
                        "FROM catalogue.lexical_unit_revisions revision "
                        "WHERE revision.lexical_unit_id=sense.lexical_unit_id "
                        "AND revision.pack_revision_id=sense_revision.pack_revision_id "
                        "ORDER BY revision.revision_no DESC LIMIT 1) unit_revision ON true "
                        "WHERE member.profile_id=:profile AND member.snapshot_id=:snapshot "
                        "ORDER BY member.position"
                    ),
                    {"profile": profile_id, "snapshot": snapshot_id},
                )
            )
            .mappings()
            .all()
        )
        packs = {UUID(str(row["pack_revision_id"])) for row in rows}
        if len(packs) != 1:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        members = tuple(
            StackMember(
                sense_id=UUID(str(row["sense_id"])),
                sense_revision_id=UUID(str(row["sense_revision_id"])),
                label=str(row["lemma"]),
                definition=str(row["definition"]),
                source_kind="list_snapshot",
                source_ref=f"list_snapshot:{snapshot_id}:{row['role']}",
            )
            for row in rows
        )
        return next(iter(packs)), members

    @staticmethod
    def _stack_fingerprint(
        profile_id: UUID, command: CreatePracticeStack, members: tuple[StackMember, ...]
    ) -> str:
        return canonical_json_fingerprint(
            {
                "profile_id": str(profile_id),
                "name": command.name,
                "stack_kind": command.stack_kind.value,
                "language_pack_revision_id": (
                    str(command.language_pack_revision_id)
                    if command.language_pack_revision_id
                    else None
                ),
                "pedagogical_day": (
                    command.pedagogical_day.isoformat() if command.pedagogical_day else None
                ),
                "source_list_snapshot_id": (
                    str(command.source_list_snapshot_id)
                    if command.source_list_snapshot_id
                    else None
                ),
                "source_refs": list(command.source_refs),
                "members": [
                    {
                        **asdict(item),
                        "sense_id": str(item.sense_id),
                        "sense_revision_id": str(item.sense_revision_id),
                    }
                    for item in members
                ],
                "created_at": command.created_at.isoformat(),
            }
        )

    async def _load_stack(self, session: AsyncSession, stack_id: UUID) -> PracticeStackView:
        row = (
            (
                await session.execute(
                    text("SELECT * FROM practice.practice_stacks WHERE stack_id=:id"),
                    {"id": stack_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        members = tuple(
            StackMember(
                sense_id=UUID(str(item["sense_id"])),
                sense_revision_id=UUID(str(item["sense_revision_id"])),
                label=str(item["label"]),
                definition=str(item["definition"]),
                source_kind=str(item["source_kind"]),
                source_ref=str(item["source_ref"]),
            )
            for item in (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM practice.practice_stack_members "
                            "WHERE stack_id=:id ORDER BY position"
                        ),
                        {"id": stack_id},
                    )
                )
                .mappings()
                .all()
            )
        )
        return PracticeStackView(
            stack_id=UUID(str(row["stack_id"])),
            profile_id=UUID(str(row["profile_id"])),
            language_pack_revision_id=UUID(str(row["language_pack_revision_id"])),
            name=str(row["name"]),
            stack_kind=PracticeStackKind(str(row["stack_kind"])),
            pedagogical_day=row["pedagogical_day"],
            source_refs=tuple(row["source_refs"]),
            checksum=str(row["checksum"]),
            created_at=row["created_at"],
            members=members,
        )

    async def _insert_stack(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        profile_id: UUID,
        command: CreatePracticeStack,
        pack_revision_id: UUID,
        members: tuple[StackMember, ...],
        fingerprint: str,
        idempotency_key: str,
    ) -> PracticeStackView:
        checksum = practice_stack_checksum(members, pack_revision_id=pack_revision_id)
        stack_id = self._ids.new()
        await session.execute(
            text(
                "INSERT INTO practice.practice_stacks "
                "(stack_id,profile_id,language_pack_revision_id,name,stack_kind,pedagogical_day,"
                "source_refs,member_count,checksum,created_at) VALUES "
                "(:id,:profile,:pack,:name,:kind,:day,CAST(:sources AS jsonb),"
                ":count,:checksum,:at)"
            ),
            {
                "id": stack_id,
                "profile": profile_id,
                "pack": pack_revision_id,
                "name": command.name.strip(),
                "kind": command.stack_kind.value,
                "day": command.pedagogical_day,
                "sources": json.dumps(list(command.source_refs)),
                "count": len(members),
                "checksum": checksum,
                "at": command.created_at,
            },
        )
        for position, member in enumerate(members, 1):
            await session.execute(
                text(
                    "INSERT INTO practice.practice_stack_members "
                    "(stack_member_id,stack_id,profile_id,sense_id,sense_revision_id,position,"
                    "label,definition,source_kind,source_ref) VALUES "
                    "(:id,:stack,:profile,:sense,:revision,:position,:label,:definition,:kind,:ref)"
                ),
                {
                    "id": self._ids.new(),
                    "stack": stack_id,
                    "profile": profile_id,
                    "sense": member.sense_id,
                    "revision": member.sense_revision_id,
                    "position": position,
                    "label": member.label,
                    "definition": member.definition,
                    "kind": member.source_kind,
                    "ref": member.source_ref,
                },
            )
        await self._record_command(
            session,
            actor_id=actor_id,
            profile_id=profile_id,
            command_type="CreatePracticeStack",
            aggregate_type="practice_stack",
            aggregate_id=stack_id,
            aggregate_version=1,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            at=command.created_at,
            event_type="practice.stack.created",
        )
        return await self._load_stack(session, stack_id)

    async def create_stack(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: CreatePracticeStack,
        *,
        idempotency_key: str,
    ) -> PracticeStackView:
        if command.created_at.tzinfo is None or not command.name.strip():
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._assert_owner(session, actor_id, profile_id)
            if command.source_list_snapshot_id is not None:
                if command.members:
                    raise DomainError(ErrorCode.VALIDATION_FAILED)
                pack_revision_id, members = await self._members_from_list_snapshot(
                    session, profile_id, command.source_list_snapshot_id
                )
            else:
                if command.language_pack_revision_id is None:
                    raise DomainError(ErrorCode.VALIDATION_FAILED)
                pack_revision_id = command.language_pack_revision_id
                members = command.members
            await self._validate_pack(session, profile_id, pack_revision_id)
            await self._validate_members(session, pack_revision_id, members)
            fingerprint = self._stack_fingerprint(profile_id, command, members)
            replay = await self._replay(
                session,
                actor_id=actor_id,
                command_type="CreatePracticeStack",
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
            )
            if replay is not None:
                return await self._load_stack(session, replay)
            return await self._insert_stack(
                session,
                actor_id=actor_id,
                profile_id=profile_id,
                command=command,
                pack_revision_id=pack_revision_id,
                members=members,
                fingerprint=fingerprint,
                idempotency_key=idempotency_key,
            )

    async def combine_stacks(
        self,
        actor_id: UUID,
        profile_id: UUID,
        *,
        stack_ids: tuple[UUID, ...],
        name: str,
        created_at: datetime,
        idempotency_key: str,
    ) -> PracticeStackView:
        if len(stack_ids) < 2 or len(set(stack_ids)) != len(stack_ids):
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._assert_owner(session, actor_id, profile_id)
            stacks = tuple([await self._load_stack(session, value) for value in stack_ids])
            if any(stack.profile_id != profile_id for stack in stacks):
                raise DomainError(ErrorCode.NOT_FOUND)
            packs = {stack.language_pack_revision_id for stack in stacks}
            if len(packs) != 1:
                raise DomainError(ErrorCode.VALIDATION_FAILED)
            members = combine_stack_members(tuple(stack.members for stack in stacks))
            command = CreatePracticeStack(
                name=name,
                stack_kind=PracticeStackKind.COMBINED,
                language_pack_revision_id=next(iter(packs)),
                pedagogical_day=None,
                source_list_snapshot_id=None,
                source_refs=tuple(f"practice_stack:{value}" for value in stack_ids),
                members=members,
                created_at=created_at,
            )
            fingerprint = self._stack_fingerprint(profile_id, command, members)
            replay = await self._replay(
                session,
                actor_id=actor_id,
                command_type="CreatePracticeStack",
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
            )
            if replay is not None:
                return await self._load_stack(session, replay)
            return await self._insert_stack(
                session,
                actor_id=actor_id,
                profile_id=profile_id,
                command=command,
                pack_revision_id=next(iter(packs)),
                members=members,
                fingerprint=fingerprint,
                idempotency_key=idempotency_key,
            )

    async def list_stacks(self, actor_id: UUID, profile_id: UUID) -> tuple[PracticeStackView, ...]:
        async with self._session_factory() as session:
            await self._set_actor(session, actor_id)
            await self._assert_owner(session, actor_id, profile_id)
            ids = tuple(
                (
                    await session.execute(
                        text(
                            "SELECT stack_id FROM practice.practice_stacks "
                            "WHERE profile_id=:profile ORDER BY pedagogical_day DESC NULLS LAST,"
                            "created_at DESC,stack_id DESC "
                            "LIMIT 100"
                        ),
                        {"profile": profile_id},
                    )
                ).scalars()
            )
            return tuple([await self._load_stack(session, UUID(str(value))) for value in ids])

    async def get_stack(self, actor_id: UUID, stack_id: UUID) -> PracticeStackView:
        async with self._session_factory() as session:
            await self._set_actor(session, actor_id)
            return await self._load_stack(session, stack_id)

    async def inject_stack(
        self,
        actor_id: UUID,
        stack_id: UUID,
        *,
        requested_at: datetime,
        idempotency_key: str,
    ) -> StackInjectionView:
        fingerprint = canonical_json_fingerprint(
            {"stack_id": str(stack_id), "requested_at": requested_at.isoformat()}
        )
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            stack = await self._load_stack(session, stack_id)
            replay = await self._replay(
                session,
                actor_id=actor_id,
                command_type="InjectPracticeStack",
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
            )
            if replay is not None:
                row = (
                    (
                        await session.execute(
                            text(
                                "SELECT * FROM practice.sprint_stack_injections "
                                "WHERE injection_id=:id"
                            ),
                            {"id": replay},
                        )
                    )
                    .mappings()
                    .one()
                )
                return self._injection_view(row)
            existing = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM practice.sprint_stack_injections "
                            "WHERE profile_id=:profile AND stack_id=:stack AND status='pending'"
                        ),
                        {"profile": stack.profile_id, "stack": stack_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                injection_id = UUID(str(existing["injection_id"]))
            else:
                injection_id = self._ids.new()
                await session.execute(
                    text(
                        "INSERT INTO practice.sprint_stack_injections "
                        "(injection_id,profile_id,stack_id,status,requested_at,version) "
                        "VALUES (:id,:profile,:stack,'pending',:at,1)"
                    ),
                    {
                        "id": injection_id,
                        "profile": stack.profile_id,
                        "stack": stack_id,
                        "at": requested_at,
                    },
                )
            await self._record_command(
                session,
                actor_id=actor_id,
                profile_id=stack.profile_id,
                command_type="InjectPracticeStack",
                aggregate_type="stack_injection",
                aggregate_id=injection_id,
                aggregate_version=1,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                at=requested_at,
                event_type="practice.stack.injected",
            )
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM practice.sprint_stack_injections WHERE injection_id=:id"
                        ),
                        {"id": injection_id},
                    )
                )
                .mappings()
                .one()
            )
            return self._injection_view(row)

    @staticmethod
    def _injection_view(row: Any) -> StackInjectionView:
        return StackInjectionView(
            injection_id=UUID(str(row["injection_id"])),
            profile_id=UUID(str(row["profile_id"])),
            stack_id=UUID(str(row["stack_id"])),
            status=str(row["status"]),
            version=int(row["version"]),
            requested_at=row["requested_at"],
        )

    async def _load_preset(self, session: AsyncSession, preset_id: UUID) -> PracticePresetView:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT preset.*,revision.preset_revision_id,revision.revision_no,"
                        "revision.name,revision.stack_ids,revision.direction,revision.mode,"
                        "revision.settings FROM practice.practice_presets preset "
                        "JOIN practice.practice_preset_revisions revision "
                        "ON revision.preset_revision_id=preset.current_revision_id "
                        "WHERE preset.preset_id=:id"
                    ),
                    {"id": preset_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        return PracticePresetView(
            preset_id=UUID(str(row["preset_id"])),
            profile_id=UUID(str(row["profile_id"])),
            preset_revision_id=UUID(str(row["preset_revision_id"])),
            revision_no=int(row["revision_no"]),
            name=str(row["name"]),
            stack_ids=tuple(UUID(str(value)) for value in row["stack_ids"]),
            direction=PracticeDirection(str(row["direction"])),
            mode=PracticeMode(str(row["mode"])),
            settings=dict(row["settings"]),
            status=str(row["status"]),
            version=int(row["version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def create_preset(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: CreatePracticePreset,
        *,
        idempotency_key: str,
    ) -> PracticePresetView:
        validate_preset(
            name=command.name,
            stack_ids=command.stack_ids,
            direction=command.direction,
            mode=command.mode,
        )
        fingerprint = canonical_json_fingerprint(
            {
                "profile_id": str(profile_id),
                "name": command.name,
                "stack_ids": [str(value) for value in command.stack_ids],
                "direction": command.direction.value,
                "mode": command.mode.value,
                "settings": command.settings,
                "created_at": command.created_at.isoformat(),
            }
        )
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._assert_owner(session, actor_id, profile_id)
            replay = await self._replay(
                session,
                actor_id=actor_id,
                command_type="CreatePracticePreset",
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
            )
            if replay is not None:
                return await self._load_preset(session, replay)
            stacks = tuple([await self._load_stack(session, value) for value in command.stack_ids])
            if any(stack.profile_id != profile_id for stack in stacks):
                raise DomainError(ErrorCode.NOT_FOUND)
            if len({stack.language_pack_revision_id for stack in stacks}) != 1:
                raise DomainError(ErrorCode.VALIDATION_FAILED)
            preset_id = self._ids.new()
            revision_id = self._ids.new()
            await session.execute(
                text(
                    "INSERT INTO practice.practice_presets "
                    "(preset_id,profile_id,status,version,created_at,updated_at) "
                    "VALUES (:id,:profile,'active',1,:at,:at)"
                ),
                {"id": preset_id, "profile": profile_id, "at": command.created_at},
            )
            await session.execute(
                text(
                    "INSERT INTO practice.practice_preset_revisions "
                    "(preset_revision_id,preset_id,profile_id,revision_no,name,stack_ids,direction,"
                    "mode,settings,created_at) VALUES "
                    "(:revision,:preset,:profile,1,:name,:stacks,:direction,:mode,"
                    "CAST(:settings AS jsonb),:at)"
                ),
                {
                    "revision": revision_id,
                    "preset": preset_id,
                    "profile": profile_id,
                    "name": command.name.strip(),
                    "stacks": list(command.stack_ids),
                    "direction": command.direction.value,
                    "mode": command.mode.value,
                    "settings": json.dumps(command.settings),
                    "at": command.created_at,
                },
            )
            await session.execute(
                text(
                    "UPDATE practice.practice_presets SET current_revision_id=:revision "
                    "WHERE preset_id=:preset"
                ),
                {"revision": revision_id, "preset": preset_id},
            )
            await self._record_command(
                session,
                actor_id=actor_id,
                profile_id=profile_id,
                command_type="CreatePracticePreset",
                aggregate_type="practice_preset",
                aggregate_id=preset_id,
                aggregate_version=1,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                at=command.created_at,
                event_type="practice.preset.created",
            )
            return await self._load_preset(session, preset_id)

    async def list_presets(
        self, actor_id: UUID, profile_id: UUID
    ) -> tuple[PracticePresetView, ...]:
        async with self._session_factory() as session:
            await self._set_actor(session, actor_id)
            await self._assert_owner(session, actor_id, profile_id)
            ids = tuple(
                (
                    await session.execute(
                        text(
                            "SELECT preset_id FROM practice.practice_presets "
                            "WHERE profile_id=:profile AND status='active' "
                            "ORDER BY updated_at DESC,preset_id DESC LIMIT 100"
                        ),
                        {"profile": profile_id},
                    )
                ).scalars()
            )
            return tuple([await self._load_preset(session, UUID(str(value))) for value in ids])

    async def _load_run(self, session: AsyncSession, run_id: UUID) -> PracticeRunView:
        row = (
            (
                await session.execute(
                    text("SELECT * FROM practice.practice_runs WHERE run_id=:id"),
                    {"id": run_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        snapshot = dict(row["run_snapshot"])
        current_item = None
        if int(row["current_position"]) < int(row["member_count"]):
            item = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM practice.practice_run_items "
                            "WHERE run_id=:run AND position=:position"
                        ),
                        {"run": run_id, "position": int(row["current_position"]) + 1},
                    )
                )
                .mappings()
                .one()
            )
            prompt = dict(item["prompt_snapshot"])
            current_item = StackMember(
                sense_id=UUID(str(item["sense_id"])),
                sense_revision_id=UUID(str(item["sense_revision_id"])),
                label=str(prompt["label"]),
                definition=str(prompt["definition"]),
                source_kind=str(prompt["source_kind"]),
                source_ref=str(prompt["source_ref"]),
            )
        return PracticeRunView(
            run_id=UUID(str(row["run_id"])),
            profile_id=UUID(str(row["profile_id"])),
            preset_id=UUID(str(row["preset_id"])),
            preset_revision_id=UUID(str(row["preset_revision_id"])),
            status=str(row["status"]),
            current_position=int(row["current_position"]),
            member_count=int(row["member_count"]),
            version=int(row["version"]),
            direction=PracticeDirection(str(snapshot["direction"])),
            mode=PracticeMode(str(snapshot["mode"])),
            current_item=current_item,
            started_at=row["started_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )

    async def start_run(
        self,
        actor_id: UUID,
        preset_id: UUID,
        *,
        started_at: datetime,
        idempotency_key: str,
    ) -> PracticeRunView:
        fingerprint = canonical_json_fingerprint(
            {"preset_id": str(preset_id), "started_at": started_at.isoformat()}
        )
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            preset = await self._load_preset(session, preset_id)
            replay = await self._replay(
                session,
                actor_id=actor_id,
                command_type="StartPracticeRun",
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
            )
            if replay is not None:
                return await self._load_run(session, replay)
            stacks = tuple([await self._load_stack(session, value) for value in preset.stack_ids])
            members = combine_stack_members(tuple(stack.members for stack in stacks))
            stack_kind = stacks[0].stack_kind if len(stacks) == 1 else PracticeStackKind.COMBINED
            pedagogical_day = stacks[0].pedagogical_day if len(stacks) == 1 else None
            snapshot = build_run_snapshot(
                preset_revision_id=preset.preset_revision_id,
                stack_ids=preset.stack_ids,
                stack_kind=stack_kind,
                pedagogical_day=pedagogical_day,
                direction=preset.direction,
                mode=preset.mode,
                members=members,
                started_at=started_at,
            )
            run_id = self._ids.new()
            snapshot_payload = {
                "schema_version": snapshot.schema_version,
                "preset_revision_id": str(snapshot.preset_revision_id),
                "stack_ids": [str(value) for value in snapshot.stack_ids],
                "stack_kind": snapshot.stack_kind.value,
                "pedagogical_day": (
                    snapshot.pedagogical_day.isoformat() if snapshot.pedagogical_day else None
                ),
                "direction": snapshot.direction.value,
                "mode": snapshot.mode.value,
                "member_count": snapshot.member_count,
                "started_at": snapshot.started_at.isoformat(),
            }
            await session.execute(
                text(
                    "INSERT INTO practice.practice_runs "
                    "(run_id,profile_id,preset_id,preset_revision_id,status,current_position,"
                    "member_count,version,run_snapshot,snapshot_fingerprint,started_at,updated_at) "
                    "VALUES (:id,:profile,:preset,:revision,'in_progress',0,:count,1,"
                    "CAST(:snapshot AS jsonb),:fingerprint,:at,:at)"
                ),
                {
                    "id": run_id,
                    "profile": preset.profile_id,
                    "preset": preset_id,
                    "revision": preset.preset_revision_id,
                    "count": snapshot.member_count,
                    "snapshot": json.dumps(snapshot_payload),
                    "fingerprint": snapshot.fingerprint,
                    "at": started_at,
                },
            )
            for position, member in enumerate(members, 1):
                await session.execute(
                    text(
                        "INSERT INTO practice.practice_run_items "
                        "(run_item_id,run_id,profile_id,sense_id,sense_revision_id,"
                        "position,prompt_snapshot) VALUES "
                        "(:id,:run,:profile,:sense,:revision,:position,CAST(:prompt AS jsonb))"
                    ),
                    {
                        "id": self._ids.new(),
                        "run": run_id,
                        "profile": preset.profile_id,
                        "sense": member.sense_id,
                        "revision": member.sense_revision_id,
                        "position": position,
                        "prompt": json.dumps(
                            {
                                "label": member.label,
                                "definition": member.definition,
                                "source_kind": member.source_kind,
                                "source_ref": member.source_ref,
                            }
                        ),
                    },
                )
            await self._record_command(
                session,
                actor_id=actor_id,
                profile_id=preset.profile_id,
                command_type="StartPracticeRun",
                aggregate_type="practice_run",
                aggregate_id=run_id,
                aggregate_version=1,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                at=started_at,
                event_type="practice.run.started",
            )
            return await self._load_run(session, run_id)

    async def get_run(self, actor_id: UUID, run_id: UUID) -> PracticeRunView:
        async with self._session_factory() as session:
            await self._set_actor(session, actor_id)
            return await self._load_run(session, run_id)

    async def _mutate_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        *,
        action: str,
        expected_version: int,
        changed_at: datetime,
        idempotency_key: str,
    ) -> PracticeRunView:
        fingerprint = canonical_json_fingerprint(
            {
                "run_id": str(run_id),
                "action": action,
                "expected_version": expected_version,
                "changed_at": changed_at.isoformat(),
            }
        )
        command_type = f"{action.title()}PracticeRun"
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            replay = await self._replay(
                session,
                actor_id=actor_id,
                command_type=command_type,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
            )
            if replay is not None:
                return await self._load_run(session, replay)
            row = (
                (
                    await session.execute(
                        text("SELECT * FROM practice.practice_runs WHERE run_id=:id FOR UPDATE"),
                        {"id": run_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if int(row["version"]) != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            status = str(row["status"])
            position = int(row["current_position"])
            member_count = int(row["member_count"])
            if action == "advance":
                if status != "in_progress" or position >= member_count:
                    raise DomainError(ErrorCode.INVALID_TRANSITION)
                position += 1
                next_status = "completed" if position == member_count else status
            else:
                transitions = {
                    ("in_progress", "interrupt"): "interrupted",
                    ("interrupted", "resume"): "in_progress",
                    ("in_progress", "abandon"): "abandoned",
                    ("interrupted", "abandon"): "abandoned",
                }
                next_status = transitions.get((status, action), "")
                if not next_status:
                    raise DomainError(ErrorCode.INVALID_TRANSITION)
            version = expected_version + 1
            completed_at = changed_at if next_status == "completed" else None
            await session.execute(
                text(
                    "UPDATE practice.practice_runs SET status=:status,current_position=:position,"
                    "version=:version,updated_at=:at,completed_at=:completed "
                    "WHERE run_id=:id"
                ),
                {
                    "status": next_status,
                    "position": position,
                    "version": version,
                    "at": changed_at,
                    "completed": completed_at,
                    "id": run_id,
                },
            )
            await self._record_command(
                session,
                actor_id=actor_id,
                profile_id=UUID(str(row["profile_id"])),
                command_type=command_type,
                aggregate_type="practice_run",
                aggregate_id=run_id,
                aggregate_version=version,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                at=changed_at,
                event_type={
                    "advance": "practice.run.advanced",
                    "interrupt": "practice.run.interrupted",
                    "resume": "practice.run.resumed",
                    "abandon": "practice.run.abandoned",
                }[action],
            )
            return await self._load_run(session, run_id)

    async def advance_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        *,
        expected_version: int,
        advanced_at: datetime,
        idempotency_key: str,
    ) -> PracticeRunView:
        return await self._mutate_run(
            actor_id,
            run_id,
            action="advance",
            expected_version=expected_version,
            changed_at=advanced_at,
            idempotency_key=idempotency_key,
        )

    async def transition_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        *,
        action: str,
        expected_version: int,
        changed_at: datetime,
        idempotency_key: str,
    ) -> PracticeRunView:
        if action not in {"interrupt", "resume", "abandon"}:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        return await self._mutate_run(
            actor_id,
            run_id,
            action=action,
            expected_version=expected_version,
            changed_at=changed_at,
            idempotency_key=idempotency_key,
        )
