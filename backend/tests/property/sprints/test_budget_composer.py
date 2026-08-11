from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from polyglot.modules.sprints.composer import DailySprintComposer
from polyglot.modules.sprints.domain import BlockFamily, CandidateBlock, PlanKind, PlanningSnapshot


def uid(value: int) -> UUID:
    return UUID(f"019feb32-0000-7000-8000-{value:012x}")


def candidates() -> tuple[CandidateBlock, ...]:
    return (
        CandidateBlock(
            candidate_id=uid(1),
            family=BlockFamily.RECALL_WARMUP,
            roles=frozenset({"activation", "j1_due"}),
            p50_seconds=150,
            p80_seconds=180,
            debt_urgency=1,
            memory_due=1,
            delayed_recode_id=uid(90),
        ),
        CandidateBlock(
            candidate_id=uid(2),
            family=BlockFamily.TRANSFORMATION_GYM,
            roles=frozenset({"primary_objective", "unsupported_production"}),
            p50_seconds=270,
            p80_seconds=300,
            module_criticality=1,
            modalities=frozenset({"writing"}),
        ),
        CandidateBlock(
            candidate_id=uid(3),
            family=BlockFamily.REFLECTION_CLOSE,
            roles=frozenset({"reflection"}),
            p50_seconds=60,
            p80_seconds=90,
        ),
        CandidateBlock(
            candidate_id=uid(4),
            family=BlockFamily.LEXICAL_ACQUISITION,
            roles=frozenset({"lexical_preexposure"}),
            p50_seconds=180,
            p80_seconds=240,
            novelty_points=2,
            teaches_refs=frozenset({"lex:new"}),
            information_gain=0.9,
        ),
        CandidateBlock(
            candidate_id=uid(5),
            family=BlockFamily.VERSION_INPUT,
            roles=frozenset({"contextual_encounter", "comprehension"}),
            p50_seconds=240,
            p80_seconds=300,
            modalities=frozenset({"reading"}),
            requires_refs=frozenset({"lex:new"}),
            modality_balance=0.7,
        ),
        CandidateBlock(
            candidate_id=uid(6),
            family=BlockFamily.GRAMMAR_TOOLBOX,
            roles=frozenset({"grammar_explanation"}),
            p50_seconds=180,
            p80_seconds=240,
            novelty_points=3,
            grammar_family="IT-POLITE-REQUEST",
            teaches_refs=frozenset({"grammar:request"}),
        ),
        CandidateBlock(
            candidate_id=uid(7),
            family=BlockFamily.SHADOWING,
            roles=frozenset({"second_modality"}),
            p50_seconds=240,
            p80_seconds=300,
            modalities=frozenset({"speaking"}),
            modality_balance=0.8,
        ),
        CandidateBlock(
            candidate_id=uid(8),
            family=BlockFamily.GUIDED_OUTPUT,
            roles=frozenset({"extension"}),
            p50_seconds=300,
            p80_seconds=360,
            requires_refs=frozenset({"grammar:request"}),
            modalities=frozenset({"writing"}),
            information_gain=0.8,
        ),
    )


@given(st.integers(min_value=2, max_value=12).map(lambda value: value * 5))
def test_every_supported_budget_stays_within_hard_limits(budget: int) -> None:
    snapshot = PlanningSnapshot(
        snapshot_id=uid(100 + budget),
        profile_id=uid(200),
        plan_kind=PlanKind.DAILY,
        budget_minutes=budget,
        pedagogical_day=date(2026, 8, 10),
        timezone="Europe/Paris",
        cutoff_at=datetime(2026, 8, 10, 8, tzinfo=UTC),
        seed="budget-proof",
        policy_revision="SPRINT_PRIORITY_V0",
        planner_revision="COMPOSER_V0",
        profile_band="P-ABS",
        mastered_refs=frozenset(),
        enrollment_id=uid(201),
        module_revision_id=uid(202),
        module_day_id=uid(203),
        due_delayed_recode_ids=(uid(90),),
        candidates=candidates(),
    )

    plan = DailySprintComposer().compose(uid(300 + budget), snapshot)

    assert plan.total_p50_seconds <= budget * 60 * 0.9
    assert plan.total_p80_seconds <= budget * 60
    assert len(plan.blocks) <= snapshot.max_blocks
    assert plan.novelty_points <= snapshot.novelty_limit
    assert {"activation", "primary_objective", "unsupported_production", "reflection"}.issubset(
        plan.covered_roles
    )
    assert uid(90) in {block.delayed_recode_id for block in plan.blocks}


def test_prerequisite_teaching_is_ordered_before_dependent_block() -> None:
    snapshot = PlanningSnapshot(
        snapshot_id=uid(500),
        profile_id=uid(501),
        plan_kind=PlanKind.DAILY,
        budget_minutes=30,
        pedagogical_day=date(2026, 8, 10),
        timezone="Europe/Paris",
        cutoff_at=datetime(2026, 8, 10, 8, tzinfo=UTC),
        seed="order-proof",
        policy_revision="SPRINT_PRIORITY_V0",
        planner_revision="COMPOSER_V0",
        profile_band="P-ABS",
        mastered_refs=frozenset(),
        enrollment_id=uid(503),
        module_revision_id=uid(504),
        module_day_id=uid(505),
        due_delayed_recode_ids=(uid(90),),
        candidates=candidates(),
    )

    plan = DailySprintComposer().compose(uid(502), snapshot)
    positions = {block.candidate_id: block.ordinal for block in plan.blocks}
    if uid(8) in positions:
        assert positions[uid(6)] < positions[uid(8)]


def test_daily_budget_bands_preserve_the_pedagogical_chain() -> None:
    families = (
        (BlockFamily.RECALL_WARMUP, frozenset({"activation"})),
        (BlockFamily.VERSION_INPUT, frozenset({"activation"})),
        (BlockFamily.GRAMMAR_TOOLBOX, frozenset({"grammar_explanation"})),
        (
            BlockFamily.TRANSFORMATION_GYM,
            frozenset({"guided_practice"}),
        ),
        (BlockFamily.LISTENING, frozenset({"contextual_encounter"})),
        (BlockFamily.SHADOWING, frozenset({"second_modality"})),
        (
            BlockFamily.GUIDED_OUTPUT,
            frozenset({"production", "primary_objective", "unsupported_production", "reflection"}),
        ),
        (BlockFamily.FREE_WRITING, frozenset({"production"})),
    )
    candidates_by_band = tuple(
        CandidateBlock(
            candidate_id=uid(700 + index),
            family=family,
            roles=roles,
            p50_seconds=60,
            p80_seconds=90,
            module_criticality=0.8,
        )
        for index, (family, roles) in enumerate(families)
    )

    for budget in (10, 20, 30, 45, 60):
        snapshot = PlanningSnapshot(
            snapshot_id=uid(800 + budget),
            profile_id=uid(900),
            plan_kind=PlanKind.DAILY,
            budget_minutes=budget,
            pedagogical_day=date(2026, 8, 10),
            timezone="Europe/Paris",
            cutoff_at=datetime(2026, 8, 10, 8, tzinfo=UTC),
            seed=f"band-{budget}",
            policy_revision="SPRINT_PRIORITY_V1",
            planner_revision="COMPOSER_V1",
            profile_band="P-ABS",
            mastered_refs=frozenset(),
            enrollment_id=uid(901),
            module_revision_id=uid(902),
            module_day_id=uid(903),
            candidates=candidates_by_band,
        )
        selected = {
            block.family
            for block in DailySprintComposer().compose(uid(950 + budget), snapshot).blocks
        }

        assert BlockFamily.VERSION_INPUT in selected or BlockFamily.LISTENING in selected
        assert BlockFamily.GRAMMAR_TOOLBOX in selected
        assert BlockFamily.RECALL_WARMUP in selected
        assert selected & {
            BlockFamily.DELAYED_RECODE,
            BlockFamily.GUIDED_OUTPUT,
            BlockFamily.FREE_WRITING,
        }
        if budget >= 20:
            assert BlockFamily.TRANSFORMATION_GYM in selected
            assert selected & {BlockFamily.LISTENING, BlockFamily.SHADOWING}
        if budget >= 60:
            assert BlockFamily.SHADOWING in selected


def test_mid_length_session_uses_shadowing_when_no_listening_primitive_exists() -> None:
    candidates_without_listening = tuple(
        replace(
            item,
            roles=frozenset({"guided_practice"})
            if item.family is BlockFamily.TRANSFORMATION_GYM
            else frozenset(
                {"production", "primary_objective", "unsupported_production", "reflection"}
            )
            if item.family is BlockFamily.GUIDED_OUTPUT
            else item.roles,
        )
        for item in candidates()
        if item.family not in {BlockFamily.LISTENING, BlockFamily.REFLECTION_CLOSE}
    )
    snapshot = PlanningSnapshot(
        snapshot_id=uid(1001),
        profile_id=uid(1002),
        plan_kind=PlanKind.DAILY,
        budget_minutes=30,
        pedagogical_day=date(2026, 8, 10),
        timezone="Europe/Paris",
        cutoff_at=datetime(2026, 8, 10, 8, tzinfo=UTC),
        seed="shadowing-as-audio-input",
        policy_revision="SPRINT_PRIORITY_V1",
        planner_revision="COMPOSER_V1",
        profile_band="P-ABS",
        mastered_refs=frozenset({"lex:new"}),
        enrollment_id=uid(1003),
        module_revision_id=uid(1004),
        module_day_id=uid(1005),
        due_delayed_recode_ids=(uid(90),),
        candidates=candidates_without_listening,
    )

    selected = {block.family for block in DailySprintComposer().compose(uid(1006), snapshot).blocks}

    assert BlockFamily.SHADOWING in selected
