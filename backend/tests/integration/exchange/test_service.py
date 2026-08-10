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
from polyglot.modules.lexicon.exchange.ports import (
    ResolvedLexicalCandidate,
    StoredPrivateArtifact,
)
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


class DynamicListEvaluator:
    def __init__(self, members: tuple[UUID, ...]) -> None:
        self.members = members
        self.calls: list[tuple[UUID, dict[str, object], object, int]] = []

    async def evaluate(
        self,
        profile_id: UUID,
        query_definition: dict[str, object],
        cutoff_at,
        limit: int,
    ) -> tuple[UUID, ...]:
        self.calls.append((profile_id, query_definition, cutoff_at, limit))
        return self.members


class LexicalMutationRecorder:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    async def create_imported_entry(self, command, *, session):
        self.calls.append(command)
        if self.fail:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return (
            f"lexical_unit:{uid(901)}",
            f"lexical_sense:{uid(902)}",
        )


class PrivateArtifactRecorder:
    def __init__(self, *, encryption_scheme: str = "aes-256-gcm/v1") -> None:
        self.encryption_scheme = encryption_scheme
        self.calls = []

    async def store_encrypted_export(
        self,
        *,
        export_id,
        profile_id,
        payload,
        expires_at,
    ) -> StoredPrivateArtifact:
        self.calls.append((export_id, profile_id, payload, expires_at))
        return StoredPrivateArtifact(
            media_revision_id=uid(1880),
            encryption_scheme=self.encryption_scheme,
            checksum_sha256="e" * 64,
        )


class LexicalReferenceRecorder:
    def __init__(self, candidates: tuple[ResolvedLexicalCandidate, ...] = ()) -> None:
        self.candidates = candidates
        self.calls = []

    async def list_import_candidates(self, profile_id, *, session):
        self.calls.append(profile_id)
        return self.candidates


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
    replay = await service.create_list(ACCOUNT_A, PROFILE_A, command, idempotency_key="list-create")
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
        text("SELECT event_type FROM platform.domain_events WHERE aggregate_id=:aggregate"),
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


async def test_import_preview_does_not_call_lexical_mutation_port(runtime_factory) -> None:
    mutations = LexicalMutationRecorder()
    service = SqlExchangeService(runtime_factory, lexical_mutations=mutations)
    payload = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": [
                {
                    "source_key": "binario",
                    "variety_id": str(TARGET_VARIETY),
                    "unit_type": "word",
                    "form": "binario",
                    "semantic_key": "transport.platform",
                    "visibility": "private",
                }
            ],
        }
    ).encode()

    await service.create_import(
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
        idempotency_key="import-preview-no-mutation",
    )

    assert mutations.calls == []


async def test_import_preview_reads_candidates_through_lexical_reference_port(
    runtime_factory,
) -> None:
    references = LexicalReferenceRecorder()
    service = SqlExchangeService(runtime_factory, lexical_references=references)
    payload = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": [
                {
                    "source_key": "binario",
                    "variety_id": str(TARGET_VARIETY),
                    "unit_type": "word",
                    "form": "binario",
                    "semantic_key": "transport.platform",
                    "visibility": "private",
                }
            ],
        }
    ).encode()

    await service.create_import(
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
        idempotency_key="import-reference-port",
    )

    assert references.calls == [PROFILE_A]


async def test_import_preview_lines_are_paginated_and_owner_scoped(runtime_factory) -> None:
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(1900, 1980)),
    )
    payload = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": [
                {
                    "source_key": source_key,
                    "variety_id": str(TARGET_VARIETY),
                    "unit_type": "word",
                    "form": source_key,
                    "semantic_key": semantic_key,
                    "visibility": "private",
                }
                for source_key, semantic_key in (
                    ("binario", "transport.platform"),
                    ("biglietto", "transport.ticket"),
                )
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
        idempotency_key="import-lines-preview",
    )

    first, cursor = await service.get_import_preview(
        ACCOUNT_A,
        preview.import_id,
        limit=1,
        cursor=None,
    )
    second, final_cursor = await service.get_import_preview(
        ACCOUNT_A,
        preview.import_id,
        limit=1,
        cursor=cursor,
    )

    assert first[0]["line_no"] == 1
    assert first[0]["intermediate_payload"]["normalized_form"] == "binario"
    assert cursor == "1"
    assert second[0]["line_no"] == 2
    assert final_cursor is None
    with pytest.raises(DomainError) as hidden:
        await service.get_import_preview(
            ACCOUNT_B,
            preview.import_id,
            limit=10,
            cursor=None,
        )
    assert hidden.value.code is ErrorCode.NOT_FOUND


async def test_import_commit_uses_lexical_mutation_port(runtime_factory) -> None:
    mutations = LexicalMutationRecorder()
    service = SqlExchangeService(runtime_factory, lexical_mutations=mutations)
    payload = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": [
                {
                    "source_key": "binario",
                    "variety_id": str(TARGET_VARIETY),
                    "unit_type": "word",
                    "form": "binario",
                    "semantic_key": "transport.platform",
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
        idempotency_key="import-port-preview",
    )

    committed = await service.commit_import(
        ACCOUNT_A,
        preview.import_id,
        preview_checksum=preview.preview_checksum,
        current_catalogue_version="catalogue:17",
        expected_version=1,
        committed_at=NOW + timedelta(minutes=1),
        idempotency_key="import-port-commit",
    )

    assert committed.created_refs == (
        f"lexical_unit:{uid(901)}",
        f"lexical_sense:{uid(902)}",
    )
    assert len(mutations.calls) == 1
    assert mutations.calls[0].profile_id == PROFILE_A
    assert mutations.calls[0].normalized_form == "binario"
    assert mutations.calls[0].semantic_key == "transport.platform"


async def test_lexical_mutation_failure_rolls_back_import_commit(
    runtime_factory, migration_session
) -> None:
    mutations = LexicalMutationRecorder(fail=True)
    service = SqlExchangeService(runtime_factory, lexical_mutations=mutations)
    payload = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": [
                {
                    "source_key": "binario",
                    "variety_id": str(TARGET_VARIETY),
                    "unit_type": "word",
                    "form": "binario",
                    "semantic_key": "transport.platform",
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
        idempotency_key="import-port-failure-preview",
    )

    with pytest.raises(DomainError) as raised:
        await service.commit_import(
            ACCOUNT_A,
            preview.import_id,
            preview_checksum=preview.preview_checksum,
            current_catalogue_version="catalogue:17",
            expected_version=1,
            committed_at=NOW + timedelta(minutes=1),
            idempotency_key="import-port-failure-commit",
        )

    assert raised.value.code == ErrorCode.INVALID_TRANSITION
    await set_actor(migration_session, ACCOUNT_A)
    status = await migration_session.scalar(
        text("SELECT status FROM exchange.import_runs WHERE import_id=:id"),
        {"id": preview.import_id},
    )
    manifests = await migration_session.scalar(
        text("SELECT count(*) FROM exchange.import_manifests WHERE import_id=:id"),
        {"id": preview.import_id},
    )
    assert status == "preview_ready"
    assert manifests == 0


async def test_tampered_import_manifest_is_rejected_before_revert(
    runtime_factory,
    migration_session,
) -> None:
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(1600, 1670)),
    )
    payload = json.dumps(
        {
            "format": "polyglot.lexicon.bundle/v1",
            "schema_version": 1,
            "entries": [
                {
                    "source_key": "biglietto",
                    "variety_id": str(TARGET_VARIETY),
                    "unit_type": "word",
                    "form": "biglietto",
                    "semantic_key": "transport.ticket",
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
        idempotency_key="tamper-preview",
    )
    committed = await service.commit_import(
        ACCOUNT_A,
        preview.import_id,
        preview_checksum=preview.preview_checksum,
        current_catalogue_version="catalogue:17",
        expected_version=1,
        committed_at=NOW + timedelta(minutes=1),
        idempotency_key="tamper-commit",
    )

    await set_actor(migration_session, ACCOUNT_A)
    await migration_session.execute(
        text("ALTER TABLE exchange.import_manifests DISABLE TRIGGER USER")
    )
    try:
        await migration_session.execute(
            text(
                "UPDATE exchange.import_manifests SET inverse_operations='[]'::jsonb "
                "WHERE import_id=:id"
            ),
            {"id": preview.import_id},
        )
        await migration_session.commit()
    finally:
        await migration_session.execute(
            text("ALTER TABLE exchange.import_manifests ENABLE TRIGGER USER")
        )
        await migration_session.commit()

    with pytest.raises(DomainError) as rejected:
        await service.revert_import(
            ACCOUNT_A,
            preview.import_id,
            expected_version=committed.version,
            reverted_at=NOW + timedelta(minutes=2),
            idempotency_key="tamper-revert",
        )

    assert rejected.value.code is ErrorCode.VALIDATION_FAILED


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
            list_type="manual",
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
    assert tuple(item["publication_id"] for item in visible) == (str(publication.resource_id),)

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


async def test_export_becomes_ready_only_after_encrypted_private_storage(
    runtime_factory,
    migration_session,
) -> None:
    artifacts = PrivateArtifactRecorder()
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(1700, 1780)),
        private_artifacts=artifacts,
    )
    session_id = uid(1690)
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
            "fingerprint": "c" * 64,
            "csrf": "d" * 64,
            "at": NOW,
            "idle": NOW + timedelta(hours=1),
            "absolute": NOW + timedelta(days=7),
        },
    )
    await migration_session.commit()
    requested = await service.execute_command(
        command_name="RequestExport",
        actor_id=ACCOUNT_A,
        resource_id=PROFILE_A,
        payload={
            "scope": {"word_bank": True, "vocabulary_lists": True},
            "requested_at": NOW + timedelta(minutes=1),
        },
        idempotency_key="encrypted-export-request",
        expected_version=None,
        session_id=session_id,
    )

    ready = await service.complete_export(
        ACCOUNT_A,
        requested.resource_id,
        completed_at=NOW + timedelta(minutes=2),
    )
    replay = await service.complete_export(
        ACCOUNT_A,
        requested.resource_id,
        completed_at=NOW + timedelta(minutes=3),
    )

    exported = json.loads(artifacts.calls[0][2])
    assert ready.status == "ready"
    assert replay.status == "ready"
    assert len(artifacts.calls) == 1
    assert exported["format"] == "polyglot.user.export/v1"
    assert exported["scope"] == ["vocabulary_lists", "word_bank"]
    await set_actor(migration_session, ACCOUNT_A)
    row = (
        await migration_session.execute(
            text(
                "SELECT run.status,artifact.encryption_scheme FROM exchange.export_runs run "
                "JOIN exchange.export_artifacts artifact USING (export_id) "
                "WHERE run.export_id=:id"
            ),
            {"id": requested.resource_id},
        )
    ).one()
    assert tuple(row) == ("ready", "aes-256-gcm/v1")


async def test_plaintext_export_attestation_marks_run_failed(
    runtime_factory,
    migration_session,
) -> None:
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(1800, 1870)),
        private_artifacts=PrivateArtifactRecorder(encryption_scheme="plaintext"),
    )
    session_id = uid(1790)
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
            "fingerprint": "f" * 64,
            "csrf": "1" * 64,
            "at": NOW,
            "idle": NOW + timedelta(hours=1),
            "absolute": NOW + timedelta(days=7),
        },
    )
    await migration_session.commit()
    requested = await service.execute_command(
        command_name="RequestExport",
        actor_id=ACCOUNT_A,
        resource_id=PROFILE_A,
        payload={"scope": {"word_bank": True}, "requested_at": NOW},
        idempotency_key="plaintext-export-request",
        expected_version=None,
        session_id=session_id,
    )

    with pytest.raises(DomainError) as rejected:
        await service.complete_export(
            ACCOUNT_A,
            requested.resource_id,
            completed_at=NOW + timedelta(minutes=1),
        )

    assert rejected.value.code is ErrorCode.VALIDATION_FAILED
    await set_actor(migration_session, ACCOUNT_A)
    status = await migration_session.scalar(
        text("SELECT status FROM exchange.export_runs WHERE export_id=:id"),
        {"id": requested.resource_id},
    )
    artifacts = await migration_session.scalar(
        text("SELECT count(*) FROM exchange.export_artifacts WHERE export_id=:id"),
        {"id": requested.resource_id},
    )
    assert status == "failed"
    assert artifacts == 0


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


@pytest.mark.parametrize(
    ("list_type", "query_definition", "code"),
    (
        ("manual", {"tag_in": ["voyage"]}, ErrorCode.VALIDATION_FAILED),
        ("dynamic", {"sql": "SELECT *"}, ErrorCode.VALIDATION_FAILED),
        ("editorial", None, ErrorCode.FORBIDDEN),
    ),
)
async def test_persisted_list_types_enforce_domain_policy(
    runtime_factory,
    list_type,
    query_definition,
    code,
) -> None:
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(1100, 1160)),
    )

    with pytest.raises(DomainError) as rejected:
        await service.create_list(
            ACCOUNT_A,
            PROFILE_A,
            CreateVocabularyList(
                variety_id=TARGET_VARIETY,
                list_type=list_type,
                name="Politique",
                purpose="Valider le domaine avant persistance",
                ordered=True,
                color=None,
                tags=(),
                query_definition=query_definition,
                member_sense_ids=(),
                created_at=NOW,
            ),
            idempotency_key=f"policy-{list_type}",
        )

    assert rejected.value.code is code


async def test_author_can_create_editorial_and_learner_can_create_dynamic_list(
    runtime_factory,
    migration_session,
) -> None:
    await set_actor(migration_session, ACCOUNT_A)
    await migration_session.execute(
        text(
            "INSERT INTO identity.account_roles "
            "(role_grant_id,account_id,role,granted_at,granted_by_actor_id) "
            "VALUES (:grant,:account,'author',:at,:account)"
        ),
        {"grant": uid(1190), "account": ACCOUNT_A, "at": NOW},
    )
    await migration_session.commit()
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(1200, 1280)),
    )

    editorial = await service.create_list(
        ACCOUNT_A,
        PROFILE_A,
        CreateVocabularyList(
            variety_id=TARGET_VARIETY,
            list_type="editorial",
            name="Éditorial",
            purpose="Publication contrôlée",
            ordered=True,
            color=None,
            tags=(),
            query_definition=None,
            member_sense_ids=(),
            created_at=NOW,
        ),
        idempotency_key="editorial-valid",
    )
    dynamic = await service.create_list(
        ACCOUNT_A,
        PROFILE_A,
        CreateVocabularyList(
            variety_id=TARGET_VARIETY,
            list_type="dynamic",
            name="Rappels voyage",
            purpose="Sélection bornée",
            ordered=False,
            color=None,
            tags=(),
            query_definition={
                "all": [
                    {"tag_in": ["voyage"]},
                    {"has_due_prompt": True},
                ]
            },
            member_sense_ids=(),
            created_at=NOW + timedelta(minutes=1),
        ),
        idempotency_key="dynamic-valid",
    )

    assert editorial.list_type == "editorial"
    assert dynamic.list_type == "dynamic"
    assert dynamic.query_definition == {"all": [{"tag_in": ["voyage"]}, {"has_due_prompt": True}]}
    revised = await service.execute_command(
        command_name="ReviseVocabularyList",
        actor_id=ACCOUNT_A,
        resource_id=dynamic.list_id,
        payload={
            "name": "Rappels voyage prioritaires",
            "revised_at": NOW + timedelta(minutes=2),
        },
        idempotency_key="dynamic-revise",
        expected_version=1,
    )
    current = await service.get_list(ACCOUNT_A, dynamic.list_id)
    assert revised.version == 2
    assert current.query_definition == dynamic.query_definition

    with pytest.raises(DomainError) as explicit_members:
        await service.change_members(
            ACCOUNT_A,
            dynamic.list_id,
            ChangeListMembers(
                add_sense_ids=(uid(1290),),
                remove_sense_ids=(),
                changed_at=NOW + timedelta(minutes=3),
            ),
            expected_version=2,
            idempotency_key="dynamic-members",
        )
    assert explicit_members.value.code is ErrorCode.INVALID_TRANSITION

    await set_actor(migration_session, ACCOUNT_A)
    await migration_session.execute(
        text(
            "UPDATE identity.account_roles SET revoked_at=:at "
            "WHERE account_id=:account AND role='author'"
        ),
        {"at": NOW + timedelta(minutes=4), "account": ACCOUNT_A},
    )
    await migration_session.commit()
    with pytest.raises(DomainError) as revoked_author:
        await service.execute_command(
            command_name="ArchiveVocabularyList",
            actor_id=ACCOUNT_A,
            resource_id=editorial.list_id,
            payload={"at": NOW + timedelta(minutes=5)},
            idempotency_key="editorial-archive-revoked",
            expected_version=1,
        )
    assert revoked_author.value.code is ErrorCode.FORBIDDEN


async def test_dynamic_snapshot_freezes_port_result_at_cutoff(runtime_factory) -> None:
    evaluator = DynamicListEvaluator((uid(1300), uid(1301)))
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(1310, 1380)),
        dynamic_lists=evaluator,
    )
    dynamic = await service.create_list(
        ACCOUNT_A,
        PROFILE_A,
        CreateVocabularyList(
            variety_id=TARGET_VARIETY,
            list_type="dynamic",
            name="À revoir",
            purpose="Résultat exact au cutoff",
            ordered=False,
            color=None,
            tags=(),
            query_definition={"has_due_prompt": True},
            member_sense_ids=(),
            created_at=NOW,
        ),
        idempotency_key="dynamic-cutoff-list",
    )

    snapshot = await service.freeze_list(
        ACCOUNT_A,
        dynamic.list_id,
        expected_version=1,
        frozen_at=NOW + timedelta(minutes=1),
        idempotency_key="dynamic-cutoff-snapshot",
    )

    assert snapshot.member_sense_revision_ids == (uid(1300), uid(1301))
    assert evaluator.calls == [
        (PROFILE_A, {"has_due_prompt": True}, NOW + timedelta(minutes=1), 10_000)
    ]


async def test_dynamic_preview_is_bounded_and_does_not_create_snapshot(
    runtime_factory,
    migration_session,
) -> None:
    evaluator = DynamicListEvaluator((uid(1400), uid(1401), uid(1402)))
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(1410, 1480)),
        dynamic_lists=evaluator,
    )
    dynamic = await service.create_list(
        ACCOUNT_A,
        PROFILE_A,
        CreateVocabularyList(
            variety_id=TARGET_VARIETY,
            list_type="dynamic",
            name="Aperçu des rappels",
            purpose="Lecture sans mutation",
            ordered=False,
            color=None,
            tags=(),
            query_definition={"has_due_prompt": True},
            member_sense_ids=(),
            created_at=NOW,
        ),
        idempotency_key="dynamic-preview-list",
    )

    preview = await service.preview_dynamic_list(
        ACCOUNT_A,
        dynamic.list_id,
        cutoff_at=NOW + timedelta(minutes=1),
        limit=2,
    )

    await set_actor(migration_session, ACCOUNT_A)
    snapshots = await migration_session.scalar(
        text("SELECT count(*) FROM lexicon.list_snapshots WHERE list_id=:list"),
        {"list": dynamic.list_id},
    )
    assert preview.member_sense_ids == (uid(1400), uid(1401))
    assert preview.truncated is True
    assert preview.revision_id == dynamic.revision_id
    assert evaluator.calls == [(PROFILE_A, {"has_due_prompt": True}, NOW + timedelta(minutes=1), 3)]
    assert snapshots == 0


async def test_dynamic_preview_rejects_manual_lists(runtime_factory) -> None:
    service = SqlExchangeService(
        runtime_factory,
        ids=SequenceIdGenerator(uid(value) for value in range(1490, 1530)),
        dynamic_lists=DynamicListEvaluator(()),
    )
    manual = await service.create_list(
        ACCOUNT_A,
        PROFILE_A,
        CreateVocabularyList(
            variety_id=TARGET_VARIETY,
            list_type="manual",
            name="Manuelle",
            purpose="Pas de requête dynamique",
            ordered=True,
            color=None,
            tags=(),
            query_definition=None,
            member_sense_ids=(),
            created_at=NOW,
        ),
        idempotency_key="manual-preview-list",
    )

    with pytest.raises(DomainError) as rejected:
        await service.preview_dynamic_list(
            ACCOUNT_A,
            manual.list_id,
            cutoff_at=NOW + timedelta(minutes=1),
            limit=10,
        )

    assert rejected.value.code is ErrorCode.INVALID_TRANSITION
