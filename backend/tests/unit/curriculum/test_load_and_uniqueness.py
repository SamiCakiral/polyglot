from __future__ import annotations

from dataclasses import replace

import pytest

from polyglot.modules.curriculum import ArcType, CurriculumError
from polyglot.modules.curriculum.validation import validate_curriculum
from tests.unit.curriculum.test_module_contract import day
from tests.unit.curriculum.test_validation import base_input


def test_day_rejects_duplicate_targets_content_and_modality_objectives() -> None:
    base = day(1)
    for changes in (
        {"primary_target_refs": ("skill:1", "skill:1")},
        {"content_revision_ids": (base.module_day_id, base.module_day_id)},
        {
            "modality_objectives": (
                ("written_production", "produce-1"),
                ("written_production", "produce-1"),
            )
        },
    ):
        with pytest.raises(CurriculumError, match="duplicate_reference"):
            replace(base, **changes)


def test_validation_requires_exactly_one_novelty_entry_per_day() -> None:
    data = base_input()
    missing = validate_curriculum(replace(data, day_novelty_points=()))
    duplicate = validate_curriculum(
        replace(data, day_novelty_points=((1, 3.5), (1, 3.5), (2, 3.5), (3, 0.0)))
    )

    assert "module_load_budget_exceeded" in {
        item.message_code for item in missing.findings
    }
    assert "module_load_budget_exceeded" in {
        item.message_code for item in duplicate.findings
    }


def test_transfer_still_rejects_nonzero_novelty_after_full_coverage() -> None:
    data = base_input()
    report = validate_curriculum(
        replace(data, day_novelty_points=((1, 3.5), (2, 3.5), (3, 0.5)))
    )
    assert data.module.days[-1].arc_type is ArcType.TRANSFER
    assert "module_novelty_budget_exceeded" in {
        item.message_code for item in report.findings
    }
