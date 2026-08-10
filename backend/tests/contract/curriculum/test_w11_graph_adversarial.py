from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from polyglot.modules.curriculum import BindingRole
from polyglot.modules.curriculum.fixtures import _production_validation_input
from polyglot.modules.curriculum.validation import ValidationInput, validate_curriculum

FIXTURE = Path(__file__).parents[4] / "fixtures" / "canonical" / "FX-MODULE-IT"


def payload(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((FIXTURE / name).read_text(encoding="utf-8")),
    )


def pilot_data() -> ValidationInput:
    return _production_validation_input(
        payload("module.json"),
        cast(list[dict[str, Any]], payload("days.json")["days"]),
        payload("bindings.json"),
        payload("exercises.json"),
    )


def test_pilot_graph_has_closed_targets_gym_recalls_and_transfer_novelty() -> None:
    data = pilot_data()
    for day in data.module.days:
        target_universe = set(day.primary_target_refs) | set(day.secondary_target_refs)
        assert {
            target
            for exercise in day.exercise_bindings
            for target in exercise.target_bindings
        }.issubset(target_universe)
        for target in day.primary_target_refs:
            if target.startswith("skill:"):
                assert any(
                    binding.target_ref == target and binding.credit_eligible
                    for binding in day.skill_bindings
                )
        allowed_gym = {
            operation
            for binding in day.grammar_bindings
            for operation in binding.allowed_operations
        }
        assert {
            exercise.gym_operation
            for exercise in day.exercise_bindings
            if exercise.gym_operation is not None
        }.issubset(allowed_gym)
        if day.ordinal > 1:
            source = data.module.days[day.ordinal - 2]
            source_targets = set(source.primary_target_refs) | set(
                source.secondary_target_refs
            )
            source_exercises = {
                binding.definition_revision_id for binding in source.exercise_bindings
            }
            assert all(
                recall.source_day_ordinal == source.ordinal
                and recall.target_ref in source_targets
                and recall.source_exercise_binding_id in source_exercises
                for recall in day.recall_specs
            )
        if day.novelty_budget == 0:
            assert all(
                binding.role is not BindingRole.NEW
                for bindings in (
                    day.skill_bindings,
                    day.lexicon_bindings,
                    day.grammar_bindings,
                    day.morphology_bindings,
                    day.pronunciation_bindings,
                )
                for binding in bindings
            )


def test_graph_validator_rejects_unbound_skill_exercise_gym_and_recall() -> None:
    data = pilot_data()
    day1, day2, day3 = data.module.days
    hostile_day1 = replace(
        day1,
        skill_bindings=(replace(day1.skill_bindings[0], role=BindingRole.SUPPORT),),
        exercise_bindings=(
            replace(
                day1.exercise_bindings[0],
                target_bindings=("skill:does-not-exist",),
                gym_operation="GYM-15",
            ),
            *day1.exercise_bindings[1:],
        ),
    )
    hostile_day2 = replace(
        day2,
        recall_specs=(
            replace(
                day2.recall_specs[0],
                target_ref="skill:does-not-exist",
                source_day_ordinal=999,
            ),
        ),
    )
    hostile = replace(
        data,
        module=replace(
            data.module,
            days=(hostile_day1, hostile_day2, day3),
            payload_checksum="",
        ),
    )

    codes = {item.message_code for item in validate_curriculum(hostile).findings}

    assert {
        "module_target_uncovered",
        "module_recall_source_missing",
        "module_validation_input_unbound",
    }.issubset(codes)
