from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from polyglot.modules.exercises.core.domain import CorrectionVerdict, HintLevel
from polyglot.platform.errors import DomainError, ErrorCode

NOW = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)


def _requirement(index: int, kind: str):
    from polyglot.modules.exercises.gym.cycle import G1Requirement, G1RequirementKind

    return G1Requirement(
        requirement_id=f"g1:{kind}:{index}",
        kind=G1RequirementKind(kind),
        revision_id=UUID(f"019fe010-4000-7000-8000-{index:012x}"),
    )


def _cycle():
    from polyglot.modules.exercises.gym.cycle import GymCycle

    return GymCycle.start(
        cycle_id=UUID("019fe010-4000-7000-8000-000000000101"),
        plan_revision_id=UUID("019fe010-4000-7000-8000-000000000102"),
        grammar_target_revision_id=UUID("019fe010-4000-7000-8000-000000000103"),
        started_at=NOW,
        g1_requirements=(
            _requirement(1, "guided_production"),
            _requirement(2, "transformation"),
            _requirement(3, "transformation"),
            _requirement(4, "transformation"),
        ),
    )


def _record(cycle, key: str, requirement_id: str | None = None):
    return cycle.record(
        verdict=CorrectionVerdict.CORRECT,
        hint_level=HintLevel.H0,
        context_id=f"context:{requirement_id or cycle.stage.value}",
        scene_id="station:desk",
        structure_cued=cycle.stage.value in {"g0", "g1"},
        recorded_at=NOW + timedelta(minutes=1),
        idempotency_key=key,
        g1_requirement_id=requirement_id,
    )


def test_g1_reaches_g2_only_after_guided_production_and_every_planned_step() -> None:
    cycle = _record(_cycle(), "g0")
    assert cycle.stage.value == "g1"

    cycle = _record(cycle, "guided", "g1:guided_production:1")
    assert cycle.stage.value == "g1"
    cycle = _record(cycle, "step-1", "g1:transformation:2")
    assert cycle.stage.value == "g1"
    cycle = _record(cycle, "step-2", "g1:transformation:3")
    assert cycle.stage.value == "g1"
    cycle = _record(cycle, "step-3", "g1:transformation:4")

    assert cycle.stage.value == "g2"
    assert cycle.completed_g1_requirement_ids == (
        "g1:guided_production:1",
        "g1:transformation:2",
        "g1:transformation:3",
        "g1:transformation:4",
    )


def test_duplicate_step_under_another_key_is_not_counted_or_journaled_twice() -> None:
    cycle = _record(_record(_cycle(), "g0"), "guided", "g1:guided_production:1")
    completed = _record(cycle, "step-first", "g1:transformation:2")
    duplicate = _record(completed, "step-concurrent", "g1:transformation:2")

    assert duplicate.stage.value == "g1"
    assert duplicate.completed_g1_requirement_ids.count("g1:transformation:2") == 1
    assert len(duplicate.records) == len(completed.records)
    assert len(duplicate.receipts) == len(completed.receipts) + 1
    assert _record(duplicate, "step-concurrent", "g1:transformation:2") == duplicate


def test_unknown_g1_step_and_revisionless_requirement_are_rejected() -> None:
    cycle = _record(_cycle(), "g0")
    with pytest.raises(DomainError) as unknown:
        _record(cycle, "unknown", "g1:transformation:999")

    assert unknown.value.code is ErrorCode.REFERENCE_NOT_FOUND


def test_same_key_with_different_g1_step_remains_an_idempotency_conflict() -> None:
    cycle = _record(_cycle(), "g0")
    completed = _record(cycle, "same-key", "g1:guided_production:1")

    with pytest.raises(DomainError) as conflict:
        _record(completed, "same-key", "g1:transformation:2")

    assert conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT

