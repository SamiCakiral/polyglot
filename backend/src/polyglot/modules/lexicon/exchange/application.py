from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from polyglot.modules.lexicon.exchange.domain import ImportStrategy


@dataclass(frozen=True, slots=True)
class CreateVocabularyList:
    variety_id: UUID
    list_type: str
    name: str
    purpose: str
    ordered: bool
    color: str | None
    tags: tuple[str, ...]
    query_definition: dict[str, object] | None
    member_sense_ids: tuple[UUID, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ChangeListMembers:
    add_sense_ids: tuple[UUID, ...]
    remove_sense_ids: tuple[UUID, ...]
    changed_at: datetime


@dataclass(frozen=True, slots=True)
class CreateImport:
    format_id: str
    encoding: str
    payload: bytes
    strategy: ImportStrategy
    catalogue_version: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class VocabularyListView:
    list_id: UUID
    profile_id: UUID
    variety_id: UUID
    list_type: str
    status: str
    version: int
    revision_id: UUID
    revision_no: int
    name: str
    purpose: str
    ordered: bool
    color: str | None
    tags: tuple[str, ...]
    query_definition: dict[str, object] | None
    member_sense_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ListSnapshotView:
    snapshot_id: UUID
    list_id: UUID
    profile_id: UUID
    source_revision_id: UUID
    checksum: str
    member_sense_revision_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ImportRunView:
    import_id: UUID
    profile_id: UUID
    format_id: str
    status: str
    strategy: ImportStrategy
    preview_checksum: str
    catalogue_version: str
    version: int
    unresolved_conflicts: int
    created_refs: tuple[str, ...] = ()
    reused_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MutationView:
    resource_id: UUID
    version: int
    status: str
