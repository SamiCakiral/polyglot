from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ReferenceStatus(StrEnum):
    PUBLISHED = "published"
    RETIRED = "retired"
    DRAFT = "draft"
    MISSING = "missing"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    reference: str
    kind: str
    status: ReferenceStatus
    pack_revision_id: str
    variety_id: str
    checksum: str
    provenance_id: str
    rights_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReferenceExpectation:
    reference: str
    kind: str
    pack_revision_id: str
    variety_id: str
    checksum: str


class CurriculumReferencePort(Protocol):
    def resolve(self, references: tuple[str, ...]) -> tuple[ResolvedReference, ...]: ...
