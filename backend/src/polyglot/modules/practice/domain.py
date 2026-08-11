from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.json_types import JsonValue


class PracticeStackKind(StrEnum):
    DAILY = "daily"
    LIST_SNAPSHOT = "list_snapshot"
    DUE = "due"
    WEAK = "weak"
    SELECTION = "selection"
    COMBINED = "combined"


class PracticeDirection(StrEnum):
    TARGET_TO_SUPPORT = "target_to_support"
    SUPPORT_TO_TARGET = "support_to_target"
    BIDIRECTIONAL = "bidirectional"


class PracticeMode(StrEnum):
    CARDS = "cards"
    RECOGNITION = "recognition"
    RECALL = "recall"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class StackMember:
    sense_id: UUID
    sense_revision_id: UUID
    label: str
    definition: str
    source_kind: str
    source_ref: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (self.label, self.definition, self.source_kind, self.source_ref)
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED)


def combine_stack_members(stacks: tuple[tuple[StackMember, ...], ...]) -> tuple[StackMember, ...]:
    result: list[StackMember] = []
    seen: set[UUID] = set()
    for stack in stacks:
        for member in stack:
            if member.sense_id not in seen:
                result.append(member)
                seen.add(member.sense_id)
    if not result:
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    return tuple(result)


def practice_stack_checksum(members: tuple[StackMember, ...], *, pack_revision_id: UUID) -> str:
    if not members or len({item.sense_id for item in members}) != len(members):
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    return canonical_json_fingerprint(
        {
            "pack_revision_id": str(pack_revision_id),
            "members": [
                {
                    **asdict(item),
                    "sense_id": str(item.sense_id),
                    "sense_revision_id": str(item.sense_revision_id),
                }
                for item in members
            ],
        }
    )


def validate_preset(
    *,
    name: str,
    stack_ids: tuple[UUID, ...],
    direction: PracticeDirection,
    mode: PracticeMode,
) -> None:
    if (
        not name.strip()
        or len(name) > 200
        or not stack_ids
        or len(stack_ids) > 31
        or len(set(stack_ids)) != len(stack_ids)
        or not isinstance(direction, PracticeDirection)
        or not isinstance(mode, PracticeMode)
    ):
        raise DomainError(ErrorCode.VALIDATION_FAILED)


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    schema_version: int
    preset_revision_id: UUID
    stack_ids: tuple[UUID, ...]
    stack_kind: PracticeStackKind
    pedagogical_day: date | None
    direction: PracticeDirection
    mode: PracticeMode
    members: tuple[StackMember, ...]
    member_count: int
    started_at: datetime
    fingerprint: str


def build_run_snapshot(
    *,
    preset_revision_id: UUID,
    stack_ids: tuple[UUID, ...],
    stack_kind: PracticeStackKind,
    pedagogical_day: date | None,
    direction: PracticeDirection,
    mode: PracticeMode,
    members: tuple[StackMember, ...],
    started_at: datetime,
) -> RunSnapshot:
    if not stack_ids or not members or started_at.tzinfo is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED)
    payload: dict[str, JsonValue] = {
        "schema_version": 1,
        "preset_revision_id": str(preset_revision_id),
        "stack_ids": [str(value) for value in stack_ids],
        "stack_kind": stack_kind.value,
        "pedagogical_day": pedagogical_day.isoformat() if pedagogical_day else None,
        "direction": direction.value,
        "mode": mode.value,
        "members": [
            {
                **asdict(item),
                "sense_id": str(item.sense_id),
                "sense_revision_id": str(item.sense_revision_id),
            }
            for item in members
        ],
        "started_at": started_at.isoformat(),
    }
    return RunSnapshot(
        schema_version=1,
        preset_revision_id=preset_revision_id,
        stack_ids=stack_ids,
        stack_kind=stack_kind,
        pedagogical_day=pedagogical_day,
        direction=direction,
        mode=mode,
        members=members,
        member_count=len(members),
        started_at=started_at,
        fingerprint=canonical_json_fingerprint(payload),
    )
