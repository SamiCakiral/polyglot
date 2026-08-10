from __future__ import annotations

import shutil
import socket
from pathlib import Path

import pytest

from polyglot.modules.curriculum import CurriculumError
from polyglot.modules.curriculum.fixtures import load_italian_curriculum_fixture

FIXTURE = Path(__file__).parents[4] / "fixtures" / "canonical" / "FX-MODULE-IT"


def test_fx_module_it_executes_every_declared_oracle_offline() -> None:
    report = load_italian_curriculum_fixture(FIXTURE)

    assert report.day_codes == ("IT-PILOT-D1", "IT-PILOT-D2", "IT-PILOT-D3")
    assert report.profile_codes == ("P-ABS", "P-FAUX", "P-INT")
    assert report.executed_oracle_ids == report.declared_oracle_ids
    assert report.invalid_case_codes == (
        "module_duration_out_of_range",
        "module_human_review_required",
        "module_load_budget_exceeded",
        "module_past_day_mutated",
        "module_prerequisite_cycle",
        "module_support_lexicon_miscredited",
        "module_target_unresolved",
    )
    assert report.network_dependencies == ()
    assert report.linguistic_review == "pending_human"
    assert report.pedagogical_review == "pending_human"
    assert report.credit_eligible_refs.isdisjoint(report.support_refs)


def test_fx_module_it_replay_is_byte_stable() -> None:
    fingerprints = {load_italian_curriculum_fixture(FIXTURE).fingerprint for _ in range(100)}
    assert len(fingerprints) == 1


def test_fx_module_it_rejects_payload_tampering(tmp_path: Path) -> None:
    target = tmp_path / "FX-MODULE-IT"
    shutil.copytree(FIXTURE, target)
    (target / "days.json").write_text('{"tampered":true}', encoding="utf-8")

    with pytest.raises(CurriculumError, match="fixture_checksum_mismatch"):
        load_italian_curriculum_fixture(target)


def test_fx_module_it_never_opens_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    assert load_italian_curriculum_fixture(FIXTURE).network_dependencies == ()
