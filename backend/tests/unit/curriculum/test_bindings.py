from __future__ import annotations

from uuid import UUID

import pytest

from polyglot.modules.curriculum import (
    BindingRole,
    CurriculumError,
    ExerciseBinding,
    GrammarTargetBinding,
    LexiconTargetBinding,
    MorphologyTargetBinding,
    PronunciationEvaluability,
    PronunciationTargetBinding,
    SkillTargetBinding,
)


def uid(suffix: int) -> UUID:
    return UUID(f"019fe111-0000-7000-8000-{suffix:012d}")


def test_bindings_are_typed_frozen_and_credit_roles_are_closed() -> None:
    skill = SkillTargetBinding(uid(1), BindingRole.TARGET, ("written_production",), ("produce",), (uid(2),))
    lexicon = LexiconTargetBinding(uid(3), BindingRole.SUPPORT, (uid(4),), (uid(5),))
    grammar = GrammarTargetBinding(uid(6), (uid(7),), uid(8), BindingRole.NEW, "request", ("GYM-01",))
    morphology = MorphologyTargetBinding(uid(9), "volere.cond.pres", (("person", "1"),), BindingRole.NEW, ("EX-RECALL-06",))
    pronunciation = PronunciationTargetBinding(uid(10), "e-vs-e-accent", uid(11), uid(12), BindingRole.CONTRAST, PronunciationEvaluability.PERCEPTION)
    exercise = ExerciseBinding(uid(13), "EX-TRANSFORM-01", ("grammar:request",), uid(14), 2000, 5000)

    assert skill.credit_eligible
    assert not lexicon.credit_eligible
    assert grammar.credit_eligible and morphology.credit_eligible
    assert pronunciation.credit_eligible
    assert exercise.estimated_p50_ms <= exercise.estimated_p80_ms
    with pytest.raises((AttributeError, TypeError)):
        grammar.allowed_operations += ("GYM-02",)  # type: ignore[misc]


def test_binding_rejects_unknown_operations_and_false_credit() -> None:
    with pytest.raises(CurriculumError, match="module_gym_without_w10_contract"):
        GrammarTargetBinding(uid(1), (uid(2),), uid(3), BindingRole.NEW, "request", ("GYM-99",))
    with pytest.raises(CurriculumError, match="module_support_lexicon_miscredited"):
        SkillTargetBinding(uid(1), BindingRole.SUPPORT, ("written_production",), ("credit",), (uid(2),))
