# ruff: noqa: E501

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from polyglot.platform.fingerprint import canonical_json_bytes
from polyglot.platform.json_types import JsonValue
from polyglot.platform.persistence.models import metadata
from polyglot.platform.persistence.records import DomainEvent
from polyglot.platform.persistence.repositories import SqlEventOutboxRepository

content_items = Table(
    "content_items",
    metadata,
    Column("content_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("content_type", String(120), nullable=False),
    Column(
        "variety_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_varieties.variety_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("editorial_owner_id", PG_UUID(as_uuid=True), nullable=False),
    Column("lineage_root_id", PG_UUID(as_uuid=True), nullable=False),
    Column(
        "parent_content_id",
        PG_UUID(as_uuid=True),
        ForeignKey("content.content_items.content_id", ondelete="RESTRICT"),
    ),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "content.is_uuid7(content_id) AND content.is_uuid7(variety_id) AND content.is_uuid7(editorial_owner_id) AND content.is_uuid7(lineage_root_id)",
        name="ck_content_item_uuid7",
    ),
    CheckConstraint("version >= 1", name="ck_content_item_version"),
    schema="content",
)

content_revisions = Table(
    "content_revisions",
    metadata,
    Column("content_revision_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "content_id",
        PG_UUID(as_uuid=True),
        ForeignKey("content.content_items.content_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("revision_no", Integer, nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("payload_checksum", String(64), nullable=False),
    Column(
        "provenance_id",
        PG_UUID(as_uuid=True),
        ForeignKey("platform.provenance_records.provenance_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("rights_ref", String(500), nullable=False),
    Column("pinned_revision_refs", JSONB, nullable=False),
    Column("created_by_actor_id", PG_UUID(as_uuid=True), nullable=False),
    Column("approved_by_actor_id", PG_UUID(as_uuid=True)),
    Column("status", String(24), nullable=False),
    Column("channel_code", String(40)),
    Column("compatibility_range", String(120)),
    Column(
        "supersedes_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("content.content_revisions.content_revision_id", ondelete="RESTRICT"),
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("validated_at", DateTime(timezone=True)),
    Column("approved_at", DateTime(timezone=True)),
    Column("published_at", DateTime(timezone=True)),
    Column("retired_at", DateTime(timezone=True)),
    CheckConstraint("revision_no >= 1 AND schema_version >= 1", name="ck_content_revision_numbers"),
    CheckConstraint("payload_checksum ~ '^[0-9a-f]{64}$'", name="ck_content_revision_checksum"),
    CheckConstraint(
        "status IN ('draft', 'validating', 'validated', 'approved', 'published', 'retired', 'superseded', 'rejected', 'abandoned')",
        name="ck_content_revision_status",
    ),
    CheckConstraint(
        "jsonb_typeof(payload) = 'object' AND "
        "payload->>'schema_version' ~ '^[1-9][0-9]*$' AND "
        "jsonb_typeof(pinned_revision_refs) = 'array'",
        name="ck_content_revision_payload",
    ),
    UniqueConstraint("content_id", "revision_no", name="uq_content_revision_number"),
    schema="content",
)
Index(
    "ix_content_revisions_content_status",
    content_revisions.c.content_id,
    content_revisions.c.status,
    content_revisions.c.revision_no,
)

validation_reports = Table(
    "validation_reports",
    metadata,
    Column("report_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "subject_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("content.content_revisions.content_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("validator_set_revision_id", PG_UUID(as_uuid=True), nullable=False),
    Column("status", String(24), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("summary_checksum", String(64), nullable=False),
    CheckConstraint(
        "status IN ('pending', 'running', 'passed', 'failed', 'human_required', 'cancelled')",
        name="ck_content_validation_report_status",
    ),
    CheckConstraint(
        "summary_checksum ~ '^[0-9a-f]{64}$'", name="ck_content_validation_report_checksum"
    ),
    schema="content",
)

validation_findings = Table(
    "validation_findings",
    metadata,
    Column("finding_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "report_id",
        PG_UUID(as_uuid=True),
        ForeignKey("content.validation_reports.report_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("ordinal", Integer, nullable=False),
    Column("validator_code", String(120), nullable=False),
    Column("severity", String(24), nullable=False),
    Column("path", String(500), nullable=False),
    Column("message_code", String(120), nullable=False),
    Column("redacted_value", String(1000)),
    Column(
        "resolved_by_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("content.content_revisions.content_revision_id", ondelete="RESTRICT"),
    ),
    CheckConstraint(
        "severity IN ('blocking', 'warning', 'information', 'human_required')",
        name="ck_content_validation_finding_severity",
    ),
    UniqueConstraint("report_id", "ordinal", name="uq_content_validation_finding_ordinal"),
    schema="content",
)

content_approval_decisions = Table(
    "content_approval_decisions",
    metadata,
    Column("approval_decision_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "content_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("content.content_revisions.content_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("author_id", PG_UUID(as_uuid=True), nullable=False),
    Column("reviewer_id", PG_UUID(as_uuid=True), nullable=False),
    Column("decision", String(16), nullable=False),
    Column("reason_code", String(120)),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "decision IN ('approved', 'rejected') AND author_id <> reviewer_id",
        name="ck_content_approval_distinct",
    ),
    schema="content",
)

publication_manifests = Table(
    "publication_manifests",
    metadata,
    Column("publication_manifest_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "content_id",
        PG_UUID(as_uuid=True),
        ForeignKey("content.content_items.content_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "content_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("content.content_revisions.content_revision_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    ),
    Column("channel_code", String(40), nullable=False),
    Column("compatibility_range", String(120), nullable=False),
    Column("checksum", String(64), nullable=False),
    Column(
        "provenance_id",
        PG_UUID(as_uuid=True),
        ForeignKey("platform.provenance_records.provenance_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("published_at", DateTime(timezone=True), nullable=False),
    Column("retired_at", DateTime(timezone=True)),
    CheckConstraint("checksum ~ '^[0-9a-f]{64}$'", name="ck_content_publication_manifest_checksum"),
    schema="content",
)
Index(
    "uq_content_active_publication",
    publication_manifests.c.content_id,
    publication_manifests.c.channel_code,
    publication_manifests.c.compatibility_range,
    unique=True,
    postgresql_where=publication_manifests.c.retired_at.is_(None),
)

publication_manifest_entries = Table(
    "publication_manifest_entries",
    metadata,
    Column(
        "publication_manifest_id",
        PG_UUID(as_uuid=True),
        ForeignKey("content.publication_manifests.publication_manifest_id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column("ordinal", Integer, primary_key=True),
    Column("referenced_revision_id", PG_UUID(as_uuid=True), nullable=False),
    Column("reference_kind", String(120), nullable=False),
    schema="content",
)

historical_content_references = Table(
    "historical_content_references",
    metadata,
    Column("reference_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "content_revision_id",
        PG_UUID(as_uuid=True),
        ForeignKey("content.content_revisions.content_revision_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("usage_type", String(120), nullable=False),
    Column("usage_ref", String(500), nullable=False),
    Column("context_checksum", String(64), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("context_checksum ~ '^[0-9a-f]{64}$'", name="ck_content_history_checksum"),
    schema="content",
)


@dataclass(frozen=True, slots=True)
class StoredContentRevision:
    content_revision_id: UUID
    content_id: UUID
    status: str
    payload: dict[str, JsonValue]


class SqlContentPublicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_approved_revision(
        self,
        *,
        content_id: UUID,
        content_revision_id: UUID,
        variety_id: UUID,
        author_id: UUID,
        reviewer_id: UUID,
        provenance_id: UUID,
        payload: dict[str, JsonValue],
        rights_ref: str,
        now: datetime,
    ) -> None:
        checksum = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        await self._session.execute(
            content_items.insert().values(
                content_id=content_id,
                content_type="dialogue",
                variety_id=variety_id,
                editorial_owner_id=author_id,
                lineage_root_id=content_id,
                parent_content_id=None,
                version=1,
                created_at=now,
            )
        )
        await self._session.execute(
            content_revisions.insert().values(
                content_revision_id=content_revision_id,
                content_id=content_id,
                revision_no=1,
                schema_version=1,
                payload=payload,
                payload_checksum=checksum,
                provenance_id=provenance_id,
                rights_ref=rights_ref,
                pinned_revision_refs=[],
                created_by_actor_id=author_id,
                approved_by_actor_id=reviewer_id,
                status="approved",
                channel_code=None,
                compatibility_range=None,
                supersedes_revision_id=None,
                created_at=now,
                validated_at=now,
                approved_at=now,
                published_at=None,
                retired_at=None,
            )
        )

    async def publish(
        self,
        *,
        content_id: UUID,
        content_revision_id: UUID,
        actor_id: UUID,
        command_id: UUID,
        correlation_id: UUID,
        event_id: UUID,
        manifest_id: UUID,
        channel_code: str,
        compatibility_range: str,
        now: datetime,
    ) -> StoredContentRevision:
        revision = (
            (
                await self._session.execute(
                    select(content_revisions)
                    .where(content_revisions.c.content_revision_id == content_revision_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one()
        )
        if revision["content_id"] != content_id or revision["status"] != "approved":
            raise ValueError("content revision is not publishable")
        old_manifest = (
            (
                await self._session.execute(
                    select(publication_manifests)
                    .where(
                        publication_manifests.c.content_id == content_id,
                        publication_manifests.c.channel_code == channel_code,
                        publication_manifests.c.compatibility_range == compatibility_range,
                        publication_manifests.c.retired_at.is_(None),
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if old_manifest is not None:
            await self._session.execute(
                publication_manifests.update()
                .where(
                    publication_manifests.c.publication_manifest_id
                    == old_manifest["publication_manifest_id"]
                )
                .values(retired_at=now)
            )
            await self._session.execute(
                content_revisions.update()
                .where(
                    content_revisions.c.content_revision_id == old_manifest["content_revision_id"]
                )
                .values(status="superseded")
            )
        await self._session.execute(
            content_revisions.update()
            .where(content_revisions.c.content_revision_id == content_revision_id)
            .values(
                status="published",
                channel_code=channel_code,
                compatibility_range=compatibility_range,
                published_at=now,
            )
        )
        checksum = hashlib.sha256(canonical_json_bytes(revision["payload"])).hexdigest()
        await self._session.execute(
            publication_manifests.insert().values(
                publication_manifest_id=manifest_id,
                content_id=content_id,
                content_revision_id=content_revision_id,
                channel_code=channel_code,
                compatibility_range=compatibility_range,
                checksum=checksum,
                provenance_id=revision["provenance_id"],
                published_at=now,
                retired_at=None,
            )
        )
        aggregate_version = await self._session.scalar(
            content_items.update()
            .where(content_items.c.content_id == content_id)
            .values(version=content_items.c.version + 1)
            .returning(content_items.c.version)
        )
        assert isinstance(aggregate_version, int)
        event = DomainEvent(
            event_id=event_id,
            event_type="content_published",
            schema_version=1,
            aggregate_type="content_item",
            aggregate_id=content_id,
            aggregate_version=aggregate_version,
            actor_type="account",
            actor_id=actor_id,
            profile_id=None,
            occurred_at=now,
            recorded_at=now,
            correlation_id=correlation_id,
            causation_id=None,
            command_id=command_id,
            privacy_class="public",
            policy_versions={},
            payload={
                "schema_version": 1,
                "content_revision_id": str(content_revision_id),
                "publication_manifest_id": str(manifest_id),
            },
        )
        await SqlEventOutboxRepository(self._session).add(event, destinations=("local",))
        return StoredContentRevision(
            content_revision_id=content_revision_id,
            content_id=content_id,
            status="published",
            payload=dict(revision["payload"]),
        )

    async def record_historical_reference(
        self,
        *,
        reference_id: UUID,
        content_revision_id: UUID,
        usage_type: str,
        usage_ref: str,
        context_checksum: str,
        now: datetime,
    ) -> None:
        await self._session.execute(
            historical_content_references.insert().values(
                reference_id=reference_id,
                content_revision_id=content_revision_id,
                usage_type=usage_type,
                usage_ref=usage_ref,
                context_checksum=context_checksum,
                recorded_at=now,
            )
        )

    async def retire(self, *, content_revision_id: UUID, now: datetime) -> None:
        await self._session.execute(
            content_revisions.update()
            .where(
                content_revisions.c.content_revision_id == content_revision_id,
                content_revisions.c.status == "published",
            )
            .values(status="retired", retired_at=now)
        )
        await self._session.execute(
            publication_manifests.update()
            .where(
                publication_manifests.c.content_revision_id == content_revision_id,
                publication_manifests.c.retired_at.is_(None),
            )
            .values(retired_at=now)
        )

    async def get_historical_revision(self, content_revision_id: UUID) -> StoredContentRevision:
        revision = (
            (
                await self._session.execute(
                    select(content_revisions).where(
                        content_revisions.c.content_revision_id == content_revision_id
                    )
                )
            )
            .mappings()
            .one()
        )
        return StoredContentRevision(
            content_revision_id=revision["content_revision_id"],
            content_id=revision["content_id"],
            status=revision["status"],
            payload=dict(revision["payload"]),
        )
