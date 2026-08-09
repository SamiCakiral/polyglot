#!/usr/bin/env python3
"""Black-box contract tests for the W00 registry validator."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
VALIDATOR = ROOT / "scripts" / "validate_contract_registry.py"


class ContractRegistryValidatorTest(unittest.TestCase):
    """Each fixture names a distinct registry defect that must be rejected."""

    def test_rejects_unknown_enum_value(self) -> None:
        self.assert_rejected("unknown-enum")

    def test_rejects_duplicate_http_route(self) -> None:
        self.assert_rejected("duplicate-route")

    def test_rejects_event_without_schema_version(self) -> None:
        self.assert_rejected("missing-event-schema-version")

    def test_rejects_tool_without_limits(self) -> None:
        self.assert_rejected("missing-tool-limits")

    def assert_rejected(self, fixture_name: str) -> None:
        case = json.loads((FIXTURES / "negative" / fixture_name / "case.json").read_text())
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            contracts = root / "contracts"
            shutil.copytree(ROOT / "contracts", contracts)
            registry = contracts / "registry"
            tests = contracts / "tests"
            self.apply_mutation(contracts, case["mutation"])
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), str(registry), str(tests)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn(case["expected_error"], result.stdout)

    def write_valid_registry(self, root: Path, tests: Path) -> None:
        registry = root / "registry"
        events = root / "events"
        tools = root / "tools"
        (registry / "events").mkdir(parents=True)
        events.mkdir()
        tools.mkdir()
        tests.mkdir()
        files = {
            "enums.yaml": {"enums": {"account_role": ["learner", "author"]}},
            "commands.yaml": {
                "commands": [
                    {
                        "name": "RegisterAccount",
                        "method": "POST",
                        "route": "/api/v1/accounts",
                        "events": ["account_registered"],
                        "enum_values": {"account_role": ["author"]},
                        "idempotency": "required",
                    }
                ]
            },
            "queries.yaml": {"queries": [{"name": "GetCurrentUser", "method": "GET", "route": "/api/v1/session"}]},
            "errors.yaml": {"errors": ["validation_failed"]},
            "events/envelope.schema.json": {"type": "object", "required": ["event_id", "event_type", "schema_version"]},
            "events/event-catalogue.yaml": {"events": [{"event_type": "account_registered", "schema_version": 1}]},
            "tools/manifest.yaml": {
                "common_limits": {
                    "max_input_bytes": 262144,
                    "max_output_bytes": 1048576,
                    "max_free_text_characters": 20000,
                },
                "forbidden_effects": [
                    "approve",
                    "publish",
                    "retire",
                    "award_mastery",
                    "modify_fsrs_schedule",
                ],
                "tools": [
                    {
                        "tool_name": "profile.read_authorized",
                        "input_schema": "profile.read_authorized.input.schema.json",
                        "output_schema": "profile.read_authorized.output.schema.json",
                        "side_effect": "none",
                        "limits": {"max_input_bytes": 262144, "max_output_bytes": 1048576},
                    }
                ]
            },
            "tools/profile.read_authorized.input.schema.json": {"type": "object"},
            "tools/profile.read_authorized.output.schema.json": {"type": "object"},
        }
        for relative_path, content in files.items():
            target = root / relative_path if relative_path.startswith(("events/", "tools/")) else registry / relative_path
            target.write_text(json.dumps(content, indent=2) + "\n")

    def apply_mutation(self, root: Path, mutation: dict[str, object]) -> None:
        relative_path = str(mutation["path"])
        base = root if relative_path.startswith(("events/", "tools/")) else root / "registry"
        path = base / relative_path
        content = json.loads(path.read_text())
        operation = mutation["operation"]
        if operation == "append_command":
            content["commands"].append(mutation["value"])
        elif operation == "set_enum_value":
            content["commands"][0]["enum_values"] = mutation["value"]
        elif operation == "remove_event_schema_version":
            content["events"][0].pop("schema_version")
        elif operation == "remove_tool_limits":
            content["tools"][0].pop("limits")
        else:
            self.fail(f"unsupported fixture mutation: {operation}")
        path.write_text(json.dumps(content, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
