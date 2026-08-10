"""Catalogue domain contracts."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from polyglot.modules.catalogue.core import domain as catalogue_domain
from polyglot.modules.catalogue.core.domain import (
    ContentRevisionStatus,
    LanguagePackRevision,
    PrerequisiteEdgeType,
    SkillPrerequisiteEdge,
    SkillRevision,
)
from polyglot.modules.catalogue.core.graph import SkillGraph
from polyglot.platform.errors import DomainError, ErrorCode

PACK_ID = UUID("019fe900-4000-7000-8000-000000000001")
PACK_REVISION_ID = UUID("019fe900-4000-7000-8000-000000000002")
TARGET_VARIETY_ID = UUID("019fe900-4000-7000-8000-000000000003")
SUPPORT_VARIETY_ID = UUID("019fe900-4000-7000-8000-000000000004")
PROVENANCE_ID = UUID("019fe900-4000-7000-8000-000000000005")
PUBLISHED_AT = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def skill_revision(number: int, code: str) -> SkillRevision:
    return SkillRevision(
        skill_revision_id=UUID(f"019fe900-4000-7000-8001-{number:012x}"),
        skill_id=UUID(f"019fe900-4000-7000-8002-{number:012x}"),
        revision_no=1,
        skill_code=code,
        skill_type="communicative_function",
        modality="speaking",
        operation="interact",
        target_ref=code,
        scope=("it-IT",),
        evidence_protocol_ids=(),
        load_profile=(("complexity", 1),),
        status=ContentRevisionStatus.PUBLISHED,
        provenance_id=PROVENANCE_ID,
    )


def edge(
    number: int,
    source: SkillRevision,
    target: SkillRevision,
    edge_type: PrerequisiteEdgeType = PrerequisiteEdgeType.REQUIRED,
) -> SkillPrerequisiteEdge:
    return SkillPrerequisiteEdge(
        edge_id=UUID(f"019fe900-4000-7000-8003-{number:012x}"),
        from_skill_revision_id=source.skill_revision_id,
        to_skill_revision_id=target.skill_revision_id,
        edge_type=edge_type,
        provenance_id=PROVENANCE_ID,
    )


def published_pack() -> LanguagePackRevision:
    return LanguagePackRevision(
        pack_revision_id=PACK_REVISION_ID,
        pack_id=PACK_ID,
        revision_no=1,
        target_variety_id=TARGET_VARIETY_ID,
        support_variety_ids=(SUPPORT_VARIETY_ID,),
        status=ContentRevisionStatus.PUBLISHED,
        engine_min_version="2.0.0",
        engine_max_version="2.0.x",
        capabilities=("catalogue", "lexicon", "skill_graph"),
        checksum_manifest=(
            ("catalogue.json", "a" * 64),
            ("manifest.json", "b" * 64),
        ),
        license_refs=("CC-BY-4.0",),
        provenance_id=PROVENANCE_ID,
        published_at=PUBLISHED_AT,
    )


def test_revision_schema_requires_uuid7_support_language_and_publish_timestamp() -> None:
    values = published_pack()

    with pytest.raises(DomainError) as invalid_id:
        LanguagePackRevision(
            **{
                **values.as_dict(),
                "pack_revision_id": UUID("00000000-0000-4000-8000-000000000001"),
            }
        )
    assert invalid_id.value.code is ErrorCode.VALIDATION_FAILED

    with pytest.raises(DomainError) as missing_support:
        LanguagePackRevision(**{**values.as_dict(), "support_variety_ids": ()})
    assert missing_support.value.code is ErrorCode.VALIDATION_FAILED

    with pytest.raises(DomainError) as missing_timestamp:
        LanguagePackRevision(**{**values.as_dict(), "published_at": None})
    assert missing_timestamp.value.code is ErrorCode.VALIDATION_FAILED


def test_stable_codes_use_the_same_ascii_contract_as_postgresql() -> None:
    values = skill_revision(1, "IT-PRAG-001")
    with pytest.raises(DomainError) as invalid:
        replace(values, skill_code="IT-PRAG-é01")
    assert invalid.value.code is ErrorCode.VALIDATION_FAILED


def test_published_revision_is_immutable_and_retirement_creates_a_successor() -> None:
    published = published_pack()

    with pytest.raises(DomainError) as immutable:
        published.change_status(ContentRevisionStatus.RETIRED)
    assert immutable.value.code is ErrorCode.INVALID_TRANSITION

    retired = published.retire(UUID("019fe900-4000-7000-8000-000000000006"))

    assert published.status is ContentRevisionStatus.PUBLISHED
    assert published.revision_no == 1
    assert retired.status is ContentRevisionStatus.RETIRED
    assert retired.revision_no == 2
    assert retired.pack_revision_id != published.pack_revision_id
    assert retired.published_at is None


def test_only_required_prerequisites_must_be_acyclic() -> None:
    first = skill_revision(1, "IT-PRAG-001")
    second = skill_revision(2, "IT-ID-001")
    third = skill_revision(3, "IT-POLITE-002")

    with pytest.raises(DomainError) as cycle:
        SkillGraph(
            (first, second, third),
            (
                edge(1, first, second),
                edge(2, second, third),
                edge(3, third, first),
            ),
        )
    assert cycle.value.code is ErrorCode.PREREQUISITE_CYCLE

    graph = SkillGraph(
        (first, second, third),
        (
            edge(1, first, second),
            edge(2, second, third),
            edge(3, third, first, PrerequisiteEdgeType.RECOMMENDED),
        ),
    )
    assert len(graph.edges) == 3


def test_prerequisite_traversal_is_bounded_deterministic_and_reports_truncation() -> None:
    first = skill_revision(1, "IT-PRAG-001")
    second = skill_revision(2, "IT-ID-001")
    third = skill_revision(3, "IT-GRAM-002")
    fourth = skill_revision(4, "IT-GRAM-004")
    graph = SkillGraph(
        (fourth, second, first, third),
        (
            edge(3, third, fourth),
            edge(2, second, fourth),
            edge(1, first, third),
        ),
    )

    complete = graph.prerequisites_for(fourth.skill_revision_id, max_depth=2, max_nodes=3)
    repeated = graph.prerequisites_for(fourth.skill_revision_id, max_depth=2, max_nodes=3)
    bounded = graph.prerequisites_for(fourth.skill_revision_id, max_depth=2, max_nodes=2)

    assert complete == repeated
    assert complete.skill_revision_ids == (
        second.skill_revision_id,
        third.skill_revision_id,
        first.skill_revision_id,
    )
    assert complete.truncated is False
    assert bounded.skill_revision_ids == (second.skill_revision_id, third.skill_revision_id)
    assert bounded.truncated is True


def test_published_foundation_aggregate_requires_the_complete_coherent_it_pilot() -> None:
    required_names = (
        "FoundationCheckerKind",
        "PublishedFoundationItem",
        "PublishedFoundationBlock",
        "PublishedFoundationGate",
        "PublishedFoundationDefinition",
        "PublishedFoundationCatalogue",
    )
    missing = [name for name in required_names if not hasattr(catalogue_domain, name)]
    assert not missing, f"W04F foundation contracts are missing: {missing}"

    checker_kind = catalogue_domain.FoundationCheckerKind
    item_type = catalogue_domain.PublishedFoundationItem
    block_type = catalogue_domain.PublishedFoundationBlock
    gate_type = catalogue_domain.PublishedFoundationGate
    definition_type = catalogue_domain.PublishedFoundationDefinition
    aggregate_type = catalogue_domain.PublishedFoundationCatalogue

    def identifier(namespace: int, number: int) -> UUID:
        return UUID(f"019fe900-4200-7000-{namespace:04x}-{number:012x}")

    def item(block_number: int, item_number: int) -> object:
        return item_type(
            item_revision_id=identifier(0x8003 + block_number, item_number),
            block_revision_id=identifier(0x8010 + block_number, 1),
            pack_revision_id=PACK_REVISION_ID,
            item_code=f"ITF-F{block_number}-{item_number:02d}",
            ordinal=item_number,
            target_refs=(f"IT-TARGET-F{block_number}-{item_number:02d}",),
            response_kind="raw",
            checker_kind=(
                checker_kind.NOT_EVALUABLE
                if block_number == 2 and item_number == 2
                else checker_kind.EXACT_CHOICE
            ),
            checker_values=(() if block_number == 2 and item_number == 2 else ("accepted",)),
            modalities=("reading",),
            status=ContentRevisionStatus.PUBLISHED,
            checksum="a" * 64,
        )

    blocks = tuple(
        block_type(
            block_revision_id=identifier(0x8010 + block_number, 1),
            foundation_revision_id=identifier(0x8001, 1),
            pack_revision_id=PACK_REVISION_ID,
            block_code=f"F{block_number}",
            ordinal=block_number,
            component_type=("script_perception" if block_number == 1 else "interaction"),
            prerequisite_refs=(),
            items=(item(block_number, 1), item(block_number, 2)),
            modalities=("reading",),
            backend_criteria=("deterministic",),
            waiver_policy_ref="DIAGNOSTIC_WAIVER_V0",
            status=ContentRevisionStatus.PUBLISHED,
            checksum="b" * 64,
        )
        for block_number in range(1, 6)
    )
    gate = gate_type(
        gate_revision_id=identifier(0x8002, 1),
        foundation_revision_id=identifier(0x8001, 1),
        pack_revision_id=PACK_REVISION_ID,
        gate_code="FOUNDATIONS_IT_V0",
        blocking_target_refs=tuple(
            item.target_refs[0]
            for block in blocks
            for item in block.items
            if item.checker_kind is not checker_kind.NOT_EVALUABLE
        ),
        blocking_facet_refs=("grapheme_sound", "controlled_reading", "survival_exchange"),
        coverage_threshold=0.8,
        confidence_threshold=0.6,
        minimum_distinct_sessions=2,
        delayed_control_hours=24,
        grapheme_sound_minimum=8,
        grapheme_sound_total=10,
        targeted_reading_minimum=8,
        targeted_reading_total=10,
        survival_exchange_minimum=4,
        survival_exchange_total=5,
        oral_policy="not_evaluable_non_blocking",
        status=ContentRevisionStatus.PUBLISHED,
        checksum="c" * 64,
    )
    definition = definition_type(
        foundation_id=identifier(0x8000, 1),
        foundation_revision_id=identifier(0x8001, 1),
        pack_revision_id=PACK_REVISION_ID,
        foundation_code="FOUNDATIONS_IT_V0",
        revision_no=1,
        blocks=blocks,
        gate=gate,
        status=ContentRevisionStatus.PUBLISHED,
        checksum="d" * 64,
    )
    aggregate = aggregate_type(definition=definition)

    assert tuple(block.block_code for block in aggregate.definition.blocks) == (
        "F1",
        "F2",
        "F3",
        "F4",
        "F5",
    )
    assert aggregate.definition.gate.minimum_distinct_sessions == 2
    assert aggregate.definition.gate.delayed_control_hours == 24

    definition_values = {
        "foundation_id": definition.foundation_id,
        "foundation_revision_id": definition.foundation_revision_id,
        "pack_revision_id": definition.pack_revision_id,
        "foundation_code": definition.foundation_code,
        "revision_no": definition.revision_no,
        "blocks": blocks,
        "gate": gate,
        "status": definition.status,
        "checksum": definition.checksum,
    }

    with pytest.raises(DomainError) as incomplete:
        definition_type(**{**definition_values, "blocks": blocks[:-1]})
    assert incomplete.value.code is ErrorCode.VALIDATION_FAILED

    with pytest.raises(DomainError) as missing_checker:
        item_type(
            **{
                **blocks[0].items[0].as_dict(),
                "checker_values": (),
            }
        )
    assert missing_checker.value.code is ErrorCode.VALIDATION_FAILED

    with pytest.raises(DomainError) as absent_target:
        definition_type(
            **{
                **definition_values,
                "gate": gate_type(
                    **{
                        **gate.as_dict(),
                        "blocking_target_refs": (*gate.blocking_target_refs, "IT-MISSING-999"),
                    }
                ),
            }
        )
    assert absent_target.value.code is ErrorCode.REFERENCE_NOT_FOUND

    with pytest.raises(DomainError) as duplicate_ordinal:
        duplicate = blocks[1]
        definition_type(
            **{
                **definition_values,
                "blocks": (
                    blocks[0],
                    block_type(
                        block_revision_id=duplicate.block_revision_id,
                        foundation_revision_id=duplicate.foundation_revision_id,
                        pack_revision_id=duplicate.pack_revision_id,
                        block_code=duplicate.block_code,
                        ordinal=1,
                        component_type=duplicate.component_type,
                        prerequisite_refs=duplicate.prerequisite_refs,
                        items=duplicate.items,
                        modalities=duplicate.modalities,
                        backend_criteria=duplicate.backend_criteria,
                        waiver_policy_ref=duplicate.waiver_policy_ref,
                        status=duplicate.status,
                        checksum=duplicate.checksum,
                    ),
                    *blocks[2:],
                ),
            }
        )
    assert duplicate_ordinal.value.code is ErrorCode.VALIDATION_FAILED

    with pytest.raises(DomainError) as invalid_threshold:
        gate_type(**{**gate.as_dict(), "grapheme_sound_minimum": 11})
    assert invalid_threshold.value.code is ErrorCode.VALIDATION_FAILED
