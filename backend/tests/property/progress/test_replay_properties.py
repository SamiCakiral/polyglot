from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.progress.domain import (
    DelayBand,
    EvidenceSource,
    LearningEvidence,
    Modality,
    project_mastery,
    projection_fingerprint,
)

NOW = datetime(2026, 8, 10, 12, tzinfo=UTC)


def _uuid(index: int) -> UUID:
    return UUID(f"00000000-0000-7000-8000-{index:012d}")


def _fact(index: int, value: float) -> LearningEvidence:
    return LearningEvidence.from_observation_value(
        evidence_id=_uuid(1000 + index),
        observation_id=_uuid(2000 + index),
        profile_id=_uuid(1),
        target_type="skill",
        target_id="it.question",
        facet_key="recognition",
        modality=Modality.READING,
        operation="recognize",
        observation_value=value,
        source=EvidenceSource.PLANNED_SPRINT,
        independence_weight=1,
        opportunity_id=_uuid(3000 + index),
        pedagogical_session_id=f"session-{index % 3}",
        context_family_id=f"context-{index % 4}",
        delay_band=tuple(DelayBand)[index % 3],
        transfer=index % 5 == 0,
        policy_revision_id="MASTERY_V0",
        created_at=NOW - timedelta(days=index),
    )


@given(st.permutations(tuple(range(1, 9))))
def test_arrival_order_does_not_change_projection(order: list[int]) -> None:
    facts = tuple(_fact(index, 1.0 if index % 2 else -0.5) for index in order)
    canonical = tuple(_fact(index, 1.0 if index % 2 else -0.5) for index in range(1, 9))

    assert projection_fingerprint(project_mastery(facts, as_of=NOW)) == projection_fingerprint(
        project_mastery(canonical, as_of=NOW)
    )


@given(st.lists(st.integers(min_value=1, max_value=8), min_size=1, max_size=30))
def test_duplicate_delivery_is_idempotent(indices: list[int]) -> None:
    duplicated = tuple(_fact(index, 0.75) for index in indices)
    unique = tuple(_fact(index, 0.75) for index in sorted(set(indices)))

    assert projection_fingerprint(project_mastery(duplicated, as_of=NOW)) == projection_fingerprint(
        project_mastery(unique, as_of=NOW)
    )
