from dataclasses import asdict, dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode


class ContentRevisionStatus(StrEnum):
    DRAFT = "draft"
    VALIDATING = "validating"
    VALIDATED = "validated"
    APPROVED = "approved"
    PUBLISHED = "published"
    RETIRED = "retired"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    ABANDONED = "abandoned"


class PrerequisiteEdgeType(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    CONTRAST = "contrast"
    TRANSFER = "transfer"


class LexicalUnitType(StrEnum):
    WORD = "word"
    MULTIWORD_EXPRESSION = "multiword_expression"
    PROPER_NAME = "proper_name"
    LEXICALIZED_CONSTRUCTION = "lexicalized_construction"


_MODALITIES = frozenset({"reading", "listening", "writing", "speaking"})
_OPERATIONS = frozenset(
    {
        "recognize",
        "recall",
        "discriminate",
        "transform",
        "produce",
        "interact",
        "repair",
        "transfer",
    }
)
_TRANSITIONS: dict[ContentRevisionStatus, frozenset[ContentRevisionStatus]] = {
    ContentRevisionStatus.DRAFT: frozenset(
        {ContentRevisionStatus.VALIDATING, ContentRevisionStatus.ABANDONED}
    ),
    ContentRevisionStatus.VALIDATING: frozenset(
        {ContentRevisionStatus.VALIDATED, ContentRevisionStatus.REJECTED}
    ),
    ContentRevisionStatus.VALIDATED: frozenset(
        {ContentRevisionStatus.APPROVED, ContentRevisionStatus.REJECTED}
    ),
    ContentRevisionStatus.APPROVED: frozenset(
        {ContentRevisionStatus.PUBLISHED, ContentRevisionStatus.REJECTED}
    ),
}


def _invalid(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


def require_uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise _invalid(f"{field} must be UUIDv7")


def require_revision_number(value: int) -> None:
    if value < 1:
        raise _invalid("revision_no must be positive")


def require_stable_code(value: str, field: str) -> None:
    if not value or len(value) > 120 or any(character.isspace() for character in value):
        raise _invalid(f"{field} must be a non-empty stable code")


@dataclass(frozen=True, slots=True)
class LanguagePackRevision:
    pack_revision_id: UUID
    pack_id: UUID
    revision_no: int
    target_variety_id: UUID
    support_variety_ids: tuple[UUID, ...]
    status: ContentRevisionStatus
    engine_min_version: str
    engine_max_version: str
    capabilities: tuple[str, ...]
    checksum_manifest: tuple[tuple[str, str], ...]
    license_refs: tuple[str, ...]
    provenance_id: UUID
    published_at: datetime | None

    def __post_init__(self) -> None:
        for field, value in (
            ("pack_revision_id", self.pack_revision_id),
            ("pack_id", self.pack_id),
            ("target_variety_id", self.target_variety_id),
            ("provenance_id", self.provenance_id),
        ):
            require_uuid7(value, field)
        require_revision_number(self.revision_no)
        if not self.support_variety_ids:
            raise _invalid("at least one support variety is required")
        for variety_id in self.support_variety_ids:
            require_uuid7(variety_id, "support_variety_ids")
        if len(set(self.support_variety_ids)) != len(self.support_variety_ids):
            raise _invalid("support varieties must be unique")
        if not self.engine_min_version or not self.engine_max_version:
            raise _invalid("engine compatibility must be explicit")
        if not self.capabilities or len(set(self.capabilities)) != len(self.capabilities):
            raise _invalid("capabilities must be non-empty and unique")
        if not self.license_refs:
            raise _invalid("at least one license reference is required")
        if not self.checksum_manifest:
            raise _invalid("checksum manifest must be non-empty")
        for name, checksum in self.checksum_manifest:
            invalid_checksum = len(checksum) != 64 or any(
                character not in "0123456789abcdef" for character in checksum
            )
            if not name or invalid_checksum:
                raise _invalid("checksum manifest requires lowercase SHA-256 values")
        if (self.status is ContentRevisionStatus.PUBLISHED) != (self.published_at is not None):
            raise _invalid("published_at is required exactly for published revisions")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def change_status(
        self,
        status: ContentRevisionStatus,
        *,
        published_at: datetime | None = None,
    ) -> "LanguagePackRevision":
        if self.status is ContentRevisionStatus.PUBLISHED:
            raise DomainError(
                ErrorCode.INVALID_TRANSITION,
                detail="published revisions are immutable",
            )
        if status not in _TRANSITIONS.get(self.status, frozenset()):
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return replace(self, status=status, published_at=published_at)

    def retire(self, successor_revision_id: UUID) -> "LanguagePackRevision":
        if self.status is not ContentRevisionStatus.PUBLISHED:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        require_uuid7(successor_revision_id, "successor_revision_id")
        return replace(
            self,
            pack_revision_id=successor_revision_id,
            revision_no=self.revision_no + 1,
            status=ContentRevisionStatus.RETIRED,
            published_at=None,
        )


@dataclass(frozen=True, slots=True)
class SkillRevision:
    skill_revision_id: UUID
    skill_id: UUID
    revision_no: int
    skill_code: str
    skill_type: str
    modality: str
    operation: str
    target_ref: str
    scope: tuple[str, ...]
    evidence_protocol_ids: tuple[UUID, ...]
    load_profile: tuple[tuple[str, int], ...]
    status: ContentRevisionStatus
    provenance_id: UUID

    def __post_init__(self) -> None:
        require_uuid7(self.skill_revision_id, "skill_revision_id")
        require_uuid7(self.skill_id, "skill_id")
        require_uuid7(self.provenance_id, "provenance_id")
        require_revision_number(self.revision_no)
        require_stable_code(self.skill_code, "skill_code")
        require_stable_code(self.skill_type, "skill_type")
        require_stable_code(self.target_ref, "target_ref")
        if self.modality not in _MODALITIES:
            raise _invalid("modality is not canonical")
        if self.operation not in _OPERATIONS:
            raise _invalid("operation is not canonical")
        if not self.scope:
            raise _invalid("skill scope must be non-empty")
        for protocol_id in self.evidence_protocol_ids:
            require_uuid7(protocol_id, "evidence_protocol_ids")


@dataclass(frozen=True, slots=True)
class SkillPrerequisiteEdge:
    edge_id: UUID
    from_skill_revision_id: UUID
    to_skill_revision_id: UUID
    edge_type: PrerequisiteEdgeType
    provenance_id: UUID

    def __post_init__(self) -> None:
        require_uuid7(self.edge_id, "edge_id")
        require_uuid7(self.from_skill_revision_id, "from_skill_revision_id")
        require_uuid7(self.to_skill_revision_id, "to_skill_revision_id")
        require_uuid7(self.provenance_id, "provenance_id")
        if self.from_skill_revision_id == self.to_skill_revision_id:
            if self.edge_type is PrerequisiteEdgeType.REQUIRED:
                raise DomainError(ErrorCode.PREREQUISITE_CYCLE)
            raise _invalid("a prerequisite edge cannot reference itself")
