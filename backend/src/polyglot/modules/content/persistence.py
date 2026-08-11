# ruff: noqa: E501

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    and_,
    exists,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_bytes
from polyglot.platform.json_types import JsonValue
from polyglot.platform.persistence.models import metadata

content_items = Table(
    "content_items",
    metadata,
    Column("content_id", PG_UUID(as_uuid=True), primary_key=True),
    Column("content_type", String(120), nullable=False),
    Column(
        "pack_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_packs.pack_id", ondelete="RESTRICT"),
        nullable=False,
    ),
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
        "content.is_uuid7(content_revision_id) AND content.is_uuid7(content_id) "
        "AND content.is_uuid7(provenance_id) AND content.is_uuid7(created_by_actor_id) "
        "AND (approved_by_actor_id IS NULL OR content.is_uuid7(approved_by_actor_id)) "
        "AND (supersedes_revision_id IS NULL OR content.is_uuid7(supersedes_revision_id))",
        name="ck_content_revision_uuid7",
    ),
    CheckConstraint(
        "approved_by_actor_id IS NULL OR approved_by_actor_id <> created_by_actor_id",
        name="ck_content_revision_distinct_approver",
    ),
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
    CheckConstraint(
        "created_at <= COALESCE(validated_at, created_at) "
        "AND created_at <= COALESCE(approved_at, created_at) "
        "AND created_at <= COALESCE(published_at, created_at) "
        "AND created_at <= COALESCE(retired_at, created_at)",
        name="ck_content_revision_dates",
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
    Column("command_id", PG_UUID(as_uuid=True)),
    Column("status", String(24), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True)),
    Column("finding_count", Integer, nullable=False, server_default="0"),
    Column("summary_checksum", String(64)),
    CheckConstraint(
        "status IN ('pending', 'running', 'passed', 'failed', 'human_required', 'cancelled')",
        name="ck_content_validation_report_status",
    ),
    CheckConstraint(
        "summary_checksum IS NULL OR summary_checksum ~ '^[0-9a-f]{64}$'",
        name="ck_content_validation_report_checksum",
    ),
    CheckConstraint("finding_count >= 0", name="ck_content_validation_report_count"),
    CheckConstraint(
        "content.is_uuid7(report_id) AND content.is_uuid7(subject_revision_id) "
        "AND content.is_uuid7(validator_set_revision_id)",
        name="ck_content_validation_report_uuid7",
    ),
    CheckConstraint(
        "completed_at IS NOT NULL AND completed_at >= started_at "
        "AND status IN ('passed', 'failed', 'human_required')",
        name="ck_content_validation_report_dates",
    ),
    schema="content",
)
Index(
    "ix_content_validation_report_revision",
    validation_reports.c.subject_revision_id,
    validation_reports.c.completed_at,
    validation_reports.c.report_id,
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
    CheckConstraint(
        "content.is_uuid7(finding_id) AND content.is_uuid7(report_id) "
        "AND (resolved_by_revision_id IS NULL OR content.is_uuid7(resolved_by_revision_id))",
        name="ck_content_validation_finding_uuid7",
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
    Column("command_id", PG_UUID(as_uuid=True)),
    Column("decision", String(16), nullable=False),
    Column("reason_code", String(120)),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "decision IN ('approved', 'rejected') AND author_id <> reviewer_id",
        name="ck_content_approval_distinct",
    ),
    CheckConstraint(
        "content.is_uuid7(approval_decision_id) "
        "AND content.is_uuid7(content_revision_id) AND content.is_uuid7(author_id) "
        "AND content.is_uuid7(reviewer_id)",
        name="ck_content_approval_uuid7",
    ),
    UniqueConstraint("content_revision_id", name="uq_content_approval_decision_revision"),
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
    Column("command_id", PG_UUID(as_uuid=True)),
    Column("entry_count", Integer, nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=False),
    Column("retired_at", DateTime(timezone=True)),
    CheckConstraint("checksum ~ '^[0-9a-f]{64}$'", name="ck_content_publication_manifest_checksum"),
    CheckConstraint("entry_count >= 0", name="ck_content_publication_manifest_count"),
    CheckConstraint(
        "content.is_uuid7(publication_manifest_id) AND content.is_uuid7(content_id) "
        "AND content.is_uuid7(content_revision_id) AND content.is_uuid7(provenance_id)",
        name="ck_content_publication_manifest_uuid7",
    ),
    CheckConstraint(
        "retired_at IS NULL OR retired_at >= published_at",
        name="ck_content_publication_manifest_dates",
    ),
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
    Column("reference_checksum", String(64), nullable=False),
    Column(
        "reference_provenance_id",
        PG_UUID(as_uuid=True),
        ForeignKey("platform.provenance_records.provenance_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("reference_rights_ref", String(500), nullable=False),
    Column("reference_status", String(24), nullable=False),
    CheckConstraint(
        "content.is_uuid7(publication_manifest_id) AND content.is_uuid7(referenced_revision_id) "
        "AND content.is_uuid7(reference_provenance_id)",
        name="ck_content_publication_entry_uuid7",
    ),
    CheckConstraint(
        "reference_checksum ~ '^[0-9a-f]{64}$'",
        name="ck_content_publication_entry_checksum",
    ),
    CheckConstraint(
        "reference_status = 'published'",
        name="ck_content_publication_entry_status",
    ),
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
    CheckConstraint(
        "content.is_uuid7(reference_id) AND content.is_uuid7(content_revision_id)",
        name="ck_content_history_uuid7",
    ),
    schema="content",
)
Index(
    "ix_content_history_revision",
    historical_content_references.c.content_revision_id,
    historical_content_references.c.recorded_at,
    historical_content_references.c.reference_id,
)

editorial_pack_assignments = Table(
    "editorial_pack_assignments",
    metadata,
    Column("assignment_id", PG_UUID(as_uuid=True), primary_key=True),
    Column(
        "actor_id",
        PG_UUID(as_uuid=True),
        ForeignKey("identity.accounts.account_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "pack_id",
        PG_UUID(as_uuid=True),
        ForeignKey("catalogue.language_packs.pack_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("editorial_role", String(16), nullable=False),
    Column("granted_at", DateTime(timezone=True), nullable=False),
    Column(
        "granted_by_actor_id",
        PG_UUID(as_uuid=True),
        ForeignKey("identity.accounts.account_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("revoked_at", DateTime(timezone=True)),
    CheckConstraint(
        "content.is_uuid7(assignment_id) AND content.is_uuid7(actor_id) "
        "AND content.is_uuid7(pack_id) AND content.is_uuid7(granted_by_actor_id)",
        name="ck_content_assignment_uuid7",
    ),
    CheckConstraint(
        "editorial_role IN ('author','reviewer','admin')",
        name="ck_content_assignment_role",
    ),
    CheckConstraint(
        "revoked_at IS NULL OR revoked_at >= granted_at",
        name="ck_content_assignment_dates",
    ),
    schema="content",
)
Index(
    "uq_content_editorial_pack_assignment_active",
    editorial_pack_assignments.c.actor_id,
    editorial_pack_assignments.c.pack_id,
    editorial_pack_assignments.c.editorial_role,
    unique=True,
    postgresql_where=editorial_pack_assignments.c.revoked_at.is_(None),
)

command_contexts = Table(
    "command_contexts",
    metadata,
    Column(
        "command_id",
        PG_UUID(as_uuid=True),
        ForeignKey("platform.command_receipts.command_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("transaction_id", BigInteger, nullable=False, unique=True),
    Column("command_type", String(120), nullable=False),
    Column("actor_id", PG_UUID(as_uuid=True), nullable=False),
    Column("actor_type", String(16), nullable=False),
    Column("session_id", PG_UUID(as_uuid=True), nullable=False),
    Column("pack_id", PG_UUID(as_uuid=True), nullable=False),
    Column(
        "opened_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    ),
    CheckConstraint("content.is_uuid7(command_id)", name="ck_content_command_context_uuid7"),
    CheckConstraint("actor_type = 'account'", name="ck_content_command_context_actor_type"),
    CheckConstraint(
        "command_type IN ('CreateContentDraft','ReviseContentDraft',"
        "'ValidateContentRevision','ApproveContentRevision',"
        "'PublishContentRevision','RetireContentRevision')",
        name="ck_content_command_context_type",
    ),
    schema="content",
)


@dataclass(frozen=True, slots=True)
class StoredContentRevision:
    content_revision_id: UUID
    content_id: UUID
    revision_no: int
    status: str
    payload: dict[str, JsonValue]
    payload_checksum: str
    provenance_id: UUID
    rights_ref: str
    pinned_revision_refs: tuple[dict[str, JsonValue], ...]
    created_by_actor_id: UUID
    supersedes_revision_id: UUID | None
    approved_by_actor_id: UUID | None
    created_at: datetime
    validated_at: datetime | None
    approved_at: datetime | None
    published_at: datetime | None
    retired_at: datetime | None


@dataclass(frozen=True, slots=True)
class StoredContentItem:
    content_id: UUID
    content_type: str
    pack_id: UUID
    variety_id: UUID
    editorial_owner_id: UUID
    version: int


@dataclass(frozen=True, slots=True)
class PublishedReferenceSnapshot:
    revision_id: UUID
    reference_kind: str
    checksum: str
    provenance_id: UUID
    rights_ref: str
    status: str = "published"


@dataclass(frozen=True, slots=True)
class ContentRevisionPage:
    items: tuple[StoredContentRevision, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class StoredValidationFinding:
    finding_id: UUID
    ordinal: int
    validator_code: str
    severity: str
    path: str
    message_code: str
    redacted_value: str | None


@dataclass(frozen=True, slots=True)
class StoredValidationReport:
    report_id: UUID
    subject_revision_id: UUID
    validator_set_revision_id: UUID
    status: str
    started_at: datetime
    completed_at: datetime
    summary_checksum: str
    findings: tuple[StoredValidationFinding, ...]


def _encode_cursor(kind: str, created_at: datetime, identifier: UUID) -> str:
    payload = json.dumps(
        [kind, created_at.isoformat(), str(identifier)], separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str | None, kind: str) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if not isinstance(payload, list) or len(payload) != 3 or payload[0] != kind:
            raise ValueError
        return datetime.fromisoformat(payload[1]), UUID(payload[2])
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DomainError(ErrorCode.CURSOR_INVALID) from error


def _stored_revision(row: RowMapping) -> StoredContentRevision:
    return StoredContentRevision(
        content_revision_id=row["content_revision_id"],
        content_id=row["content_id"],
        revision_no=row["revision_no"],
        status=row["status"],
        payload=dict(row["payload"]),
        payload_checksum=row["payload_checksum"],
        provenance_id=row["provenance_id"],
        rights_ref=row["rights_ref"],
        pinned_revision_refs=tuple(dict(item) for item in row["pinned_revision_refs"]),
        created_by_actor_id=row["created_by_actor_id"],
        supersedes_revision_id=row["supersedes_revision_id"],
        approved_by_actor_id=row["approved_by_actor_id"],
        created_at=row["created_at"],
        validated_at=row["validated_at"],
        approved_at=row["approved_at"],
        published_at=row["published_at"],
        retired_at=row["retired_at"],
    )


class SqlContentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def begin_command(
        self,
        *,
        command_id: UUID,
        actor_id: UUID,
        session_id: UUID,
        pack_id: UUID,
        session_proof: str,
    ) -> None:
        await self._session.execute(
            text(
                "SELECT content.begin_command("
                ":command_id, 'account', :session_id, :pack_id, :session_proof)"
            ),
            {
                "command_id": command_id,
                "actor_id": actor_id,
                "session_id": session_id,
                "pack_id": pack_id,
                "session_proof": session_proof,
            },
        )

    async def get_pack_id_for_revision(self, content_revision_id: UUID) -> UUID:
        pack_id = await self._session.scalar(
            select(content_items.c.pack_id)
            .join(
                content_revisions,
                content_revisions.c.content_id == content_items.c.content_id,
            )
            .where(content_revisions.c.content_revision_id == content_revision_id)
        )
        if not isinstance(pack_id, UUID):
            raise DomainError(ErrorCode.DRAFT_NOT_FOUND)
        return pack_id

    async def require_pack_assignment(
        self, *, actor_id: UUID, pack_id: UUID, allowed_roles: tuple[str, ...]
    ) -> None:
        allowed = await self._session.scalar(
            select(
                exists().where(
                    editorial_pack_assignments.c.actor_id == actor_id,
                    editorial_pack_assignments.c.pack_id == pack_id,
                    editorial_pack_assignments.c.editorial_role.in_(allowed_roles),
                    editorial_pack_assignments.c.revoked_at.is_(None),
                )
            )
        )
        if allowed is not True:
            raise DomainError(ErrorCode.FORBIDDEN)

    @staticmethod
    def _scope_filter(*, actor_id: UUID, roles: frozenset[str]) -> ColumnElement[bool]:
        branches: list[ColumnElement[bool]] = []
        if "author" in roles:
            branches.append(
                exists().where(
                    editorial_pack_assignments.c.actor_id == actor_id,
                    editorial_pack_assignments.c.pack_id == content_items.c.pack_id,
                    editorial_pack_assignments.c.editorial_role == "author",
                    editorial_pack_assignments.c.revoked_at.is_(None),
                    content_items.c.editorial_owner_id == actor_id,
                )
            )
        scoped_review_roles = tuple(roles.intersection({"reviewer", "admin"}))
        if scoped_review_roles:
            branches.append(
                exists().where(
                    editorial_pack_assignments.c.actor_id == actor_id,
                    editorial_pack_assignments.c.pack_id == content_items.c.pack_id,
                    editorial_pack_assignments.c.editorial_role.in_(scoped_review_roles),
                    editorial_pack_assignments.c.revoked_at.is_(None),
                )
            )
        return or_(*branches)

    async def get_command_proofs(self, command_id: UUID) -> tuple[UUID | None, UUID | None]:
        report_id = await self._session.scalar(
            select(validation_reports.c.report_id).where(
                validation_reports.c.command_id == command_id
            )
        )
        manifest_id = await self._session.scalar(
            select(publication_manifests.c.publication_manifest_id).where(
                publication_manifests.c.command_id == command_id
            )
        )
        return report_id, manifest_id

    async def create_item_and_draft(
        self,
        *,
        content_id: UUID,
        content_revision_id: UUID,
        content_type: str,
        pack_id: UUID,
        variety_id: UUID,
        author_id: UUID,
        provenance_id: UUID,
        payload: dict[str, JsonValue],
        rights_ref: str,
        pinned_revision_refs: tuple[dict[str, JsonValue], ...],
        now: datetime,
    ) -> StoredContentRevision:
        checksum = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        await self._session.execute(
            content_items.insert().values(
                content_id=content_id,
                content_type=content_type,
                pack_id=pack_id,
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
                pinned_revision_refs=list(pinned_revision_refs),
                created_by_actor_id=author_id,
                approved_by_actor_id=None,
                status="draft",
                channel_code=None,
                compatibility_range=None,
                supersedes_revision_id=None,
                created_at=now,
                validated_at=None,
                approved_at=None,
                published_at=None,
                retired_at=None,
            )
        )
        return await self.get_revision(content_revision_id)

    async def get_revision(self, content_revision_id: UUID) -> StoredContentRevision:
        row = (
            (
                await self._session.execute(
                    select(content_revisions).where(
                        content_revisions.c.content_revision_id == content_revision_id
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.DRAFT_NOT_FOUND)
        return _stored_revision(row)

    async def list_drafts(
        self,
        *,
        actor_id: UUID,
        roles: frozenset[str],
        limit: int,
        cursor: str | None,
    ) -> ContentRevisionPage:
        after = _decode_cursor(cursor, "content_drafts")
        statement = (
            select(content_revisions)
            .join(content_items, content_items.c.content_id == content_revisions.c.content_id)
            .where(
                content_revisions.c.status.in_(
                    ("draft", "validating", "validated", "approved", "rejected")
                )
            )
            .where(self._scope_filter(actor_id=actor_id, roles=roles))
        )
        if after is not None:
            after_time, after_id = after
            statement = statement.where(
                or_(
                    content_revisions.c.created_at > after_time,
                    and_(
                        content_revisions.c.created_at == after_time,
                        content_revisions.c.content_revision_id > after_id,
                    ),
                )
            )
        rows = (
            (
                await self._session.execute(
                    statement.order_by(
                        content_revisions.c.created_at,
                        content_revisions.c.content_revision_id,
                    ).limit(limit + 1)
                )
            )
            .mappings()
            .all()
        )
        visible = rows[:limit]
        next_cursor = None
        if len(rows) > limit and visible:
            last = visible[-1]
            next_cursor = _encode_cursor(
                "content_drafts", last["created_at"], last["content_revision_id"]
            )
        return ContentRevisionPage(tuple(_stored_revision(row) for row in visible), next_cursor)

    async def get_draft_for_actor(
        self,
        content_revision_id: UUID,
        *,
        actor_id: UUID,
        roles: frozenset[str],
    ) -> StoredContentRevision:
        row = (
            (
                await self._session.execute(
                    select(content_revisions, content_items.c.editorial_owner_id)
                    .join(
                        content_items, content_items.c.content_id == content_revisions.c.content_id
                    )
                    .where(
                        content_revisions.c.content_revision_id == content_revision_id,
                        content_revisions.c.status.in_(
                            ("draft", "validating", "validated", "approved", "rejected")
                        ),
                        self._scope_filter(actor_id=actor_id, roles=roles),
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        return _stored_revision(row)

    async def get_history_for_actor(
        self,
        content_id: UUID,
        *,
        actor_id: UUID,
        roles: frozenset[str],
        limit: int,
        cursor: str | None,
    ) -> ContentRevisionPage:
        after = _decode_cursor(cursor, "content_history")
        statement = (
            select(content_revisions)
            .join(content_items, content_items.c.content_id == content_revisions.c.content_id)
            .where(content_revisions.c.content_id == content_id)
            .where(self._scope_filter(actor_id=actor_id, roles=roles))
        )
        if after is not None:
            after_time, after_id = after
            statement = statement.where(
                or_(
                    content_revisions.c.created_at > after_time,
                    and_(
                        content_revisions.c.created_at == after_time,
                        content_revisions.c.content_revision_id > after_id,
                    ),
                )
            )
        rows = (
            (
                await self._session.execute(
                    statement.order_by(
                        content_revisions.c.created_at,
                        content_revisions.c.content_revision_id,
                    ).limit(limit + 1)
                )
            )
            .mappings()
            .all()
        )
        if not rows and cursor is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        visible = rows[:limit]
        next_cursor = None
        if len(rows) > limit and visible:
            last = visible[-1]
            next_cursor = _encode_cursor(
                "content_history", last["created_at"], last["content_revision_id"]
            )
        return ContentRevisionPage(tuple(_stored_revision(row) for row in visible), next_cursor)

    async def get_validation_report_for_actor(
        self,
        report_id: UUID,
        *,
        actor_id: UUID,
        roles: frozenset[str],
    ) -> StoredValidationReport:
        row = (
            (
                await self._session.execute(
                    select(validation_reports, content_items.c.editorial_owner_id)
                    .join(
                        content_revisions,
                        content_revisions.c.content_revision_id
                        == validation_reports.c.subject_revision_id,
                    )
                    .join(
                        content_items, content_items.c.content_id == content_revisions.c.content_id
                    )
                    .where(validation_reports.c.report_id == report_id)
                    .where(self._scope_filter(actor_id=actor_id, roles=roles))
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        finding_rows = (
            (
                await self._session.execute(
                    select(validation_findings)
                    .where(validation_findings.c.report_id == report_id)
                    .order_by(validation_findings.c.ordinal)
                )
            )
            .mappings()
            .all()
        )
        completed_at = row["completed_at"]
        if not isinstance(completed_at, datetime):
            raise DomainError(ErrorCode.INTERNAL_ERROR)
        return StoredValidationReport(
            report_id=row["report_id"],
            subject_revision_id=row["subject_revision_id"],
            validator_set_revision_id=row["validator_set_revision_id"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=completed_at,
            summary_checksum=row["summary_checksum"],
            findings=tuple(
                StoredValidationFinding(
                    finding_id=finding["finding_id"],
                    ordinal=finding["ordinal"],
                    validator_code=finding["validator_code"],
                    severity=finding["severity"],
                    path=finding["path"],
                    message_code=finding["message_code"],
                    redacted_value=finding["redacted_value"],
                )
                for finding in finding_rows
            ),
        )

    async def lock_item_for_revision(
        self,
        content_revision_id: UUID,
        *,
        expected_version: int,
    ) -> tuple[StoredContentItem, StoredContentRevision]:
        revision = await self.get_revision(content_revision_id)
        item_row = (
            (
                await self._session.execute(
                    select(content_items)
                    .where(content_items.c.content_id == revision.content_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one()
        )
        item = StoredContentItem(
            content_id=item_row["content_id"],
            content_type=item_row["content_type"],
            pack_id=item_row["pack_id"],
            variety_id=item_row["variety_id"],
            editorial_owner_id=item_row["editorial_owner_id"],
            version=item_row["version"],
        )
        if item.version != expected_version:
            raise DomainError(ErrorCode.VERSION_CONFLICT)
        return item, await self.get_revision(content_revision_id)

    async def bump_version(self, content_id: UUID, expected_version: int) -> int:
        version = await self._session.scalar(
            content_items.update()
            .where(
                content_items.c.content_id == content_id,
                content_items.c.version == expected_version,
            )
            .values(version=expected_version + 1)
            .returning(content_items.c.version)
        )
        if version is None:
            raise DomainError(ErrorCode.VERSION_CONFLICT)
        return int(version)

    async def add_revised_draft(
        self,
        *,
        source: StoredContentRevision,
        content_revision_id: UUID,
        actor_id: UUID,
        payload: dict[str, JsonValue],
        provenance_id: UUID,
        rights_ref: str,
        pinned_revision_refs: tuple[dict[str, JsonValue], ...],
        now: datetime,
    ) -> StoredContentRevision:
        latest_revision_no = await self._session.scalar(
            select(func.max(content_revisions.c.revision_no)).where(
                content_revisions.c.content_id == source.content_id
            )
        )
        revision_no = (
            latest_revision_no
            if isinstance(latest_revision_no, int) and not isinstance(latest_revision_no, bool)
            else 0
        ) + 1
        schema_version = payload.get("schema_version")
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise DomainError(ErrorCode.VALIDATION_FAILED)
        await self._session.execute(
            content_revisions.insert().values(
                content_revision_id=content_revision_id,
                content_id=source.content_id,
                revision_no=revision_no,
                schema_version=schema_version,
                payload=payload,
                payload_checksum=hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
                provenance_id=provenance_id,
                rights_ref=rights_ref,
                pinned_revision_refs=list(pinned_revision_refs),
                created_by_actor_id=actor_id,
                approved_by_actor_id=None,
                status="draft",
                channel_code=None,
                compatibility_range=None,
                supersedes_revision_id=source.content_revision_id,
                created_at=now,
                validated_at=None,
                approved_at=None,
                published_at=None,
                retired_at=None,
            )
        )
        return await self.get_revision(content_revision_id)

    async def begin_validation(self, content_revision_id: UUID) -> None:
        updated_id = await self._session.scalar(
            content_revisions.update()
            .where(
                content_revisions.c.content_revision_id == content_revision_id,
                content_revisions.c.status == "draft",
            )
            .values(status="validating")
            .returning(content_revisions.c.content_revision_id)
        )
        if updated_id is None:
            raise DomainError(ErrorCode.INVALID_TRANSITION)

    async def complete_validation(
        self,
        *,
        content_revision_id: UUID,
        report_id: UUID,
        command_id: UUID,
        validator_set_revision_id: UUID,
        status: str,
        findings: tuple[Mapping[str, object], ...],
        now: datetime,
    ) -> StoredContentRevision:
        await self._session.execute(
            validation_reports.insert().values(
                report_id=report_id,
                subject_revision_id=content_revision_id,
                validator_set_revision_id=validator_set_revision_id,
                command_id=command_id,
                status="running",
                started_at=now,
                completed_at=None,
                finding_count=0,
                summary_checksum=None,
            )
        )
        if findings:
            await self._session.execute(
                validation_findings.insert(),
                [dict(finding, report_id=report_id) for finding in findings],
            )
        await self._session.execute(
            validation_reports.update()
            .where(
                validation_reports.c.report_id == report_id,
                validation_reports.c.status == "running",
            )
            .values(status=status, completed_at=now)
        )
        final_status = "validated" if status == "passed" else "draft"
        values: dict[str, object] = {"status": final_status}
        if final_status == "validated":
            values["validated_at"] = now
        await self._session.execute(
            content_revisions.update()
            .where(
                content_revisions.c.content_revision_id == content_revision_id,
                content_revisions.c.status == "validating",
            )
            .values(**values)
        )
        return await self.get_revision(content_revision_id)

    async def decide_review(
        self,
        *,
        content_revision_id: UUID,
        decision_id: UUID,
        command_id: UUID,
        author_id: UUID,
        reviewer_id: UUID,
        decision: str,
        reason_code: str,
        now: datetime,
    ) -> StoredContentRevision:
        await self._session.execute(
            content_approval_decisions.insert().values(
                approval_decision_id=decision_id,
                content_revision_id=content_revision_id,
                author_id=author_id,
                reviewer_id=reviewer_id,
                command_id=command_id,
                decision=decision,
                reason_code=reason_code,
                decided_at=now,
            )
        )
        revision_values: dict[str, object] = {"status": decision}
        if decision == "approved":
            revision_values.update(
                approved_by_actor_id=reviewer_id,
                approved_at=now,
            )
        else:
            revision_values["retired_at"] = now
        await self._session.execute(
            content_revisions.update()
            .where(
                content_revisions.c.content_revision_id == content_revision_id,
                content_revisions.c.status == "validated",
            )
            .values(**revision_values)
        )
        return await self.get_revision(content_revision_id)

    async def require_provenance(self, provenance_id: UUID) -> None:
        source_type = await self._session.scalar(
            text(
                "SELECT source_type FROM platform.provenance_records "
                "WHERE provenance_id = :provenance_id"
            ),
            {"provenance_id": provenance_id},
        )
        if source_type not in {"fixture", "human_author", "import", "tool"}:
            raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)

    async def ensure_human_provenance(
        self,
        *,
        provenance_id: UUID,
        actor_id: UUID,
        source_ref: str,
        input_fingerprint: str,
        created_at: datetime,
    ) -> None:
        await self._session.execute(
            text(
                "INSERT INTO platform.provenance_records "
                "(provenance_id,source_type,source_ref,created_by_actor_id,tool_revision_id,"
                "model_code,prompt_revision_id,transformation_chain,input_fingerprint,created_at) "
                "VALUES (:provenance,'human_author',:source_ref,:actor,NULL,NULL,NULL,"
                "CAST('[]' AS jsonb),:fingerprint,:created_at) ON CONFLICT DO NOTHING"
            ),
            {
                "provenance": provenance_id,
                "source_ref": source_ref,
                "actor": actor_id,
                "fingerprint": input_fingerprint,
                "created_at": created_at,
            },
        )
        await self.require_provenance(provenance_id)

    async def resolve_published_references(
        self,
        *,
        variety_id: UUID,
        references: tuple[dict[str, JsonValue], ...],
    ) -> tuple[PublishedReferenceSnapshot, ...]:
        resolved: list[PublishedReferenceSnapshot] = []
        for reference in references:
            kind = reference.get("reference_kind")
            raw_id = reference.get("revision_id")
            if kind != "skill_revision" or not isinstance(raw_id, str):
                raise DomainError(ErrorCode.REFERENCE_NOT_PUBLISHABLE)
            try:
                revision_id = UUID(raw_id)
            except ValueError:
                raise DomainError(ErrorCode.REFERENCE_NOT_PUBLISHABLE) from None
            row = (
                (
                    await self._session.execute(
                        text(
                            "SELECT skill_revision.skill_revision_id, skill_revision.skill_type, "
                            "skill_revision.modality, skill_revision.operation, "
                            "skill_revision.target_ref, skill_revision.scope, "
                            "skill_revision.load_profile, skill_revision.provenance_id, "
                            "pack_revision.license_refs "
                            "FROM catalogue.skill_revisions AS skill_revision "
                            "JOIN catalogue.language_pack_revisions AS pack_revision "
                            "ON pack_revision.pack_revision_id = skill_revision.pack_revision_id "
                            "JOIN catalogue.language_pack_publications AS publication "
                            "ON publication.pack_revision_id = pack_revision.pack_revision_id "
                            "WHERE skill_revision.skill_revision_id = :revision_id "
                            "AND skill_revision.status = 'published' "
                            "AND pack_revision.status = 'published' "
                            "AND pack_revision.target_variety_id = :variety_id "
                            "AND publication.retired_at IS NULL"
                        ),
                        {"revision_id": revision_id, "variety_id": variety_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None or not row["license_refs"]:
                raise DomainError(ErrorCode.REFERENCE_NOT_PUBLISHABLE)
            checksum_payload = {
                "revision_id": str(row["skill_revision_id"]),
                "skill_type": row["skill_type"],
                "modality": row["modality"],
                "operation": row["operation"],
                "target_ref": row["target_ref"],
                "scope": row["scope"],
                "load_profile": row["load_profile"],
            }
            resolved.append(
                PublishedReferenceSnapshot(
                    revision_id=revision_id,
                    reference_kind=kind,
                    checksum=hashlib.sha256(canonical_json_bytes(checksum_payload)).hexdigest(),
                    provenance_id=row["provenance_id"],
                    rights_ref=row["license_refs"][0],
                )
            )
        return tuple(resolved)

    async def publish(
        self,
        *,
        content_id: UUID,
        content_revision_id: UUID,
        manifest_id: UUID,
        command_id: UUID,
        publication_provenance_id: UUID,
        channel_code: str,
        compatibility_range: str,
        manifest_checksum: str,
        references: tuple[PublishedReferenceSnapshot, ...],
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
                .values(status="superseded", retired_at=now)
            )
        await self._session.execute(
            publication_manifests.insert().values(
                publication_manifest_id=manifest_id,
                content_id=content_id,
                content_revision_id=content_revision_id,
                channel_code=channel_code,
                compatibility_range=compatibility_range,
                checksum=manifest_checksum,
                provenance_id=publication_provenance_id,
                command_id=command_id,
                entry_count=len(references),
                published_at=now,
                retired_at=None,
            )
        )
        if references:
            await self._session.execute(
                publication_manifest_entries.insert(),
                [
                    {
                        "publication_manifest_id": manifest_id,
                        "ordinal": ordinal,
                        "referenced_revision_id": reference.revision_id,
                        "reference_kind": reference.reference_kind,
                        "reference_checksum": reference.checksum,
                        "reference_provenance_id": reference.provenance_id,
                        "reference_rights_ref": reference.rights_ref,
                        "reference_status": reference.status,
                    }
                    for ordinal, reference in enumerate(references, start=1)
                ],
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
        return await self.get_revision(content_revision_id)

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
            publication_manifests.update()
            .where(
                publication_manifests.c.content_revision_id == content_revision_id,
                publication_manifests.c.retired_at.is_(None),
            )
            .values(retired_at=now)
        )
        await self._session.execute(
            content_revisions.update()
            .where(
                content_revisions.c.content_revision_id == content_revision_id,
                content_revisions.c.status == "published",
            )
            .values(status="retired", retired_at=now)
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
        return _stored_revision(revision)
