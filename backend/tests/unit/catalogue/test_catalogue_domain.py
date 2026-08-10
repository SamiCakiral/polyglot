"""Catalogue domain contracts."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

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
