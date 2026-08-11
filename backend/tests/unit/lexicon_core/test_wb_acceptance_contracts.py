from uuid import UUID

from polyglot.modules.lexicon.core.projection import (
    AssessmentScope,
    Evidence,
    LexicalPlanItem,
    Recommendation,
    apply_debt_evidence,
    diagnostic_estimates,
    freeze_sprint_snapshot,
    gym_credit,
    project_reference,
    schedule_debt,
    validate_learning_targets,
)


def uid(number: int) -> UUID:
    return UUID(f"019fec00-0000-7000-8000-{number:012x}")


def evidence(**overrides) -> Evidence:
    values = {
        "sense_id": uid(1),
        "role": "target",
        "modality": "reading",
        "operation": "recognized",
        "help_state": "none",
        "result_state": "success",
        "context_ref": "encounter:1",
        "correction_ref": "correction:1",
        "correction_confidence": 0.9,
        "form_correct": True,
        "context_correct": True,
        "retention_correct": False,
        "contradiction": False,
    }
    values.update(overrides)
    return Evidence(**values)


def test_wb_01_projects_every_reference_sense_with_explanations() -> None:
    result = project_reference((uid(1), uid(2)), (evidence(),), algorithm_version="wb-v1")
    assert tuple(item.sense_id for item in result) == (uid(1), uid(2))
    assert result[1].gap_reasons == ("absence_of_evidence",)


def test_wb_02_rejects_incomplete_observation() -> None:
    try:
        evidence(correction_ref="")
    except ValueError:
        pass
    else:
        raise AssertionError("an observation without correction provenance was accepted")


def test_wb_03_keeps_modalities_independent_and_versioned() -> None:
    result = project_reference(
        (uid(1),),
        (evidence(modality="reading"), evidence(modality="writing", result_state="failure")),
        algorithm_version="wb-v7",
    )[0]
    assert result.algorithm_version == "wb-v7"
    assert result.modalities["reading"].success_count == 1
    assert result.modalities["writing"].success_count == 0


def test_wb_04_distinguishes_gap_causes() -> None:
    item = project_reference(
        (uid(1),),
        (evidence(help_state="hint", form_correct=False, contradiction=True),),
        algorithm_version="wb-v1",
    )[0]
    assert {"help_used", "form_gap", "contradiction"} <= set(item.gap_reasons)


def test_word_knowledge_progresses_from_encounter_to_autonomous_reuse() -> None:
    result = project_reference(
        (uid(1), uid(2)),
        (
            evidence(operation="queried"),
            evidence(operation="recognize"),
            evidence(operation="recall"),
            evidence(operation="produce", modality="writing", help_state="hint"),
            evidence(operation="produce", modality="writing"),
        ),
        algorithm_version="wb-v2",
    )

    assert result[0].knowledge.stage == "autonomous_reuse"
    assert result[0].knowledge.encounter_count == 5
    assert result[0].knowledge.recognition_success_count == 1
    assert result[0].knowledge.recall_success_count == 1
    assert result[0].knowledge.guided_reuse_success_count == 1
    assert result[0].knowledge.autonomous_reuse_success_count == 1
    assert result[1].knowledge.stage == "unencountered"


def test_failed_or_helped_recall_does_not_overstate_knowledge() -> None:
    result = project_reference(
        (uid(1),),
        (
            evidence(operation="recognize"),
            evidence(operation="recall", help_state="hint"),
            evidence(operation="produce", result_state="failure"),
        ),
        algorithm_version="wb-v2",
    )[0]

    assert result.knowledge.stage == "recognized"
    assert result.knowledge.recall_success_count == 0
    assert result.knowledge.autonomous_reuse_success_count == 0


def test_wb_05_plan_roles_are_bounded_and_explained() -> None:
    item = LexicalPlanItem(uid(1), "due", "retrieval_due")
    assert item.reason == "retrieval_due"


def test_wb_06_sprint_snapshot_is_bounded_and_immutable() -> None:
    snapshot = freeze_sprint_snapshot(
        (LexicalPlanItem(uid(1), "new", "module_target"),),
        max_new=1,
        budget_minutes=10,
    )
    assert snapshot.items[0].sense_id == uid(1)
    assert snapshot.frozen is True


def test_wb_07_scheduling_debt_does_not_resolve_it() -> None:
    scheduled = schedule_debt(uid(1), due_on="2026-08-11")
    assert scheduled.resolved is False
    assert apply_debt_evidence(scheduled, evidence()).resolved is True


def test_wb_08_gym_credits_only_recalled_support() -> None:
    credit = gym_credit(structure_success=True, support_recalled=False)
    assert credit.structure is True
    assert credit.support_lexicon is False


def test_wb_09_targets_only_discriminant_or_required_units() -> None:
    targets = validate_learning_targets(
        tokens=(uid(1), uid(2), uid(3)), discriminant=(uid(2),), required=(uid(3),)
    )
    assert targets == (uid(2), uid(3))


def test_wb_10_diagnostic_never_validates_untested_words() -> None:
    estimates = diagnostic_estimates(
        reference=(uid(1), uid(2)), tested={uid(1): (0.8, 0.7)}
    )
    assert uid(1) in estimates
    assert uid(2) not in estimates


def test_wb_11_assessment_updates_only_measured_scope() -> None:
    scope = AssessmentScope(modalities=("reading",), facets=("meaning",))
    assert scope.accepts("reading", "meaning") is True
    assert scope.accepts("writing", "meaning") is False


def test_wb_12_recommendation_is_fully_explainable() -> None:
    recommendation = Recommendation(
        target_id=uid(1),
        reason="production_gap",
        missing_evidence="independent_writing",
        due_on="2026-08-11",
        proposed_activity="controlled_recall",
    )
    assert all(
        (
            recommendation.reason,
            recommendation.missing_evidence,
            recommendation.due_on,
            recommendation.proposed_activity,
        )
    )
