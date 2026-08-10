from __future__ import annotations

import hashlib
import json
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


@dataclass(frozen=True, slots=True)
class ReferenceManifest:
    source_catalog_id: str
    entries: tuple[ReferenceExpectation, ...]
    checksum: str = ""

    def __post_init__(self) -> None:
        entries = tuple(self.entries)
        object.__setattr__(self, "entries", entries)
        payload = {
            "source_catalog_id": self.source_catalog_id,
            "entries": [
                {
                    "reference": item.reference,
                    "kind": item.kind,
                    "pack_revision_id": item.pack_revision_id,
                    "variety_id": item.variety_id,
                    "checksum": item.checksum,
                }
                for item in sorted(entries, key=lambda value: value.reference)
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        object.__setattr__(self, "checksum", f"sha256:{hashlib.sha256(encoded).hexdigest()}")


class CurriculumReferencePort(Protocol):
    def resolve(self, references: tuple[str, ...]) -> tuple[ResolvedReference, ...]: ...
