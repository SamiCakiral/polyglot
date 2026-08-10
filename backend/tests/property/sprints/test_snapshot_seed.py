from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import UUID

from polyglot.modules.sprints.composer import DailySprintComposer
from polyglot.modules.sprints.domain import BlockFamily, CandidateBlock, PlanKind, PlanningSnapshot


def uid(value: int) -> UUID:
    return UUID(f"019feb33-0000-7000-8000-{value:012x}")


def test_same_snapshot_and_seed_produce_identical_plan_and_reasons() -> None:
    tied = tuple(
        CandidateBlock(
            candidate_id=uid(index),
            family=BlockFamily.GUIDED_OUTPUT,
            roles=frozenset({"extension"}),
            p50_seconds=120,
            p80_seconds=150,
            information_gain=0.5,
        )
        for index in range(10, 16)
    )
    core = (
        CandidateBlock(
            candidate_id=uid(1),
            family=BlockFamily.RECALL_WARMUP,
            roles=frozenset({"activation"}),
            p50_seconds=120,
            p80_seconds=150,
        ),
        CandidateBlock(
            candidate_id=uid(2),
            family=BlockFamily.TRANSFORMATION_GYM,
            roles=frozenset({"primary_objective", "unsupported_production"}),
            p50_seconds=240,
            p80_seconds=270,
        ),
        CandidateBlock(
            candidate_id=uid(3),
            family=BlockFamily.REFLECTION_CLOSE,
            roles=frozenset({"reflection"}),
            p50_seconds=60,
            p80_seconds=90,
        ),
    )
    snapshot = PlanningSnapshot(
        snapshot_id=uid(100),
        profile_id=uid(101),
        plan_kind=PlanKind.DAILY,
        budget_minutes=20,
        pedagogical_day=date(2026, 8, 10),
        timezone="Europe/Paris",
        cutoff_at=datetime(2026, 8, 10, 8, tzinfo=UTC),
        seed="stable-seed",
        policy_revision="SPRINT_PRIORITY_V0",
        planner_revision="COMPOSER_V0",
        profile_band="P-ABS",
        mastered_refs=frozenset(),
        enrollment_id=uid(102),
        module_revision_id=uid(103),
        module_day_id=uid(104),
        candidates=core + tied,
    )

    first = DailySprintComposer().compose(uid(200), snapshot)
    second = DailySprintComposer().compose(uid(200), replace(snapshot))

    assert first.fingerprint == second.fingerprint
    assert tuple((block.candidate_id, block.reason_codes) for block in first.blocks) == tuple(
        (block.candidate_id, block.reason_codes) for block in second.blocks
    )


def test_seed_only_breaks_true_ties_without_breaking_core() -> None:
    core = (
        CandidateBlock(
            candidate_id=uid(301),
            family=BlockFamily.RECALL_WARMUP,
            roles=frozenset({"activation"}),
            p50_seconds=120,
            p80_seconds=150,
        ),
        CandidateBlock(
            candidate_id=uid(302),
            family=BlockFamily.TRANSFORMATION_GYM,
            roles=frozenset({"primary_objective", "unsupported_production"}),
            p50_seconds=240,
            p80_seconds=270,
        ),
        CandidateBlock(
            candidate_id=uid(303),
            family=BlockFamily.REFLECTION_CLOSE,
            roles=frozenset({"reflection"}),
            p50_seconds=60,
            p80_seconds=90,
        ),
        CandidateBlock(
            candidate_id=uid(304),
            family=BlockFamily.LISTENING,
            roles=frozenset({"extension"}),
            p50_seconds=180,
            p80_seconds=210,
            modalities=frozenset({"listening"}),
        ),
        CandidateBlock(
            candidate_id=uid(305),
            family=BlockFamily.FREE_WRITING,
            roles=frozenset({"extension"}),
            p50_seconds=180,
            p80_seconds=210,
            modalities=frozenset({"writing"}),
        ),
    )
    base = PlanningSnapshot(
        snapshot_id=uid(306),
        profile_id=uid(307),
        plan_kind=PlanKind.DAILY,
        budget_minutes=15,
        pedagogical_day=date(2026, 8, 10),
        timezone="Europe/Paris",
        cutoff_at=datetime(2026, 8, 10, 8, tzinfo=UTC),
        seed="one",
        policy_revision="SPRINT_PRIORITY_V0",
        planner_revision="COMPOSER_V0",
        profile_band="P-ABS",
        mastered_refs=frozenset(),
        enrollment_id=uid(310),
        module_revision_id=uid(311),
        module_day_id=uid(312),
        candidates=core,
    )

    first = DailySprintComposer().compose(uid(308), base)
    second = DailySprintComposer().compose(uid(309), replace(base, seed="two"))

    for plan in (first, second):
        assert {"activation", "primary_objective", "unsupported_production", "reflection"}.issubset(
            plan.covered_roles
        )
