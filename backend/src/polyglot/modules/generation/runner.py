from __future__ import annotations

import json
import os
from dataclasses import dataclass

from polyglot.interfaces.tools.executor import ToolExecutor, ToolInvocation
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class RunnerTranscript:
    scenario_code: str
    scenario_version: int
    seed: int
    lines: tuple[dict[str, JsonValue], ...]
    jsonl: str
    checksum: str


class DeterministicScenarioRunner:
    def __init__(self, executor: ToolExecutor) -> None:
        self._executor = executor

    async def run(
        self,
        *,
        scenario_code: str,
        scenario_version: int,
        seed: int,
        invocations: tuple[ToolInvocation, ...],
    ) -> RunnerTranscript:
        if os.environ.get("POLYGLOT_NETWORK_DISABLED") != "1":
            raise RuntimeError("deterministic runner requires POLYGLOT_NETWORK_DISABLED=1")
        lines: list[dict[str, JsonValue]] = []
        for ordinal, invocation in enumerate(invocations, start=1):
            result = await self._executor.invoke(invocation)
            error: dict[str, JsonValue] | None = None
            if result.error is not None:
                error = {
                    "code": result.error.code,
                    "retryable": result.error.retryable,
                    "field_path": result.error.field_path,
                    "details_codes": list(result.error.details_codes),
                }
            lines.append(
                {
                    "ordinal": ordinal,
                    "invocation_id": str(result.invocation_id),
                    "tool_name": invocation.tool_name,
                    "tool_version": result.tool_version,
                    "status": result.status.value,
                    "output": result.output,
                    "error": error,
                    "output_fingerprint": result.output_fingerprint,
                    "started_at": result.started_at.isoformat(),
                    "finished_at": result.finished_at.isoformat(),
                }
            )
        jsonl = "".join(
            json.dumps(line, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
            for line in lines
        )
        fingerprint_lines: list[JsonValue] = list(lines)
        checksum = canonical_json_fingerprint(
            {
                "scenario_code": scenario_code,
                "scenario_version": scenario_version,
                "seed": seed,
                "lines": fingerprint_lines,
            }
        )
        return RunnerTranscript(
            scenario_code,
            scenario_version,
            seed,
            tuple(lines),
            jsonl,
            checksum,
        )
