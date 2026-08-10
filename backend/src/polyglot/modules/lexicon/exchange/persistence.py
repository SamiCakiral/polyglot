from __future__ import annotations

import json
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.lexicon.exchange.application import (
    AssociateVocabularyList,
    ChangeListMembers,
    CreateImport,
    CreateVocabularyList,
    DynamicListPreviewView,
    ImportRunView,
    ListSnapshotView,
    MutationView,
    VocabularyListView,
)
from polyglot.modules.lexicon.exchange.domain import (
    ExistingLexicalCandidate,
    ImportCandidate,
    ImportStrategy,
    PreviewDecision,
    create_preview,
)
from polyglot.modules.lexicon.exchange.exports import (
    require_encrypted_artifact,
    validate_export_scope,
)
from polyglot.modules.lexicon.exchange.lexical_adapter import (
    SqlLexicalMutationAdapter,
    SqlLexicalReferenceAdapter,
)
from polyglot.modules.lexicon.exchange.lists import ListAssociation, ListDefinition
from polyglot.modules.lexicon.exchange.parsing import ParseLimits, parse_import
from polyglot.modules.lexicon.exchange.ports import (
    AssociationTargetPort,
    CreateImportedLexicalEntry,
    DynamicListQueryPort,
    LexicalMutationPort,
    LexicalReferencePort,
    PrivateArtifactPort,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator


class SqlExchangeService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        ids: IdGenerator | None = None,
        parse_limits: ParseLimits | None = None,
        association_targets: AssociationTargetPort | None = None,
        dynamic_lists: DynamicListQueryPort | None = None,
        lexical_mutations: LexicalMutationPort | None = None,
        private_artifacts: PrivateArtifactPort | None = None,
        lexical_references: LexicalReferencePort | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._ids = ids or Uuid7Generator()
        self._parse_limits = parse_limits or ParseLimits()
        self._association_targets = association_targets
        self._dynamic_lists = dynamic_lists
        self._lexical_mutations = lexical_mutations or SqlLexicalMutationAdapter(self._ids)
        self._private_artifacts = private_artifacts
        self._lexical_references = lexical_references or SqlLexicalReferenceAdapter()

    async def _set_actor(self, session: AsyncSession, actor_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"),
            {"actor": str(actor_id)},
        )

    async def _assert_owner(
        self,
        session: AsyncSession,
        actor_id: UUID,
        profile_id: UUID,
    ) -> None:
        owned = await session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles "
                "WHERE profile_id=:profile AND account_id=:actor AND status <> 'deleted')"
            ),
            {"profile": profile_id, "actor": actor_id},
        )
        if owned is not True:
            raise DomainError(ErrorCode.NOT_FOUND)

    async def _actor_roles(
        self,
        session: AsyncSession,
        actor_id: UUID,
    ) -> tuple[str, ...]:
        granted = tuple(
            (
                await session.execute(
                    text(
                        "SELECT role FROM identity.account_roles "
                        "WHERE account_id=:actor AND revoked_at IS NULL"
                    ),
                    {"actor": actor_id},
                )
            ).scalars()
        )
        return ("learner", *granted)

    async def _validate_list_mutation(
        self,
        session: AsyncSession,
        actor_id: UUID,
        current: VocabularyListView,
        *,
        members: bool = False,
    ) -> None:
        ListDefinition.create(
            current.list_type,
            current.query_definition,
            actor_roles=await self._actor_roles(session, actor_id),
        )
        if members and current.list_type == "dynamic":
            raise DomainError(ErrorCode.INVALID_TRANSITION)

    async def _lock_command(
        self,
        session: AsyncSession,
        actor_id: UUID,
        command_type: str,
        idempotency_key: str,
    ) -> None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
            {"scope": f"{actor_id}:{command_type}:{idempotency_key}"},
        )

    async def _replay(
        self,
        session: AsyncSession,
        actor_id: UUID,
        command_type: str,
        idempotency_key: str,
        fingerprint: str,
    ) -> tuple[UUID, int] | None:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT request_fingerprint,status,result_ref,result_payload "
                        "FROM platform.command_receipts WHERE actor_id=:actor "
                        "AND command_type=:command AND idempotency_key=:key"
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
        payload = row["result_payload"]
        if not isinstance(payload, dict):
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return UUID(str(row["result_ref"])), int(payload["version"])

    async def _receipt(
        self,
        session: AsyncSession,
        *,
        command_id: UUID,
        command_type: str,
        actor_id: UUID,
        aggregate_type: str,
        aggregate_id: UUID,
        idempotency_key: str,
        fingerprint: str,
        expected_version: int | None,
        version: int,
        at: datetime,
        profile_id: UUID,
        event_type: str,
    ) -> None:
        await session.execute(
            text(
                "INSERT INTO platform.command_receipts "
                "(command_id,command_type,actor_id,aggregate_type,aggregate_id,idempotency_key,"
                "request_fingerprint,expected_version,received_at,result_ref,result_payload,status,"
                "expires_at) VALUES "
                "(:id,:command,:actor,:aggregate_type,:aggregate,:key,:fingerprint,:expected,:at,"
                ":aggregate,jsonb_build_object('resource_id',CAST(:resource AS text),"
                "'version',CAST(:version AS integer)),"
                "'succeeded',:expires)"
            ),
            {
                "id": command_id,
                "command": command_type,
                "actor": actor_id,
                "aggregate_type": aggregate_type,
                "aggregate": aggregate_id,
                "key": idempotency_key,
                "fingerprint": fingerprint,
                "expected": expected_version,
                "at": at,
                "resource": str(aggregate_id),
                "version": version,
                "expires": at + timedelta(days=30),
            },
        )
        event_id = self._ids.new()
        await session.execute(
            text(
                "INSERT INTO platform.domain_events "
                "(event_id,event_type,schema_version,aggregate_type,aggregate_id,"
                "aggregate_version,actor_type,actor_id,profile_id,occurred_at,recorded_at,"
                "correlation_id,causation_id,command_id,privacy_class,policy_versions,payload,"
                "expires_at,subject_type,subject_id) VALUES "
                "(:event,:event_type,1,:aggregate_type,:aggregate,:version,'account',:actor,"
                ":profile,:at,:at,:event,NULL,:command,'personal',CAST(:policies AS jsonb),"
                "CAST(:payload AS jsonb),:expires,'profile',:profile)"
            ),
            {
                "event": event_id,
                "event_type": event_type,
                "aggregate_type": aggregate_type,
                "aggregate": aggregate_id,
                "version": version,
                "actor": actor_id,
                "profile": profile_id,
                "at": at,
                "command": command_id,
                "policies": json.dumps({"exchange": "v1"}),
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

    async def _load_list(
        self,
        session: AsyncSession,
        list_id: UUID,
        *,
        for_update: bool = False,
    ) -> VocabularyListView:
        suffix = " FOR UPDATE OF list_row" if for_update else ""
        row = (
            (
                await session.execute(
                    text(
                        "SELECT list_row.*,revision.list_revision_id,revision.revision_no,"
                        "revision.name,revision.purpose,revision.ordered,revision.color,revision.tags,"
                        "revision.query_definition FROM lexicon.vocabulary_lists list_row "
                        "JOIN lexicon.vocabulary_list_revisions revision "
                        "ON revision.list_revision_id=list_row.current_revision_id "
                        "WHERE list_row.list_id=:list_id" + suffix
                    ),
                    {"list_id": list_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        members = tuple(
            (
                await session.execute(
                    text(
                        "SELECT sense_id FROM lexicon.list_memberships "
                        "WHERE list_revision_id=:revision ORDER BY position"
                    ),
                    {"revision": row["list_revision_id"]},
                )
            ).scalars()
        )
        return VocabularyListView(
            list_id=row["list_id"],
            profile_id=row["profile_id"],
            variety_id=row["variety_id"],
            list_type=row["list_type"],
            status=row["status"],
            version=row["version"],
            revision_id=row["list_revision_id"],
            revision_no=row["revision_no"],
            name=row["name"],
            purpose=row["purpose"],
            ordered=row["ordered"],
            color=row["color"],
            tags=tuple(row["tags"]),
            query_definition=row["query_definition"],
            member_sense_ids=members,
        )

    async def get_list(self, actor_id: UUID, list_id: UUID) -> VocabularyListView:
        async with self._session_factory() as session:
            await self._set_actor(session, actor_id)
            return await self._load_list(session, list_id)

    async def preview_dynamic_list(
        self,
        actor_id: UUID,
        list_id: UUID,
        *,
        cutoff_at: datetime,
        limit: int,
    ) -> DynamicListPreviewView:
        if limit < 1 or limit > 100:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        if self._dynamic_lists is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            current = await self._load_list(session, list_id)
            if current.list_type != "dynamic" or current.query_definition is None:
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            members = await self._dynamic_lists.evaluate(
                current.profile_id,
                current.query_definition,
                cutoff_at,
                limit + 1,
            )
            if len(set(members)) != len(members):
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED,
                    detail="dynamic list evaluator returned duplicate members",
                )
            return DynamicListPreviewView(
                list_id=current.list_id,
                revision_id=current.revision_id,
                cutoff_at=cutoff_at,
                member_sense_ids=members[:limit],
                truncated=len(members) > limit,
            )

    async def associate_list(
        self,
        actor_id: UUID,
        list_id: UUID,
        command: AssociateVocabularyList,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> MutationView:
        ListAssociation.create(
            target_type=command.target_type,
            target_id=command.target_id,
            role=command.role,
        )
        if command.valid_until is not None and command.valid_until <= command.valid_from:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        fingerprint = canonical_json_fingerprint(
            {
                "list_id": str(list_id),
                "target_type": command.target_type,
                "target_id": str(command.target_id),
                "role": command.role,
                "valid_from": command.valid_from.isoformat(),
                "valid_until": (
                    None if command.valid_until is None else command.valid_until.isoformat()
                ),
                "expected_version": expected_version,
            }
        )
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, "AssociateVocabularyList", idempotency_key)
            replay = await self._replay(
                session,
                actor_id,
                "AssociateVocabularyList",
                idempotency_key,
                fingerprint,
            )
            if replay is not None:
                return MutationView(replay[0], replay[1], "active")
            current = await self._load_list(session, list_id, for_update=True)
            if current.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if current.status != "active":
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            if self._association_targets is None:
                raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
            exists = await self._association_targets.verify(
                command.target_type,
                command.target_id,
                current.profile_id,
            )
            if not exists:
                raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
            association_id = self._ids.new()
            version = current.version + 1
            await session.execute(
                text(
                    "INSERT INTO lexicon.list_associations "
                    "(association_id,list_id,profile_id,target_type,target_id,role,"
                    "valid_from,valid_until,version) VALUES "
                    "(:association,:list,:profile,:target_type,:target,:role,"
                    ":valid_from,:valid_until,1)"
                ),
                {
                    "association": association_id,
                    "list": list_id,
                    "profile": current.profile_id,
                    "target_type": command.target_type,
                    "target": command.target_id,
                    "role": command.role,
                    "valid_from": command.valid_from,
                    "valid_until": command.valid_until,
                },
            )
            await session.execute(
                text(
                    "UPDATE lexicon.vocabulary_lists SET version=:version,updated_at=:at "
                    "WHERE list_id=:list"
                ),
                {"version": version, "at": command.valid_from, "list": list_id},
            )
            await self._receipt(
                session,
                command_id=self._ids.new(),
                command_type="AssociateVocabularyList",
                actor_id=actor_id,
                aggregate_type="list_association",
                aggregate_id=association_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
                version=version,
                at=command.valid_from,
                profile_id=current.profile_id,
                event_type="vocabulary_list_revised",
            )
            return MutationView(association_id, version, "active")

    async def list_resources(
        self,
        *,
        actor_id: UUID,
        resource_type: str,
        profile_id: UUID | None,
        limit: int,
        cursor: str | None,
        resource_id: UUID | None = None,
    ) -> tuple[tuple[dict[str, Any], ...], str | None]:
        if not 1 <= limit <= 100:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        async with self._session_factory() as session:
            await self._set_actor(session, actor_id)
            cursor_id: UUID | None = None
            if cursor is not None:
                try:
                    cursor_id = UUID(cursor)
                except ValueError as error:
                    raise DomainError(ErrorCode.CURSOR_INVALID) from error
            if resource_type == "vocabulary_list":
                if profile_id is None:
                    raise DomainError(ErrorCode.VALIDATION_FAILED)
                ids = tuple(
                    (
                        await session.execute(
                            text(
                                "SELECT list_id FROM lexicon.vocabulary_lists "
                                "WHERE profile_id=:profile AND (CAST(:cursor AS uuid) IS NULL "
                                "OR list_id>:cursor) ORDER BY list_id LIMIT :limit"
                            ),
                            {"profile": profile_id, "cursor": cursor_id, "limit": limit + 1},
                        )
                    ).scalars()
                )
                views = tuple([await self._load_list(session, value) for value in ids[:limit]])
                items = tuple(
                    {
                        "list_id": str(view.list_id),
                        "profile_id": str(view.profile_id),
                        "name": view.name,
                        "status": view.status,
                        "version": view.version,
                        "member_count": len(view.member_sense_ids),
                    }
                    for view in views
                )
                return items, str(ids[limit - 1]) if len(ids) > limit else None
            table = {
                "shared_list": ("exchange.shared_list_publications", "publication_id"),
                "export": ("exchange.export_runs", "export_id"),
            }.get(resource_type)
            if table is None:
                raise DomainError(ErrorCode.VALIDATION_FAILED)
            table_name, id_column = table
            if resource_id is not None:
                rows = (
                    (
                        await session.execute(
                            text(f"SELECT * FROM {table_name} WHERE {id_column}=:id"),
                            {"id": resource_id},
                        )
                    )
                    .mappings()
                    .all()
                )
            else:
                rows = (
                    (
                        await session.execute(
                            text(
                                f"SELECT * FROM {table_name} WHERE "
                                f"(CAST(:cursor AS uuid) IS NULL OR {id_column}>:cursor) "
                                f"ORDER BY {id_column} LIMIT :limit"
                            ),
                            {"cursor": cursor_id, "limit": limit + 1},
                        )
                    )
                    .mappings()
                    .all()
                )
            selected = rows[:limit]
            items = tuple(self._public_row(dict(row)) for row in selected)
            next_cursor = str(selected[-1][id_column]) if len(rows) > limit and selected else None
            return items, next_cursor

    @staticmethod
    def _public_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: (str(value) if isinstance(value, (UUID, datetime)) else value)
            for key, value in row.items()
            if key not in {"account_id", "manifest_checksum"}
        }

    @staticmethod
    def _fingerprint_value(value: Any) -> Any:
        if isinstance(value, (UUID, datetime)):
            return str(value) if isinstance(value, UUID) else value.isoformat()
        if isinstance(value, dict):
            return {
                str(key): SqlExchangeService._fingerprint_value(child)
                for key, child in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [SqlExchangeService._fingerprint_value(child) for child in value]
        return value

    async def execute_command(
        self,
        *,
        command_name: str,
        actor_id: UUID,
        resource_id: UUID,
        payload: dict[str, Any],
        idempotency_key: str,
        expected_version: int | None,
        session_id: UUID | None = None,
    ) -> MutationView:
        if command_name == "CloneVocabularyList":
            source = await self.get_list(actor_id, resource_id)
            target_profile = UUID(str(payload["target_profile_id"]))
            created = await self.create_list(
                actor_id,
                target_profile,
                CreateVocabularyList(
                    variety_id=source.variety_id,
                    list_type="manual",
                    name=str(payload.get("name") or source.name),
                    purpose=f"Clone de {source.name}",
                    ordered=source.ordered,
                    color=source.color,
                    tags=source.tags,
                    query_definition=None,
                    member_sense_ids=source.member_sense_ids,
                    created_at=cast(datetime, payload["cloned_at"]),
                ),
                idempotency_key=idempotency_key,
                _command_type="CloneVocabularyList",
                _event_type="vocabulary_list_cloned",
            )
            return MutationView(created.list_id, created.version, created.status)
        if command_name == "MergeVocabularyLists":
            source_ids = tuple(UUID(str(value)) for value in payload["source_list_ids"])
            sources = tuple([await self.get_list(actor_id, value) for value in source_ids])
            if not sources or len({view.variety_id for view in sources}) != 1:
                raise DomainError(ErrorCode.LIST_MERGE_CONFLICT)
            strategy = str(payload["strategy"])
            if strategy == "intersection":
                common = set(sources[0].member_sense_ids)
                for source in sources[1:]:
                    common &= set(source.member_sense_ids)
                members = tuple(value for value in sources[0].member_sense_ids if value in common)
            else:
                members = tuple(
                    dict.fromkeys(value for source in sources for value in source.member_sense_ids)
                )
            created = await self.create_list(
                actor_id,
                UUID(str(payload["target_profile_id"])),
                CreateVocabularyList(
                    variety_id=sources[0].variety_id,
                    list_type="manual",
                    name=str(payload["name"]),
                    purpose="Fusion explicite de listes",
                    ordered=strategy == "ordered_union",
                    color=None,
                    tags=("fusion",),
                    query_definition=None,
                    member_sense_ids=members,
                    created_at=cast(datetime, payload["merged_at"]),
                ),
                idempotency_key=idempotency_key,
                _command_type="MergeVocabularyLists",
                _event_type="vocabulary_lists_merged",
            )
            return MutationView(created.list_id, created.version, created.status)

        supported = {
            "ArchiveVocabularyList",
            "ReviseVocabularyList",
            "PublishVocabularyListSnapshot",
            "RetireSharedVocabularyList",
            "ResolveImportConflict",
            "RequestExport",
        }
        if command_name not in supported:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        fingerprint = canonical_json_fingerprint(
            cast(
                Any,
                {
                    "command": command_name,
                    "resource_id": str(resource_id),
                    "payload": self._fingerprint_value(payload),
                    "expected_version": expected_version,
                },
            )
        )
        command_at = next(
            (
                value
                for key, value in payload.items()
                if key.endswith("_at") and isinstance(value, datetime)
            ),
            datetime.now().astimezone(),
        )
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, command_name, idempotency_key)
            replay = await self._replay(
                session, actor_id, command_name, idempotency_key, fingerprint
            )
            if replay is not None:
                return MutationView(
                    replay[0],
                    replay[1],
                    {
                        "ArchiveVocabularyList": "archived",
                        "ReviseVocabularyList": "active",
                        "PublishVocabularyListSnapshot": "published",
                        "RetireSharedVocabularyList": "retired",
                        "ResolveImportConflict": "resolved",
                        "RequestExport": "requested",
                    }[command_name],
                )
            if command_name == "ArchiveVocabularyList":
                if expected_version is None:
                    raise DomainError(ErrorCode.VERSION_CONFLICT)
                current = await self._load_list(session, resource_id, for_update=True)
                await self._validate_list_mutation(session, actor_id, current)
                if current.version != expected_version:
                    raise DomainError(ErrorCode.VERSION_CONFLICT)
                if current.status != "active":
                    raise DomainError(ErrorCode.INVALID_TRANSITION)
                version = current.version + 1
                await session.execute(
                    text(
                        "UPDATE lexicon.vocabulary_lists SET status='archived',"
                        "version=:version,updated_at=:at WHERE list_id=:list"
                    ),
                    {"version": version, "at": payload["at"], "list": resource_id},
                )
                result_id, status = resource_id, "archived"
                result_profile_id = current.profile_id
            elif command_name == "ReviseVocabularyList":
                if expected_version is None:
                    raise DomainError(ErrorCode.VERSION_CONFLICT)
                current = await self._load_list(session, resource_id, for_update=True)
                await self._validate_list_mutation(session, actor_id, current)
                if current.version != expected_version:
                    raise DomainError(ErrorCode.VERSION_CONFLICT)
                revised_query = cast(
                    dict[str, Any] | None,
                    payload.get("query_definition", current.query_definition),
                )
                ListDefinition.create(
                    current.list_type,
                    revised_query,
                    actor_roles=await self._actor_roles(session, actor_id),
                )
                revision_id = self._ids.new()
                await self._insert_revision(
                    session,
                    list_id=resource_id,
                    profile_id=current.profile_id,
                    revision_id=revision_id,
                    revision_no=current.revision_no + 1,
                    name=str(payload.get("name") or current.name),
                    purpose=str(payload.get("purpose") or current.purpose),
                    ordered=(
                        current.ordered
                        if payload.get("ordered") is None
                        else bool(payload["ordered"])
                    ),
                    color=cast(str | None, payload.get("color", current.color)),
                    tags=(
                        current.tags
                        if payload.get("tags") is None
                        else tuple(cast(list[str], payload["tags"]))
                    ),
                    query_definition=cast(
                        dict[str, object] | None,
                        revised_query,
                    ),
                    provenance_id=self._ids.new(),
                    members=current.member_sense_ids,
                    at=cast(datetime, payload["revised_at"]),
                )
                version = current.version + 1
                await session.execute(
                    text(
                        "UPDATE lexicon.vocabulary_lists SET current_revision_id=:revision,"
                        "version=:version,updated_at=:at WHERE list_id=:list"
                    ),
                    {
                        "revision": revision_id,
                        "version": version,
                        "at": payload["revised_at"],
                        "list": resource_id,
                    },
                )
                result_id, status = resource_id, "active"
                result_profile_id = current.profile_id
            elif command_name == "PublishVocabularyListSnapshot":
                if expected_version is None:
                    raise DomainError(ErrorCode.VERSION_CONFLICT)
                list_id = UUID(str(payload["list_id"]))
                current = await self._load_list(session, list_id, for_update=True)
                if current.version != expected_version:
                    raise DomainError(ErrorCode.VERSION_CONFLICT)
                snapshot = await self._load_snapshot(session, resource_id)
                if snapshot.list_id != list_id or not str(payload["license_ref"]).strip():
                    raise DomainError(ErrorCode.LICENSE_MISSING)
                publication_id = self._ids.new()
                public_payload = {
                    "schema_version": 1,
                    "list_id": str(list_id),
                    "snapshot_id": str(snapshot.snapshot_id),
                    "member_sense_revision_ids": [
                        str(value) for value in snapshot.member_sense_revision_ids
                    ],
                }
                await session.execute(
                    text(
                        "INSERT INTO exchange.shared_list_publications "
                        "(publication_id,profile_id,list_snapshot_id,license_ref,provenance_id,"
                        "status,published_at,version,public_payload) VALUES "
                        "(:id,:profile,:snapshot,:license,:provenance,'published',:at,1,"
                        "CAST(:payload AS jsonb))"
                    ),
                    {
                        "id": publication_id,
                        "profile": snapshot.profile_id,
                        "snapshot": snapshot.snapshot_id,
                        "license": payload["license_ref"],
                        "provenance": payload["provenance_id"],
                        "at": payload["published_at"],
                        "payload": json.dumps(public_payload),
                    },
                )
                result_id, version, status = publication_id, 1, "published"
                result_profile_id = snapshot.profile_id
            elif command_name == "RetireSharedVocabularyList":
                row = (
                    (
                        await session.execute(
                            text(
                                "SELECT version,status,profile_id "
                                "FROM exchange.shared_list_publications "
                                "WHERE publication_id=:id FOR UPDATE"
                            ),
                            {"id": resource_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise DomainError(ErrorCode.NOT_FOUND)
                if row["version"] != expected_version:
                    raise DomainError(ErrorCode.VERSION_CONFLICT)
                if row["status"] != "published":
                    raise DomainError(ErrorCode.PUBLICATION_NOT_ACTIVE)
                version = row["version"] + 1
                await session.execute(
                    text(
                        "UPDATE exchange.shared_list_publications SET status='retired',"
                        "retired_at=:at,version=:version WHERE publication_id=:id"
                    ),
                    {"at": payload["at"], "version": version, "id": resource_id},
                )
                result_id, status = resource_id, "retired"
                result_profile_id = row["profile_id"]
            elif command_name == "ResolveImportConflict":
                row = (
                    (
                        await session.execute(
                            text(
                                "SELECT conflict.*,line.import_id,run.preview_checksum,"
                                "run.version AS "
                                "import_version FROM exchange.import_conflicts conflict "
                                "JOIN exchange.import_lines line "
                                "ON line.import_line_id=conflict.import_line_id "
                                "JOIN exchange.import_runs run ON run.import_id=line.import_id "
                                "WHERE conflict.conflict_id=:id FOR UPDATE OF conflict,run"
                            ),
                            {"id": resource_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None or row["import_id"] != UUID(str(payload["import_id"])):
                    raise DomainError(ErrorCode.NOT_FOUND)
                if row["version"] != expected_version:
                    raise DomainError(ErrorCode.VERSION_CONFLICT)
                if row["preview_checksum"] != payload["preview_checksum"]:
                    raise DomainError(ErrorCode.PREVIEW_STALE)
                if payload["action"] not in row["allowed_actions"]:
                    raise DomainError(ErrorCode.CONFLICT_ACTION_INVALID)
                version = row["version"] + 1
                await session.execute(
                    text(
                        "UPDATE exchange.import_conflicts SET selected_action=:action,"
                        "decided_by_actor_id=:actor,decided_at=:at,version=:version "
                        "WHERE conflict_id=:id"
                    ),
                    {
                        "action": payload["action"],
                        "actor": actor_id,
                        "at": payload["decided_at"],
                        "version": version,
                        "id": resource_id,
                    },
                )
                line_status = "rejected" if payload["action"] == "reject" else "accepted"
                await session.execute(
                    text(
                        "UPDATE exchange.import_lines SET status=:status,"
                        "intermediate_payload=intermediate_payload || "
                        "jsonb_build_object('_selected_action',CAST(:action AS text),"
                        "'_candidate_refs',candidate.candidate_refs) "
                        "FROM exchange.import_conflicts candidate "
                        "WHERE candidate.conflict_id=:conflict "
                        "AND exchange.import_lines.import_line_id=candidate.import_line_id"
                    ),
                    {
                        "status": line_status,
                        "action": payload["action"],
                        "conflict": resource_id,
                    },
                )
                remaining = await session.scalar(
                    text(
                        "SELECT count(*) FROM exchange.import_conflicts conflict "
                        "JOIN exchange.import_lines line "
                        "ON line.import_line_id=conflict.import_line_id "
                        "WHERE line.import_id=:import AND conflict.selected_action IS NULL"
                    ),
                    {"import": row["import_id"]},
                )
                await session.execute(
                    text(
                        "UPDATE exchange.import_runs SET status=:status,version=version+1 "
                        "WHERE import_id=:import"
                    ),
                    {
                        "status": "preview_ready" if not remaining else "awaiting_decision",
                        "import": row["import_id"],
                    },
                )
                result_id, status = resource_id, "resolved"
                result_profile_id = row["profile_id"]
            else:
                profile_id = resource_id
                await self._assert_owner(session, actor_id, profile_id)
                validate_export_scope(cast(dict[str, object], payload["scope"]))
                if session_id is None:
                    raise DomainError(ErrorCode.UNAUTHENTICATED)
                authenticated_at = await session.scalar(
                    text(
                        "SELECT authenticated_at FROM identity.auth_sessions "
                        "WHERE session_id=:session AND account_id=:actor AND revoked_at IS NULL"
                    ),
                    {"session": session_id, "actor": actor_id},
                )
                requested_at = cast(datetime, payload["requested_at"])
                if (
                    authenticated_at is None
                    or requested_at < authenticated_at
                    or requested_at - authenticated_at > timedelta(minutes=10)
                ):
                    raise DomainError(ErrorCode.UNAUTHENTICATED)
                export_id = self._ids.new()
                job_id = self._ids.new()
                await session.execute(
                    text(
                        "INSERT INTO exchange.export_runs "
                        "(export_id,account_id,profile_id,job_id,scope,status,requested_at,"
                        "expires_at,version) VALUES "
                        "(:export,:actor,:profile,:job,CAST(:scope AS jsonb),'requested',"
                        ":at,:expires,1)"
                    ),
                    {
                        "export": export_id,
                        "actor": actor_id,
                        "profile": profile_id,
                        "job": job_id,
                        "scope": json.dumps(payload["scope"]),
                        "at": requested_at,
                        "expires": requested_at + timedelta(hours=72),
                    },
                )
                result_id, version, status = export_id, 1, "requested"
                result_profile_id = profile_id
            await self._receipt(
                session,
                command_id=self._ids.new(),
                command_type=command_name,
                actor_id=actor_id,
                aggregate_type=(
                    "vocabulary_list" if command_name == "ReviseVocabularyList" else "exchange"
                ),
                aggregate_id=result_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
                version=version,
                at=command_at,
                profile_id=result_profile_id,
                event_type={
                    "ArchiveVocabularyList": "vocabulary_list_archived",
                    "ReviseVocabularyList": "vocabulary_list_revised",
                    "PublishVocabularyListSnapshot": "vocabulary_list_snapshot_published",
                    "RetireSharedVocabularyList": "shared_vocabulary_list_retired",
                    "ResolveImportConflict": "import_conflict_resolved",
                    "RequestExport": "export_requested",
                }[command_name],
            )
            return MutationView(result_id, version, status)

    async def create_list(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: CreateVocabularyList,
        *,
        idempotency_key: str,
        _command_type: str = "CreateVocabularyList",
        _event_type: str = "vocabulary_list_created",
    ) -> VocabularyListView:
        fingerprint = canonical_json_fingerprint(
            {
                "profile_id": str(profile_id),
                "variety_id": str(command.variety_id),
                "list_type": command.list_type,
                "name": command.name,
                "purpose": command.purpose,
                "ordered": command.ordered,
                "color": command.color,
                "tags": list(command.tags),
                "query_definition": cast(Any, command.query_definition),
                "member_sense_ids": [str(value) for value in command.member_sense_ids],
                "created_at": command.created_at.isoformat(),
                "command_type": _command_type,
            }
        )
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._assert_owner(session, actor_id, profile_id)
            await self._lock_command(session, actor_id, _command_type, idempotency_key)
            replay = await self._replay(
                session, actor_id, _command_type, idempotency_key, fingerprint
            )
            if replay is not None:
                return await self._load_list(session, replay[0])
            ListDefinition.create(
                command.list_type,
                command.query_definition,
                actor_roles=await self._actor_roles(session, actor_id),
            )
            if len(set(command.member_sense_ids)) != len(command.member_sense_ids):
                raise DomainError(ErrorCode.MEMBER_CONFLICT)
            list_id = self._ids.new()
            revision_id = self._ids.new()
            provenance_id = self._ids.new()
            await session.execute(
                text(
                    "INSERT INTO lexicon.vocabulary_lists "
                    "(list_id,profile_id,editorial_owner_id,variety_id,list_type,status,"
                    "current_revision_id,version,created_at,updated_at) VALUES "
                    "(:list,:profile,:editorial_owner,:variety,:type,'active',NULL,1,:at,:at)"
                ),
                {
                    "list": list_id,
                    "profile": profile_id,
                    "editorial_owner": (actor_id if command.list_type == "editorial" else None),
                    "variety": command.variety_id,
                    "type": command.list_type,
                    "at": command.created_at,
                },
            )
            await self._insert_revision(
                session,
                list_id=list_id,
                profile_id=profile_id,
                revision_id=revision_id,
                revision_no=1,
                name=command.name,
                purpose=command.purpose,
                ordered=command.ordered,
                color=command.color,
                tags=command.tags,
                query_definition=command.query_definition,
                provenance_id=provenance_id,
                members=command.member_sense_ids,
                at=command.created_at,
            )
            await session.execute(
                text(
                    "UPDATE lexicon.vocabulary_lists SET current_revision_id=:revision "
                    "WHERE list_id=:list"
                ),
                {"revision": revision_id, "list": list_id},
            )
            await self._receipt(
                session,
                command_id=self._ids.new(),
                command_type=_command_type,
                actor_id=actor_id,
                aggregate_type="vocabulary_list",
                aggregate_id=list_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=None,
                version=1,
                at=command.created_at,
                profile_id=profile_id,
                event_type=_event_type,
            )
            return await self._load_list(session, list_id)

    async def _insert_revision(
        self,
        session: AsyncSession,
        *,
        list_id: UUID,
        profile_id: UUID,
        revision_id: UUID,
        revision_no: int,
        name: str,
        purpose: str,
        ordered: bool,
        color: str | None,
        tags: tuple[str, ...],
        query_definition: dict[str, object] | None,
        provenance_id: UUID,
        members: tuple[UUID, ...],
        at: datetime,
    ) -> None:
        await session.execute(
            text(
                "INSERT INTO lexicon.vocabulary_list_revisions "
                "(list_revision_id,list_id,profile_id,revision_no,name,purpose,query_definition,"
                "ordered,color,tags,provenance_id,created_at) VALUES "
                "(:revision,:list,:profile,:number,:name,:purpose,CAST(:query AS jsonb),"
                ":ordered,:color,CAST(:tags AS jsonb),:provenance,:at)"
            ),
            {
                "revision": revision_id,
                "list": list_id,
                "profile": profile_id,
                "number": revision_no,
                "name": name,
                "purpose": purpose,
                "query": None if query_definition is None else json.dumps(query_definition),
                "ordered": ordered,
                "color": color,
                "tags": json.dumps(list(tags)),
                "provenance": provenance_id,
                "at": at,
            },
        )
        for position, sense_id in enumerate(members, 1):
            await session.execute(
                text(
                    "INSERT INTO lexicon.list_memberships "
                    "(membership_id,list_revision_id,profile_id,sense_id,position,role) "
                    "VALUES (:id,:revision,:profile,:sense,:position,'target')"
                ),
                {
                    "id": self._ids.new(),
                    "revision": revision_id,
                    "profile": profile_id,
                    "sense": sense_id,
                    "position": position,
                },
            )

    async def change_members(
        self,
        actor_id: UUID,
        list_id: UUID,
        command: ChangeListMembers,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> VocabularyListView:
        fingerprint = canonical_json_fingerprint(
            {
                "list_id": str(list_id),
                "add": [str(value) for value in command.add_sense_ids],
                "remove": [str(value) for value in command.remove_sense_ids],
                "expected_version": expected_version,
                "changed_at": command.changed_at.isoformat(),
            }
        )
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, "ChangeListMembers", idempotency_key)
            replay = await self._replay(
                session, actor_id, "ChangeListMembers", idempotency_key, fingerprint
            )
            if replay is not None:
                return await self._load_list(session, replay[0])
            current = await self._load_list(session, list_id, for_update=True)
            await self._validate_list_mutation(
                session,
                actor_id,
                current,
                members=True,
            )
            if current.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            additions = set(command.add_sense_ids)
            removals = set(command.remove_sense_ids)
            if additions & removals:
                raise DomainError(ErrorCode.MEMBER_CONFLICT)
            members = tuple(value for value in current.member_sense_ids if value not in removals)
            members += tuple(value for value in command.add_sense_ids if value not in members)
            revision_id = self._ids.new()
            await self._insert_revision(
                session,
                list_id=list_id,
                profile_id=current.profile_id,
                revision_id=revision_id,
                revision_no=current.revision_no + 1,
                name=current.name,
                purpose=current.purpose,
                ordered=current.ordered,
                color=current.color,
                tags=current.tags,
                query_definition=current.query_definition,
                provenance_id=self._ids.new(),
                members=members,
                at=command.changed_at,
            )
            version = current.version + 1
            await session.execute(
                text(
                    "UPDATE lexicon.vocabulary_lists SET current_revision_id=:revision,"
                    "version=:version,updated_at=:at WHERE list_id=:list"
                ),
                {
                    "revision": revision_id,
                    "version": version,
                    "at": command.changed_at,
                    "list": list_id,
                },
            )
            await self._receipt(
                session,
                command_id=self._ids.new(),
                command_type="ChangeListMembers",
                actor_id=actor_id,
                aggregate_type="vocabulary_list",
                aggregate_id=list_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
                version=version,
                at=command.changed_at,
                profile_id=current.profile_id,
                event_type="vocabulary_list_revised",
            )
            return await self._load_list(session, list_id)

    async def freeze_list(
        self,
        actor_id: UUID,
        list_id: UUID,
        *,
        expected_version: int,
        frozen_at: datetime,
        idempotency_key: str,
    ) -> ListSnapshotView:
        fingerprint = canonical_json_fingerprint(
            {
                "list_id": str(list_id),
                "expected_version": expected_version,
                "frozen_at": frozen_at.isoformat(),
            }
        )
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, "FreezeVocabularyList", idempotency_key)
            replay = await self._replay(
                session, actor_id, "FreezeVocabularyList", idempotency_key, fingerprint
            )
            if replay is not None:
                return await self._load_snapshot(session, replay[0])
            current = await self._load_list(session, list_id, for_update=True)
            if current.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            members = current.member_sense_ids
            if current.list_type == "dynamic":
                if self._dynamic_lists is None:
                    raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
                if current.query_definition is None:
                    raise DomainError(ErrorCode.VALIDATION_FAILED)
                members = await self._dynamic_lists.evaluate(
                    current.profile_id,
                    current.query_definition,
                    frozen_at,
                    10_000,
                )
                if len(members) > 10_000:
                    raise DomainError(ErrorCode.SIZE_LIMIT_EXCEEDED)
                if len(set(members)) != len(members):
                    raise DomainError(ErrorCode.MEMBER_CONFLICT)
                if not current.ordered:
                    members = tuple(sorted(members))
            snapshot_id = self._ids.new()
            checksum = canonical_json_fingerprint(
                {
                    "list_id": str(list_id),
                    "revision_id": str(current.revision_id),
                    "members": [str(value) for value in members],
                }
            )
            await session.execute(
                text(
                    "INSERT INTO lexicon.list_snapshots "
                    "(snapshot_id,list_id,profile_id,source_revision_id,created_at,checksum) "
                    "VALUES (:snapshot,:list,:profile,:revision,:at,:checksum)"
                ),
                {
                    "snapshot": snapshot_id,
                    "list": list_id,
                    "profile": current.profile_id,
                    "revision": current.revision_id,
                    "at": frozen_at,
                    "checksum": checksum,
                },
            )
            for position, sense_id in enumerate(members, 1):
                await session.execute(
                    text(
                        "INSERT INTO lexicon.list_snapshot_members "
                        "(snapshot_member_id,snapshot_id,profile_id,sense_revision_id,"
                        "position,role) "
                        "VALUES (:id,:snapshot,:profile,:sense,:position,'target')"
                    ),
                    {
                        "id": self._ids.new(),
                        "snapshot": snapshot_id,
                        "profile": current.profile_id,
                        "sense": sense_id,
                        "position": position,
                    },
                )
            await self._receipt(
                session,
                command_id=self._ids.new(),
                command_type="FreezeVocabularyList",
                actor_id=actor_id,
                aggregate_type="list_snapshot",
                aggregate_id=snapshot_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
                version=1,
                at=frozen_at,
                profile_id=current.profile_id,
                event_type="vocabulary_list_snapshot_created",
            )
            return await self._load_snapshot(session, snapshot_id)

    async def _load_snapshot(
        self,
        session: AsyncSession,
        snapshot_id: UUID,
    ) -> ListSnapshotView:
        row = (
            (
                await session.execute(
                    text("SELECT * FROM lexicon.list_snapshots WHERE snapshot_id=:id"),
                    {"id": snapshot_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        members = tuple(
            (
                await session.execute(
                    text(
                        "SELECT sense_revision_id FROM lexicon.list_snapshot_members "
                        "WHERE snapshot_id=:id ORDER BY position"
                    ),
                    {"id": snapshot_id},
                )
            ).scalars()
        )
        return ListSnapshotView(
            snapshot_id=row["snapshot_id"],
            list_id=row["list_id"],
            profile_id=row["profile_id"],
            source_revision_id=row["source_revision_id"],
            checksum=row["checksum"],
            member_sense_revision_ids=members,
        )

    async def _known_candidates(
        self,
        session: AsyncSession,
        profile_id: UUID,
    ) -> tuple[ExistingLexicalCandidate, ...]:
        rows = await self._lexical_references.list_import_candidates(
            profile_id,
            session=session,
        )
        return tuple(
            ExistingLexicalCandidate(
                entity_ref=row.entity_ref,
                variety_id=row.variety_id,
                unit_type=row.unit_type,
                normalized_form=row.normalized_form,
                semantic_key=row.semantic_key,
                prompt_key=None,
                external_identity=None,
                external_revision=None,
                visibility=row.visibility,
                payload_checksum="0" * 64,
            )
            for row in rows
        )

    @staticmethod
    def _candidate_payload(candidate: ImportCandidate) -> dict[str, object]:
        return {
            "line_no": candidate.line_no,
            "source_key": candidate.source_key,
            "variety_id": str(candidate.variety_id),
            "unit_type": candidate.unit_type,
            "normalized_form": candidate.normalized_form,
            "semantic_key": candidate.semantic_key,
            "prompt_key": candidate.prompt_key,
            "external_identity": candidate.external_identity,
            "external_revision": candidate.external_revision,
            "visibility": candidate.visibility,
            "payload_checksum": candidate.payload_checksum,
        }

    async def create_import(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: CreateImport,
        *,
        idempotency_key: str,
    ) -> ImportRunView:
        if command.format_id == "polyglot.user.export/v1":
            raise DomainError(ErrorCode.UNSUPPORTED_IMPORT_FORMAT)
        parsed = parse_import(
            command.payload,
            command.format_id,
            command.encoding,
            self._parse_limits,
        )
        fingerprint = canonical_json_fingerprint(
            {
                "profile_id": str(profile_id),
                "format_id": command.format_id,
                "source_checksum": parsed.source_checksum,
                "strategy": command.strategy.value,
                "catalogue_version": command.catalogue_version,
                "created_at": command.created_at.isoformat(),
                "expires_at": command.expires_at.isoformat(),
            }
        )
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._assert_owner(session, actor_id, profile_id)
            await self._lock_command(session, actor_id, "CreateImport", idempotency_key)
            replay = await self._replay(
                session, actor_id, "CreateImport", idempotency_key, fingerprint
            )
            if replay is not None:
                return await self._load_import(session, replay[0])
            preview = create_preview(
                parsed.rows,
                await self._known_candidates(session, profile_id),
                command.strategy,
                command.catalogue_version,
            )
            import_id = self._ids.new()
            unresolved = sum(line.decision is PreviewDecision.CONFLICT for line in preview.lines)
            status = "awaiting_decision" if unresolved else "preview_ready"
            await session.execute(
                text(
                    "INSERT INTO exchange.import_runs "
                    "(import_id,profile_id,format_id,schema_version,status,source_checksum,encoding,"
                    "strategy,catalogue_version_at_preview,preview_checksum,created_at,expires_at,"
                    "version) VALUES "
                    "(:import,:profile,:format,:schema,:status,:source,:encoding,:strategy,"
                    ":catalogue,:preview,:created,:expires,1)"
                ),
                {
                    "import": import_id,
                    "profile": profile_id,
                    "format": command.format_id,
                    "schema": parsed.schema_version,
                    "status": status,
                    "source": parsed.source_checksum,
                    "encoding": command.encoding,
                    "strategy": command.strategy.value,
                    "catalogue": command.catalogue_version,
                    "preview": preview.checksum,
                    "created": command.created_at,
                    "expires": command.expires_at,
                },
            )
            by_line = {candidate.line_no: candidate for candidate in parsed.rows}
            for line in preview.lines:
                line_id = self._ids.new()
                intermediate = self._candidate_payload(by_line[line.line_no])
                if line.decision is PreviewDecision.REUSE:
                    intermediate["_selected_action"] = "reuse_exact"
                    intermediate["_candidate_refs"] = [line.candidate_ref]
                await session.execute(
                    text(
                        "INSERT INTO exchange.import_lines "
                        "(import_line_id,import_id,profile_id,line_no,source_path,status,"
                        "intermediate_payload) VALUES "
                        "(:id,:import,:profile,:line,:path,:status,CAST(:payload AS jsonb))"
                    ),
                    {
                        "id": line_id,
                        "import": import_id,
                        "profile": profile_id,
                        "line": line.line_no,
                        "path": line.source_key,
                        "status": (
                            "conflict" if line.decision is PreviewDecision.CONFLICT else "accepted"
                        ),
                        "payload": json.dumps(intermediate),
                    },
                )
                if line.conflict_class is not None:
                    await session.execute(
                        text(
                            "INSERT INTO exchange.import_conflicts "
                            "(conflict_id,import_line_id,profile_id,conflict_class,candidate_refs,"
                            "allowed_actions,selected_action,decided_by_actor_id,decided_at,"
                            "version) VALUES "
                            "(:id,:line,:profile,:class,CAST(:candidates AS jsonb),"
                            "CAST(:actions AS jsonb),:selected,:decided_by,:decided_at,1)"
                        ),
                        {
                            "id": self._ids.new(),
                            "line": line_id,
                            "profile": profile_id,
                            "class": line.conflict_class.value,
                            "candidates": json.dumps([line.candidate_ref]),
                            "actions": json.dumps(list(line.allowed_actions)),
                            "selected": (
                                "reuse_exact" if line.decision is PreviewDecision.REUSE else None
                            ),
                            "decided_by": (
                                actor_id if line.decision is PreviewDecision.REUSE else None
                            ),
                            "decided_at": (
                                command.created_at
                                if line.decision is PreviewDecision.REUSE
                                else None
                            ),
                        },
                    )
            await self._receipt(
                session,
                command_id=self._ids.new(),
                command_type="CreateImport",
                actor_id=actor_id,
                aggregate_type="import",
                aggregate_id=import_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=None,
                version=1,
                at=command.created_at,
                profile_id=profile_id,
                event_type="import_created",
            )
            return await self._load_import(session, import_id)

    async def _load_import(
        self,
        session: AsyncSession,
        import_id: UUID,
        *,
        for_update: bool = False,
    ) -> ImportRunView:
        suffix = " FOR UPDATE" if for_update else ""
        row = (
            (
                await session.execute(
                    text("SELECT * FROM exchange.import_runs WHERE import_id=:id" + suffix),
                    {"id": import_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        unresolved = await session.scalar(
            text(
                "SELECT count(*) FROM exchange.import_conflicts conflict "
                "JOIN exchange.import_lines line ON line.import_line_id=conflict.import_line_id "
                "WHERE line.import_id=:id AND conflict.selected_action IS NULL"
            ),
            {"id": import_id},
        )
        manifest = (
            (
                await session.execute(
                    text(
                        "SELECT profile_id,created_refs,reused_refs,inverse_operations,checksum "
                        "FROM exchange.import_manifests "
                        "WHERE import_id=:id"
                    ),
                    {"id": import_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if manifest is not None:
            expected_manifest_checksum = self._manifest_checksum(
                import_id=import_id,
                profile_id=manifest["profile_id"],
                created_refs=list(manifest["created_refs"]),
                reused_refs=list(manifest["reused_refs"]),
                inverse_operations=list(manifest["inverse_operations"]),
            )
            if manifest["checksum"] != expected_manifest_checksum:
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED,
                    detail="import manifest integrity check failed",
                )
        return ImportRunView(
            import_id=row["import_id"],
            profile_id=row["profile_id"],
            format_id=row["format_id"],
            status=row["status"],
            strategy=ImportStrategy(row["strategy"]),
            preview_checksum=row["preview_checksum"],
            catalogue_version=row["catalogue_version_at_preview"],
            version=row["version"],
            unresolved_conflicts=int(unresolved or 0),
            created_refs=() if manifest is None else tuple(manifest["created_refs"]),
            reused_refs=() if manifest is None else tuple(manifest["reused_refs"]),
        )

    @staticmethod
    def _manifest_checksum(
        *,
        import_id: UUID,
        profile_id: UUID,
        created_refs: list[str],
        reused_refs: list[str],
        inverse_operations: list[dict[str, object]],
    ) -> str:
        return canonical_json_fingerprint(
            cast(
                Any,
                {
                    "import_id": str(import_id),
                    "profile_id": str(profile_id),
                    "created_refs": created_refs,
                    "reused_refs": reused_refs,
                    "inverse_operations": inverse_operations,
                },
            )
        )

    async def get_import(self, actor_id: UUID, import_id: UUID) -> ImportRunView:
        async with self._session_factory() as session:
            await self._set_actor(session, actor_id)
            return await self._load_import(session, import_id)

    async def get_import_preview(
        self,
        actor_id: UUID,
        import_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[tuple[dict[str, Any], ...], str | None]:
        if not 1 <= limit <= 100:
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        try:
            after_line = 0 if cursor is None else int(cursor)
        except ValueError as error:
            raise DomainError(ErrorCode.CURSOR_INVALID) from error
        if after_line < 0:
            raise DomainError(ErrorCode.CURSOR_INVALID)
        async with self._session_factory() as session:
            await self._set_actor(session, actor_id)
            await self._load_import(session, import_id)
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT line.import_line_id,line.line_no,line.source_path,line.status,"
                            "line.intermediate_payload,line.redacted_error_value,"
                            "conflict.conflict_id,conflict.conflict_class,"
                            "conflict.candidate_refs,conflict.allowed_actions,"
                            "conflict.selected_action,conflict.version AS conflict_version "
                            "FROM exchange.import_lines line LEFT JOIN exchange.import_conflicts "
                            "conflict ON conflict.import_line_id=line.import_line_id "
                            "WHERE line.import_id=:import AND line.line_no>:after "
                            "ORDER BY line.line_no LIMIT :limit"
                        ),
                        {"import": import_id, "after": after_line, "limit": limit + 1},
                    )
                )
                .mappings()
                .all()
            )
            selected = rows[:limit]
            items = tuple(
                {
                    "import_line_id": str(row["import_line_id"]),
                    "line_no": row["line_no"],
                    "source_path": row["source_path"],
                    "status": row["status"],
                    "intermediate_payload": row["intermediate_payload"],
                    "redacted_error_value": row["redacted_error_value"],
                    "conflict": (
                        None
                        if row["conflict_id"] is None
                        else {
                            "conflict_id": str(row["conflict_id"]),
                            "conflict_class": row["conflict_class"],
                            "candidate_refs": row["candidate_refs"],
                            "allowed_actions": row["allowed_actions"],
                            "selected_action": row["selected_action"],
                            "version": row["conflict_version"],
                        }
                    ),
                }
                for row in selected
            )
            next_cursor = str(selected[-1]["line_no"]) if len(rows) > limit else None
            return items, next_cursor

    async def current_catalogue_version(self, actor_id: UUID, profile_id: UUID) -> str:
        async with self._session_factory() as session:
            await self._set_actor(session, actor_id)
            await self._assert_owner(session, actor_id, profile_id)
            version = await session.scalar(
                text(
                    "SELECT md5(coalesce(string_agg(revision.pack_revision_id::text,',' "
                    "ORDER BY revision.pack_revision_id),'')) "
                    "FROM language_profiles.learner_language_profiles profile "
                    "LEFT JOIN catalogue.language_pack_revisions revision "
                    "ON revision.target_variety_id=profile.target_variety_id "
                    "AND revision.status='published' WHERE profile.profile_id=:profile"
                ),
                {"profile": profile_id},
            )
            return f"catalogue:{version}"

    async def _build_export_payload(
        self,
        session: AsyncSession,
        *,
        export_id: UUID,
        profile_id: UUID,
        scope: dict[str, object],
        requested_at: datetime,
    ) -> bytes:
        selected = validate_export_scope(scope)
        queries = {
            "word_bank": (
                "SELECT coalesce(jsonb_agg(to_jsonb(item) ORDER BY item.kind,item.id),'[]') "
                "FROM ("
                "SELECT 'unit' AS kind,lexical_unit_id AS id,to_jsonb(unit) AS payload "
                "FROM lexicon.private_lexical_units unit WHERE profile_id=:profile "
                "UNION ALL "
                "SELECT 'sense',sense_id,to_jsonb(sense) FROM lexicon.private_lexical_senses sense "
                "WHERE profile_id=:profile) item"
            ),
            "vocabulary_lists": (
                "SELECT coalesce(jsonb_agg(to_jsonb(item) ORDER BY item.list_id),'[]') "
                "FROM lexicon.vocabulary_lists item WHERE profile_id=:profile"
            ),
            "memory_prompts": (
                "SELECT coalesce(jsonb_agg(to_jsonb(item) ORDER BY item.prompt_id),'[]') "
                "FROM memory.memory_prompts item WHERE profile_id=:profile"
            ),
            "learning_history": (
                "SELECT coalesce(jsonb_agg(to_jsonb(item) "
                "ORDER BY item.occurred_at,item.encounter_id),"
                "'[]') FROM lexicon.lexical_encounters item WHERE profile_id=:profile"
            ),
        }
        data: dict[str, object] = {}
        for section in selected:
            data[section] = await session.scalar(
                text(queries[section]),
                {"profile": profile_id},
            )
        document = {
            "format": "polyglot.user.export/v1",
            "schema_version": 1,
            "export_id": str(export_id),
            "profile_id": str(profile_id),
            "requested_at": requested_at.isoformat(),
            "scope": list(selected),
            "data": data,
        }
        return json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    async def _fail_export(
        self,
        actor_id: UUID,
        export_id: UUID,
        *,
        failed_at: datetime,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            await session.execute(
                text(
                    "UPDATE exchange.export_runs SET status='failed',completed_at=:at,"
                    "version=version+1 WHERE export_id=:id AND status='running'"
                ),
                {"id": export_id, "at": failed_at},
            )

    async def complete_export(
        self,
        actor_id: UUID,
        export_id: UUID,
        *,
        completed_at: datetime,
    ) -> MutationView:
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            row = (
                (
                    await session.execute(
                        text("SELECT * FROM exchange.export_runs WHERE export_id=:id FOR UPDATE"),
                        {"id": export_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if row["status"] == "ready":
                return MutationView(export_id, row["version"], "ready")
            if row["status"] not in {"requested", "running"}:
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            if row["expires_at"] <= completed_at:
                raise DomainError(ErrorCode.RUN_EXPIRED)
            payload = await self._build_export_payload(
                session,
                export_id=export_id,
                profile_id=row["profile_id"],
                scope=row["scope"],
                requested_at=row["requested_at"],
            )
            if row["status"] == "requested":
                await session.execute(
                    text(
                        "UPDATE exchange.export_runs SET status='running',version=version+1 "
                        "WHERE export_id=:id"
                    ),
                    {"id": export_id},
                )
            profile_id = row["profile_id"]
            expires_at = row["expires_at"]

        if self._private_artifacts is None:
            await self._fail_export(actor_id, export_id, failed_at=completed_at)
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        try:
            artifact = await self._private_artifacts.store_encrypted_export(
                export_id=export_id,
                profile_id=profile_id,
                payload=payload,
                expires_at=expires_at,
            )
            require_encrypted_artifact(
                artifact.encryption_scheme,
                artifact.checksum_sha256,
            )
        except Exception:
            await self._fail_export(actor_id, export_id, failed_at=completed_at)
            raise

        manifest_checksum = sha256(payload).hexdigest()
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT status,version FROM exchange.export_runs "
                            "WHERE export_id=:id FOR UPDATE"
                        ),
                        {"id": export_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if row["status"] == "ready":
                return MutationView(export_id, row["version"], "ready")
            if row["status"] != "running":
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            await session.execute(
                text(
                    "INSERT INTO exchange.export_artifacts "
                    "(export_artifact_id,export_id,profile_id,media_revision_id,"
                    "encryption_scheme,schema_version,created_at) VALUES "
                    "(:artifact,:export,:profile,:media,:scheme,1,:at)"
                ),
                {
                    "artifact": self._ids.new(),
                    "export": export_id,
                    "profile": profile_id,
                    "media": artifact.media_revision_id,
                    "scheme": artifact.encryption_scheme,
                    "at": completed_at,
                },
            )
            version = int(row["version"]) + 1
            await session.execute(
                text(
                    "UPDATE exchange.export_runs SET status='ready',completed_at=:at,"
                    "manifest_checksum=:checksum,version=:version WHERE export_id=:id"
                ),
                {
                    "id": export_id,
                    "at": completed_at,
                    "checksum": manifest_checksum,
                    "version": version,
                },
            )
            return MutationView(export_id, version, "ready")

    async def commit_import(
        self,
        actor_id: UUID,
        import_id: UUID,
        *,
        preview_checksum: str,
        current_catalogue_version: str,
        expected_version: int,
        committed_at: datetime,
        idempotency_key: str,
    ) -> ImportRunView:
        fingerprint = canonical_json_fingerprint(
            {
                "import_id": str(import_id),
                "preview_checksum": preview_checksum,
                "catalogue_version": current_catalogue_version,
                "expected_version": expected_version,
                "committed_at": committed_at.isoformat(),
            }
        )
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, "CommitImport", idempotency_key)
            replay = await self._replay(
                session, actor_id, "CommitImport", idempotency_key, fingerprint
            )
            if replay is not None:
                return await self._load_import(session, replay[0])
            run = await self._load_import(session, import_id, for_update=True)
            if run.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if (
                run.status not in {"preview_ready", "awaiting_decision"}
                or run.preview_checksum != preview_checksum
                or run.catalogue_version != current_catalogue_version
            ):
                raise DomainError(ErrorCode.PREVIEW_STALE)
            if run.unresolved_conflicts:
                raise DomainError(ErrorCode.UNRESOLVED_CONFLICT)
            if run.format_id == "polyglot.memory.prompts/v1":
                raise DomainError(
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    detail="transactional memory import port is unavailable",
                )
            if run.format_id == "polyglot.authoring.bundle/v1":
                raise DomainError(
                    ErrorCode.INVALID_TRANSITION,
                    detail="authoring imports require editorial handoff",
                )
            if run.format_id not in {
                "polyglot.lexicon.bundle/v1",
                "polyglot.generic.qa/v1",
            }:
                raise DomainError(ErrorCode.UNSUPPORTED_IMPORT_FORMAT)
            rows = (
                await session.execute(
                    text(
                        "SELECT * FROM exchange.import_lines WHERE import_id=:id "
                        "AND status='accepted' ORDER BY line_no FOR UPDATE"
                    ),
                    {"id": import_id},
                )
            ).mappings()
            created_refs: list[str] = []
            reused_refs: list[str] = []
            for row in rows:
                candidate = row["intermediate_payload"]
                if candidate.get("_selected_action") in {
                    "reuse_exact",
                    "link_shared",
                    "merge_intent",
                }:
                    refs = [
                        str(value)
                        for value in candidate.get("_candidate_refs", [])
                        if value is not None
                    ]
                    reused_refs.extend(refs)
                    await session.execute(
                        text(
                            "UPDATE exchange.import_lines SET status='committed',"
                            "result_entity_refs=CAST(:refs AS jsonb) WHERE import_line_id=:line"
                        ),
                        {"refs": json.dumps(refs), "line": row["import_line_id"]},
                    )
                    continue
                refs = list(
                    await self._lexical_mutations.create_imported_entry(
                        CreateImportedLexicalEntry(
                            profile_id=run.profile_id,
                            variety_id=UUID(candidate["variety_id"]),
                            unit_type=candidate["unit_type"],
                            normalized_form=candidate["normalized_form"],
                            semantic_key=candidate["semantic_key"],
                            provenance_ref=f"import:{import_id}:line:{row['line_no']}",
                            created_at=committed_at,
                        ),
                        session=session,
                    )
                )
                created_refs.extend(refs)
                await session.execute(
                    text(
                        "UPDATE exchange.import_lines SET status='committed',"
                        "result_entity_refs=CAST(:refs AS jsonb) WHERE import_line_id=:line"
                    ),
                    {"refs": json.dumps(refs), "line": row["import_line_id"]},
                )
            manifest_id = self._ids.new()
            inverse_operations: list[dict[str, object]] = [
                {"operation": "delete_if_exclusive", "ref": ref} for ref in created_refs
            ]
            checksum = self._manifest_checksum(
                import_id=import_id,
                profile_id=run.profile_id,
                created_refs=created_refs,
                reused_refs=reused_refs,
                inverse_operations=inverse_operations,
            )
            await session.execute(
                text(
                    "INSERT INTO exchange.import_manifests "
                    "(manifest_id,import_id,profile_id,created_refs,reused_refs,inverse_operations,"
                    "checksum,created_at) VALUES "
                    "(:manifest,:import,:profile,CAST(:created AS jsonb),CAST(:reused AS jsonb),"
                    "CAST(:inverse AS jsonb),:checksum,:at)"
                ),
                {
                    "manifest": manifest_id,
                    "import": import_id,
                    "profile": run.profile_id,
                    "created": json.dumps(created_refs),
                    "reused": json.dumps(reused_refs),
                    "inverse": json.dumps(inverse_operations),
                    "checksum": checksum,
                    "at": committed_at,
                },
            )
            version = run.version + 1
            await session.execute(
                text(
                    "UPDATE exchange.import_runs SET status='committed',committed_at=:at,"
                    "version=:version WHERE import_id=:id"
                ),
                {"at": committed_at, "version": version, "id": import_id},
            )
            await self._receipt(
                session,
                command_id=self._ids.new(),
                command_type="CommitImport",
                actor_id=actor_id,
                aggregate_type="import",
                aggregate_id=import_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
                version=version,
                at=committed_at,
                profile_id=run.profile_id,
                event_type="import_committed",
            )
            return await self._load_import(session, import_id)

    async def revert_import(
        self,
        actor_id: UUID,
        import_id: UUID,
        *,
        expected_version: int,
        reverted_at: datetime,
        idempotency_key: str,
    ) -> ImportRunView:
        fingerprint = canonical_json_fingerprint(
            {
                "import_id": str(import_id),
                "expected_version": expected_version,
                "reverted_at": reverted_at.isoformat(),
            }
        )
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, "RevertImport", idempotency_key)
            replay = await self._replay(
                session, actor_id, "RevertImport", idempotency_key, fingerprint
            )
            if replay is not None:
                return await self._load_import(session, replay[0])
            run = await self._load_import(session, import_id, for_update=True)
            if run.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if run.status != "committed":
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            sense_ids = tuple(
                UUID(ref.split(":", 1)[1])
                for ref in run.created_refs
                if ref.startswith("lexical_sense:")
            )
            unit_ids = tuple(
                UUID(ref.split(":", 1)[1])
                for ref in run.created_refs
                if ref.startswith("lexical_unit:")
            )
            reused = await session.scalar(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM lexicon.list_memberships WHERE sense_id=ANY(:senses) "
                    "UNION ALL SELECT 1 FROM memory.memory_prompts WHERE target_ref=ANY(:senses) "
                    "UNION ALL SELECT 1 FROM lexicon.personal_lexical_relations "
                    "WHERE source_sense_id=ANY(:senses) OR target_sense_id=ANY(:senses))"
                ),
                {"senses": list(sense_ids)},
            )
            if reused is True:
                raise DomainError(ErrorCode.RESOURCE_REUSED)
            await session.execute(
                text("SELECT exchange.revert_import_lexical(:profile,:import,:units,:senses)"),
                {
                    "profile": run.profile_id,
                    "import": import_id,
                    "units": list(unit_ids),
                    "senses": list(sense_ids),
                },
            )
            await session.execute(
                text(
                    "UPDATE exchange.import_lines SET status='reverted' "
                    "WHERE import_id=:id AND status='committed'"
                ),
                {"id": import_id},
            )
            version = run.version + 1
            await session.execute(
                text(
                    "UPDATE exchange.import_runs SET status='reverted',reverted_at=:at,"
                    "version=:version WHERE import_id=:id"
                ),
                {"at": reverted_at, "version": version, "id": import_id},
            )
            await self._receipt(
                session,
                command_id=self._ids.new(),
                command_type="RevertImport",
                actor_id=actor_id,
                aggregate_type="import",
                aggregate_id=import_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                expected_version=expected_version,
                version=version,
                at=reverted_at,
                profile_id=run.profile_id,
                event_type="import_reverted",
            )
            return await self._load_import(session, import_id)
