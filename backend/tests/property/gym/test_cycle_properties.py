from datetime import UTC, datetime
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.exercises.core.domain import CorrectionVerdict, HintLevel

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


@given(st.sampled_from(tuple(HintLevel)))
def test_g0_never_creates_credit_for_any_hint_level(hint_level: HintLevel) -> None:
    from polyglot.modules.exercises.gym.cycle import G1Requirement, G1RequirementKind, GymCycle

    cycle = GymCycle.start(
        cycle_id=UUID("019fe010-2000-7000-8000-000000000001"),
        plan_revision_id=UUID("019fe010-2000-7000-8000-000000000002"),
        grammar_target_revision_id=UUID("019fe010-2000-7000-8000-000000000003"),
        started_at=NOW,
        g1_requirements=(
            G1Requirement(
                "g1:guided",
                G1RequirementKind.GUIDED_PRODUCTION,
                UUID("019fe010-2000-7000-8000-000000000004"),
            ),
            G1Requirement(
                "g1:transform",
                G1RequirementKind.TRANSFORMATION,
                UUID("019fe010-2000-7000-8000-000000000005"),
            ),
        ),
    )
    result = cycle.record(
        verdict=CorrectionVerdict.CORRECT,
        hint_level=hint_level,
        context_id="explanation",
        scene_id="lesson",
        structure_cued=True,
        recorded_at=NOW,
        idempotency_key="g0",
    )

    assert result.records[0].credit == 0.0
    assert result.records[0].is_evidence is False


@given(st.sampled_from((CorrectionVerdict.AMBIGUOUS, CorrectionVerdict.NOT_EVALUABLE)))
def test_non_decisive_verdicts_never_advance_or_create_evidence(
    verdict: CorrectionVerdict,
) -> None:
    from polyglot.modules.exercises.gym.cycle import G1Requirement, G1RequirementKind, GymCycle

    cycle = GymCycle.start(
        cycle_id=UUID("019fe010-2000-7000-8000-000000000011"),
        plan_revision_id=UUID("019fe010-2000-7000-8000-000000000012"),
        grammar_target_revision_id=UUID("019fe010-2000-7000-8000-000000000013"),
        started_at=NOW,
        g1_requirements=(
            G1Requirement(
                "g1:guided",
                G1RequirementKind.GUIDED_PRODUCTION,
                UUID("019fe010-2000-7000-8000-000000000014"),
            ),
            G1Requirement(
                "g1:transform",
                G1RequirementKind.TRANSFORMATION,
                UUID("019fe010-2000-7000-8000-000000000015"),
            ),
        ),
    )
    result = cycle.record(
        verdict=verdict,
        hint_level=HintLevel.H0,
        context_id="explanation",
        scene_id="lesson",
        structure_cued=True,
        recorded_at=NOW,
        idempotency_key="non-decisive",
    )

    assert result.stage == cycle.stage
    assert result.records[0].credit == 0.0
    assert result.records[0].is_evidence is False
