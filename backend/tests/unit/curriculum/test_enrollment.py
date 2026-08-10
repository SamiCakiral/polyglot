from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from polyglot.modules.curriculum import CurriculumError
from tests.unit.curriculum.test_module_contract import uid

NOW = datetime(2026, 8, 10, 18, 0, tzinfo=UTC)


def enrollment():  # type: ignore[no-untyped-def]
    from polyglot.modules.curriculum.enrollment import ModuleEnrollment

    return ModuleEnrollment.plan(
        enrollment_id=uid(300),
        profile_id=uid(301),
        module_revision_id=uid(302),
        nominal_days=3,
        max_days=5,
        waiver_refs=("waiver:pronunciation",),
    )


def test_enrollment_pins_revision_and_follows_planned_active_paused_states() -> None:
    from polyglot.modules.curriculum.enrollment import EnrollmentStatus

    planned = enrollment()
    active = planned.start(pedagogical_day=date(2026, 8, 10))
    paused = active.pause(paused_at=NOW)
    resumed = paused.resume(resumed_at=NOW)

    assert planned.status is EnrollmentStatus.PLANNED
    assert active.status is EnrollmentStatus.ACTIVE
    assert active.module_revision_id == planned.module_revision_id
    assert active.started_on_pedagogical_day == date(2026, 8, 10)
    assert paused.status is EnrollmentStatus.PAUSED
    assert resumed.status is EnrollmentStatus.ACTIVE
    assert resumed.current_day_ordinal == 1


def test_day_advances_only_after_required_core_and_never_past_nominal_days() -> None:
    active = enrollment().start(pedagogical_day=date(2026, 8, 10))

    with pytest.raises(CurriculumError, match="required_block_incomplete"):
        active.advance_day(required_core_complete=False)

    day_two = active.advance_day(required_core_complete=True)
    day_three = day_two.advance_day(required_core_complete=True)
    with pytest.raises(CurriculumError, match="module_day_ordinal_gap"):
        day_three.advance_day(required_core_complete=True)

    assert day_two.current_day_ordinal == 2
    assert day_three.current_day_ordinal == 3


def test_completion_requires_last_day_and_exit_criteria() -> None:
    from polyglot.modules.curriculum.enrollment import EnrollmentStatus

    active = enrollment().start(pedagogical_day=date(2026, 8, 10))
    with pytest.raises(CurriculumError, match="completion_criteria_missing"):
        active.complete(completed_at=NOW, exit_criteria_satisfied=False)

    last_day = active.advance_day(required_core_complete=True).advance_day(
        required_core_complete=True
    )
    completed = last_day.complete(completed_at=NOW, exit_criteria_satisfied=True)

    assert completed.status is EnrollmentStatus.COMPLETED
    assert completed.completed_at == NOW


def test_terminal_enrollment_cannot_resume_or_change_pinned_revision() -> None:
    cancelled = enrollment().cancel(cancelled_at=NOW)

    with pytest.raises(CurriculumError, match="module_enrollment_transition_invalid"):
        cancelled.resume(resumed_at=NOW)
    with pytest.raises(CurriculumError, match="module_enrollment_revision_pinned"):
        cancelled.migrate_revision(
            module_revision_id=uid(303),
            mapping_revision_id=None,
            consented=False,
        )


def test_revision_migration_requires_explicit_mapping_and_consent() -> None:
    planned = enrollment()
    with pytest.raises(CurriculumError, match="module_enrollment_migration_not_consented"):
        planned.migrate_revision(
            module_revision_id=uid(303),
            mapping_revision_id=uid(304),
            consented=False,
        )

    migrated = planned.migrate_revision(
        module_revision_id=uid(303),
        mapping_revision_id=uid(304),
        consented=True,
    )
    assert migrated.module_revision_id == uid(303)
    assert migrated.migration_map_revision_id == uid(304)
