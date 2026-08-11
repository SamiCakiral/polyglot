from types import MappingProxyType

from polyglot.modules.exercises.core.persistence import _json


def test_exercise_json_encodes_frozen_structured_answers() -> None:
    answer = MappingProxyType(
        {"confidence": 1, "details": MappingProxyType({"repeated": True})}
    )

    assert _json(answer) == '{"confidence":1,"details":{"repeated":true}}'
