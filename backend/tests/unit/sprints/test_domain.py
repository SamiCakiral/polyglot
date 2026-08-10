from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from polyglot.modules.sprints.domain import (
    BlockFamily,
    BlockStatus,
    CandidateBlock,
    DelayedRecodeSpec,
    PlanKind,
    PlanningSnapshot,
    PlanStatus,
    SprintDomainError,
    SprintRun,
    SprintRunStatus,
)


def uid(value: int) -> UUID:
    return UUID(f"019feb31-0000-7000-8000-{value:012x}")


NOW = datetime(2026, 8, 10, 8, tzinfo=UTC)


def test_delayed_recode_pins_only_evaluable_corrected_source() -> None:
    spec = DelayedRecodeSpec(
        delayed_recode_id=uid(1),
        profile_id=uid(2),
        source_attempt_id=uid(3),
        source_correction_revision_id=uid(4),
        source_exercise_instance_id=uid(5),
        target_stimulus="Vorrei un biglietto per Roma.",
        corrected_support_text="Je voudrais un billet pour Rome.",
        accepted_target_answers=("Vorrei un biglietto per Roma.",),
        target_language_tag="it-IT",
        support_language_tag="fr-FR",
        target_refs=("IT-PRAG-001",),
        correction_policy_revision_id=uid(6),
        content_revision_ids=(uid(7),),
        source_corrected_at=NOW,
        due_on_next_active_session=True,
        not_before=NOW + timedelta(hours=12),
        source_evaluable=True,
        source_contested=False,
        source_invalidated=False,
    )

    assert spec.is_due(NOW + timedelta(hours=13), next_active_session=True)
    assert not spec.is_due(NOW + timedelta(hours=11), next_active_session=True)

    after_24h = replace(spec, due_after_24h=True)
    assert not after_24h.is_due(NOW + timedelta(hours=23), next_active_session=True)
    assert after_24h.is_due(NOW + timedelta(hours=24), next_active_session=True)

    with pytest.raises(SprintDomainError, match="delayed_source_invalid"):
        DelayedRecodeSpec(
            delayed_recode_id=uid(11),
            profile_id=uid(2),
            source_attempt_id=uid(3),
            source_correction_revision_id=uid(4),
            source_exercise_instance_id=uid(5),
            target_stimulus="source",
            corrected_support_text="support",
            accepted_target_answers=("source",),
            target_language_tag="it-IT",
            support_language_tag="fr-FR",
            target_refs=("IT-PRAG-001",),
            correction_policy_revision_id=uid(6),
            content_revision_ids=(uid(7),),
            source_corrected_at=NOW,
            not_before=NOW + timedelta(hours=12),
            source_evaluable=False,
        )


def test_run_interruption_resumes_exact_block_and_free_run_never_consumes_day() -> None:
    run = SprintRun.start(
        run_id=uid(20),
        plan_id=uid(21),
        profile_id=uid(22),
        plan_kind=PlanKind.FREE,
        pedagogical_day=date(2026, 8, 10),
        block_ids=(uid(23), uid(24)),
        required_block_ids=(uid(23),),
        started_at=NOW,
        expires_at=NOW + timedelta(days=2),
    )
    run = run.start_block(uid(23), NOW + timedelta(minutes=1))
    run = run.interrupt(NOW + timedelta(minutes=3), "user_pause")

    assert run.status is SprintRunStatus.INTERRUPTED
    assert run.current_block_id == uid(23)
    assert run.block_status(uid(23)) is BlockStatus.IN_PROGRESS

    resumed = run.resume(NOW + timedelta(hours=1))
    completed_block = resumed.complete_block(uid(23), NOW + timedelta(hours=1, minutes=2))
    completed = completed_block.complete(NOW + timedelta(hours=1, minutes=3))

    assert completed.status is SprintRunStatus.COMPLETED
    assert completed.consumes_module_day is False


def test_run_cannot_complete_with_required_block_open() -> None:
    run = SprintRun.start(
        run_id=uid(30),
        plan_id=uid(31),
        profile_id=uid(32),
        plan_kind=PlanKind.DAILY,
        pedagogical_day=date(2026, 8, 10),
        block_ids=(uid(33),),
        required_block_ids=(uid(33),),
        started_at=NOW,
        expires_at=NOW + timedelta(days=2),
    )

    with pytest.raises(SprintDomainError, match="required_block_incomplete"):
        run.complete(NOW + timedelta(minutes=2))


def test_snapshot_rejects_unready_candidate() -> None:
    candidate = CandidateBlock(
        candidate_id=uid(40),
        family=BlockFamily.RECALL_WARMUP,
        roles=frozenset({"activation"}),
        p50_seconds=120,
        p80_seconds=150,
        corrector_ready=False,
    )
    with pytest.raises(SprintDomainError, match="content_unavailable"):
        PlanningSnapshot(
            snapshot_id=uid(41),
            profile_id=uid(42),
            plan_kind=PlanKind.FREE,
            budget_minutes=15,
            pedagogical_day=date(2026, 8, 10),
            timezone="Europe/Paris",
            cutoff_at=NOW,
            seed="seed",
            policy_revision="SPRINT_PRIORITY_V0",
            planner_revision="COMPOSER_V0",
            profile_band="P-ABS",
            mastered_refs=frozenset(),
            candidates=(candidate,),
        )


def test_snapshot_rejects_unsupported_budget() -> None:
    with pytest.raises(SprintDomainError, match="budget_infeasible"):
        PlanningSnapshot(
            snapshot_id=uid(43),
            profile_id=uid(44),
            plan_kind=PlanKind.FREE,
            budget_minutes=17,
            pedagogical_day=date(2026, 8, 10),
            timezone="Europe/Paris",
            cutoff_at=NOW,
            seed="seed",
            policy_revision="SPRINT_PRIORITY_V0",
            planner_revision="COMPOSER_V0",
            profile_band="P-ABS",
            mastered_refs=frozenset(),
            candidates=(),
        )


def test_plan_statuses_are_closed_contract() -> None:
    assert {item.value for item in PlanStatus} == {
        "draft",
        "preparing",
        "ready",
        "failed",
        "expired",
        "cancelled",
    }
