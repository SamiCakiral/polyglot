"""Offline loader for the W03 diagnostic and foundation golden bundles."""

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import cast

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class W03Fixture:
    fixture_id: str
    scenario_ids: tuple[str, ...]
    oracles: dict[str, dict[str, JsonValue]]
    network_dependencies: tuple[str, ...]


def _invalid(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


def _object(path: Path) -> dict[str, JsonValue]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise _invalid(f"invalid W03 fixture file: {path.name}") from error
    if not isinstance(value, dict):
        raise _invalid(f"W03 fixture file must be an object: {path.name}")
    return cast(dict[str, JsonValue], value)


def load_w03_fixture(root: Path) -> W03Fixture:
    manifest = _object(root / "manifest.json")
    metadata = _object(root / "fixture-metadata.json")
    fixture_id = manifest.get("id")
    if (
        not isinstance(fixture_id, str)
        or manifest.get("kind") != "positive"
        or manifest.get("expected_status") != "accepted"
    ):
        raise _invalid("W03 fixture manifest is not accepted")
    payloads = metadata.get("payloads")
    dependencies = metadata.get("network_dependencies")
    if not isinstance(payloads, dict) or len(payloads) != 1 or dependencies != []:
        raise _invalid("W03 fixtures require one offline payload")
    payload_name, expected_hash = next(iter(payloads.items()))
    if not isinstance(payload_name, str) or Path(payload_name).name != payload_name:
        raise _invalid("W03 fixture payload path is invalid")
    payload_path = root / payload_name
    try:
        actual_hash = f"sha256:{sha256(payload_path.read_bytes()).hexdigest()}"
    except OSError as error:
        raise _invalid("W03 fixture payload is missing") from error
    if expected_hash != actual_hash:
        raise _invalid("W03 fixture payload checksum mismatch")
    payload = _object(payload_path)
    scenarios = payload.get("scenarios")
    if payload.get("schema_version") != 1 or not isinstance(scenarios, list):
        raise _invalid("W03 fixture payload schema is invalid")
    oracles: dict[str, dict[str, JsonValue]] = {}
    for raw_scenario in scenarios:
        if not isinstance(raw_scenario, dict):
            raise _invalid("W03 fixture scenario is invalid")
        scenario_id = raw_scenario.get("id")
        oracle = raw_scenario.get("oracle")
        if not isinstance(scenario_id, str) or not isinstance(oracle, dict):
            raise _invalid("W03 fixture oracle is invalid")
        if scenario_id in oracles:
            raise _invalid("W03 fixture scenario ids must be unique")
        oracles[scenario_id] = oracle
    required = {
        "FX-PERSONAS": ("P-ABS", "P-FAUX", "P-INT", "P-RETOUR"),
        "FX-IT-FOUND": ("F1-F5", "audio-absent", "gate-24h", "revelation"),
    }.get(fixture_id)
    if required is None or set(oracles) != set(required):
        raise _invalid("W03 fixture scenario set is incomplete")
    return W03Fixture(
        fixture_id=fixture_id,
        scenario_ids=required,
        oracles=oracles,
        network_dependencies=(),
    )
