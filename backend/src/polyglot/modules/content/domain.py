from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue


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


class ValidationReportStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    HUMAN_REQUIRED = "human_required"


def _invalid(field: str) -> DomainError:
    return DomainError(
        ErrorCode.VALIDATION_FAILED,
        field_errors=[{"location": field, "code": "invalid"}],
    )


def _require_uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise _invalid(field)


def _freeze_payload(value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    copied = deepcopy(dict(value))
    if not isinstance(copied.get("schema_version"), int):
        raise _invalid("payload.schema_version")
    return MappingProxyType(copied)


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    validator_set_revision_id: UUID
    status: ValidationReportStatus

    def __post_init__(self) -> None:
        _require_uuid7(self.validator_set_revision_id, "validator_set_revision_id")

    @classmethod
    def passed(cls, validator_set_revision_id: UUID) -> ValidationOutcome:
        return cls(validator_set_revision_id, ValidationReportStatus.PASSED)

    @classmethod
    def failed(cls, validator_set_revision_id: UUID) -> ValidationOutcome:
        return cls(validator_set_revision_id, ValidationReportStatus.FAILED)

    @classmethod
    def human_required(cls, validator_set_revision_id: UUID) -> ValidationOutcome:
        return cls(validator_set_revision_id, ValidationReportStatus.HUMAN_REQUIRED)


@dataclass(frozen=True, slots=True)
class ContentItem:
    content_id: UUID
    content_type: str
    variety_id: UUID
    editorial_owner_id: UUID
    lineage_root_id: UUID
    parent_content_id: UUID | None
    version: int
    created_at: datetime

    def __post_init__(self) -> None:
        for field in (
            "content_id",
            "variety_id",
            "editorial_owner_id",
            "lineage_root_id",
        ):
            _require_uuid7(getattr(self, field), field)
        if self.parent_content_id is not None:
            _require_uuid7(self.parent_content_id, "parent_content_id")
        if not self.content_type or self.version < 1:
            raise _invalid("content_item")


@dataclass(frozen=True, slots=True)
class ContentRevision:
    content_id: UUID
    content_revision_id: UUID
    revision_no: int
    variety_id: UUID
    created_by_actor_id: UUID
    provenance_id: UUID
    rights_ref: str
    payload: Mapping[str, JsonValue]
    status: ContentRevisionStatus
    created_at: datetime
    supersedes_revision_id: UUID | None = None
    validator_set_revision_id: UUID | None = None
    approved_by_actor_id: UUID | None = None
    validated_at: datetime | None = None
    approved_at: datetime | None = None
    published_at: datetime | None = None
    retired_at: datetime | None = None

    def __post_init__(self) -> None:
        for field in (
            "content_id",
            "content_revision_id",
            "variety_id",
            "created_by_actor_id",
            "provenance_id",
        ):
            _require_uuid7(getattr(self, field), field)
        for field in (
            "supersedes_revision_id",
            "validator_set_revision_id",
            "approved_by_actor_id",
        ):
            value = getattr(self, field)
            if value is not None:
                _require_uuid7(value, field)
        if self.revision_no < 1 or not self.rights_ref:
            raise _invalid("content_revision")
        object.__setattr__(self, "payload", _freeze_payload(self.payload))

    @classmethod
    def create_draft(
        cls,
        *,
        content_id: UUID,
        content_revision_id: UUID,
        revision_no: int,
        variety_id: UUID,
        created_by_actor_id: UUID,
        provenance_id: UUID,
        rights_ref: str,
        payload: Mapping[str, JsonValue],
        now: datetime,
    ) -> ContentRevision:
        return cls(
            content_id=content_id,
            content_revision_id=content_revision_id,
            revision_no=revision_no,
            variety_id=variety_id,
            created_by_actor_id=created_by_actor_id,
            provenance_id=provenance_id,
            rights_ref=rights_ref,
            payload=payload,
            status=ContentRevisionStatus.DRAFT,
            created_at=now,
        )

    def revise(
        self,
        *,
        content_revision_id: UUID,
        revision_no: int,
        actor_id: UUID,
        payload: Mapping[str, JsonValue],
        provenance_id: UUID,
        rights_ref: str,
        now: datetime,
    ) -> ContentRevision:
        if self.status is not ContentRevisionStatus.DRAFT:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        if actor_id != self.created_by_actor_id or revision_no != self.revision_no + 1:
            raise DomainError(ErrorCode.FORBIDDEN)
        return ContentRevision.create_draft(
            content_id=self.content_id,
            content_revision_id=content_revision_id,
            revision_no=revision_no,
            variety_id=self.variety_id,
            created_by_actor_id=actor_id,
            provenance_id=provenance_id,
            rights_ref=rights_ref,
            payload=payload,
            now=now,
        )._with(supersedes_revision_id=self.content_revision_id)

    def complete_validation(
        self,
        outcome: ValidationOutcome,
        *,
        now: datetime,
    ) -> ContentRevision:
        if self.status is not ContentRevisionStatus.DRAFT:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        if outcome.status is not ValidationReportStatus.PASSED:
            return self._with(validator_set_revision_id=outcome.validator_set_revision_id)
        return self._with(
            status=ContentRevisionStatus.VALIDATED,
            validator_set_revision_id=outcome.validator_set_revision_id,
            validated_at=now,
        )

    def approve(self, *, actor_id: UUID, now: datetime) -> ContentRevision:
        if actor_id == self.created_by_actor_id:
            raise DomainError(ErrorCode.SELF_APPROVAL_FORBIDDEN)
        if self.status is not ContentRevisionStatus.VALIDATED:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return self._with(
            status=ContentRevisionStatus.APPROVED,
            approved_by_actor_id=actor_id,
            approved_at=now,
        )

    def publish(self, *, now: datetime) -> ContentRevision:
        if self.status is not ContentRevisionStatus.APPROVED:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return self._with(status=ContentRevisionStatus.PUBLISHED, published_at=now)

    def retire(self, *, now: datetime) -> ContentRevision:
        if self.status is not ContentRevisionStatus.PUBLISHED:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return self._with(status=ContentRevisionStatus.RETIRED, retired_at=now)

    def supersede(self) -> ContentRevision:
        if self.status is not ContentRevisionStatus.PUBLISHED:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return self._with(status=ContentRevisionStatus.SUPERSEDED)

    def _with(self, **changes: object) -> ContentRevision:
        return replace(self, **changes)
