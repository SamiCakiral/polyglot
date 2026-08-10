from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import text

from polyglot.modules.lexicon.exchange.application import (
    AssociateVocabularyList,
    ChangeListMembers,
    CreateImport,
    CreateVocabularyList,
)
from polyglot.modules.lexicon.exchange.domain import ImportStrategy
from polyglot.modules.lexicon.exchange.persistence import SqlExchangeService
from polyglot.platform.errors import DomainError, ErrorCode

from .conftest import ACCOUNT_A, ACCOUNT_B, NOW, PROFILE_A, TARGET_VARIETY, set_actor, uid


class SequenceIdGenerator:
    def __init__(self, values: Iterable[UUID]) -> None:
        self._values = iter(values)

    def new(self) -> UUID:
        return next(self._values)


class TargetVerifier:
    def __init__(self, *, exists: bool = True) -> None:
        self.exists = exists
        self.calls: list[tuple[str, UUID, UUID]] = []

    async def verify(
        self,
        target_type: str,
        target_id: UUID,
        profile_id: UUID,
    ) -> bool:
        self.calls.append((target_type, target_id, profile_id))
        return self.exists


async def test_list_revisions_and_snapshots_are_immutable_and_idempotent(
    runtime_factory,
) -> None:
    ids = SequenceIdGenerator(uid(value) for value in range(100, 140))
    service = SqlExchangeService(runtime_factory, ids=ids)
    command = CreateVocabularyList(
        variety_id=TARGET_VARIETY,
        list_type="manual",
        name="Voyage en train",
        purpose="Préparer le module arrivée",
        ordered=True,
        color="#287271",
        tags=("voyage",),
        query_definition=None,
        member_sense_ids=(uid(501), uid(502)),
        created_at=NOW,
    )

    created = await service.create_list(
        ACCOUNT_A, PROFILE_A, command, idempotency_key="list-create"
    )
    replay = await service.create_list(
        ACCOUNT_A, PROFILE_A, command, idempotency_key="list-create"
    )
    revised = await service.change_members(
        ACCOUNT_A,
        created.list_id,
        ChangeListMembers(
            add_sense_ids=(uid(503),),
            remove_sense_ids=(uid(501),),
            changed_at=NOW + timedelta(minutes=1),
        ),
        expected_version=1,
        idempotency_key="list-members",
    )
    snapshot = await service.freeze_list(
        ACCOUNT_A,
        created.list_id,
        expected_version=2,
        frozen_at=NOW + timedelta(minutes=2),
        idempotency_key="list-freeze",
    )

    assert replay == created
    assert revised.version == 2
    assert revised.member_sense_ids == (uid(502), uid(503))
    assert snapshot.source_revision_id == revised.revision_id
    assert snapshot.member_sense_revision_ids == revised.member_sense_ids


async def test_exchange_command_records_event_and_outbox_atomically(
    runtime_factory,
    migration_session,
) -> None:
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(140, 180)),
    )

    created = await service.create_list(
        ACCOUNT_A,
        PROFILE_A,
        CreateVocabularyList(
            variety_id=TARGET_VARIETY,
            list_type="manual",
            name="Audit",
            purpose="Prouver la reconstruction",
            ordered=True,
            color=None,
            tags=(),
            query_definition=None,
            member_sense_ids=(),
            created_at=NOW,
        ),
        idempotency_key="audit-create",
    )
    await set_actor(migration_session, ACCOUNT_A)
    event = (
        await migration_session.execute(
            text(
                "SELECT event.event_type,event.aggregate_id,outbox.destination "
                "FROM platform.domain_events event JOIN platform.outbox_messages outbox "
                "ON outbox.event_id=event.event_id WHERE event.aggregate_id=:aggregate"
            ),
            {"aggregate": created.list_id},
        )
    ).one()

    assert event.event_type == "vocabulary_list_created"
    assert event.aggregate_id == created.list_id
    assert event.destination == "learning-events"

    clone = await service.execute_command(
        command_name="CloneVocabularyList",
        actor_id=ACCOUNT_A,
        resource_id=created.list_id,
        payload={
            "target_profile_id": PROFILE_A,
            "name": "Audit copie",
            "cloned_at": NOW + timedelta(minutes=1),
        },
        idempotency_key="audit-clone",
        expected_version=None,
    )
    clone_event = await migration_session.scalar(
        text(
            "SELECT event_type FROM platform.domain_events "
            "WHERE aggregate_id=:aggregate"
        ),
        {"aggregate": clone.resource_id},
    )

    assert clone_event == "vocabulary_list_cloned"


async def test_import_preview_commit_and_revert_are_atomic(runtime_factory) -> None:
    ids = SequenceIdGenerator(uid(value) for value in range(200, 260))
    service = SqlExchangeService(runtime_factory, ids=ids)
    payload = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": [
                {
                    "source_key": "treno",
                    "variety_id": str(TARGET_VARIETY),
                    "unit_type": "word",
                    "form": "treno",
                    "semantic_key": "transport.train",
                    "visibility": "private",
                }
            ],
        }
    ).encode()
    preview = await service.create_import(
        ACCOUNT_A,
        PROFILE_A,
        CreateImport(
            format_id="polyglot.lexicon.bundle/v1",
            encoding="utf-8",
            payload=payload,
            strategy=ImportStrategy.INTERACTIVE,
            catalogue_version="catalogue:17",
            created_at=NOW,
            expires_at=NOW + timedelta(hours=2),
        ),
        idempotency_key="import-create",
    )
    committed = await service.commit_import(
        ACCOUNT_A,
        preview.import_id,
        preview_checksum=preview.preview_checksum,
        current_catalogue_version="catalogue:17",
        expected_version=1,
        committed_at=NOW + timedelta(minutes=1),
        idempotency_key="import-commit",
    )
    reverted = await service.revert_import(
        ACCOUNT_A,
        preview.import_id,
        expected_version=2,
        reverted_at=NOW + timedelta(minutes=2),
        idempotency_key="import-revert",
    )

    assert preview.status == "preview_ready"
    assert committed.status == "committed"
    assert len(committed.created_refs) == 2
    assert reverted.status == "reverted"


async def test_stale_preview_and_reused_resource_block_commit_or_revert(
    runtime_factory,
) -> None:
    ids = SequenceIdGenerator(uid(value) for value in range(300, 360))
    service = SqlExchangeService(runtime_factory, ids=ids)
    payload = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": [
                {
                    "source_key": "binario",
                    "variety_id": str(TARGET_VARIETY),
                    "form": "binario",
                }
            ],
        }
    ).encode()
    preview = await service.create_import(
        ACCOUNT_A,
        PROFILE_A,
        CreateImport(
            format_id="polyglot.lexicon.bundle/v1",
            encoding="utf-8",
            payload=payload,
            strategy=ImportStrategy.INTERACTIVE,
            catalogue_version="catalogue:17",
            created_at=NOW,
            expires_at=NOW + timedelta(hours=2),
        ),
        idempotency_key="stale-create",
    )

    with pytest.raises(DomainError) as stale:
        await service.commit_import(
            ACCOUNT_A,
            preview.import_id,
            preview_checksum=preview.preview_checksum,
            current_catalogue_version="catalogue:18",
            expected_version=1,
            committed_at=NOW + timedelta(minutes=1),
            idempotency_key="stale-commit",
        )
    assert stale.value.code is ErrorCode.PREVIEW_STALE


async def test_revert_refuses_a_created_sense_reused_by_a_list(runtime_factory) -> None:
    ids = SequenceIdGenerator(uid(value) for value in range(400, 490))
    service = SqlExchangeService(runtime_factory, ids=ids)
    payload = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": [
                {
                    "source_key": "ritardo",
                    "variety_id": str(TARGET_VARIETY),
                    "form": "ritardo",
                }
            ],
        }
    ).encode()
    preview = await service.create_import(
        ACCOUNT_A,
        PROFILE_A,
        CreateImport(
            format_id="polyglot.lexicon.bundle/v1",
            encoding="utf-8",
            payload=payload,
            strategy=ImportStrategy.INTERACTIVE,
            catalogue_version="catalogue:17",
            created_at=NOW,
            expires_at=NOW + timedelta(hours=2),
        ),
        idempotency_key="reuse-create",
    )
    committed = await service.commit_import(
        ACCOUNT_A,
        preview.import_id,
        preview_checksum=preview.preview_checksum,
        current_catalogue_version="catalogue:17",
        expected_version=1,
        committed_at=NOW + timedelta(minutes=1),
        idempotency_key="reuse-commit",
    )
    sense_id = UUID(
        next(ref for ref in committed.created_refs if ref.startswith("lexical_sense:")).split(
            ":", 1
        )[1]
    )
    await service.create_list(
        ACCOUNT_A,
        PROFILE_A,
        CreateVocabularyList(
            variety_id=TARGET_VARIETY,
            list_type="manual",
            name="Retards",
            purpose="Réemploi explicite",
            ordered=True,
            color=None,
            tags=(),
            query_definition=None,
            member_sense_ids=(sense_id,),
            created_at=NOW + timedelta(minutes=2),
        ),
        idempotency_key="reuse-list",
    )

    with pytest.raises(DomainError) as reused:
        await service.revert_import(
            ACCOUNT_A,
            preview.import_id,
            expected_version=2,
            reverted_at=NOW + timedelta(minutes=3),
            idempotency_key="reuse-revert",
        )

    assert reused.value.code is ErrorCode.RESOURCE_REUSED


async def test_reuse_exact_records_existing_refs_without_creating_duplicates(
    runtime_factory,
) -> None:
    ids = SequenceIdGenerator(uid(value) for value in range(500, 590))
    service = SqlExchangeService(runtime_factory, ids=ids)
    payload = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": [
                {
                    "source_key": "treno",
                    "variety_id": str(TARGET_VARIETY),
                    "unit_type": "word",
                    "form": "treno",
                    "semantic_key": "transport.train",
                    "visibility": "private",
                }
            ],
        }
    ).encode()

    original = await service.create_import(
        ACCOUNT_A,
        PROFILE_A,
        CreateImport(
            format_id="polyglot.lexicon.bundle/v1",
            encoding="utf-8",
            payload=payload,
            strategy=ImportStrategy.INTERACTIVE,
            catalogue_version="catalogue:17",
            created_at=NOW,
            expires_at=NOW + timedelta(hours=2),
        ),
        idempotency_key="reuse-exact-original",
    )
    original = await service.commit_import(
        ACCOUNT_A,
        original.import_id,
        preview_checksum=original.preview_checksum,
        current_catalogue_version="catalogue:17",
        expected_version=1,
        committed_at=NOW + timedelta(minutes=1),
        idempotency_key="reuse-exact-original-commit",
    )
    duplicate = await service.create_import(
        ACCOUNT_A,
        PROFILE_A,
        CreateImport(
            format_id="polyglot.lexicon.bundle/v1",
            encoding="utf-8",
            payload=payload,
            strategy=ImportStrategy.REUSE_EXACT,
            catalogue_version="catalogue:17",
            created_at=NOW + timedelta(minutes=2),
            expires_at=NOW + timedelta(hours=2),
        ),
        idempotency_key="reuse-exact-duplicate",
    )
    duplicate = await service.commit_import(
        ACCOUNT_A,
        duplicate.import_id,
        preview_checksum=duplicate.preview_checksum,
        current_catalogue_version="catalogue:17",
        expected_version=1,
        committed_at=NOW + timedelta(minutes=3),
        idempotency_key="reuse-exact-duplicate-commit",
    )

    assert duplicate.created_refs == ()
    assert duplicate.reused_refs == tuple(
        ref for ref in original.created_refs if ref.startswith("lexical_sense:")
    )


async def test_interactive_reuse_resolves_conflict_before_commit(
    runtime_factory,
    migration_session,
) -> None:
    ids = SequenceIdGenerator(uid(value) for value in range(600, 700))
    service = SqlExchangeService(runtime_factory, ids=ids)
    payload = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": [
                {
                    "source_key": "binario",
                    "variety_id": str(TARGET_VARIETY),
                    "form": "binario",
                    "semantic_key": "rail.platform",
                }
            ],
        }
    ).encode()
    first = await service.create_import(
        ACCOUNT_A,
        PROFILE_A,
        CreateImport(
            format_id="polyglot.lexicon.bundle/v1",
            encoding="utf-8",
            payload=payload,
            strategy=ImportStrategy.INTERACTIVE,
            catalogue_version="catalogue:17",
            created_at=NOW,
            expires_at=NOW + timedelta(hours=2),
        ),
        idempotency_key="interactive-original",
    )
    first = await service.commit_import(
        ACCOUNT_A,
        first.import_id,
        preview_checksum=first.preview_checksum,
        current_catalogue_version="catalogue:17",
        expected_version=1,
        committed_at=NOW + timedelta(minutes=1),
        idempotency_key="interactive-original-commit",
    )
    duplicate = await service.create_import(
        ACCOUNT_A,
        PROFILE_A,
        CreateImport(
            format_id="polyglot.lexicon.bundle/v1",
            encoding="utf-8",
            payload=payload,
            strategy=ImportStrategy.INTERACTIVE,
            catalogue_version="catalogue:17",
            created_at=NOW + timedelta(minutes=2),
            expires_at=NOW + timedelta(hours=2),
        ),
        idempotency_key="interactive-duplicate",
    )
    assert duplicate.status == "awaiting_decision"
    await set_actor(migration_session, ACCOUNT_A)
    conflict_id = await migration_session.scalar(
        text(
            "SELECT conflict.conflict_id FROM exchange.import_conflicts conflict "
            "JOIN exchange.import_lines line "
            "ON line.import_line_id=conflict.import_line_id "
            "WHERE line.import_id=:import"
        ),
        {"import": duplicate.import_id},
    )
    assert conflict_id is not None

    resolved = await service.execute_command(
        command_name="ResolveImportConflict",
        actor_id=ACCOUNT_A,
        resource_id=conflict_id,
        payload={
            "import_id": duplicate.import_id,
            "preview_checksum": duplicate.preview_checksum,
            "action": "reuse_exact",
            "decided_at": NOW + timedelta(minutes=3),
        },
        idempotency_key="interactive-resolve",
        expected_version=1,
    )
    committed = await service.commit_import(
        ACCOUNT_A,
        duplicate.import_id,
        preview_checksum=duplicate.preview_checksum,
        current_catalogue_version="catalogue:17",
        expected_version=2,
        committed_at=NOW + timedelta(minutes=4),
        idempotency_key="interactive-commit",
    )

    assert resolved.status == "resolved"
    assert committed.created_refs == ()
    assert committed.reused_refs == tuple(
        ref for ref in first.created_refs if ref.startswith("lexical_sense:")
    )


async def test_published_snapshot_is_public_until_explicit_retirement(
    runtime_factory,
) -> None:
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(700, 780)),
    )
    vocabulary_list = await service.create_list(
        ACCOUNT_A,
        PROFILE_A,
        CreateVocabularyList(
            variety_id=TARGET_VARIETY,
            list_type="editorial",
            name="Arrivée en Italie",
            purpose="Liste publique sans contexte privé",
            ordered=True,
            color=None,
            tags=("arrivee",),
            query_definition=None,
            member_sense_ids=(),
            created_at=NOW,
        ),
        idempotency_key="public-list",
    )
    snapshot = await service.freeze_list(
        ACCOUNT_A,
        vocabulary_list.list_id,
        expected_version=1,
        frozen_at=NOW + timedelta(minutes=1),
        idempotency_key="public-snapshot",
    )
    publication = await service.execute_command(
        command_name="PublishVocabularyListSnapshot",
        actor_id=ACCOUNT_A,
        resource_id=snapshot.snapshot_id,
        payload={
            "list_id": vocabulary_list.list_id,
            "license_ref": "CC-BY-4.0",
            "provenance_id": uid(990),
            "published_at": NOW + timedelta(minutes=2),
        },
        idempotency_key="public-publish",
        expected_version=1,
    )

    visible, _ = await service.list_resources(
        actor_id=ACCOUNT_B,
        resource_type="shared_list",
        profile_id=None,
        limit=10,
        cursor=None,
    )
    assert tuple(item["publication_id"] for item in visible) == (
        str(publication.resource_id),
    )

    retired = await service.execute_command(
        command_name="RetireSharedVocabularyList",
        actor_id=ACCOUNT_A,
        resource_id=publication.resource_id,
        payload={"at": NOW + timedelta(minutes=3)},
        idempotency_key="public-retire",
        expected_version=1,
    )
    hidden, _ = await service.list_resources(
        actor_id=ACCOUNT_B,
        resource_type="shared_list",
        profile_id=None,
        limit=10,
        cursor=None,
    )

    assert retired.status == "retired"
    assert hidden == ()


async def test_export_requires_recent_session_and_replays_one_request(
    runtime_factory,
    migration_session,
) -> None:
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(810, 860)),
    )
    session_id = uid(800)
    await set_actor(migration_session, ACCOUNT_A)
    await migration_session.execute(
        text(
            "INSERT INTO identity.auth_sessions "
            "(session_id,account_id,session_fingerprint,csrf_secret_hash,roles_snapshot,"
            "account_session_version,created_at,authenticated_at,last_seen_at,rotated_at,"
            "idle_expires_at,absolute_expires_at) VALUES "
            "(:session,:account,:fingerprint,:csrf,ARRAY['learner']::varchar[],1,"
            ":at,:at,:at,:at,:idle,:absolute)"
        ),
        {
            "session": session_id,
            "account": ACCOUNT_A,
            "fingerprint": "a" * 64,
            "csrf": "b" * 64,
            "at": NOW,
            "idle": NOW + timedelta(hours=1),
            "absolute": NOW + timedelta(days=7),
        },
    )
    await migration_session.commit()

    with pytest.raises(DomainError) as missing_session:
        await service.execute_command(
            command_name="RequestExport",
            actor_id=ACCOUNT_A,
            resource_id=PROFILE_A,
            payload={
                "scope": {"word_bank": True},
                "requested_at": NOW + timedelta(minutes=5),
            },
            idempotency_key="export-missing-session",
            expected_version=None,
        )
    assert missing_session.value.code is ErrorCode.UNAUTHENTICATED

    requested = await service.execute_command(
        command_name="RequestExport",
        actor_id=ACCOUNT_A,
        resource_id=PROFILE_A,
        payload={
            "scope": {"word_bank": True},
            "requested_at": NOW + timedelta(minutes=5),
        },
        idempotency_key="export-valid",
        expected_version=None,
        session_id=session_id,
    )
    replay = await service.execute_command(
        command_name="RequestExport",
        actor_id=ACCOUNT_A,
        resource_id=PROFILE_A,
        payload={
            "scope": {"word_bank": True},
            "requested_at": NOW + timedelta(minutes=5),
        },
        idempotency_key="export-valid",
        expected_version=None,
        session_id=session_id,
    )

    assert requested.status == "requested"
    assert replay.resource_id == requested.resource_id


async def test_list_association_verifies_target_and_versions_list(
    runtime_factory,
    migration_session,
) -> None:
    verifier = TargetVerifier()
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(900, 960)),
        association_targets=verifier,
    )
    vocabulary_list = await service.create_list(
        ACCOUNT_A,
        PROFILE_A,
        CreateVocabularyList(
            variety_id=TARGET_VARIETY,
            list_type="manual",
            name="Module ferroviaire",
            purpose="Contexte lexical explicite",
            ordered=True,
            color=None,
            tags=(),
            query_definition=None,
            member_sense_ids=(),
            created_at=NOW,
        ),
        idempotency_key="association-list",
    )
    target_id = uid(980)

    association = await service.associate_list(
        ACCOUNT_A,
        vocabulary_list.list_id,
        AssociateVocabularyList(
            target_type="module_revision",
            target_id=target_id,
            role="target",
            valid_from=NOW + timedelta(minutes=1),
            valid_until=None,
        ),
        expected_version=1,
        idempotency_key="association-create",
    )
    await set_actor(migration_session, ACCOUNT_A)
    stored = (
        await migration_session.execute(
            text(
                "SELECT target_type,target_id,role FROM lexicon.list_associations "
                "WHERE association_id=:association"
            ),
            {"association": association.resource_id},
        )
    ).one()

    assert association.version == 2
    assert verifier.calls == [("module_revision", target_id, PROFILE_A)]
    assert tuple(stored) == ("module_revision", target_id, "target")


async def test_archiving_list_preserves_snapshot_and_replays_exact_status(
    runtime_factory,
    migration_session,
) -> None:
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(1000, 1060)),
    )
    vocabulary_list = await service.create_list(
        ACCOUNT_A,
        PROFILE_A,
        CreateVocabularyList(
            variety_id=TARGET_VARIETY,
            list_type="manual",
            name="Archive",
            purpose="Historique conservé",
            ordered=True,
            color=None,
            tags=(),
            query_definition=None,
            member_sense_ids=(),
            created_at=NOW,
        ),
        idempotency_key="archive-list",
    )
    snapshot = await service.freeze_list(
        ACCOUNT_A,
        vocabulary_list.list_id,
        expected_version=1,
        frozen_at=NOW + timedelta(minutes=1),
        idempotency_key="archive-snapshot",
    )
    payload = {"at": NOW + timedelta(minutes=2)}
    archived = await service.execute_command(
        command_name="ArchiveVocabularyList",
        actor_id=ACCOUNT_A,
        resource_id=vocabulary_list.list_id,
        payload=payload,
        idempotency_key="archive-command",
        expected_version=1,
    )
    replay = await service.execute_command(
        command_name="ArchiveVocabularyList",
        actor_id=ACCOUNT_A,
        resource_id=vocabulary_list.list_id,
        payload=payload,
        idempotency_key="archive-command",
        expected_version=1,
    )
    current = await service.get_list(ACCOUNT_A, vocabulary_list.list_id)
    await set_actor(migration_session, ACCOUNT_A)
    snapshot_count = await migration_session.scalar(
        text("SELECT count(*) FROM lexicon.list_snapshots WHERE snapshot_id=:id"),
        {"id": snapshot.snapshot_id},
    )

    assert archived == replay
    assert archived.status == "archived"
    assert current.status == "archived"
    assert current.version == 2
    assert snapshot_count == 1
