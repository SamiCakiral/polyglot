from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from .bindings import CurriculumError, _require_unique, _require_uuid7


class EnrollmentStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    CANCELLED = "cancelled"


_TERMINAL = {
    EnrollmentStatus.COMPLETED,
    EnrollmentStatus.ABANDONED,
    EnrollmentStatus.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class ModuleEnrollment:
    enrollment_id: UUID
    profile_id: UUID
    module_revision_id: UUID
    nominal_days: int
    max_days: int
    status: EnrollmentStatus = EnrollmentStatus.PLANNED
    current_day_ordinal: int = 1
    started_on_pedagogical_day: date | None = None
    completed_at: datetime | None = None
    terminal_at: datetime | None = None
    paused_at: datetime | None = None
    waiver_refs: tuple[str, ...] = ()
    migration_map_revision_id: UUID | None = None
    version: int = 1

    def __post_init__(self) -> None:
        for field in ("enrollment_id", "profile_id", "module_revision_id"):
            _require_uuid7(getattr(self, field), field)
        if self.migration_map_revision_id is not None:
            _require_uuid7(self.migration_map_revision_id, "migration_map_revision_id")
        waivers = tuple(self.waiver_refs)
        _require_unique(waivers, "waiver_refs")
        object.__setattr__(self, "waiver_refs", tuple(sorted(waivers)))
        if not 3 <= self.nominal_days <= self.max_days <= 30:
            raise CurriculumError("module_duration_out_of_range")
        if not 1 <= self.current_day_ordinal <= self.nominal_days or self.version < 1:
            raise CurriculumError("module_day_ordinal_gap")
        for value in (self.completed_at, self.terminal_at, self.paused_at):
            if value is not None and value.tzinfo is None:
                raise CurriculumError("module_enrollment_clock_invalid")
        if (self.status is EnrollmentStatus.COMPLETED) != (self.completed_at is not None):
            raise CurriculumError("completion_criteria_missing")
        if (self.status in _TERMINAL) != (self.terminal_at is not None):
            raise CurriculumError("module_enrollment_transition_invalid")
        if (self.status is EnrollmentStatus.PAUSED) != (self.paused_at is not None):
            raise CurriculumError("module_enrollment_transition_invalid")
        if self.status is EnrollmentStatus.PLANNED and self.started_on_pedagogical_day is not None:
            raise CurriculumError("module_enrollment_transition_invalid")
        if self.status not in {EnrollmentStatus.PLANNED, EnrollmentStatus.CANCELLED} and (
            self.started_on_pedagogical_day is None
        ):
            raise CurriculumError("module_enrollment_transition_invalid")

    @classmethod
    def plan(
        cls,
        *,
        enrollment_id: UUID,
        profile_id: UUID,
        module_revision_id: UUID,
        nominal_days: int,
        max_days: int,
        waiver_refs: tuple[str, ...] = (),
    ) -> ModuleEnrollment:
        return cls(
            enrollment_id=enrollment_id,
            profile_id=profile_id,
            module_revision_id=module_revision_id,
            nominal_days=nominal_days,
            max_days=max_days,
            waiver_refs=waiver_refs,
        )

    def start(self, *, pedagogical_day: date) -> ModuleEnrollment:
        self._require_status(EnrollmentStatus.PLANNED)
        return replace(
            self,
            status=EnrollmentStatus.ACTIVE,
            started_on_pedagogical_day=pedagogical_day,
            version=self.version + 1,
        )

    def pause(self, *, paused_at: datetime) -> ModuleEnrollment:
        self._require_status(EnrollmentStatus.ACTIVE)
        return replace(
            self,
            status=EnrollmentStatus.PAUSED,
            paused_at=paused_at,
            version=self.version + 1,
        )

    def resume(self, *, resumed_at: datetime) -> ModuleEnrollment:
        del resumed_at
        self._require_status(EnrollmentStatus.PAUSED)
        return replace(
            self,
            status=EnrollmentStatus.ACTIVE,
            paused_at=None,
            version=self.version + 1,
        )

    def advance_day(self, *, required_core_complete: bool) -> ModuleEnrollment:
        self._require_status(EnrollmentStatus.ACTIVE)
        if not required_core_complete:
            raise CurriculumError("required_block_incomplete")
        if self.current_day_ordinal >= self.nominal_days:
            raise CurriculumError("module_day_ordinal_gap")
        return replace(
            self,
            current_day_ordinal=self.current_day_ordinal + 1,
            version=self.version + 1,
        )

    def complete(
        self, *, completed_at: datetime, exit_criteria_satisfied: bool
    ) -> ModuleEnrollment:
        self._require_status(EnrollmentStatus.ACTIVE)
        if not exit_criteria_satisfied or self.current_day_ordinal != self.nominal_days:
            raise CurriculumError("completion_criteria_missing")
        return replace(
            self,
            status=EnrollmentStatus.COMPLETED,
            completed_at=completed_at,
            terminal_at=completed_at,
            version=self.version + 1,
        )

    def abandon(self, *, abandoned_at: datetime) -> ModuleEnrollment:
        self._require_status(EnrollmentStatus.ACTIVE)
        return replace(
            self,
            status=EnrollmentStatus.ABANDONED,
            terminal_at=abandoned_at,
            version=self.version + 1,
        )

    def cancel(self, *, cancelled_at: datetime) -> ModuleEnrollment:
        self._require_status(EnrollmentStatus.PLANNED)
        return replace(
            self,
            status=EnrollmentStatus.CANCELLED,
            terminal_at=cancelled_at,
            version=self.version + 1,
        )

    def migrate_revision(
        self,
        *,
        module_revision_id: UUID,
        mapping_revision_id: UUID | None,
        consented: bool,
    ) -> ModuleEnrollment:
        if self.status in _TERMINAL:
            raise CurriculumError("module_enrollment_revision_pinned")
        if not consented or mapping_revision_id is None:
            raise CurriculumError("module_enrollment_migration_not_consented")
        _require_uuid7(module_revision_id, "module_revision_id")
        _require_uuid7(mapping_revision_id, "migration_map_revision_id")
        return replace(
            self,
            module_revision_id=module_revision_id,
            migration_map_revision_id=mapping_revision_id,
            version=self.version + 1,
        )

    def _require_status(self, expected: EnrollmentStatus) -> None:
        if self.status is not expected:
            raise CurriculumError("module_enrollment_transition_invalid")


__all__ = ["EnrollmentStatus", "ModuleEnrollment"]
