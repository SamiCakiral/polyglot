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


def test_mapping_rejects_missing_destinations_duplicates_and_conflicts() -> None:
    source = source_module()
    successor = build_successor_revision(
        source,
        successor_revision_id=uid(80),
        candidate_days=source.days,
        executed_through_ordinal=1,
        expected_revision_no=1,
    )
    entries = tuple(
        RevisionMappingEntry(day.ordinal, 999, target, "skill:does-not-exist")
        for day in source.days
        for target in day.primary_target_refs
    )
    hostile = ModuleRevisionMapping(
        uid(81),
        source.module_revision_id,
        successor.module_revision_id,
        (*entries, entries[0], replace(entries[0], target_day_ordinal=1)),
        True,
    )

    findings = validate_revision_mapping(source, successor, hostile)

    assert {
        "module_revision_mapping_target_missing",
        "module_revision_mapping_duplicate",
        "module_revision_mapping_conflict",
    }.issubset({item.message_code for item in findings})


def complete_entries(source, target):  # type: ignore[no-untyped-def]
    return tuple(
        RevisionMappingEntry(day.ordinal, day.ordinal, reference, reference)
        for day in source.days
        for reference in day.primary_target_refs
        if (day.ordinal, reference)
        in {
            (target_day.ordinal, target_ref)
            for target_day in target.days
            for target_ref in target_day.primary_target_refs
        }
    )


def test_mapping_only_accepts_the_direct_successor_of_the_same_module() -> None:
    source = source_module()
    successor = build_successor_revision(
        source,
        successor_revision_id=uid(90),
        candidate_days=source.days,
        executed_through_ordinal=0,
        expected_revision_no=source.revision_no,
    )
    unrelated = replace(
        successor,
        module_id=uid(91),
        revision_no=99,
        supersedes_revision_id=None,
        payload_checksum="",
    )
    mapping = ModuleRevisionMapping(
        uid(92),
        source.module_revision_id,
        unrelated.module_revision_id,
        complete_entries(source, unrelated),
        True,
    )

    findings = validate_revision_mapping(source, unrelated, mapping)

    assert "module_revision_not_direct_successor" in {
        item.message_code for item in findings
    }


def test_mapping_cannot_merge_multiple_source_objectives() -> None:
    source = source_module()
    successor = build_successor_revision(
        source,
        successor_revision_id=uid(93),
        candidate_days=source.days,
        executed_through_ordinal=0,
        expected_revision_no=source.revision_no,
    )
    destination = (successor.days[0].ordinal, successor.days[0].primary_target_refs[0])
    entries = tuple(
        RevisionMappingEntry(day.ordinal, destination[0], source_ref, destination[1])
        for day in source.days
        for source_ref in day.primary_target_refs
    )
    mapping = ModuleRevisionMapping(
        uid(94),
        source.module_revision_id,
        successor.module_revision_id,
        entries,
        True,
    )

    findings = validate_revision_mapping(source, successor, mapping)

    assert "module_revision_mapping_conflict" in {
        item.message_code for item in findings
    }
