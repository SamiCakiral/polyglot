from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from polyglot.modules.practice.domain import (
    PracticeDirection,
    PracticeMode,
    PracticeStackKind,
    StackMember,
    build_run_snapshot,
    combine_stack_members,
    practice_stack_checksum,
    validate_preset,
)
from polyglot.platform.errors import DomainError


def uid(number: int) -> UUID:
    return UUID(f"019fec00-0000-7000-8000-{number:012x}")


def member(number: int, *, label: str | None = None) -> StackMember:
    return StackMember(
        sense_id=uid(number),
        sense_revision_id=uid(number + 100),
        label=label or f"mot {number}",
        definition=f"definition {number}",
        source_kind="selection",
        source_ref=f"sense:{uid(number)}",
    )


def test_stack_checksum_covers_order_and_frozen_text() -> None:
    first = practice_stack_checksum((member(1), member(2)), pack_revision_id=uid(500))
    reordered = practice_stack_checksum((member(2), member(1)), pack_revision_id=uid(500))
    relabelled = practice_stack_checksum(
        (member(1, label="autre"), member(2)), pack_revision_id=uid(500)
    )

    assert first != reordered
    assert first != relabelled


def test_combining_stacks_is_stable_and_deduplicates_senses() -> None:
    assert combine_stack_members(((member(1), member(2)), (member(2), member(3)))) == (
        member(1),
        member(2),
        member(3),
    )


def test_preset_requires_at_least_one_stack() -> None:
    with pytest.raises(DomainError):
        validate_preset(
            name="Vide",
            stack_ids=(),
            direction=PracticeDirection.TARGET_TO_SUPPORT,
            mode=PracticeMode.CARDS,
        )


def test_run_snapshot_is_exact_and_versioned() -> None:
    snapshot = build_run_snapshot(
        preset_revision_id=uid(700),
        stack_ids=(uid(10),),
        stack_kind=PracticeStackKind.DAILY,
        pedagogical_day=date(2026, 8, 11),
        direction=PracticeDirection.BIDIRECTIONAL,
        mode=PracticeMode.MIXED,
        members=(member(1), member(2)),
        started_at=datetime(2026, 8, 11, tzinfo=UTC),
    )

    assert snapshot.schema_version == 1
    assert snapshot.member_count == 2
    assert snapshot.members == (member(1), member(2))
    assert snapshot.fingerprint
