from __future__ import annotations

from dataclasses import replace

from polyglot.modules.curriculum.validation import (
    HumanGateStatus,
    HumanReviewGate,
    validate_curriculum,
)
from tests.unit.curriculum.test_validation import base_input


def codes(gates: tuple[HumanReviewGate, ...]) -> set[str]:
    report = validate_curriculum(replace(base_input(), human_gates=gates))
    return {item.message_code for item in report.findings}


def test_human_gate_set_is_required_closed_and_unique() -> None:
    assert "module_human_gate_missing" in codes(())
    assert "module_human_gate_missing" in codes(
        (HumanReviewGate("P-LING", HumanGateStatus.PENDING_HUMAN),)
    )
    assert {
        "module_human_gate_missing",
        "module_human_gate_unknown",
    }.issubset(
        codes((HumanReviewGate("P-FAKE", HumanGateStatus.PENDING_HUMAN),))
    )
    assert "module_human_gate_duplicate" in codes(
        (
            HumanReviewGate("P-LING", HumanGateStatus.PENDING_HUMAN),
            HumanReviewGate("P-LING", HumanGateStatus.PENDING_HUMAN),
            HumanReviewGate("P-PED", HumanGateStatus.PENDING_HUMAN),
        )
    )


def test_approved_label_without_bound_human_evidence_is_not_approval() -> None:
    forged = (
        HumanReviewGate("P-LING", HumanGateStatus.APPROVED),
        HumanReviewGate("P-PED", HumanGateStatus.APPROVED),
    )
    assert "module_human_approval_evidence_invalid" in codes(forged)
