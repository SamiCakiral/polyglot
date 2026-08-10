from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from polyglot.modules.exercises.core.domain import CorrectionVerdict, HintLevel
from polyglot.platform.errors import DomainError, ErrorCode

START = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)


def _cycle():
    from polyglot.modules.exercises.gym.cycle import GymCycle

    return GymCycle.start(
        cycle_id=UUID("019fe010-1000-7000-8000-000000000001"),
        plan_revision_id=UUID("019fe010-1000-7000-8000-000000000002"),
        grammar_target_revision_id=UUID("019fe010-1000-7000-8000-000000000003"),
        started_at=START,
    )


def _complete(cycle, *, now, key, verdict=CorrectionVerdict.CORRECT, **values):
    return cycle.record(
        verdict=verdict,
        hint_level=values.pop("hint_level", HintLevel.H0),
        context_id=values.pop("context_id", f"context:{cycle.stage.value}"),
        scene_id=values.pop("scene_id", f"scene:{cycle.stage.value}"),
        structure_cued=values.pop("structure_cued", False),
        recorded_at=now,
        idempotency_key=key,
        **values,
    )


def _through_g1():
    cycle = _complete(_cycle(), now=START, key="g0")
    return _complete(cycle, now=START + timedelta(minutes=5), key="g1")


def test_g0_is_activity_only_then_g1_creates_guided_evidence() -> None:
    from polyglot.modules.exercises.gym.cycle import GymStage

    initial = _cycle()
    after_g0 = _complete(initial, now=START, key="g0", hint_level=HintLevel.H4)
    after_g1 = _complete(after_g0, now=START + timedelta(minutes=5), key="g1")

    assert initial.stage is GymStage.G0
    assert after_g0.stage is GymStage.G1
    assert after_g0.records[-1].credit == 0.0
    assert after_g0.records[-1].is_evidence is False
    assert after_g1.stage is GymStage.G2
    assert after_g1.records[-1].credit == 0.65
    assert after_g1.records[-1].is_evidence is True


def test_g2_cannot_run_before_j_plus_one_and_requires_no_model() -> None:
    cycle = _through_g1()

    with pytest.raises(DomainError) as early:
        _complete(cycle, now=START + timedelta(hours=23), key="g2-early")
    with pytest.raises(DomainError) as helped:
        _complete(
            cycle,
            now=START + timedelta(days=1),
            key="g2-helped",
            hint_level=HintLevel.H2,
        )

    assert early.value.code is ErrorCode.GATE_NOT_READY
    assert helped.value.code is ErrorCode.HINT_NOT_AVAILABLE
    assert cycle.stage.value == "g2"


def test_immediate_j_plus_one_spaced_and_transfer_cycle_is_monotonic() -> None:
    from polyglot.modules.exercises.gym.cycle import GymStage

    cycle = _through_g1()
    g2 = _complete(
        cycle,
        now=START + timedelta(days=1),
        key="g2",
        context_id="station:near",
        scene_id="station:platform",
    )
    g3 = _complete(
        g2,
        now=START + timedelta(days=3),
        key="g3",
        context_id="hotel:varied",
        scene_id="hotel:desk",
    )
    g4 = _complete(
        g3,
        now=START + timedelta(days=7),
        key="g4",
        context_id="clinic:transfer",
        scene_id="clinic:reception",
        structure_cued=False,
    )

    assert g2.stage is GymStage.G3
    assert g3.stage is GymStage.G4
    assert g4.stage is GymStage.G4
    assert g4.completed is True
    assert tuple(record.stage for record in g4.records) == tuple(GymStage)
    assert g4.records[-1].credit == 1.0


def test_transfer_requires_a_new_scene_and_no_structure_cue() -> None:
    cycle = _through_g1()
    cycle = _complete(
        cycle,
        now=START + timedelta(days=1),
        key="g2",
        context_id="station:near",
        scene_id="station:platform",
    )
    cycle = _complete(
        cycle,
        now=START + timedelta(days=3),
        key="g3",
        context_id="hotel:varied",
        scene_id="hotel:desk",
    )

    with pytest.raises(DomainError) as same_scene:
        _complete(
            cycle,
            now=START + timedelta(days=7),
            key="g4-same",
            context_id="station:transfer",
            scene_id="station:platform",
        )
    with pytest.raises(DomainError) as cued:
        _complete(
            cycle,
            now=START + timedelta(days=7),
            key="g4-cued",
            context_id="clinic:transfer",
            scene_id="clinic:reception",
            structure_cued=True,
        )

    assert same_scene.value.code is ErrorCode.INSUFFICIENT_COVERAGE
    assert cued.value.code is ErrorCode.EVIDENCE_SCOPE_FORBIDDEN


def test_not_evaluable_and_h4_are_activity_without_credit_or_progression() -> None:
    cycle = _through_g1()
    unavailable = _complete(
        cycle,
        now=START + timedelta(days=1),
        key="g2-unavailable",
        verdict=CorrectionVerdict.NOT_EVALUABLE,
    )
    revealed = _complete(
        unavailable,
        now=START + timedelta(days=1),
        key="g2-revealed",
        hint_level=HintLevel.H4,
    )

    assert unavailable.stage == cycle.stage
    assert unavailable.records[-1].credit == 0.0
    assert unavailable.records[-1].is_evidence is False
    assert revealed.stage == cycle.stage
    assert revealed.records[-1].credit == 0.0
    assert revealed.records[-1].is_evidence is False


def test_replay_after_progression_is_idempotent_and_conflicts_are_explicit() -> None:
    cycle = _cycle()
    progressed = _complete(cycle, now=START, key="g0")
    replayed = _complete(
        progressed,
        now=START,
        key="g0",
        context_id="context:g0",
        scene_id="scene:g0",
    )

    assert replayed == progressed
    assert len(replayed.records) == 1
    with pytest.raises(DomainError) as conflict:
        _complete(
            progressed,
            now=START + timedelta(minutes=1),
            key="g0",
            context_id="changed",
        )
    assert conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
