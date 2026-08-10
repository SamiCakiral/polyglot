from __future__ import annotations

from dataclasses import replace

from polyglot.modules.curriculum import (
    BindingRole,
    ExerciseBinding,
    GrammarTargetBinding,
    LexiconTargetBinding,
    MorphologyTargetBinding,
    PronunciationEvaluability,
    PronunciationTargetBinding,
    RecallSpec,
    SkillTargetBinding,
)
from tests.unit.curriculum.test_module_contract import day, revision, uid


def test_module_day_owns_the_complete_typed_planning_graph() -> None:
    required_fields = {
        "secondary_target_refs",
        "context_revision_ids",
        "skill_bindings",
        "lexicon_bindings",
        "grammar_bindings",
        "morphology_bindings",
        "pronunciation_bindings",
        "exercise_bindings",
        "recall_specs",
        "fallback_revision_ids",
        "final_output_spec",
        "validator_revision_ids",
        "prerequisite_day_ordinals",
    }
    assert required_fields.issubset(day(1).__dataclass_fields__)


def test_module_reference_graph_includes_every_typed_binding_destination() -> None:
    graph_day = replace(
        day(1),
        context_revision_ids=(uid(101),),
        skill_bindings=(
            SkillTargetBinding(
                uid(102), BindingRole.TARGET, ("written_production",), ("produce",), (uid(103),)
            ),
        ),
        lexicon_bindings=(
            LexiconTargetBinding(uid(104), BindingRole.NEW, (uid(105),), (uid(106),)),
        ),
        grammar_bindings=(
            GrammarTargetBinding(
                uid(107), (uid(108),), uid(109), BindingRole.NEW, "identity", ("GYM-01",)
            ),
        ),
        morphology_bindings=(
            MorphologyTargetBinding(
                uid(110), "essere.ind.pres", (("person", "1"),), BindingRole.TARGET,
                ("EX-RECALL-06",),
            ),
        ),
        pronunciation_bindings=(
            PronunciationTargetBinding(
                uid(111), "e-vs-e-accent", uid(112), uid(113), BindingRole.CONTRAST,
                PronunciationEvaluability.PERCEPTION,
            ),
        ),
        exercise_bindings=(
            ExerciseBinding(uid(114), "EX-TRANSFORM-01", ("grammar:identity",), uid(115), 500, 900),
        ),
        recall_specs=(RecallSpec("grammar:identity", "j+1", 1, uid(116), "h0"),),
        fallback_revision_ids=(uid(117),),
        final_output_spec="produce a three-turn exchange",
        validator_revision_ids=(uid(118),),
        prerequisite_day_ordinals=(),
    )
    module = revision(days=(graph_day, day(2), day(3)))
    references = set(module.all_reference_keys())

    assert {
        f"context:{uid(101)}",
        f"skill:{uid(102)}",
        f"evidence:{uid(103)}",
        f"sense:{uid(104)}",
        f"form:{uid(105)}",
        f"usage:{uid(106)}",
        f"grammar:{uid(107)}",
        f"pattern:{uid(108)}",
        f"skill:{uid(109)}",
        f"analysis:{uid(110)}",
        f"pronunciation:{uid(111)}",
        f"transcript:{uid(112)}",
        f"media:{uid(113)}",
        f"exercise:{uid(114)}",
        f"policy:{uid(115)}",
        f"exercise:{uid(116)}",
        f"fallback:{uid(117)}",
        f"validator:{uid(118)}",
    }.issubset(references)
