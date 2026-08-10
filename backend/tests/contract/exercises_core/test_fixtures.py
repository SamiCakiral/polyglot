import hashlib
import json
import shutil
import socket
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from polyglot.platform.errors import DomainError, ErrorCode

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures/canonical/FX-PRIMITIVES"
MANIFEST_SCHEMA = json.loads((ROOT / "contracts/fixtures/manifest.schema.json").read_text())


def test_fx_primitives_executes_every_oracle_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from polyglot.modules.exercises.core.fixtures import load_and_run_primitive_fixture

    Draft202012Validator(MANIFEST_SCHEMA).validate(
        json.loads((FIXTURE / "manifest.json").read_text())
    )

    def deny_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("FX-PRIMITIVES must stay offline")

    monkeypatch.setattr(socket, "socket", deny_network)
    report = load_and_run_primitive_fixture(FIXTURE)

    assert len(report.primitive_ids) == 22
    assert report.case_counts == (
        ("abandon", 22),
        ("ambiguous", 22),
        ("h0", 22),
        ("h1", 22),
        ("h2", 22),
        ("h3", 22),
        ("h4", 22),
        ("negative", 22),
        ("not_evaluable", 22),
        ("positive", 22),
        ("replay", 22),
        ("skip", 22),
        ("unavailable", 22),
    )
    assert report.a11y_certified == report.primitive_ids
    assert report.replay_without_duplicates == report.primitive_ids
    assert report.network_dependencies == ()
    assert report.replay_order == report.expected_replay_order


def test_fx_primitives_rejects_a_missing_per_primitive_oracle(tmp_path: Path) -> None:
    from polyglot.modules.exercises.core.fixtures import load_and_run_primitive_fixture

    mutated = tmp_path / "FX-PRIMITIVES"
    shutil.copytree(FIXTURE, mutated)
    payload_path = mutated / "primitives.json"
    payload = json.loads(payload_path.read_text())
    payload["primitives"][0]["case_ids"].remove("unavailable")
    payload_path.write_text(json.dumps(payload, sort_keys=True))
    metadata_path = mutated / "fixture-metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["payloads"]["primitives.json"] = (
        "sha256:" + hashlib.sha256(payload_path.read_bytes()).hexdigest()
    )
    metadata_path.write_text(json.dumps(metadata, sort_keys=True))

    with pytest.raises(DomainError) as rejected:
        load_and_run_primitive_fixture(mutated)

    assert rejected.value.code is ErrorCode.VALIDATION_FAILED
