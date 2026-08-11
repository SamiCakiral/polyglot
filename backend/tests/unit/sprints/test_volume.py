from polyglot.modules.sprints.persistence import _instance_repetitions


def test_long_session_repeats_practice_without_repeating_explanations() -> None:
    assert _instance_repetitions(30, "guided_output") == 1
    assert _instance_repetitions(60, "grammar_toolbox") == 1
    assert _instance_repetitions(60, "guided_output") == 2
    assert _instance_repetitions(60, "shadowing") == 2
