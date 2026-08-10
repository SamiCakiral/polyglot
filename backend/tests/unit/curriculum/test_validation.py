from __future__ import annotations

from dataclasses import replace

from polyglot.modules.curriculum import ArcType
from polyglot.modules.curriculum.ports import ReferenceStatus, ResolvedReference
from polyglot.modules.curriculum.validation import (
    HumanGateStatus,
    MorphologyOracle,
    PronunciationOracle,
    ValidationInput,
    validate_curriculum,
)
from tests.unit.curriculum.test_module_contract import day, revision, uid


def resolved(
    reference: str, status: ReferenceStatus = ReferenceStatus.PUBLISHED
) -> ResolvedReference:
    return ResolvedReference(
        reference,
        reference.partition(":")[0],
        status,
        str(uid(3)),
        str(uid(4)),
        f"sha256:{'a' * 64}",
        "prov:it-pilot",
        ("rights:cc-by-4.0",),
    )


def base_input() -> ValidationInput:
    module = revision(days=(day(1), day(2, arc=ArcType.GUIDED_USE), day(3, arc=ArcType.TRANSFER)))
    refs = tuple(resolved(value) for value in module.all_reference_keys())
    return ValidationInput(
        module=module,
        resolved_references=refs,
        grammar_explanations=((1, "identity"), (2, "polite-request")),
        grammar_practices=((1, "identity", "GYM-01"), (2, "polite-request", "GYM-08")),
        morphology_oracles=(
            MorphologyOracle("form:sono", (("person", "1"), ("number", "singular")), "sono", True),
        ),
        pronunciation_oracles=(
            PronunciationOracle(
                "pron:e-accent", "È qui", f"sha256:{'b' * 64}", f"sha256:{'b' * 64}", "perception"
            ),
        ),
        profile_novelty_limits=(("P-ABS", 6.0), ("P-FAUX", 8.0), ("P-INT", 10.0)),
        day_novelty_points=((1, 3.5), (2, 3.5), (3, 0.0)),
        human_gates=(
            ("P-LING", HumanGateStatus.PENDING_HUMAN),
            ("P-PED", HumanGateStatus.PENDING_HUMAN),
        ),
    )


def test_validation_reports_all_reference_and_human_gate_findings_deterministically() -> None:
    data = base_input()
    references = list(data.resolved_references)
    references[0] = replace(references[0], status=ReferenceStatus.RETIRED)
    references[1] = replace(references[1], status=ReferenceStatus.MISSING)
    references[2] = replace(references[2], rights_refs=())

    report = validate_curriculum(replace(data, resolved_references=tuple(reversed(references))))

    assert report.blocking
    assert {finding.message_code for finding in report.findings} >= {
        "module_reference_retired_for_new_use",
        "module_target_unresolved",
        "module_rights_missing",
        "module_human_review_required",
    }
    assert report.findings == tuple(sorted(report.findings, key=lambda item: item.sort_key))


def test_validation_rejects_missing_morphology_oracle_and_false_oral_credit() -> None:
    data = base_input()
    broken_morphology = replace(data.morphology_oracles[0], oracle_available=False)
    broken_pronunciation = replace(data.pronunciation_oracles[0], evaluability="self_assessment")

    report = validate_curriculum(
        replace(
            data,
            morphology_oracles=(broken_morphology,),
            pronunciation_oracles=(broken_pronunciation,),
        )
    )

    assert {finding.message_code for finding in report.findings} >= {
        "module_morphology_oracle_missing",
        "module_pronunciation_not_evaluable",
    }
    assert report.credit_eligible_pronunciation_refs == ()


def test_validation_requires_explanation_before_gym_and_zero_transfer_novelty() -> None:
    data = base_input()
    report = validate_curriculum(
        replace(
            data,
            grammar_explanations=((1, "identity"),),
            day_novelty_points=((1, 3.5), (2, 3.5), (3, 0.5)),
        )
    )
    assert {finding.message_code for finding in report.findings} >= {
        "module_new_structure_without_explanation",
        "module_novelty_budget_exceeded",
    }
