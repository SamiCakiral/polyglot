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
POLICY_TRANSCRIPT_PREFIX = "tool policy simulation: "


class W00ContractDeliveryTest(unittest.TestCase):
    def test_executes_positive_and_negative_fixture_for_each_tool(self) -> None:
        result = self.run_validator("--validate-tool-fixtures")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("22 tool fixtures valid", result.stdout)

    def test_executes_six_closed_policy_simulations_without_effects(self) -> None:
        result = self.run_validator("--validate-tool-fixtures")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        transcripts = [
            json.loads(line.removeprefix(POLICY_TRANSCRIPT_PREFIX))
            for line in result.stdout.splitlines()
            if line.startswith(POLICY_TRANSCRIPT_PREFIX)
        ]
        expected_errors = {
            "idempotency_conflict": "idempotency_conflict",
            "role_denial": "tool_not_allowed",
            "stale_reference": "version_conflict",
            "size_limit": "size_limit_exceeded",
            "timeout": "timeout",
            "forbidden_effect": "tool_not_allowed",
        }
        self.assertEqual(set(expected_errors), {item["case"] for item in transcripts})
        self.assertEqual(6, len(transcripts))
        for item in transcripts:
            with self.subTest(case=item["case"]):
                self.assertEqual({"status", "error"}, set(item["result"]))
                self.assertEqual(
                    {"code", "retryable", "details_codes"},
                    set(item["result"]["error"]),
                )
                self.assertEqual(expected_errors[item["case"]], item["result"]["error"]["code"])
                self.assertIs(item["result"]["error"]["retryable"], False)
                self.assertEqual([], item["result"]["error"]["details_codes"])
                self.assertEqual([], item["effects"])
                self.assertEqual([], item["forbidden_effects"])

    def test_rejects_policy_case_without_invocation_context(self) -> None:
        result = self.run_mutation(
            "tests/fixtures/tools/meta-cases.json",
            lambda document: document[0].pop("invocation_context"),
            "--validate-tool-fixtures",
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("tool policy invocation context missing", result.stdout)

    def test_rejects_policy_error_not_allowed_for_tool(self) -> None:
        def use_other_tools_error(document: list[dict[str, object]]) -> None:
            case = document[0]
            case["expected_error"] = "draft_not_found"
            case["expected_output"]["error"]["code"] = "draft_not_found"

        result = self.run_mutation(
            "tests/fixtures/tools/meta-cases.json",
            use_other_tools_error,
            "--validate-tool-fixtures",
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn(
            "tool policy error not allowed: exercise.submit_draft.draft_not_found",
            result.stdout,
        )

    def test_policy_simulation_uses_manifest_roles(self) -> None:
        result = self.run_mutation(
            "tools/manifest.yaml",
            lambda document: document["tools"][4].update({"roles": ["reviewer"]}),
            "--validate-tool-fixtures",
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn(
            "tool policy result mismatch: idempotency_conflict: expected idempotency_conflict, got tool_not_allowed",
            result.stdout,
        )

    def test_idempotency_conflict_fixture_reuses_key_with_changed_fingerprint(self) -> None:
        cases = json.loads((ROOT / "contracts/tests/fixtures/tools/meta-cases.json").read_text())
        case = next(item for item in cases if item["case"] == "idempotency_conflict")
        context = case["invocation_context"]
        self.assertEqual(context["stored_idempotency_key"], context["idempotency_key"])
        self.assertNotEqual(context["stored_fingerprint"], context["request_fingerprint"])

    def test_each_policy_case_depends_on_its_invocation_context(self) -> None:
        def use_new_idempotency_key(context: dict[str, object]) -> None:
            fingerprints = (context["stored_fingerprint"], context["request_fingerprint"])
            self.assertEqual(context["stored_idempotency_key"], context["idempotency_key"])
            self.assertNotEqual(*fingerprints)
            context["idempotency_key"] = "idem-exercise-new"
            self.assertNotEqual(context["stored_idempotency_key"], context["idempotency_key"])
            self.assertEqual(fingerprints, (context["stored_fingerprint"], context["request_fingerprint"]))

        def allow_role(context: dict[str, object]) -> None:
            context["actor_role"] = "author"

        def refresh_reference(context: dict[str, object]) -> None:
            context["current_version"] = context["expected_version"]

        def fit_input(context: dict[str, object]) -> None:
            context["input_bytes"] = 262144

        def finish_in_time(context: dict[str, object]) -> None:
            context["elapsed_seconds"] = 30

        def request_allowed_effect(context: dict[str, object]) -> None:
            context["requested_effect"] = "create_draft"

        repairs = {
            "idempotency_conflict": use_new_idempotency_key,
            "role_denial": allow_role,
            "stale_reference": refresh_reference,
            "size_limit": fit_input,
            "timeout": finish_in_time,
            "forbidden_effect": request_allowed_effect,
        }
        for case_name, repair in repairs.items():
            with self.subTest(case=case_name):
                def mutate(document: list[dict[str, object]]) -> None:
                    case = next(item for item in document if item["case"] == case_name)
                    repair(case["invocation_context"])

                result = self.run_mutation(
                    "tests/fixtures/tools/meta-cases.json",
                    mutate,
                    "--validate-tool-fixtures",
                )
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn(f"tool policy case did not reject: {case_name}", result.stdout)

    def test_timeout_policy_uses_manifest_limit(self) -> None:
        result = self.run_mutation(
            "tools/manifest.yaml",
            lambda document: document["tools"][5]["limits"].update({"timeout_seconds": 31}),
            "--validate-tool-fixtures",
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("tool policy case did not reject: timeout", result.stdout)

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

    def test_registers_all_common_tool_errors(self) -> None:
        errors = json.loads((ROOT / "contracts/registry/errors.yaml").read_text())["errors"]
        self.assertTrue(
            {"scope_forbidden", "reference_not_found"}.issubset(errors),
            "document 30 common tool errors must remain canonical",
        )

    def test_docs_links_and_artifact_boundaries_are_repeatable(self) -> None:
        result = self.run_validator("--check-doc-links", "--check-artifacts")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("documentation links valid", result.stdout)
        self.assertIn("artifact boundary valid", result.stdout)

    def test_rejects_changed_canonical_http_mapping(self) -> None:
        result = self.run_mutation(
            "registry/commands.yaml",
            lambda document: document["commands"][0].update({"method": "PUT"}),
        )
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("canonical command mapping mismatch", result.stdout)

    def test_rejects_published_exercise_draft_output(self) -> None:
        result = self.run_validator("--validate-tool-fixtures")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        fixture = ROOT / "contracts/tests/fixtures/tools/negative/exercise.submit_draft.json"
        self.assertIn("published", fixture.read_text())

    def test_rejects_untracked_v1_and_unapproved_artifacts(self) -> None:
        app = ROOT / "app"
        app.mkdir()
        marker = app / "runtime.py"
        marker.write_text("# V1 runtime marker\n")
        try:
            result = self.run_validator("--check-artifacts")
        finally:
            marker.unlink()
            app.rmdir()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn("forbidden untracked private artifact: app/", result.stdout)

    def test_rejects_untracked_files_in_protected_trees(self) -> None:
        paths = [
            ROOT / "contracts/local-private.json",
            ROOT / "scripts/generate_pillar_content_v2.py",
            ROOT / "docs/private-notes.txt",
        ]
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT)):
                remove_parent = not path.parent.exists()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("local\n")
                try:
                    result = self.run_validator("--check-artifacts")
                finally:
                    path.unlink()
                    if remove_parent:
                        path.parent.rmdir()
                self.assertEqual(1, result.returncode, result.stdout + result.stderr)
                self.assertIn(
                    f"forbidden untracked private artifact: {path.relative_to(ROOT)}",
                    result.stdout,
                )

    def test_allows_only_exact_sdd_bookkeeping_names(self) -> None:
        directory = ROOT / ".superpowers/sdd/27-plan-implementation-detaille"
        bookkeeping = directory / "task-W99-brief.md"
        bookkeeping.write_text("# SDD bookkeeping\n")
        try:
            result = self.run_validator("--check-artifacts")
        finally:
            bookkeeping.unlink()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

        arbitrary = directory / "private-notes.md"
        arbitrary.write_text("private\n")
        try:
            result = self.run_validator("--check-artifacts")
        finally:
            arbitrary.unlink()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertIn(
            "forbidden untracked private artifact: .superpowers/sdd/27-plan-implementation-detaille/private-notes.md",
            result.stdout,
        )

    def run_validator(self, *flags: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), "contracts/registry", "contracts/tests", *flags],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )

    def run_mutation(self, relative_path: str, mutate: object, *flags: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory) / "contracts"
            shutil.copytree(ROOT / "contracts", temporary_root)
            path = temporary_root / relative_path
            document = json.loads(path.read_text())
            mutate(document)
            path.write_text(json.dumps(document, indent=2) + "\n")
            return subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    str(temporary_root / "registry"),
                    str(temporary_root / "tests"),
                    *flags,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
