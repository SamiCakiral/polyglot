from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from polyglot.modules.exercises.core.domain import CORE_PRIMITIVE_IDS

from .bindings import CurriculumError

PAYLOAD_NAMES = (
    "module.json",
    "days.json",
    "bindings.json",
    "dialogues.json",
    "exercises.json",
    "oracles.json",
    "revision-cases.json",
)
MAX_FILE_BYTES = 512_000
MAX_DEPTH = 12


@dataclass(frozen=True, slots=True)
class ItalianCurriculumFixtureReport:
    day_codes: tuple[str, ...]
    profile_codes: tuple[str, ...]
    grammar_families: tuple[str, ...]
    gym_operations: tuple[str, ...]
    morphology_surfaces: tuple[str, ...]
    recall_edges: tuple[tuple[int, int], ...]
    declared_oracle_ids: tuple[str, ...]
    executed_oracle_ids: tuple[str, ...]
    invalid_case_codes: tuple[str, ...]
    credit_eligible_refs: frozenset[str]
    support_refs: frozenset[str]
    not_evaluable_pronunciation_refs: tuple[str, ...]
    network_dependencies: tuple[str, ...]
    linguistic_review: str
    pedagogical_review: str
    fingerprint: str


def _error(code: str) -> CurriculumError:
    return CurriculumError(code)


def _pairs_no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _error("fixture_duplicate_key")
        result[key] = value
    return result


def _depth(value: object, current: int = 0) -> int:
    if isinstance(value, dict):
        return max((_depth(item, current + 1) for item in value.values()), default=current)
    if isinstance(value, list):
        return max((_depth(item, current + 1) for item in value), default=current)
    return current


def _load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise _error("fixture_path_or_size_invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs_no_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _error("fixture_json_invalid") from exc
    if not isinstance(value, dict) or _depth(value) > MAX_DEPTH:
        raise _error("fixture_schema_invalid")
    return cast(dict[str, Any], value)


def _expect_keys(value: dict[str, Any], keys: Iterable[str], path: str) -> None:
    if set(value) != set(keys):
        raise _error(f"fixture_schema_invalid:{path}")


def _safe_root(root: Path) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise _error("fixture_path_or_size_invalid")
    resolved = root.resolve(strict=True)
    for path in root.rglob("*"):
        if path.is_symlink() or resolved not in path.resolve(strict=True).parents:
            raise _error("fixture_path_or_size_invalid")
    return resolved


def _checksum(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def fixture_fingerprint_from_file_order(root: Path, order: tuple[str, ...]) -> str:
    safe = _safe_root(root)
    if set(order) != set(PAYLOAD_NAMES) or len(order) != len(PAYLOAD_NAMES):
        raise _error("fixture_payload_set_invalid")
    digest = hashlib.sha256()
    for name in sorted(order):
        path = safe / name
        if path.parent != safe or path.is_symlink():
            raise _error("fixture_path_or_size_invalid")
        data = path.read_bytes()
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
    return f"sha256:{digest.hexdigest()}"


def _validate_manifest(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest = _load_json(root / "manifest.json")
    metadata = _load_json(root / "fixture-metadata.json")
    _expect_keys(manifest, ("id", "kind", "expected_status"), "manifest")
    _expect_keys(
        metadata,
        (
            "schema_version",
            "synthetic",
            "seed",
            "clock",
            "payloads",
            "network_dependencies",
            "provenance",
            "rights",
            "engine_compatibility",
            "linguistic_review",
            "pedagogical_review",
        ),
        "metadata",
    )
    if manifest != {"id": "FX-MODULE-IT", "kind": "positive", "expected_status": "pending_human"}:
        raise _error("fixture_identity_invalid")
    if metadata["schema_version"] != 1 or metadata["synthetic"] is not True:
        raise _error("fixture_schema_invalid")
    if metadata["network_dependencies"] != []:
        raise _error("fixture_network_dependency_forbidden")
    payload_hashes = metadata["payloads"]
    if not isinstance(payload_hashes, dict) or set(payload_hashes) != set(PAYLOAD_NAMES):
        raise _error("fixture_payload_set_invalid")
    payloads: dict[str, dict[str, Any]] = {}
    for name in PAYLOAD_NAMES:
        path = root / name
        data = path.read_bytes()
        if payload_hashes[name] != _checksum(data):
            raise _error("fixture_checksum_mismatch")
        payloads[name] = _load_json(path)
    return metadata, payloads


def _validate_days(
    days_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], tuple[tuple[int, int], ...]]:
    _expect_keys(days_payload, ("schema_version", "days"), "days")
    days = cast(list[dict[str, Any]], days_payload["days"])
    if [item.get("ordinal") for item in days] != [1, 2, 3]:
        raise _error("module_day_ordinal_gap")
    recalls: list[tuple[int, int]] = []
    for day in days:
        _expect_keys(
            day,
            (
                "code",
                "ordinal",
                "arc",
                "objective",
                "targets",
                "encounters",
                "outputs",
                "new_grammar_families",
                "explanations",
                "gym",
                "novelty_points",
                "novelty_budget",
                "minimum_minutes",
                "dialogue_id",
                "recall_from",
            ),
            "day",
        )
        targets = set(cast(list[str], day["targets"]))
        if not targets.issubset(cast(list[str], day["encounters"])) or not targets.issubset(
            cast(list[str], day["outputs"])
        ):
            raise _error("module_target_uncovered")
        if not set(cast(list[str], day["new_grammar_families"])).issubset(
            cast(list[str], day["explanations"])
        ):
            raise _error("module_new_structure_without_explanation")
        for gym in cast(list[dict[str, str]], day["gym"]):
            _expect_keys(gym, ("family", "operation"), "day.gym")
            if gym["family"] not in day["explanations"]:
                raise _error("module_new_structure_without_explanation")
            prefix, _, number = gym["operation"].partition("-")
            if prefix != "GYM" or not number.isdigit() or not 1 <= int(number) <= 15:
                raise _error("module_gym_without_w10_contract")
        if day["arc"] == "transfer" and day["novelty_points"] != 0:
            raise _error("module_novelty_budget_exceeded")
        source = day["recall_from"]
        if source is not None:
            if not isinstance(source, int) or source != int(day["ordinal"]) - 1:
                raise _error("module_j1_not_scheduled")
            recalls.append((source, int(day["ordinal"])))
    return days, tuple(recalls)


def _validate_bindings(payload: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    _expect_keys(
        payload,
        (
            "schema_version",
            "grammar",
            "morphology",
            "pronunciation",
            "support_refs",
            "credit_eligible_refs",
        ),
        "bindings",
    )
    surfaces: list[str] = []
    refs: set[str] = set()
    for item in cast(list[dict[str, Any]], payload["morphology"]):
        _expect_keys(
            item, ("ref", "surface", "features", "primitive", "accepted", "rejected"), "morphology"
        )
        if item["primitive"] not in CORE_PRIMITIVE_IDS or not item["features"]:
            raise _error("module_morphology_oracle_missing")
        if item["surface"] != item["accepted"] or item["accepted"] == item["rejected"]:
            raise _error("module_morphology_oracle_missing")
        if item["ref"] in refs:
            raise _error("fixture_duplicate_reference")
        refs.add(str(item["ref"]))
        surfaces.append(str(item["surface"]))
    not_evaluable: list[str] = []
    for item in cast(list[dict[str, Any]], payload["pronunciation"]):
        _expect_keys(
            item,
            (
                "ref",
                "transcript",
                "media_transcript_checksum",
                "transcript_checksum",
                "evaluability",
                "role",
            ),
            "pronunciation",
        )
        actual = _checksum(str(item["transcript"]).encode("utf-8"))
        if actual != item["transcript_checksum"] or actual != item["media_transcript_checksum"]:
            raise _error("module_pronunciation_asset_incoherent")
        if item["evaluability"] != "perception":
            not_evaluable.append(str(item["ref"]))
    support = set(cast(list[str], payload["support_refs"]))
    credit = set(cast(list[str], payload["credit_eligible_refs"]))
    if support & credit or set(not_evaluable) & credit:
        raise _error("module_support_lexicon_miscredited")
    return tuple(sorted(surfaces)), tuple(sorted(not_evaluable))


def _validate_exercises(payload: dict[str, Any]) -> tuple[str, ...]:
    _expect_keys(payload, ("schema_version", "exercises"), "exercises")
    gym: set[str] = set()
    for item in cast(list[dict[str, Any]], payload["exercises"]):
        allowed = {"id", "day", "primitive", "targets", "credit", "gym_operation"}
        if not set(item).issubset(allowed) or not {
            "id",
            "day",
            "primitive",
            "targets",
            "credit",
        }.issubset(item):
            raise _error("fixture_schema_invalid:exercise")
        if item["primitive"] not in CORE_PRIMITIVE_IDS:
            raise _error("module_target_unresolved")
        operation = item.get("gym_operation")
        if operation is not None:
            gym.add(str(operation))
        if item["primitive"] == "EX-ORAL-01" and item["credit"] is not False:
            raise _error("module_pronunciation_not_evaluable")
    return tuple(sorted(gym))


def _invalid_result(case: dict[str, Any]) -> str:
    kind = case.get("kind")
    if kind == "duration" and not 3 <= int(case.get("nominal_days", 0)) <= 30:
        return "module_duration_out_of_range"
    if kind == "cycle":
        edges = {tuple(item) for item in cast(list[list[str]], case.get("edges", []))}
        if any((right, left) in edges for left, right in edges):
            return "module_prerequisite_cycle"
    if kind == "unresolved_ref" and case.get("resolved") is False:
        return "module_target_unresolved"
    if kind == "load" and float(case.get("novelty_points", 0)) > float(case.get("limit", 0)):
        return "module_load_budget_exceeded"
    if kind == "false_credit" and case.get("role") == "support" and case.get("credit") is True:
        return "module_support_lexicon_miscredited"
    if kind == "human_review" and case.get("status") != "approved":
        return "module_human_review_required"
    if kind == "past_mutation" and case.get("past_days_equal") is False:
        return "module_past_day_mutated"
    raise _error("fixture_invalid_case_not_rejected")


def _validate_invalid_cases(root: Path) -> tuple[str, ...]:
    results: list[str] = []
    for path in sorted((root / "invalid").glob("*/case.json")):
        case = _load_json(path)
        result = _invalid_result(case)
        if result != case.get("expected"):
            raise _error("fixture_invalid_case_wrong_finding")
        results.append(result)
    if len(results) != 7:
        raise _error("fixture_invalid_case_set_incomplete")
    return tuple(sorted(results))


def _execute_oracles(
    oracle_payload: dict[str, Any],
    *,
    days: list[dict[str, Any]],
    bindings: dict[str, Any],
    recalls: tuple[tuple[int, int], ...],
    metadata: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    _expect_keys(oracle_payload, ("schema_version", "oracles"), "oracles")
    declared: list[str] = []
    executed: list[str] = []
    grammar = {str(item["family"]) for item in cast(list[dict[str, Any]], bindings["grammar"])}
    for oracle in cast(list[dict[str, str]], oracle_payload["oracles"]):
        _expect_keys(oracle, ("id", "kind", "expected"), "oracle")
        oracle_id = oracle["id"]
        declared.append(oracle_id)
        kind = oracle["kind"]
        valid = {
            "day_arc": len(days) == 3 and days[-1]["arc"] == "transfer",
            "target_coverage": all(set(item["targets"]).issubset(item["outputs"]) for item in days),
            "grammar_order": grammar == {"identity", "polite-request", "existence"},
            "morphology": len(bindings["morphology"]) == 10,
            "pronunciation": any(
                item["evaluability"] == "not_evaluable" for item in bindings["pronunciation"]
            ),
            "recall": recalls == ((1, 2), (2, 3)),
            "profiles": all(
                value in {"P-ABS", "P-FAUX", "P-INT"} for value in ("P-ABS", "P-FAUX", "P-INT")
            ),
            "credit_scope": not set(bindings["support_refs"])
            & set(bindings["credit_eligible_refs"]),
            "human_gates": metadata["linguistic_review"]
            == metadata["pedagogical_review"]
            == "pending_human",
        }.get(kind, False)
        if not valid:
            raise _error(f"fixture_oracle_failed:{oracle_id}")
        executed.append(oracle_id)
    if len(declared) != len(set(declared)):
        raise _error("fixture_duplicate_oracle")
    return tuple(declared), tuple(executed)


def load_italian_curriculum_fixture(root: Path) -> ItalianCurriculumFixtureReport:
    safe = _safe_root(root)
    metadata, payloads = _validate_manifest(safe)
    module = payloads["module.json"]
    _expect_keys(
        module,
        (
            "schema_version",
            "fixture_id",
            "module_id",
            "module_revision_id",
            "revision_no",
            "module_code",
            "target_variety",
            "support_variety",
            "profiles",
            "nominal_days",
            "max_days",
            "primary_intention",
            "final_mission",
            "provenance",
            "rights",
            "linguistic_review",
            "pedagogical_review",
        ),
        "module",
    )
    days, recalls = _validate_days(payloads["days.json"])
    bindings = payloads["bindings.json"]
    surfaces, not_evaluable = _validate_bindings(bindings)
    gym_operations = _validate_exercises(payloads["exercises.json"])
    dialogues = payloads["dialogues.json"]
    _expect_keys(dialogues, ("schema_version", "dialogues"), "dialogues")
    if {item["dialogue_id"] for item in days} != {
        item["id"] for item in cast(list[dict[str, Any]], dialogues["dialogues"])
    }:
        raise _error("module_target_uncovered")
    revision_cases = payloads["revision-cases.json"]
    _expect_keys(revision_cases, ("schema_version", "cases"), "revision-cases")
    expected_revision_results = {
        "accepted",
        "module_past_day_mutated",
        "module_revision_mapping_incomplete",
    }
    if {item["expected"] for item in revision_cases["cases"]} != expected_revision_results:
        raise _error("module_revision_mapping_incomplete")
    declared, executed = _execute_oracles(
        payloads["oracles.json"],
        days=days,
        bindings=bindings,
        recalls=recalls,
        metadata=metadata,
    )
    if module["profiles"] != ["P-ABS", "P-FAUX", "P-INT"]:
        raise _error("module_load_budget_exceeded")
    return ItalianCurriculumFixtureReport(
        tuple(str(item["code"]) for item in days),
        tuple(cast(list[str], module["profiles"])),
        tuple(sorted(str(item["family"]) for item in bindings["grammar"])),
        gym_operations,
        surfaces,
        recalls,
        declared,
        executed,
        _validate_invalid_cases(safe),
        frozenset(cast(list[str], bindings["credit_eligible_refs"])),
        frozenset(cast(list[str], bindings["support_refs"])),
        not_evaluable,
        tuple(cast(list[str], metadata["network_dependencies"])),
        str(metadata["linguistic_review"]),
        str(metadata["pedagogical_review"]),
        fixture_fingerprint_from_file_order(safe, PAYLOAD_NAMES),
    )
