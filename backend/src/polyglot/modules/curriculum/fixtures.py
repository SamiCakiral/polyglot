from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from polyglot.modules.exercises.core.domain import CORE_PRIMITIVE_IDS

from .bindings import (
    BindingRole,
    CurriculumError,
    ExerciseBinding,
    GrammarTargetBinding,
    LexiconTargetBinding,
    MorphologyTargetBinding,
    PronunciationEvaluability,
    PronunciationTargetBinding,
    RecallSpec,
    SkillTargetBinding,
)
from .domain import ArcType, LearningModuleRevision, ModuleDay, ModuleStatus
from .italian_pilot_catalog import NORMATIVE_CHECKSUMS
from .ports import (
    ReferenceExpectation,
    ReferenceManifest,
    ReferenceStatus,
    ResolvedReference,
)
from .revisioning import (
    ModuleRevisionMapping,
    RevisionMappingEntry,
    build_successor_revision,
    validate_revision_mapping,
)
from .validation import (
    HumanGateStatus,
    HumanReviewGate,
    MorphologyOracle,
    PronunciationOracle,
    ValidationInput,
    validate_curriculum,
)

PAYLOAD_NAMES = (
    "module.json",
    "days.json",
    "bindings.json",
    "dialogues.json",
    "exercises.json",
    "oracles.json",
    "revision-cases.json",
)
INVALID_CASE_NAMES = (
    "invalid/cycle/case.json",
    "invalid/duration/case.json",
    "invalid/false-credit/case.json",
    "invalid/load/case.json",
    "invalid/missing-human-review/case.json",
    "invalid/past-mutation/case.json",
    "invalid/unresolved-ref/case.json",
)
BUNDLE_NAMES = (
    "fixture-metadata.json",
    "manifest.json",
    *PAYLOAD_NAMES,
    *INVALID_CASE_NAMES,
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
    lexicon_set_sizes: tuple[tuple[str, int], ...]
    target_lexicon_count: int
    exercise_count: int
    pinned_exercise_revision_count: int
    final_mission_criteria: tuple[str, ...]
    budget_plan_keys: tuple[str, ...]


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
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, InvalidJsonConstant) as exc:
        raise _error("fixture_json_invalid") from exc
    if not isinstance(value, dict) or _depth(value) > MAX_DEPTH:
        raise _error("fixture_schema_invalid")
    return cast(dict[str, Any], value)


class InvalidJsonConstant(ValueError):
    pass


def _reject_json_constant(value: str) -> None:
    raise InvalidJsonConstant(value)


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
    actual_names = {
        path.relative_to(safe).as_posix() for path in safe.rglob("*") if path.is_file()
    }
    if actual_names != set(BUNDLE_NAMES):
        raise _error("fixture_bundle_set_invalid")
    digest = hashlib.sha256()
    # The fingerprint is external to the bundle, so no recursive field is excluded.
    for name in sorted(BUNDLE_NAMES):
        path = safe / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
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
                "secondary_targets",
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


def _semantic_checksum(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_normative_catalog(payloads: dict[str, dict[str, Any]]) -> None:
    bindings = payloads["bindings.json"]
    module = payloads["module.json"]
    categories: dict[str, dict[str, object]] = {
        "exercise": {
            str(item["id"]): item
            for item in cast(list[dict[str, Any]], payloads["exercises.json"]["exercises"])
        },
        "morphology": {
            str(item["ref"]): item
            for item in cast(list[dict[str, Any]], bindings["morphology"])
        },
        "pronunciation": {
            str(item["ref"]): item
            for item in cast(list[dict[str, Any]], bindings["pronunciation"])
        },
        "dialogue": {
            str(item["id"]): item
            for item in cast(
                list[dict[str, Any]], payloads["dialogues.json"]["dialogues"]
            )
        },
        "budget": {
            str(item["key"]): item
            for item in cast(list[dict[str, Any]], module["budget_plans"])
        },
        "lexicon": {
            str(sense["ref"]): {"set_code": item["set_code"], **sense}
            for item in cast(list[dict[str, Any]], bindings["lexicon_sets"])
            for sense in cast(list[dict[str, Any]], item["senses"])
        },
    }
    for category, expected in NORMATIVE_CHECKSUMS.items():
        actual = categories[category]
        if set(actual) != set(expected):
            raise _error(f"fixture_normative_semantic_mismatch:{category}:set")
        for key, expected_checksum in expected.items():
            if _semantic_checksum(actual[key]) != expected_checksum:
                raise _error(f"fixture_normative_semantic_mismatch:{category}:{key}")


def _validate_bindings(
    payload: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...], frozenset[str]]:
    _expect_keys(
        payload,
        (
            "schema_version",
            "grammar",
            "lexicon_sets",
            "morphology",
            "pronunciation",
            "support_refs",
            "credit_eligible_refs",
        ),
        "bindings",
    )
    lexicon_sets = cast(list[dict[str, Any]], payload["lexicon_sets"])
    if [item.get("set_code") for item in lexicon_sets] != [
        "IT-LEXSET-D1",
        "IT-LEXSET-D2",
        "IT-LEXSET-D3",
    ]:
        raise _error("module_target_unresolved")
    sense_refs: set[str] = set()
    for lexicon_set in lexicon_sets:
        _expect_keys(lexicon_set, ("set_code", "set_revision_id", "senses"), "lexicon_set")
        if UUID(str(lexicon_set["set_revision_id"])).version != 7:
            raise _error("module_target_unresolved")
        senses = cast(list[dict[str, str]], lexicon_set["senses"])
        if len(senses) != 8:
            raise _error("module_target_uncovered")
        for sense in senses:
            _expect_keys(sense, ("ref", "sense_revision_id", "surface"), "lexicon_sense")
            if UUID(sense["sense_revision_id"]).version != 7 or sense["ref"] in sense_refs:
                raise _error("module_target_unresolved")
            sense_refs.add(sense["ref"])
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
    return tuple(sorted(surfaces)), tuple(sorted(not_evaluable)), frozenset(sense_refs)


def _validate_exercises(
    payload: dict[str, Any],
) -> tuple[tuple[str, ...], int, int, frozenset[str]]:
    _expect_keys(payload, ("schema_version", "exercises"), "exercises")
    gym: set[str] = set()
    for item in cast(list[dict[str, Any]], payload["exercises"]):
        allowed = {
            "id", "definition_revision_id", "day", "primitive", "targets", "credit",
            "gym_operation", "gym_plan_revision_id",
        }
        if not set(item).issubset(allowed) or not {
            "id",
            "definition_revision_id",
            "day",
            "primitive",
            "targets",
            "credit",
        }.issubset(item):
            raise _error("fixture_schema_invalid:exercise")
        if item["primitive"] not in CORE_PRIMITIVE_IDS:
            raise _error("module_target_unresolved")
        if UUID(str(item["definition_revision_id"])).version != 7:
            raise _error("module_target_unresolved")
        operation = item.get("gym_operation")
        if operation is not None:
            gym.add(str(operation))
            if UUID(str(item.get("gym_plan_revision_id", ""))).version != 7:
                raise _error("module_gym_without_w10_contract")
        if item["primitive"] == "EX-ORAL-01" and item["credit"] is not False:
            raise _error("module_pronunciation_not_evaluable")
    exercises = cast(list[dict[str, Any]], payload["exercises"])
    ids = frozenset(str(item["id"]) for item in exercises)
    if len(exercises) != 35 or len(ids) != 35:
        raise _error("module_target_uncovered")
    return tuple(sorted(gym)), len(exercises), len(ids), ids


def _fixture_uuid(group: int, value: int) -> UUID:
    return UUID(f"019fe113-0000-7000-{group:04d}-{value:012d}")


def _production_validation_input(
    module_payload: dict[str, Any],
    days_payload: list[dict[str, Any]],
    bindings: dict[str, Any],
    exercises_payload: dict[str, Any],
) -> ValidationInput:
    grammar_items = {
        str(item["family"]): item
        for item in cast(list[dict[str, Any]], bindings["grammar"])
    }
    morphology_items = cast(list[dict[str, Any]], bindings["morphology"])
    pronunciation_items = cast(list[dict[str, Any]], bindings["pronunciation"])
    lexicon_sets = cast(list[dict[str, Any]], bindings["lexicon_sets"])
    exercise_items = cast(list[dict[str, Any]], exercises_payload["exercises"])
    module_days: list[ModuleDay] = []
    for item in days_payload:
        ordinal = int(item["ordinal"])
        grammar_bindings = tuple(
            GrammarTargetBinding(
                _fixture_uuid(9200, ordinal * 10 + index),
                tuple(
                    _fixture_uuid(9210 + ordinal, ordinal * 100 + index * 10 + pattern_index)
                    for pattern_index, _ in enumerate(
                        cast(list[str], grammar_items[family]["patterns"]), start=1
                    )
                ),
                _fixture_uuid(9250, ordinal * 10 + index),
                BindingRole(str(grammar_items[family]["role"])),
                family,
                tuple(
                    str(gym["operation"])
                    for gym in cast(list[dict[str, Any]], item["gym"])
                    if str(gym["family"]) == family
                ),
            )
            for index, family in enumerate(
                cast(list[str], item["explanations"]), start=1
            )
        )
        day_exercises = tuple(
            exercise for exercise in exercise_items if int(exercise["day"]) == ordinal
        )
        exercise_bindings = tuple(
            ExerciseBinding(
                UUID(str(exercise["definition_revision_id"])),
                str(exercise["primitive"]),
                tuple(cast(list[str], exercise["targets"])),
                _fixture_uuid(9300 + ordinal, index),
                30_000,
                60_000,
                str(exercise["gym_operation"])
                if exercise.get("gym_operation") is not None
                else None,
            )
            for index, exercise in enumerate(day_exercises, start=1)
        )
        lexicon_senses = cast(list[dict[str, Any]], lexicon_sets[ordinal - 1]["senses"])
        morphology_slice = {
            1: morphology_items[:2],
            2: morphology_items[2:8],
            3: morphology_items[8:],
        }[ordinal]
        pronunciation_slice = {
            1: pronunciation_items[:1],
            2: pronunciation_items[1:],
            3: [],
        }[ordinal]
        module_days.append(
            ModuleDay(
                module_day_id=_fixture_uuid(8100, ordinal),
                ordinal=ordinal,
                arc_type=ArcType(str(item["arc"])),
                objective_codes=(str(item["code"]),),
                modality_objectives=(("written_production", str(item["objective"])),),
                primary_target_refs=tuple(cast(list[str], item["targets"])),
                encountered_target_refs=tuple(cast(list[str], item["encounters"])),
                output_target_refs=tuple(cast(list[str], item["outputs"])),
                minimum_useful_minutes=int(item["minimum_minutes"]),
                novelty_budget=float(item["novelty_budget"]),
                required_block_roles=("explanation", "practice", "production"),
                new_grammar_family_codes=tuple(
                    cast(list[str], item["new_grammar_families"])
                ),
                explained_grammar_family_codes=tuple(
                    cast(list[str], item["explanations"])
                ),
                gym_grammar_family_codes=tuple(
                    str(gym["family"])
                    for gym in cast(list[dict[str, Any]], item["gym"])
                ),
                context_revision_ids=(_fixture_uuid(8200, ordinal),),
                secondary_target_refs=tuple(
                    cast(list[str], item["secondary_targets"])
                ),
                skill_bindings=tuple(
                    SkillTargetBinding(
                        _fixture_uuid(9400 + ordinal, index),
                        BindingRole.TARGET,
                        ("written_production",),
                        ("produce",),
                        (),
                        target,
                    )
                    for index, target in enumerate(
                        (
                            target
                            for target in cast(list[str], item["targets"])
                            if target.startswith("skill:")
                        ),
                        start=1,
                    )
                ),
                lexicon_bindings=tuple(
                    LexiconTargetBinding(
                        UUID(str(sense["sense_revision_id"])),
                        BindingRole.DUE if ordinal == 3 else BindingRole.NEW,
                        (_fixture_uuid(9500 + ordinal, index),),
                        (_fixture_uuid(9600 + ordinal, index),),
                    )
                    for index, sense in enumerate(lexicon_senses, start=1)
                ),
                grammar_bindings=grammar_bindings,
                morphology_bindings=tuple(
                    MorphologyTargetBinding(
                        _fixture_uuid(9700 + ordinal, index),
                        str(morphology["ref"]),
                        tuple(
                            sorted(
                                cast(dict[str, str], morphology["features"]).items()
                            )
                        ),
                        BindingRole.TARGET,
                        (str(morphology["primitive"]),),
                    )
                    for index, morphology in enumerate(morphology_slice, start=1)
                ),
                pronunciation_bindings=tuple(
                    PronunciationTargetBinding(
                        _fixture_uuid(9800 + ordinal, index),
                        str(pronunciation["ref"]),
                        _fixture_uuid(9850 + ordinal, index),
                        _fixture_uuid(9900 + ordinal, index),
                        BindingRole(str(pronunciation["role"])),
                        PronunciationEvaluability(str(pronunciation["evaluability"])),
                    )
                    for index, pronunciation in enumerate(
                        pronunciation_slice, start=1
                    )
                ),
                exercise_bindings=exercise_bindings,
                recall_specs=(
                    RecallSpec(
                        str(cast(list[str], days_payload[ordinal - 2]["targets"])[0]),
                        "j+1",
                        int(item["recall_from"]),
                        UUID(
                            str(
                                next(
                                    exercise["definition_revision_id"]
                                    for exercise in exercise_items
                                    if int(exercise["day"]) == ordinal - 1
                                )
                            )
                        ),
                        "h0",
                    ),
                )
                if ordinal > 1
                else (),
                fallback_revision_ids=(_fixture_uuid(8300, ordinal),),
                final_output_spec=str(item["objective"]),
                validator_revision_ids=(_fixture_uuid(8400, ordinal),),
                prerequisite_day_ordinals=(ordinal - 1,) if ordinal > 1 else (),
            )
        )
    module = LearningModuleRevision(
        module_revision_id=UUID(str(module_payload["module_revision_id"])),
        module_id=UUID(str(module_payload["module_id"])),
        revision_no=int(module_payload["revision_no"]),
        status=ModuleStatus.DRAFT,
        pack_revision_id=_fixture_uuid(8500, 1),
        target_variety_id=_fixture_uuid(8500, 2),
        support_variety_ids=(_fixture_uuid(8500, 3),),
        primary_intention=str(module_payload["primary_intention"]),
        final_mission_revision_id=UUID(
            str(cast(dict[str, Any], module_payload["mission"])["mission_revision_id"])
        ),
        entry_profile_codes=tuple(cast(list[str], module_payload["profiles"])),
        nominal_days=int(module_payload["nominal_days"]),
        max_days=int(module_payload["max_days"]),
        prerequisite_skill_revision_ids=(_fixture_uuid(8600, 1),),
        target_skill_revision_ids=tuple(_fixture_uuid(8600, value) for value in (2, 3, 4)),
        exit_policy_revision_id=_fixture_uuid(8700, 1),
        recall_policy_revision_id=_fixture_uuid(8700, 2),
        provenance_id=str(module_payload["provenance"]),
        rights_refs=tuple(cast(list[str], module_payload["rights"])),
        validator_set_revision_id=_fixture_uuid(8700, 3),
        schema_version=1,
        compatibility_range=">=1,<2",
        days=tuple(module_days),
    )
    resolved = tuple(
        ResolvedReference(
            reference=reference,
            kind=reference.partition(":")[0],
            status=ReferenceStatus.PUBLISHED,
            pack_revision_id=str(module.pack_revision_id),
            variety_id=str(module.target_variety_id),
            checksum=f"sha256:{hashlib.sha256(reference.encode()).hexdigest()}",
            provenance_id=module.provenance_id,
            rights_refs=module.rights_refs,
        )
        for reference in module.all_reference_keys()
    )
    expectations = tuple(
        ReferenceExpectation(
            item.reference,
            item.kind,
            item.pack_revision_id,
            item.variety_id,
            item.checksum,
        )
        for item in resolved
    )
    manifest = ReferenceManifest("FX-MODULE-IT:REFERENCE-CATALOGUE-V1", expectations)
    module = replace(
        module,
        reference_manifest_checksum=manifest.checksum,
        payload_checksum="",
    )
    return ValidationInput(
        module=module,
        resolved_references=resolved,
        reference_expectations=expectations,
        reference_manifest=manifest,
        grammar_explanations=tuple(
            (int(item["ordinal"]), family)
            for item in days_payload
            for family in cast(list[str], item["explanations"])
        ),
        grammar_practices=tuple(
            (int(item["ordinal"]), str(gym["family"]), str(gym["operation"]))
            for item in days_payload
            for gym in cast(list[dict[str, Any]], item["gym"])
        ),
        morphology_oracles=tuple(
            MorphologyOracle(
                f"analysis:{binding.form_analysis_id}",
                binding.feature_bundle,
                str(item["accepted"]),
                True,
            )
            for day in module.days
            for binding, item in zip(
                day.morphology_bindings,
                {
                    1: morphology_items[:2],
                    2: morphology_items[2:8],
                    3: morphology_items[8:],
                }[day.ordinal],
                strict=True,
            )
        ),
        pronunciation_oracles=tuple(
            PronunciationOracle(
                f"pronunciation:{binding.target_revision_id}",
                str(item["transcript"]),
                str(item["transcript_checksum"]),
                str(item["media_transcript_checksum"]),
                str(item["evaluability"]),
            )
            for day in module.days
            for binding, item in zip(
                day.pronunciation_bindings,
                {1: pronunciation_items[:1], 2: pronunciation_items[1:], 3: []}[
                    day.ordinal
                ],
                strict=True,
            )
        ),
        profile_novelty_limits=(("P-ABS", 6.0), ("P-FAUX", 8.0), ("P-INT", 10.0)),
        day_novelty_points=tuple(
            (int(item["ordinal"]), float(item["novelty_points"])) for item in days_payload
        ),
        human_gates=(
            HumanReviewGate("P-LING", HumanGateStatus.PENDING_HUMAN),
            HumanReviewGate("P-PED", HumanGateStatus.PENDING_HUMAN),
        ),
    )


def _run_production_validation(data: ValidationInput) -> None:
    report = validate_curriculum(data)
    allowed = {
        "module_human_review_required",
        "module_pronunciation_not_evaluable",
    }
    unexpected = {
        finding.message_code for finding in report.findings if finding.message_code not in allowed
    }
    if unexpected:
        raise _error(f"fixture_production_validation_failed:{sorted(unexpected)[0]}")


def _invalid_result(case: dict[str, Any], data: ValidationInput) -> str:
    kind = case.get("kind")
    if kind == "duration":
        try:
            replace(
                data.module,
                nominal_days=int(case.get("nominal_days", 0)),
                max_days=int(case.get("nominal_days", 0)),
                days=data.module.days[: int(case.get("nominal_days", 0))],
            )
        except CurriculumError as error:
            return str(error)
    if kind == "cycle":
        try:
            replace(data.module.days[1], prerequisite_day_ordinals=(2,))
        except CurriculumError as error:
            return str(error)
    if kind == "unresolved_ref":
        hostile = replace(data.resolved_references[0], status=ReferenceStatus.MISSING)
        report = validate_curriculum(
            replace(data, resolved_references=(hostile, *data.resolved_references[1:]))
        )
        if any(item.message_code == "module_target_unresolved" for item in report.findings):
            return "module_target_unresolved"
    if kind == "load":
        report = validate_curriculum(
            replace(
                data,
                day_novelty_points=(
                    (1, float(case.get("novelty_points", 0))),
                    *data.day_novelty_points[1:],
                ),
            )
        )
        if any(item.message_code == "module_load_budget_exceeded" for item in report.findings):
            return "module_load_budget_exceeded"
    if kind == "false_credit":
        try:
            SkillTargetBinding(
                _fixture_uuid(8800, 1),
                BindingRole.SUPPORT,
                ("written_production",),
                ("produce",),
                (_fixture_uuid(8800, 2),),
            )
        except CurriculumError as error:
            return str(error)
    if kind == "human_review":
        report = validate_curriculum(data)
        if any(
            item.message_code == "module_human_review_required" for item in report.findings
        ):
            return "module_human_review_required"
    if kind == "past_mutation":
        try:
            build_successor_revision(
                data.module,
                successor_revision_id=_fixture_uuid(8900, 1),
                candidate_days=(
                    replace(data.module.days[0], objective_codes=("mutated",)),
                    *data.module.days[1:],
                ),
                executed_through_ordinal=1,
                expected_revision_no=data.module.revision_no,
            )
        except CurriculumError as error:
            return str(error)
    raise _error("fixture_invalid_case_not_rejected")


def _validate_invalid_cases(root: Path, data: ValidationInput) -> tuple[str, ...]:
    results: list[str] = []
    for path in sorted((root / "invalid").glob("*/case.json")):
        case = _load_json(path)
        result = _invalid_result(case, data)
        if result != case.get("expected"):
            raise _error("fixture_invalid_case_wrong_finding")
        results.append(result)
    if len(results) != 7:
        raise _error("fixture_invalid_case_set_incomplete")
    return tuple(sorted(results))


def _validate_revision_cases(payload: dict[str, Any], data: ValidationInput) -> None:
    _expect_keys(payload, ("schema_version", "cases"), "revision-cases")
    source = data.module
    for index, case in enumerate(cast(list[dict[str, Any]], payload["cases"]), start=1):
        _expect_keys(
            case,
            ("id", "executed_through", "past_days_equal", "mapping_complete", "expected"),
            "revision-case",
        )
        expected = str(case["expected"])
        try:
            candidate_days = source.days
            if not case["past_days_equal"]:
                candidate_days = (
                    replace(source.days[0], objective_codes=("mutated",)),
                    *source.days[1:],
                )
            successor = build_successor_revision(
                source,
                successor_revision_id=_fixture_uuid(9000, index),
                candidate_days=candidate_days,
                executed_through_ordinal=int(case["executed_through"]),
                expected_revision_no=source.revision_no,
            )
            entries = tuple(
                RevisionMappingEntry(day.ordinal, day.ordinal, target, target)
                for day in source.days
                for target in day.primary_target_refs
            )
            if not case["mapping_complete"]:
                entries = entries[:1]
            mapping = ModuleRevisionMapping(
                _fixture_uuid(9100, index),
                source.module_revision_id,
                successor.module_revision_id,
                entries,
                True,
            )
            findings = validate_revision_mapping(source, successor, mapping)
            actual = (
                "module_revision_mapping_incomplete"
                if any(
                    item.message_code == "module_revision_mapping_incomplete"
                    for item in findings
                )
                else "accepted"
            )
        except CurriculumError as error:
            actual = str(error)
        if actual != expected:
            raise _error(f"fixture_revision_case_mismatch:{case['id']}")


def _execute_oracles(
    oracle_payload: dict[str, Any],
    *,
    days: list[dict[str, Any]],
    bindings: dict[str, Any],
    recalls: tuple[tuple[int, int], ...],
    metadata: dict[str, Any],
    module: dict[str, Any],
    dialogues: dict[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    _expect_keys(oracle_payload, ("schema_version", "oracles"), "oracles")
    declared: list[str] = []
    executed: list[str] = []
    grammar_items = cast(list[dict[str, Any]], bindings["grammar"])
    grammar = {str(item["family"]) for item in grammar_items}
    grammar_by_ref = {str(item["ref"]): str(item["family"]) for item in grammar_items}
    morphology_by_ref = {
        str(item["ref"]): str(item["accepted"])
        for item in cast(list[dict[str, Any]], bindings["morphology"])
    }
    pronunciation_by_ref = {
        str(item["ref"]): str(item["evaluability"])
        for item in cast(list[dict[str, Any]], bindings["pronunciation"])
    }
    dialogue_by_ref = {
        str(item["id"]): _checksum(
            json.dumps(
                {
                    "lines": item["lines"],
                    "grammar_refs": item["grammar_refs"],
                    "lexicon_refs": item["lexicon_refs"],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        for item in cast(list[dict[str, Any]], dialogues["dialogues"])
    }
    budgets = cast(list[dict[str, Any]], module["budget_plans"])
    budget_shape = {
        (int(item["day"]), int(item["budget_minutes"])) for item in budgets
    }
    for oracle in cast(list[dict[str, str]], oracle_payload["oracles"]):
        if not {"id", "kind", "expected"}.issubset(oracle) or not set(oracle).issubset(
            {"id", "kind", "expected", "target_ref"}
        ):
            raise _error("fixture_schema_invalid:oracle")
        oracle_id = str(oracle["id"])
        declared.append(oracle_id)
        kind = str(oracle["kind"])
        target_ref = str(oracle.get("target_ref", ""))
        actual = {
            "day_arc": "valid"
            if len(days) == 3 and days[-1]["arc"] == "transfer"
            else "invalid",
            "target_coverage": "covered"
            if all(set(item["targets"]).issubset(item["outputs"]) for item in days)
            else "uncovered",
            "grammar_order": "ordered"
            if grammar
            == {
                "identity",
                "polite-request",
                "existence",
                "formal-request",
                "need",
            }
            else "unordered",
            "morphology": "all_distinct"
            if len(morphology_by_ref) == len(bindings["morphology"]) == 10
            else "invalid",
            "pronunciation": "bounded_credit"
            if "not_evaluable" in pronunciation_by_ref.values()
            else "invalid",
            "recall": "1>2>3" if recalls == ((1, 2), (2, 3)) else "invalid",
            "profiles": "15/30/60"
            if module["profiles"] == ["P-ABS", "P-FAUX", "P-INT"]
            and budget_shape
            == {(day, minutes) for day in (1, 2, 3) for minutes in (15, 30, 60)}
            else "invalid",
            "credit_scope": "support_zero"
            if not set(bindings["support_refs"]) & set(bindings["credit_eligible_refs"])
            else "invalid",
            "human_gates": "pending_human"
            if module["linguistic_review"]
            == module["pedagogical_review"]
            == metadata["linguistic_review"]
            == metadata["pedagogical_review"]
            == "pending_human"
            else "invalid",
            "grammar_target": grammar_by_ref.get(target_ref, "missing"),
            "morphology_form": morphology_by_ref.get(target_ref, "missing"),
            "pronunciation_target": pronunciation_by_ref.get(target_ref, "missing"),
            "dialogue": dialogue_by_ref.get(target_ref, "missing"),
        }.get(kind, "unknown")
        if actual != oracle["expected"]:
            raise _error(f"fixture_oracle_expected_mismatch:{oracle_id}")
        if actual in {"invalid", "missing", "unknown", "uncovered", "unordered"}:
            raise _error(f"fixture_oracle_failed:{oracle_id}")
        executed.append(oracle_id)
    if len(declared) != len(set(declared)):
        raise _error("fixture_duplicate_oracle")
    return tuple(declared), tuple(executed)


def load_italian_curriculum_fixture(root: Path) -> ItalianCurriculumFixtureReport:
    safe = _safe_root(root)
    metadata, payloads = _validate_manifest(safe)
    _validate_normative_catalog(payloads)
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
            "mission",
            "budget_plans",
            "linguistic_review",
            "pedagogical_review",
        ),
        "module",
    )
    if not module["rights"]:
        raise _error("module_rights_missing")
    if not module["provenance"]:
        raise _error("module_provenance_missing")
    if (
        module["rights"] != metadata["rights"]
        or [module["provenance"]] != metadata["provenance"]
        or module["linguistic_review"] != metadata["linguistic_review"]
        or module["pedagogical_review"] != metadata["pedagogical_review"]
    ):
        raise _error("module_human_review_required")
    days, recalls = _validate_days(payloads["days.json"])
    bindings = payloads["bindings.json"]
    surfaces, not_evaluable, sense_refs = _validate_bindings(bindings)
    gym_operations, exercise_count, pinned_count, exercise_ids = _validate_exercises(
        payloads["exercises.json"]
    )
    dialogues = payloads["dialogues.json"]
    _expect_keys(dialogues, ("schema_version", "dialogues"), "dialogues")
    if {item["dialogue_id"] for item in days} != {
        item["id"] for item in cast(list[dict[str, Any]], dialogues["dialogues"])
    }:
        raise _error("module_target_uncovered")
    grammar_refs = {
        str(item["ref"]) for item in cast(list[dict[str, Any]], bindings["grammar"])
    }
    allowed_lexicon_refs = sense_refs | frozenset(
        cast(list[str], bindings["support_refs"])
    )
    for dialogue in cast(list[dict[str, Any]], dialogues["dialogues"]):
        _expect_keys(
            dialogue,
            ("id", "day", "lines", "grammar_refs", "lexicon_refs"),
            "dialogue",
        )
        if (
            not dialogue["lines"]
            or not set(dialogue["grammar_refs"]).issubset(grammar_refs)
            or not set(dialogue["lexicon_refs"]).issubset(allowed_lexicon_refs)
        ):
            raise _error("module_target_unresolved")
    production_data = _production_validation_input(
        module, days, bindings, payloads["exercises.json"]
    )
    _run_production_validation(production_data)
    revision_cases = payloads["revision-cases.json"]
    _validate_revision_cases(revision_cases, production_data)
    declared, executed = _execute_oracles(
        payloads["oracles.json"],
        days=days,
        bindings=bindings,
        recalls=recalls,
        metadata=metadata,
        module=module,
        dialogues=dialogues,
    )
    if module["profiles"] != ["P-ABS", "P-FAUX", "P-INT"]:
        raise _error("module_load_budget_exceeded")
    mission = cast(dict[str, Any], module["mission"])
    _expect_keys(
        mission,
        ("mission_revision_id", "primitive", "correction_strategy", "criteria"),
        "mission",
    )
    if (
        UUID(str(mission["mission_revision_id"])).version != 7
        or mission["primitive"] != "EX-PROD-03"
        or mission["correction_strategy"] != "rubric"
    ):
        raise _error("module_final_mission_uncovered")
    budget_plans = cast(list[dict[str, Any]], module["budget_plans"])
    budget_keys: list[str] = []
    for plan in budget_plans:
        _expect_keys(
            plan,
            ("key", "day", "budget_minutes", "planned_seconds", "exercise_ids"),
            "budget_plan",
        )
        if (
            int(plan["planned_seconds"]) > int(plan["budget_minutes"]) * 60
            or not set(cast(list[str], plan["exercise_ids"])).issubset(exercise_ids)
        ):
            raise _error("module_load_budget_exceeded")
        budget_keys.append(str(plan["key"]))
    lexicon_sets = cast(list[dict[str, Any]], bindings["lexicon_sets"])
    return ItalianCurriculumFixtureReport(
        tuple(str(item["code"]) for item in days),
        tuple(cast(list[str], module["profiles"])),
        tuple(sorted(str(item["family"]) for item in bindings["grammar"])),
        gym_operations,
        surfaces,
        recalls,
        declared,
        executed,
        _validate_invalid_cases(safe, production_data),
        frozenset(cast(list[str], bindings["credit_eligible_refs"])),
        frozenset(cast(list[str], bindings["support_refs"])),
        not_evaluable,
        tuple(cast(list[str], metadata["network_dependencies"])),
        str(metadata["linguistic_review"]),
        str(metadata["pedagogical_review"]),
        fixture_fingerprint_from_file_order(safe, PAYLOAD_NAMES),
        tuple(
            (str(item["set_code"]), len(cast(list[object], item["senses"])))
            for item in lexicon_sets
        ),
        sum(len(cast(list[object], item["senses"])) for item in lexicon_sets),
        exercise_count,
        pinned_count,
        tuple(sorted(cast(list[str], mission["criteria"]))),
        tuple(budget_keys),
    )
