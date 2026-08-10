import json
from pathlib import Path

from polyglot.interfaces.tools.registry import TOOL_DEFINITIONS

ROOT = Path(__file__).resolve().parents[4]


def test_every_tool_exposes_machine_readable_input_and_output_schemas() -> None:
    for definition in TOOL_DEFINITIONS:
        input_schema = definition.input_schema()
        output_schema = definition.output_schema()
        assert input_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert input_schema["additionalProperties"] is False
        assert output_schema["additionalProperties"] is False
        assert output_schema["type"] == "object"
        json.dumps(input_schema)
        json.dumps(output_schema)


def test_w00_registry_contains_generation_job_and_tool_commands() -> None:
    commands = json.loads((ROOT / "contracts/registry/commands.yaml").read_text())["commands"]
    by_name = {item["name"]: item for item in commands}
    assert by_name["RequestGenerationJob"]["idempotency"] == "required"
    assert by_name["CancelGenerationJob"]["idempotency"] == "required"
    assert by_name["InvokeAuthoringTool"]["idempotency"] == "required"
