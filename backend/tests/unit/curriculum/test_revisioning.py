from __future__ import annotations

from dataclasses import replace

import pytest

from polyglot.modules.curriculum import ArcType, CurriculumError
from polyglot.modules.curriculum.revisioning import (
    ModuleRevisionMapping,
    RevisionMappingEntry,
    build_successor_revision,
    validate_revision_mapping,
)
from tests.unit.curriculum.test_module_contract import day, revision, uid


def source_module():  # type: ignore[no-untyped-def]
    return revision(days=(day(1), day(2, arc=ArcType.GUIDED_USE), day(3, arc=ArcType.TRANSFER)))


def test_successor_preserves_executed_prefix_and_requires_expected_revision() -> None:
    source = source_module()
    future = replace(day(3, arc=ArcType.TRANSFER), objective_codes=("new-transfer",))
    successor = build_successor_revision(
        source,
        successor_revision_id=uid(50),
        candidate_days=(source.days[0], source.days[1], future),
        executed_through_ordinal=2,
        expected_revision_no=1,
    )
    assert successor.revision_no == 2
    assert successor.days[:2] == source.days[:2]
    assert successor.days[2] == future

    with pytest.raises(CurriculumError, match="module_past_day_mutated"):
        build_successor_revision(
            source,
            successor_revision_id=uid(51),
            candidate_days=(
                replace(source.days[0], objective_codes=("mutated",)),
                *source.days[1:],
            ),
            executed_through_ordinal=2,
            expected_revision_no=1,
        )


def test_mapping_requires_every_day_and_target_and_explicit_enrollment_consent() -> None:
    source = source_module()
    successor = build_successor_revision(
        source,
        successor_revision_id=uid(52),
        candidate_days=source.days,
        executed_through_ordinal=1,
        expected_revision_no=1,
    )
    incomplete = ModuleRevisionMapping(
        uid(60),
        source.module_revision_id,
        successor.module_revision_id,
        (RevisionMappingEntry(1, 1, "skill:1", "skill:1"),),
        False,
    )

    findings = validate_revision_mapping(source, successor, incomplete)

    assert {item.message_code for item in findings} >= {
        "module_revision_mapping_incomplete",
        "module_enrollment_migration_not_consented",
    }
