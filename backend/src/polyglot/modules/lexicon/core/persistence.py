from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Column,
    DateTime,
    Numeric,
    String,
    Table,
    Text,
    and_,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.platform.persistence.models import metadata

lexical_encounters = Table(
    "lexical_encounters",
    metadata,
    Column("encounter_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("profile_id", PG_UUID(as_uuid=True), nullable=False),
    Column("exact_surface", Text, nullable=False),
    Column("source_type", String(32), nullable=False),
    Column("source_ref", Text, nullable=False),
    Column("source_revision_ref", Text, nullable=False),
    Column("modality", String(16), nullable=False),
    Column("lexical_role", String(32), nullable=False),
    Column("operation", String(32), nullable=False),
    Column("help_state", String(32), nullable=False),
    Column("result_state", String(32), nullable=False),
    Column("correction_ref", Text, nullable=False),
    Column("correction_confidence", Numeric(5, 4), nullable=False),
    Column("context_private", Text),
    Column("context_fingerprint", String(64), nullable=False),
    Column("context_retention", String(32), nullable=False),
    Column("context_deleted_at", DateTime(timezone=True)),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_fingerprint", String(64), nullable=False),
    schema="lexicon",
)

mention_resolutions = Table(
    "mention_resolutions",
    metadata,
    Column("resolution_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("profile_id", PG_UUID(as_uuid=True), nullable=False),
    Column("mention_id", PG_UUID(as_uuid=True), nullable=False),
    Column("candidate_id", PG_UUID(as_uuid=True), nullable=False),
    Column("sense_id", PG_UUID(as_uuid=True), nullable=False),
    Column("resolver_type", String(32), nullable=False),
    Column("confidence", Numeric(5, 4), nullable=False),
    Column("supersedes_resolution_id", PG_UUID(as_uuid=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_fingerprint", String(64), nullable=False),
    schema="lexicon",
)

command_receipts = Table(
    "lexicon_command_receipts",
    metadata,
    Column("receipt_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("profile_id", PG_UUID(as_uuid=True), nullable=False),
    Column("command_name", String(120), nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("request_fingerprint", String(64), nullable=False),
    Column("resource_id", PG_UUID(as_uuid=True), nullable=False),
    Column("result_payload", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    schema="lexicon",
)


@dataclass(frozen=True, slots=True)
class EncounterRecord:
    encounter_id: UUID
    profile_id: UUID
    exact_surface: str
    source_type: str
    source_ref: str
    source_revision_ref: str
    modality: str
    lexical_role: str
    operation: str
    help_state: str
    result_state: str
    correction_ref: str
    correction_confidence: float
    context_private: str | None
    context_fingerprint: str
    context_retention: str
    context_deleted_at: datetime | None
    occurred_at: datetime
    idempotency_key: str
    request_fingerprint: str


@dataclass(frozen=True, slots=True)
class ResolutionRecord:
    resolution_id: UUID
    profile_id: UUID
    mention_id: UUID
    candidate_id: UUID
    sense_id: UUID
    resolver_type: str
    confidence: float
    supersedes_resolution_id: UUID | None
    created_at: datetime
    idempotency_key: str
    request_fingerprint: str


@dataclass(frozen=True, slots=True)
class CommandReceipt:
    receipt_id: UUID
    profile_id: UUID
    command_name: str
    idempotency_key: str
    request_fingerprint: str
    resource_id: UUID
    result_payload: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class LexicalImportCandidateRecord:
    sense_id: UUID
    variety_id: UUID
    unit_type: str
    normalization_key: str
    sense_code: str


class LexiconRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_encounter(self, record: EncounterRecord) -> None:
        await self._session.execute(insert(lexical_encounters).values(**asdict(record)))

    async def resolve_mention(self, record: ResolutionRecord) -> None:
        await self._session.execute(insert(mention_resolutions).values(**asdict(record)))

    async def delete_private_context(
        self,
        *,
        profile_id: UUID,
        encounter_id: UUID,
        deleted_at: datetime,
    ) -> bool:
        result = await self._session.execute(
            update(lexical_encounters)
            .where(
                and_(
                    lexical_encounters.c.profile_id == profile_id,
                    lexical_encounters.c.encounter_id == encounter_id,
                    lexical_encounters.c.context_deleted_at.is_(None),
                )
            )
            .values(context_private=None, context_deleted_at=deleted_at)
        )
        return bool(getattr(result, "rowcount", 0))

    async def get_command_receipt(
        self,
        *,
        profile_id: UUID,
        command_name: str,
        idempotency_key: str,
    ) -> CommandReceipt | None:
        row = (
            (
                await self._session.execute(
                    select(command_receipts).where(
                        and_(
                            command_receipts.c.profile_id == profile_id,
                            command_receipts.c.command_name == command_name,
                            command_receipts.c.idempotency_key == idempotency_key,
                        )
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else CommandReceipt(**dict(row))

    async def save_command_receipt(self, receipt: CommandReceipt) -> None:
        await self._session.execute(insert(command_receipts).values(**asdict(receipt)))

    async def list_private_import_candidates(
        self,
        profile_id: UUID,
    ) -> tuple[LexicalImportCandidateRecord, ...]:
        rows = (
            await self._session.execute(
                text(
                    "SELECT sense.sense_id,unit.variety_id,unit.unit_type,"
                    "unit.normalization_key,sense.sense_code "
                    "FROM lexicon.private_lexical_senses sense "
                    "JOIN lexicon.private_lexical_units unit "
                    "ON unit.lexical_unit_id=sense.lexical_unit_id "
                    "AND unit.profile_id=sense.profile_id "
                    "WHERE sense.profile_id=:profile AND unit.merged_into_unit_id IS NULL"
                ),
                {"profile": profile_id},
            )
        ).mappings()
        return tuple(LexicalImportCandidateRecord(**dict(row)) for row in rows)
