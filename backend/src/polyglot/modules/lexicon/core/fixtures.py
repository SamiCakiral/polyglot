import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

from polyglot.platform.errors import DomainError, ErrorCode


@dataclass(frozen=True, slots=True)
class LexiconFixture:
    has_homonyms: bool
    has_polysemy: bool
    has_syncretism: bool
    has_multiword_expression: bool
    has_private_unit: bool
    has_late_resolution: bool
    network_dependencies: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WordBankFixture:
    empty_profile_count: int
    small_profile_count: int
    synthetic_count: int
    seed: int
    cross_user_oracle: bool
    private_context_deleted: bool
    reference_revision: str
    network_dependencies: tuple[str, ...]


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"{path.name} must be object")
    return cast(dict[str, Any], value)


def _validate(root: Path, payload_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _object(root / "manifest.json")
    schema_path = root.parents[2] / "contracts" / "fixtures" / "manifest.schema.json"
    if not schema_path.exists():
        schema_path = (
            Path(__file__).resolve().parents[6]
            / "contracts/fixtures/manifest.schema.json"
        )
    Draft202012Validator(_object(schema_path)).validate(manifest)
    if manifest != {"id": root.name, "kind": "positive", "expected_status": "accepted"}:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="fixture manifest is not canonical")
    metadata = _object(root / "fixture-metadata.json")
    payload_path = root / payload_name
    expected = metadata["payloads"][payload_name]
    actual = "sha256:" + hashlib.sha256(payload_path.read_bytes()).hexdigest()
    if expected != actual or metadata.get("network_dependencies") != []:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="fixture integrity mismatch")
    return _object(payload_path), metadata


def load_lexicon_fixture(root: Path) -> LexiconFixture:
    payload, metadata = _validate(root, "lexicon.json")
    cases = {item["id"]: item for item in payload["cases"]}
    piano = cases["piano-homonym"]
    return LexiconFixture(
        has_homonyms=len(piano["unit_ids"]) == 2,
        has_polysemy=len(piano["sense_ids"]) == 3,
        has_syncretism=len(cases["sono-syncretism"]["analyses"]) == 2,
        has_multiword_expression=len(cases["avere-bisogno-di"]["components"]) == 3,
        has_private_unit=cases["private-family-word"]["visibility"] == "private",
        has_late_resolution=cases["late-resolution"]["raw_fact_mutated"] is False,
        network_dependencies=tuple(metadata["network_dependencies"]),
    )


def load_word_bank_fixture(root: Path) -> WordBankFixture:
    payload, metadata = _validate(root, "word-bank.json")
    return WordBankFixture(
        empty_profile_count=int(payload["profiles"]["empty"]["sense_count"]),
        small_profile_count=int(payload["profiles"]["small"]["sense_count"]),
        synthetic_count=int(payload["synthetic_generator"]["sense_count"]),
        seed=int(payload["seed"]),
        cross_user_oracle=payload["profiles"]["cross_user"]["can_read_owner"] is False,
        private_context_deleted=payload["private_context"]["deleted"] is True,
        reference_revision=str(payload["synthetic_generator"]["reference_revision"]),
        network_dependencies=tuple(metadata["network_dependencies"]),
    )
