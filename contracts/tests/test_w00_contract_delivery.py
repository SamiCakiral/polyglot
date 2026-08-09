#!/usr/bin/env python3
"""Delivery-level W00 contract tests against the shipped registry."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate_contract_registry.py"


class W00ContractDeliveryTest(unittest.TestCase):
    def test_executes_positive_and_negative_fixture_for_each_tool(self) -> None:
        result = self.run_validator("--validate-tool-fixtures")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("22 tool fixtures valid", result.stdout)

    def test_rejects_unknown_command_error_reference(self) -> None:
        result = self.run_mutation(
            "registry/commands.yaml",
            lambda document: document["commands"][0].update({"errors": ["invented_failure"]}),
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("unknown command error: RegisterAccount.invented_failure", result.stdout)

    def test_rejects_unknown_tool_error_reference(self) -> None:
        result = self.run_mutation(
            "tools/manifest.yaml",
            lambda document: document["tools"][0].update({"errors": ["invented_failure"]}),
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("unknown tool error: profile.read_authorized.invented_failure", result.stdout)

    def test_rejects_missing_canonical_tool(self) -> None:
        result = self.run_mutation(
            "tools/manifest.yaml",
            lambda document: document["tools"].pop(),
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("canonical tool set mismatch", result.stdout)

    def test_rejects_missing_common_tool_safety_policy(self) -> None:
        result = self.run_mutation(
            "tools/manifest.yaml",
            lambda document: document.pop("common_limits"),
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("missing common tool limits", result.stdout)

    def test_docs_links_and_artifact_boundaries_are_repeatable(self) -> None:
        result = self.run_validator("--check-doc-links", "--check-artifacts")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("documentation links valid", result.stdout)
        self.assertIn("artifact boundary valid", result.stdout)

    def run_validator(self, *flags: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), "contracts/registry", "contracts/tests", *flags],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def run_mutation(self, relative_path: str, mutate: object) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory) / "contracts"
            shutil.copytree(ROOT / "contracts", temporary_root)
            path = temporary_root / relative_path
            document = json.loads(path.read_text())
            mutate(document)
            path.write_text(json.dumps(document, indent=2) + "\n")
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(temporary_root / "registry"), str(temporary_root / "tests")],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
