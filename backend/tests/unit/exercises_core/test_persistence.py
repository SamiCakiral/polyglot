from types import MappingProxyType

from polyglot.modules.exercises.core.persistence import _json, _resolved_stimulus


def test_exercise_json_encodes_frozen_structured_answers() -> None:
    answer = MappingProxyType({"confidence": 1, "details": MappingProxyType({"repeated": True})})

    assert _json(answer) == '{"confidence":1,"details":{"repeated":true}}'


def test_grammar_target_resolves_to_a_teachable_then_transformable_stimulus() -> None:
    exposure = _resolved_stimulus("EX-EXPOSE-01", {}, ("grammar:IT-GRAM-002",))
    transformation = _resolved_stimulus("EX-TRANSFORM-01", {}, ("grammar:IT-GRAM-002",))

    assert exposure["support_template"] == "je voudrais + nom/infinitif"
    assert exposure["target_template"] == "vorrei + nome/infinito"
    assert "Comprenez la fonction" in str(exposure["prompt"])
    assert "Utilisez puis transformez" in str(transformation["prompt"])
    assert "register" in transformation["transformations"]


def test_grammar_binding_does_not_replace_authored_oral_content() -> None:
    authored = {
        "prompt": "Répétez : こんにちは。わたしはサミです。",
        "model_answer": "こんにちは。わたしはサミです。",
    }

    resolved = _resolved_stimulus("EX-ORAL-01", authored, ("grammar:JA-GRAM-001",))

    assert resolved == authored
