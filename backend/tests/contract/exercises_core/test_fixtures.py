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


def _seeded_order(primitive_ids: list[str], seed: int) -> list[str]:
    return sorted(
        primitive_ids,
        key=lambda primitive_id: hashlib.sha256(
            f"{seed}:{primitive_id}".encode()
        ).digest(),
    )


def _rewrite_checksum(root: Path) -> None:
    payload_path = root / "primitives.json"
    metadata_path = root / "fixture-metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["payloads"]["primitives.json"] = (
        "sha256:" + hashlib.sha256(payload_path.read_bytes()).hexdigest()
    )
    metadata_path.write_text(json.dumps(metadata, sort_keys=True))


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
    _rewrite_checksum(mutated)

    with pytest.raises(DomainError) as rejected:
        load_and_run_primitive_fixture(mutated)

    assert rejected.value.code is ErrorCode.VALIDATION_FAILED


def test_fx_seed_reaches_every_instance_and_controls_replay(tmp_path: Path) -> None:
    from polyglot.modules.exercises.core.fixtures import load_and_run_primitive_fixture

    baseline = load_and_run_primitive_fixture(FIXTURE)
    repeated = load_and_run_primitive_fixture(FIXTURE)
    assert baseline.instance_seeds == (9009,) * 22
    assert repeated.replay_order == baseline.replay_order

    mutated = tmp_path / "FX-PRIMITIVES"
    shutil.copytree(FIXTURE, mutated)
    payload_path = mutated / "primitives.json"
    payload = json.loads(payload_path.read_text())
    changed_seed = 123456
    primitive_ids = [item["primitive_id"] for item in payload["primitives"]]
    payload["seed"] = changed_seed
    payload["expected_replay_order"] = _seeded_order(primitive_ids, changed_seed)
    payload_path.write_text(json.dumps(payload, sort_keys=True))
    metadata_path = mutated / "fixture-metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["seed"] = changed_seed
    metadata_path.write_text(json.dumps(metadata, sort_keys=True))
    _rewrite_checksum(mutated)

    changed = load_and_run_primitive_fixture(mutated)

    assert changed.instance_seeds == (changed_seed,) * 22
    assert changed.replay_order == tuple(_seeded_order(primitive_ids, changed_seed))
    assert changed.replay_order != baseline.replay_order


def test_fx_executes_a_distinct_sample_typed_oracle_for_every_primitive(
    tmp_path: Path,
) -> None:
    from polyglot.modules.exercises.core.fixtures import load_and_run_primitive_fixture

    report = load_and_run_primitive_fixture(FIXTURE)

    assert len(report.primitive_oracles) == 22
    assert len({evidence.oracle_id for evidence in report.primitive_oracles}) == 22
    assert all(evidence.sample_used for evidence in report.primitive_oracles)
    assert all(
        evidence.verdicts[0] == "correct"
        and evidence.verdicts[1] in {"incorrect", "partially_correct"}
        and evidence.verdicts[2:] == ("ambiguous", "not_evaluable")
        for evidence in report.primitive_oracles
    )
    assert all(
        evidence.declared_strategies == evidence.executed_strategies
        for evidence in report.primitive_oracles
    )
    strategies = {
        strategy
        for evidence in report.primitive_oracles
        for strategy in evidence.executed_strategies
    }
    assert {
        "accepted_set",
        "exact_normalized",
        "morphological",
        "structural_constraints",
        "bounded_translation",
        "rubric",
        "self_assessment",
        "before_after",
    }.issubset(strategies)
    assert all(
        evidence.ambiguous_policy == f"{evidence.primitive_id}:ambiguous"
        and evidence.not_evaluable_policy == f"{evidence.primitive_id}:not_evaluable"
        for evidence in report.primitive_oracles
    )

    evidence_by_id = {
        evidence.primitive_id: evidence for evidence in report.primitive_oracles
    }
    assert evidence_by_id["EX-RECALL-02"].executed_strategies == ("morphological",)
    assert evidence_by_id["EX-RECALL-06"].executed_strategies == ("morphological",)
    assert evidence_by_id["EX-PROD-01"].executed_strategies == (
        "structural_constraints",
        "rubric",
    )
    assert evidence_by_id["EX-PROD-02"].executed_strategies == ("rubric",)
    assert evidence_by_id["EX-PROD-03"].executed_strategies == ("rubric",)
    assert evidence_by_id["EX-ORAL-01"].executed_strategies == ("self_assessment",)
    assert evidence_by_id["EX-REPAIR-01"].executed_strategies == ("before_after",)

    mutated = tmp_path / "FX-PRIMITIVES"
    shutil.copytree(FIXTURE, mutated)
    payload_path = mutated / "primitives.json"
    payload = json.loads(payload_path.read_text())
    payload["primitives"][0]["correction_oracle"]["positive_verdict"] = "incorrect"
    payload_path.write_text(json.dumps(payload, sort_keys=True))
    _rewrite_checksum(mutated)

    with pytest.raises(DomainError) as rejected:
        load_and_run_primitive_fixture(mutated)

    assert rejected.value.code is ErrorCode.VALIDATION_FAILED
