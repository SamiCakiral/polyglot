from __future__ import annotations

from dataclasses import replace

from polyglot.modules.curriculum.validation import validate_curriculum
from tests.unit.curriculum.test_validation import base_input


def test_validation_rejects_days_without_a_complete_typed_graph() -> None:
    report = validate_curriculum(base_input())

    assert "module_day_graph_incomplete" in {
        finding.message_code for finding in report.findings
    }


def test_validation_rejects_parallel_semantics_without_bound_targets() -> None:
    data = base_input()
    report = validate_curriculum(
        replace(
            data,
            grammar_explanations=((1, "unbound-family"),),
            grammar_practices=((1, "unbound-family", "GYM-01"),),
        )
    )

    assert "module_validation_input_unbound" in {
        finding.message_code for finding in report.findings
    }
