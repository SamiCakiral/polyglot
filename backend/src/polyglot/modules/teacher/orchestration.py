# ruff: noqa: E501
from __future__ import annotations

import json
from dataclasses import dataclass

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue

ALLOWED_ACTION_FIELDS: dict[str, frozenset[str]] = {
    "add_word_to_list": frozenset({"word", "list_name", "context"}),
    "create_learning_debt": frozenset({"target", "reason"}),
    "prepare_exercise": frozenset({"primitive", "target", "instruction"}),
    "create_practice_preset": frozenset({"name", "mode", "direction", "stack_refs"}),
    "record_encounter": frozenset({"surface", "context"}),
}


@dataclass(frozen=True, slots=True)
class ProposedTeacherAction:
    action_type: str
    payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ParsedTeacherReply:
    reply: str
    actions: tuple[ProposedTeacherAction, ...]


def parse_teacher_reply(raw: str) -> ParsedTeacherReply:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False) from error
    if not isinstance(value, dict) or set(value) != {"reply", "actions"}:
        raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
    reply = value.get("reply")
    actions = value.get("actions")
    if not isinstance(reply, str) or not reply.strip() or len(reply) > 12000:
        raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
    if not isinstance(actions, list) or len(actions) > 3:
        raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
    parsed: list[ProposedTeacherAction] = []
    for item in actions:
        if not isinstance(item, dict) or set(item) != {"type", "payload"}:
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
        action_type = item.get("type")
        payload = item.get("payload")
        if not isinstance(action_type, str) or action_type not in ALLOWED_ACTION_FIELDS:
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
        if (
            not isinstance(payload, dict)
            or not payload
            or not set(payload) <= ALLOWED_ACTION_FIELDS[action_type]
        ):
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
        if any(not isinstance(key, str) for key in payload):
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode()) > 4000:
            raise DomainError(ErrorCode.TOOL_SCHEMA_INVALID, retryable=False)
        parsed.append(ProposedTeacherAction(action_type, payload))
    return ParsedTeacherReply(reply.strip(), tuple(parsed))


def teacher_system_prompt() -> str:
    return (
        "You are Polyglot's patient language teacher. Decide immediately and keep private "
        "reasoning under 300 tokens without repeating or rehearsing these instructions. "
        "Use the support language for explanations "
        "and the target language for examples. Be concise, precise, and contrastive when known "
        "languages help. Never assign mastery, publish content, grade an official assessment, or "
        "delete anything. Return only strict JSON with exactly two keys: reply (string) and actions "
        "(array). Actions are optional and only allowed after an explicit user request. Each action "
        "must have exactly type and payload. Allowed types: add_word_to_list, "
        "create_learning_debt, prepare_exercise, create_practice_preset, record_encounter. "
        "Payload must be an object using only these fields: add_word_to_list uses word, "
        "list_name, context; create_learning_debt uses target, reason; prepare_exercise uses "
        "primitive, target, instruction; create_practice_preset uses name, mode, direction, "
        "stack_refs; record_encounter uses surface, context. For example: "
        '{"type":"create_learning_debt","payload":{"target":"vorrei vs voglio",'
        '"reason":"contrast to practise"}}. '
        "Never wrap JSON in markdown."
    )
