from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from polyglot.interfaces.tools.deterministic import DeterministicToolHandlers
from polyglot.interfaces.tools.executor import ToolExecutor, ToolInvocation, ToolScope
from polyglot.modules.generation.runner import DeterministicScenarioRunner

NOW = datetime(2026, 8, 10, 12, tzinfo=UTC)


class Sequence:
    def __init__(self) -> None:
        self.value = 200

    def id(self) -> UUID:
        self.value += 1
        return UUID(f"019fec30-0000-7000-8000-{self.value:012x}")

    def now(self) -> datetime:
        self.value += 1
        return NOW + timedelta(milliseconds=self.value)


def build() -> tuple[DeterministicScenarioRunner, ToolInvocation]:
    sequence = Sequence()
    runner = DeterministicScenarioRunner(
        ToolExecutor(
            DeterministicToolHandlers(sequence.id).handlers(),
            now=sequence.now,
            provenance_id=sequence.id,
        )
    )
    invocation = ToolInvocation(
        "catalogue.list_targets",
        "1.0.0",
        sequence.id(),
        sequence.id(),
        "learner",
        ToolScope(),
        "read-1",
        None,
        {"pack_revision_id": "it-v1", "limit": 10},
        sequence.id(),
        None,
        {"security": "v1"},
    )
    return runner, invocation


@pytest.mark.asyncio
async def test_offline_runner_produces_the_same_jsonl_and_checksum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGLOT_NETWORK_DISABLED", "1")
    first_runner, first_invocation = build()
    second_runner, second_invocation = build()
    first = await first_runner.run(
        scenario_code="FX-TOOLS", scenario_version=1, seed=5016, invocations=(first_invocation,)
    )
    second = await second_runner.run(
        scenario_code="FX-TOOLS", scenario_version=1, seed=5016, invocations=(second_invocation,)
    )
    assert first.jsonl == second.jsonl
    assert first.checksum == second.checksum


@pytest.mark.asyncio
async def test_runner_refuses_to_start_when_network_is_not_explicitly_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLYGLOT_NETWORK_DISABLED", raising=False)
    runner, invocation = build()
    with pytest.raises(RuntimeError, match="NETWORK_DISABLED"):
        await runner.run(
            scenario_code="FX-TOOLS", scenario_version=1, seed=5016, invocations=(invocation,)
        )
