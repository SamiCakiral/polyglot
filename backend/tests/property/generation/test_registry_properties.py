from hypothesis import given
from hypothesis import strategies as st

from polyglot.interfaces.tools.registry import TOOL_DEFINITIONS


@given(st.sampled_from(TOOL_DEFINITIONS))
def test_tool_schemas_are_closed_and_versions_are_pinned(definition: object) -> None:
    tool = definition
    schema = tool.input_schema()  # type: ignore[attr-defined]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) <= set(schema["properties"])
    assert tool.version == "1.0.0"  # type: ignore[attr-defined]
