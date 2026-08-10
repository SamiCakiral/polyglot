from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from .bindings import CurriculumError, _require_uuid7
from .domain import LearningModuleRevision, ModuleDay, ModuleStatus
from .validation import FindingSeverity, ValidationFinding


@dataclass(frozen=True, slots=True)
class RevisionMappingEntry:
    source_day_ordinal: int
    target_day_ordinal: int
    source_target_ref: str
    target_target_ref: str


@dataclass(frozen=True, slots=True)
class ModuleRevisionMapping:
    mapping_id: UUID
    source_revision_id: UUID
    target_revision_id: UUID
    entries: tuple[RevisionMappingEntry, ...]
    enrollment_migration_consented: bool

    def __post_init__(self) -> None:
        for field in ("mapping_id", "source_revision_id", "target_revision_id"):
            _require_uuid7(getattr(self, field), field)
        object.__setattr__(self, "entries", tuple(self.entries))


def build_successor_revision(
    source: LearningModuleRevision,
    *,
    successor_revision_id: UUID,
    candidate_days: tuple[ModuleDay, ...],
    executed_through_ordinal: int,
    expected_revision_no: int,
) -> LearningModuleRevision:
    _require_uuid7(successor_revision_id, "successor_revision_id")
    if expected_revision_no != source.revision_no:
        raise CurriculumError("module_revision_conflict")
    if not 0 <= executed_through_ordinal <= source.nominal_days:
        raise CurriculumError("module_day_ordinal_gap")
    if candidate_days[:executed_through_ordinal] != source.days[:executed_through_ordinal]:
        raise CurriculumError("module_past_day_mutated")
    return replace(
        source,
        module_revision_id=successor_revision_id,
        revision_no=source.revision_no + 1,
        status=ModuleStatus.DRAFT,
        days=tuple(candidate_days),
        supersedes_revision_id=source.module_revision_id,
        payload_checksum="",
    )


def validate_revision_mapping(
    source: LearningModuleRevision,
    target: LearningModuleRevision,
    mapping: ModuleRevisionMapping,
) -> tuple[ValidationFinding, ...]:
    findings: list[ValidationFinding] = []
    mapped = {
        (entry.source_day_ordinal, entry.source_target_ref)
        for entry in mapping.entries
    }
    required = {
        (item.ordinal, reference)
        for item in source.days
        for reference in item.primary_target_refs
    }
    if mapping.source_revision_id != source.module_revision_id or mapping.target_revision_id != target.module_revision_id or not required.issubset(mapped):
        findings.append(
            ValidationFinding(
                "W11-REVISION-V1",
                FindingSeverity.BLOCKING,
                "revision_mapping.entries",
                "module_revision_mapping_incomplete",
            )
        )
    if not mapping.enrollment_migration_consented:
        findings.append(
            ValidationFinding(
                "W11-REVISION-V1",
                FindingSeverity.BLOCKING,
                "revision_mapping.enrollment",
                "module_enrollment_migration_not_consented",
            )
        )
    return tuple(sorted(findings, key=lambda item: item.sort_key))
