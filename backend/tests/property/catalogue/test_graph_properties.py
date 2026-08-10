from datetime import UTC, datetime
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.catalogue.core.domain import (
    ContentRevisionStatus,
    LanguagePackRevision,
    PrerequisiteEdgeType,
    SkillPrerequisiteEdge,
    SkillRevision,
)
from polyglot.modules.catalogue.core.graph import SkillGraph
from polyglot.platform.errors import DomainError, ErrorCode

PROVENANCE_ID = UUID("019fe900-4100-7000-8000-000000000001")


def identifier(namespace: int, number: int) -> UUID:
    return UUID(f"019fe900-4100-7000-{namespace:04x}-{number:012x}")


def skill(number: int) -> SkillRevision:
    return SkillRevision(
        skill_revision_id=identifier(0x8001, number),
        skill_id=identifier(0x8002, number),
        revision_no=1,
        skill_code=f"IT-SKILL-{number:03d}",
        skill_type="communicative_function",
        modality="speaking",
        operation="interact",
        target_ref=f"IT-TARGET-{number:03d}",
        scope=("it-IT",),
        evidence_protocol_ids=(),
        load_profile=(("complexity", 1),),
        status=ContentRevisionStatus.PUBLISHED,
        provenance_id=PROVENANCE_ID,
    )


def edge(number: int, source: int, target: int) -> SkillPrerequisiteEdge:
    return SkillPrerequisiteEdge(
        edge_id=identifier(0x8003, number),
        from_skill_revision_id=identifier(0x8001, source),
        to_skill_revision_id=identifier(0x8001, target),
        edge_type=PrerequisiteEdgeType.REQUIRED,
        provenance_id=PROVENANCE_ID,
    )


@given(
    node_count=st.integers(min_value=1, max_value=25),
    candidates=st.lists(
        st.tuples(st.integers(min_value=0, max_value=24), st.integers(min_value=0, max_value=24)),
        unique=True,
        max_size=80,
    ),
)
def test_forward_edges_always_form_an_acyclic_required_graph(
    node_count: int,
    candidates: list[tuple[int, int]],
) -> None:
    pairs = sorted({(left, right) for left, right in candidates if left < right < node_count})
    graph = SkillGraph(
        tuple(skill(number) for number in range(node_count)),
        tuple(edge(number + 1, left, right) for number, (left, right) in enumerate(pairs)),
    )

    assert len(graph.edges) == len(pairs)


@given(node_count=st.integers(min_value=2, max_value=25))
def test_closing_a_required_chain_is_always_rejected(node_count: int) -> None:
    edges = [edge(number + 1, number, number + 1) for number in range(node_count - 1)]
    edges.append(edge(node_count, node_count - 1, 0))

    with pytest.raises(DomainError) as cycle:
        SkillGraph(tuple(skill(number) for number in range(node_count)), tuple(edges))

    assert cycle.value.code is ErrorCode.PREREQUISITE_CYCLE


@given(
    node_count=st.integers(min_value=2, max_value=25),
    max_depth=st.integers(min_value=0, max_value=8),
    max_nodes=st.integers(min_value=1, max_value=12),
)
def test_traversal_never_exceeds_explicit_bounds(
    node_count: int,
    max_depth: int,
    max_nodes: int,
) -> None:
    graph = SkillGraph(
        tuple(skill(number) for number in range(node_count)),
        tuple(edge(number + 1, number, number + 1) for number in range(node_count - 1)),
    )

    result = graph.prerequisites_for(
        identifier(0x8001, node_count - 1),
        max_depth=max_depth,
        max_nodes=max_nodes,
    )

    assert len(result.skill_revision_ids) <= max_nodes
    assert result.depth_reached <= max_depth


@given(revision_no=st.integers(min_value=1, max_value=1_000_000))
def test_published_revision_content_cannot_be_rewritten(revision_no: int) -> None:
    revision = LanguagePackRevision(
        pack_revision_id=identifier(0x8010, revision_no),
        pack_id=identifier(0x8011, 1),
        revision_no=revision_no,
        target_variety_id=identifier(0x8012, 1),
        support_variety_ids=(identifier(0x8012, 2),),
        status=ContentRevisionStatus.PUBLISHED,
        engine_min_version="2.0.0",
        engine_max_version="2.0.x",
        capabilities=("catalogue",),
        checksum_manifest=(("catalogue.json", "a" * 64),),
        license_refs=("CC-BY-4.0",),
        provenance_id=PROVENANCE_ID,
        published_at=datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(DomainError) as immutable:
        revision.change_status(ContentRevisionStatus.RETIRED)

    assert immutable.value.code is ErrorCode.INVALID_TRANSITION
