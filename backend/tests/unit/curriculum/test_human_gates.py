from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast

from polyglot.modules.curriculum.validation import (
    ApprovalDecision,
    HumanApprovalEvidence,
    HumanGateStatus,
    HumanReviewGate,
    ReviewerRole,
    validate_curriculum,
)
from tests.unit.curriculum.test_module_contract import uid
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


class SignatureVerifier:
    def verify(self, evidence: HumanApprovalEvidence) -> bool:
        return evidence.key_id == "trusted-review-key" and evidence.signature == b"verified"


def evidence(
    gate_code: str,
    role: ReviewerRole,
    *,
    signature: bytes = b"verified",
    signed_at: datetime | Any = datetime(2026, 8, 10, 12, tzinfo=UTC),
    decision: ApprovalDecision = ApprovalDecision.APPROVED,
    reviewer_id=uid(902),  # type: ignore[no-untyped-def]
) -> HumanApprovalEvidence:
    data = base_input()
    return HumanApprovalEvidence(
        review_id=uid(900),
        gate_code=gate_code,
        reviewer_id=reviewer_id,
        reviewer_role=role,
        author_id=uid(901),
        decision=decision,
        subject_checksum=data.module.payload_checksum,
        fixture_fingerprint=f"sha256:{'c' * 64}",
        signed_at=cast(datetime, signed_at),
        key_id="trusted-review-key",
        signature=signature,
    )


def approval_codes(
    linguistic: HumanApprovalEvidence,
    pedagogical: HumanApprovalEvidence,
    *,
    verifier: SignatureVerifier | None,
) -> set[str]:
    data = base_input()
    report = validate_curriculum(
        replace(
            data,
            module_author_id=uid(901),
            fixture_fingerprint=f"sha256:{'c' * 64}",
            approval_verifier=verifier,
            human_gates=(
                HumanReviewGate("P-LING", HumanGateStatus.APPROVED, linguistic),
                HumanReviewGate("P-PED", HumanGateStatus.APPROVED, pedagogical),
            ),
        )
    )
    return {item.message_code for item in report.findings}


def test_human_approval_requires_authentic_typed_distinct_reviewers() -> None:
    codes = approval_codes(
        evidence("P-LING", ReviewerRole.LINGUIST),
        evidence("P-PED", ReviewerRole.PEDAGOGUE, reviewer_id=uid(903)),
        verifier=SignatureVerifier(),
    )

    assert "module_human_approval_evidence_invalid" not in codes
    assert "module_human_review_required" not in codes


def test_forged_or_incoherent_human_approval_remains_pending() -> None:
    invalid_pairs = (
        (
            evidence("P-LING", ReviewerRole.LINGUIST, signature=b"forged"),
            evidence("P-PED", ReviewerRole.PEDAGOGUE, reviewer_id=uid(903)),
            SignatureVerifier(),
        ),
        (
            evidence(
                "P-LING",
                ReviewerRole.LINGUIST,
                signed_at=cast(Any, "not-a-timestamp"),
            ),
            evidence("P-PED", ReviewerRole.PEDAGOGUE, reviewer_id=uid(903)),
            SignatureVerifier(),
        ),
        (
            evidence("P-LING", ReviewerRole.PEDAGOGUE),
            evidence("P-PED", ReviewerRole.LINGUIST, reviewer_id=uid(903)),
            SignatureVerifier(),
        ),
        (
            evidence("P-LING", ReviewerRole.LINGUIST, reviewer_id=uid(901)),
            evidence("P-PED", ReviewerRole.PEDAGOGUE, reviewer_id=uid(903)),
            SignatureVerifier(),
        ),
        (
            evidence("P-LING", ReviewerRole.LINGUIST),
            evidence("P-PED", ReviewerRole.PEDAGOGUE, reviewer_id=uid(903)),
            None,
        ),
        (
            evidence(
                "P-LING",
                ReviewerRole.LINGUIST,
                decision=ApprovalDecision.REJECTED,
            ),
            evidence("P-PED", ReviewerRole.PEDAGOGUE, reviewer_id=uid(903)),
            SignatureVerifier(),
        ),
    )

    for linguistic, pedagogical, verifier in invalid_pairs:
        codes = approval_codes(linguistic, pedagogical, verifier=verifier)
        assert "module_human_approval_evidence_invalid" in codes
        assert "module_human_review_required" in codes
