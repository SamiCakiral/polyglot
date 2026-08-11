import json

import pytest

from polyglot.modules.generation.orchestration import (
    build_generation_messages,
    parse_generation_plan,
)
from polyglot.platform.errors import DomainError, ErrorCode


def test_generation_prompt_exposes_only_allowlisted_closed_tools() -> None:
    messages = build_generation_messages(
        task_type="exercise_draft",
        task_input={"topic": "treno"},
        tool_allowlist=("exercise.submit_draft@1.0.0",),
    )
    system = messages[0][1]
    assert "exercise.submit_draft@1.0.0" in system
    assert "publish" not in system.lower()
    assert '"blueprint_version":1' in system
    assert json.loads(messages[1][1]) == {
        "task_input": {"topic": "treno"},
        "task_type": "exercise_draft",
    }


def test_generation_plan_requires_one_exact_allowlisted_invocation() -> None:
    plan = parse_generation_plan(
        json.dumps(
            {
                "input": {
                    "limit": 10,
                    "pack_revision_id": "it-v1",
                },
                "tool_name": "catalogue.list_targets",
                "tool_version": "1.0.0",
            }
        ),
        ("catalogue.list_targets@1.0.0",),
    )
    assert plan.tool_name == "catalogue.list_targets"
    assert plan.input["limit"] == 10

    invalid = (
        "not-json",
        '{"tool_name":"catalogue.list_targets","tool_version":"1.0.0"}',
        '{"tool_name":"exercise.submit_draft","tool_version":"1.0.0","input":{}}',
        '{"tool_name":"catalogue.list_targets","tool_version":"2.0.0","input":{}}',
        '{"tool_name":"catalogue.list_targets","tool_version":"1.0.0","input":{},"extra":1}',
    )
    for message in invalid:
        with pytest.raises(DomainError) as caught:
            parse_generation_plan(message, ("catalogue.list_targets@1.0.0",))
        assert caught.value.code in {ErrorCode.TOOL_NOT_ALLOWED, ErrorCode.TOOL_SCHEMA_INVALID}


def test_generation_plan_accepts_one_json_fence_without_surrounding_prose() -> None:
    message = """```json
{"tool_name":"catalogue.list_targets","tool_version":"1.0.0","input":{"pack_revision_id":"it-v1"}}
```"""

    plan = parse_generation_plan(message, ("catalogue.list_targets@1.0.0",))

    assert plan.tool_name == "catalogue.list_targets"
