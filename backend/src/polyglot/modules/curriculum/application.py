from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from polyglot.modules.identity.application import RequestContext


@dataclass(frozen=True, slots=True)
class ModuleSummary:
    module_id: UUID
    module_code: str
    module_revision_id: UUID
    pack_revision_id: UUID
    primary_intention: str
    nominal_days: int
    max_days: int
    min_minutes: int
    max_minutes: int
    entry_profile_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EnrollmentView:
    enrollment_id: UUID
    profile_id: UUID
    module_revision_id: UUID
    module_code: str
    nominal_days: int
    max_days: int
    status: str
    current_day_ordinal: int
    started_on_pedagogical_day: date | None
    completed_at: datetime | None
    terminal_at: datetime | None
    paused_at: datetime | None
    waiver_refs: tuple[str, ...]
    migration_map_revision_id: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class EnrollInModule:
    enrollment_id: UUID
    module_revision_id: UUID
    pedagogical_day: date
    waiver_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PauseEnrollment:
    paused_at: datetime


@dataclass(frozen=True, slots=True)
class CompleteEnrollment:
    completed_at: datetime


class CurriculumApplicationService(Protocol):
    async def list_modules(
        self,
        actor_id: UUID,
        *,
        pack_revision_id: UUID | None = None,
    ) -> tuple[ModuleSummary, ...]: ...

    async def get_enrollment(self, actor_id: UUID, enrollment_id: UUID) -> EnrollmentView: ...

    async def enroll(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: EnrollInModule,
        *,
        idempotency_key: str,
        context: RequestContext,
    ) -> EnrollmentView: ...

    async def pause(
        self,
        actor_id: UUID,
        enrollment_id: UUID,
        command: PauseEnrollment,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> EnrollmentView: ...

    async def complete(
        self,
        actor_id: UUID,
        enrollment_id: UUID,
        command: CompleteEnrollment,
        *,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> EnrollmentView: ...


__all__ = [
    "CompleteEnrollment",
    "CurriculumApplicationService",
    "EnrollInModule",
    "EnrollmentView",
    "ModuleSummary",
    "PauseEnrollment",
]
