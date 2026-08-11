import json

import pytest

from polyglot.modules.teacher.orchestration import parse_teacher_reply
from polyglot.platform.errors import DomainError, ErrorCode


def test_teacher_reply_accepts_only_bounded_reversible_actions() -> None:
    parsed = parse_teacher_reply(
        json.dumps(
            {
                "reply": "On utilise vorrei pour formuler une demande polie.",
                "actions": [
                    {
                        "type": "create_learning_debt",
                        "payload": {"target": "vorrei", "reason": "emploi hésitant"},
                    }
                ],
            }
        )
    )

    assert parsed.reply.startswith("On utilise")
    assert parsed.actions[0].action_type == "create_learning_debt"


@pytest.mark.parametrize(
    "payload",
    (
        "not-json",
        '{"reply":"ok"}',
        '{"reply":"ok","actions":[{"type":"publish_content","payload":{"id":"x"}}]}',
        '{"reply":"ok","actions":[{"type":"record_encounter","payload":{}}]}',
    ),
)
def test_teacher_reply_rejects_invalid_or_forbidden_output(payload: str) -> None:
    with pytest.raises(DomainError) as rejected:
        parse_teacher_reply(payload)

    assert rejected.value.code is ErrorCode.TOOL_SCHEMA_INVALID
