import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from polyglot.interfaces.tools.deterministic import DeterministicToolHandlers
from polyglot.interfaces.tools.executor import (
    ToolExecutor,
    ToolInvocation,
    ToolInvocationStatus,
    ToolScope,
)
from polyglot.interfaces.tools.registry import TOOL_DEFINITIONS, TOOL_REGISTRY, ToolEffect

NOW = datetime(2026, 8, 10, 12, tzinfo=UTC)


class Sequence:
    def __init__(self) -> None:
        self.value = 100

    def id(self) -> UUID:
        self.value += 1
        return UUID(f"019fec00-0000-7000-8000-{self.value:012x}")

    def now(self) -> datetime:
        self.value += 1
        return NOW + timedelta(milliseconds=self.value)


def invocation(
    name: str,
    role: str,
    payload: dict[str, object],
    *,
    key: str = "fixture-key",
) -> ToolInvocation:
    return ToolInvocation(
        name,
        "1.0.0",
        UUID("019fec00-0000-7000-8000-000000000001"),
        UUID("019fec00-0000-7000-8000-000000000002"),
        role,
        ToolScope(),
        key,
        None,
        payload,  # type: ignore[arg-type]
        UUID("019fec00-0000-7000-8000-000000000003"),
        None,
        {"security": "v1"},
    )


def executor(sequence: Sequence) -> ToolExecutor:
    return ToolExecutor(
        DeterministicToolHandlers(sequence.id).handlers(),
        now=sequence.now,
        provenance_id=sequence.id,
    )


def test_registry_contains_exactly_the_eleven_closed_tools() -> None:
    assert len(TOOL_DEFINITIONS) == len(TOOL_REGISTRY) == 11
    assert all(definition.version == "1.0.0" for definition in TOOL_DEFINITIONS)
    assert all(
        definition.input_schema()["additionalProperties"] is False
        for definition in TOOL_DEFINITIONS
    )


def test_runtime_registry_matches_the_versioned_contract_manifest() -> None:
    root = Path(__file__).resolve().parents[4]
    manifest = json.loads((root / "contracts/tools/manifest.yaml").read_text())
    manifest_tools = {item["tool_name"]: item for item in manifest["tools"]}

    assert set(manifest_tools) == set(TOOL_REGISTRY)
    for definition in TOOL_DEFINITIONS:
        item = manifest_tools[definition.name]
        assert set(item["roles"]) == definition.roles
        assert item["side_effect"] == definition.effect.value
        assert set(item["input"]) == set(definition.input_schema()["properties"])
        assert set(item["output"]) == set(definition.output_schema()["properties"])
        assert set(definition.input_schema()["required"]) == definition.required
        assert (
            set(definition.input_schema()["properties"]) - definition.required
            == definition.optional
        )
    assert not any(
        word in definition.name
        for definition in TOOL_DEFINITIONS
        for word in ("publish", "mastery")
    )


@pytest.mark.asyncio
async def test_unknown_fields_and_forbidden_roles_are_rejected_before_handler() -> None:
    sequence = Sequence()
    unknown = await executor(sequence).invoke(
        invocation(
            "catalogue.list_targets",
            "learner",
            {"pack_revision_id": "pack-1", "raw_attempts": True},
        )
    )
    forbidden = await executor(sequence).invoke(
        invocation(
            "exercise.submit_draft",
            "learner",
            {
                "pack_revision_id": "p",
                "primitive_id": "cloze",
                "blueprint_version": "1",
                "stimulus": {},
                "response_contract": {},
                "target_bindings": [],
                "accepted_answers_or_rubric": [],
                "hints": [],
                "difficulty_profile": {},
                "provenance_inputs": [],
            },
        )
    )

    assert unknown.status is ToolInvocationStatus.REJECTED
    assert unknown.error is not None and unknown.error.code == "tool_schema_invalid"
    assert forbidden.error is not None and forbidden.error.code == "tool_not_allowed"


@pytest.mark.asyncio
async def test_every_mutating_tool_only_returns_non_publishable_artifacts() -> None:
    sequence = Sequence()
    payloads = {
        "exercise.submit_draft": {
            "pack_revision_id": "p",
            "primitive_id": "cloze",
            "blueprint_version": 1,
            "stimulus": [],
            "response_contract": "free_text",
            "target_bindings": [],
            "accepted_answers_or_rubric": [],
            "hints": [],
            "difficulty_profile": "beginner",
            "provenance_inputs": [],
        },
        "curriculum.submit_module_draft": {
            "pack_revision_id": "p",
            "module": "arrival_in_italy",
            "audience": "beginner",
            "objectives": [],
            "prerequisites": [],
            "exit_policy": "complete_required_checks",
            "day_draft_refs": [],
            "length": "3_days",
            "context": "arrival",
            "provenance": "fixture",
        },
        "curriculum.submit_day_draft": {
            "module_draft_id": "d",
            "ordinal": 1,
            "arc": "discovery_practice_recall",
            "context": "arrival",
            "objectives": [],
            "novelty": "identity",
            "reviews": [],
            "next_day_needs": [],
            "lists": [],
            "compositions": [],
            "provenance": "fixture",
            "expected_version": 1,
        },
        "correction.submit_structured_draft": {
            "attempt_id": "a",
            "attempt_version": 1,
            "strategy": "rubric",
            "verdict": "partial",
            "criterion_scores": [],
            "error_codes": [],
            "proposed_answer": "x",
            "alternatives": [],
            "explanation_codes": [],
            "confidence": 0.9,
            "target_observations": [],
            "provenance": "fixture",
        },
    }
    roles = {
        "exercise.submit_draft": "author",
        "curriculum.submit_module_draft": "author",
        "curriculum.submit_day_draft": "author",
        "correction.submit_structured_draft": "reviewer",
    }
    for definition in TOOL_DEFINITIONS:
        if definition.effect in {
            ToolEffect.CREATE_DRAFT,
            ToolEffect.CREATE_MODULE_DRAFT,
            ToolEffect.CREATE_DAY_DRAFT,
            ToolEffect.CREATE_CORRECTION_DRAFT,
        }:
            result = await executor(sequence).invoke(
                invocation(definition.name, roles[definition.name], payloads[definition.name])
            )
            assert result.status is ToolInvocationStatus.SUCCEEDED
            assert result.output is not None
            assert result.output["status"] == "draft"
            assert result.output["publish_capability"] is False
            assert result.output["mastery_capability"] is False


@pytest.mark.asyncio
async def test_timeout_missing_handler_and_hostile_output_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sequence = Sequence()
    call = invocation("catalogue.list_targets", "learner", {"pack_revision_id": "it-v1"})

    async def slow(*_: object) -> dict[str, object]:
        await asyncio.sleep(0.02)
        return {"targets": [], "next_cursor": None, "stable": True}

    async def hostile(*_: object) -> dict[str, object]:
        return {
            "targets": [],
            "next_cursor": None,
            "stable": True,
            "publish": True,
        }

    original = TOOL_REGISTRY[call.tool_name]
    monkeypatch.setitem(TOOL_REGISTRY, call.tool_name, replace(original, timeout_ms=1))
    timed_out = await ToolExecutor(
        {call.tool_name: slow}, now=sequence.now, provenance_id=sequence.id
    ).invoke(call)
    unavailable = await ToolExecutor({}, now=sequence.now, provenance_id=sequence.id).invoke(call)
    monkeypatch.setitem(TOOL_REGISTRY, call.tool_name, original)
    rejected_output = await ToolExecutor(
        {call.tool_name: hostile}, now=sequence.now, provenance_id=sequence.id
    ).invoke(call)

    assert timed_out.error is not None and timed_out.error.code == "timeout"
    assert unavailable.error is not None and unavailable.error.code == "dependency_unavailable"
    assert rejected_output.error is not None
    assert rejected_output.error.code == "tool_schema_invalid"
