import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator

from polyglot.interfaces.tools.deterministic import DeterministicToolHandlers
from polyglot.interfaces.tools.executor import ToolExecutor, ToolInvocation, ToolScope
from polyglot.modules.generation.runner import DeterministicScenarioRunner

ROOT = Path(__file__).resolve().parents[4]
FIXTURE_ROOT = ROOT / "fixtures/canonical/FX-TOOLS"
SCENARIO = FIXTURE_ROOT / "scenario.json"
TRANSCRIPT = FIXTURE_ROOT / "transcript.jsonl"
MANIFEST_SCHEMA = json.loads((ROOT / "contracts/fixtures/manifest.schema.json").read_text())


class FixtureSequence:
    def __init__(self, now: datetime) -> None:
        self.value = 100
        self.instant = now

    def id(self) -> UUID:
        self.value += 1
        return UUID(f"019fec40-0000-7000-8000-{self.value:012x}")

    def now(self) -> datetime:
        self.value += 1
        return self.instant + timedelta(milliseconds=self.value)


def fixture_runner() -> tuple[
    DeterministicScenarioRunner, tuple[ToolInvocation, ...], dict[str, object]
]:
    scenario = json.loads(SCENARIO.read_text())
    sequence = FixtureSequence(datetime.fromisoformat(scenario["clock"]))
    executor = ToolExecutor(
        DeterministicToolHandlers(sequence.id).handlers(),
        now=sequence.now,
        provenance_id=sequence.id,
    )
    calls = tuple(
        ToolInvocation(
            item["tool_name"],
            item["tool_version"],
            UUID(item["invocation_id"]),
            UUID(scenario["actor_id"]),
            item["actor_role"],
            ToolScope(),
            item["idempotency_key"],
            None,
            item["input"],
            UUID(item["correlation_id"]),
            None,
            {"security": "v1"},
        )
        for item in scenario["calls"]
    )
    return DeterministicScenarioRunner(executor), calls, scenario


def test_fx_tools_manifest_and_metadata_use_canonical_contracts() -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text())
    metadata = json.loads((FIXTURE_ROOT / "fixture-metadata.json").read_text())
    Draft202012Validator(MANIFEST_SCHEMA).validate(manifest)
    assert metadata["synthetic"] is True
    assert metadata["network_dependencies"] == []
    assert metadata["payloads"]["scenario.json"] == (
        f"sha256:{hashlib.sha256(SCENARIO.read_bytes()).hexdigest()}"
    )
    assert metadata["payloads"]["transcript.jsonl"] == (
        f"sha256:{hashlib.sha256(TRANSCRIPT.read_bytes()).hexdigest()}"
    )


@pytest.mark.asyncio
async def test_fx_tools_reproduces_the_committed_offline_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POLYGLOT_NETWORK_DISABLED", "1")
    runner, calls, scenario = fixture_runner()
    transcript = await runner.run(
        scenario_code=scenario["scenario_code"],
        scenario_version=scenario["scenario_version"],
        seed=scenario["seed"],
        invocations=calls,
    )
    assert transcript.jsonl == TRANSCRIPT.read_text()
    assert [line["status"] for line in transcript.lines] == [
        item["expected_status"] for item in scenario["calls"]
    ]
    assert transcript.lines[1]["error"]["code"] == "tool_schema_invalid"
    assert all("publish" not in json.dumps(line) for line in transcript.lines)
