from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from polyglot.modules.practice.domain import (
    PracticeDirection,
    PracticeMode,
    PracticeStackKind,
    StackMember,
)
from polyglot.platform.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class CreatePracticeStack:
    name: str
    stack_kind: PracticeStackKind
    language_pack_revision_id: UUID | None
    pedagogical_day: date | None
    source_list_snapshot_id: UUID | None
    source_refs: tuple[str, ...]
    members: tuple[StackMember, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PracticeStackView:
    stack_id: UUID
    profile_id: UUID
    language_pack_revision_id: UUID
    name: str
    stack_kind: PracticeStackKind
    pedagogical_day: date | None
    source_refs: tuple[str, ...]
    checksum: str
    created_at: datetime
    members: tuple[StackMember, ...]


@dataclass(frozen=True, slots=True)
class CreatePracticePreset:
    name: str
    stack_ids: tuple[UUID, ...]
    direction: PracticeDirection
    mode: PracticeMode
    settings: dict[str, JsonValue]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PracticePresetView:
    preset_id: UUID
    profile_id: UUID
    preset_revision_id: UUID
    revision_no: int
    name: str
    stack_ids: tuple[UUID, ...]
    direction: PracticeDirection
    mode: PracticeMode
    settings: dict[str, JsonValue]
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PracticeRunView:
    run_id: UUID
    profile_id: UUID
    preset_id: UUID
    preset_revision_id: UUID
    status: str
    current_position: int
    member_count: int
    version: int
    direction: PracticeDirection
    mode: PracticeMode
    current_item: StackMember | None
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class StackInjectionView:
    injection_id: UUID
    profile_id: UUID
    stack_id: UUID
    status: str
    version: int
    requested_at: datetime


class PracticeService(Protocol):
    async def create_stack(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: CreatePracticeStack,
        *,
        idempotency_key: str,
    ) -> PracticeStackView: ...

    async def combine_stacks(
        self,
        actor_id: UUID,
        profile_id: UUID,
        *,
        stack_ids: tuple[UUID, ...],
        name: str,
        created_at: datetime,
        idempotency_key: str,
    ) -> PracticeStackView: ...

    async def list_stacks(
        self, actor_id: UUID, profile_id: UUID
    ) -> tuple[PracticeStackView, ...]: ...

    async def get_stack(self, actor_id: UUID, stack_id: UUID) -> PracticeStackView: ...

    async def inject_stack(
        self,
        actor_id: UUID,
        stack_id: UUID,
        *,
        requested_at: datetime,
        idempotency_key: str,
    ) -> StackInjectionView: ...

    async def create_preset(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: CreatePracticePreset,
        *,
        idempotency_key: str,
    ) -> PracticePresetView: ...

    async def list_presets(
        self, actor_id: UUID, profile_id: UUID
    ) -> tuple[PracticePresetView, ...]: ...

    async def start_run(
        self,
        actor_id: UUID,
        preset_id: UUID,
        *,
        started_at: datetime,
        idempotency_key: str,
    ) -> PracticeRunView: ...

    async def get_run(self, actor_id: UUID, run_id: UUID) -> PracticeRunView: ...

    async def advance_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        *,
        expected_version: int,
        advanced_at: datetime,
        idempotency_key: str,
    ) -> PracticeRunView: ...

    async def transition_run(
        self,
        actor_id: UUID,
        run_id: UUID,
        *,
        action: str,
        expected_version: int,
        changed_at: datetime,
        idempotency_key: str,
    ) -> PracticeRunView: ...
