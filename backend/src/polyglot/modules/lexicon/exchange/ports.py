from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class AssociationTargetPort(Protocol):
    async def verify(
        self,
        target_type: str,
        target_id: UUID,
        profile_id: UUID,
    ) -> bool: ...


class DynamicListQueryPort(Protocol):
    async def evaluate(
        self,
        profile_id: UUID,
        query_definition: dict[str, object],
        cutoff_at: datetime,
        limit: int,
    ) -> tuple[UUID, ...]: ...


@dataclass(frozen=True, slots=True)
class CreateImportedLexicalEntry:
    profile_id: UUID
    variety_id: UUID
    unit_type: str
    normalized_form: str
    semantic_key: str | None
    provenance_ref: str
    created_at: datetime


class LexicalMutationPort(Protocol):
    async def create_imported_entry(
        self,
        command: CreateImportedLexicalEntry,
        *,
        session: AsyncSession,
    ) -> tuple[str, str]: ...


@dataclass(frozen=True, slots=True)
class StoredPrivateArtifact:
    media_revision_id: UUID
    encryption_scheme: str
    checksum_sha256: str


class PrivateArtifactPort(Protocol):
    async def store_encrypted_export(
        self,
        *,
        export_id: UUID,
        profile_id: UUID,
        payload: bytes,
        expires_at: datetime,
    ) -> StoredPrivateArtifact: ...
