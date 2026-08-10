from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from polyglot.modules.curriculum import CurriculumError
from polyglot.modules.curriculum.fixtures import load_italian_curriculum_fixture

FIXTURE = Path(__file__).parents[4] / "fixtures" / "canonical" / "FX-MODULE-IT"


def rewrite_payload(root: Path, name: str, payload: dict[str, object]) -> None:
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
    (root / name).write_bytes(data)
    metadata_path = root / "fixture-metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["payloads"][name] = f"sha256:{hashlib.sha256(data).hexdigest()}"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def fixture_copy(tmp_path: Path) -> Path:
    target = tmp_path / "FX-MODULE-IT"
    shutil.copytree(FIXTURE, target)
    return target


def test_declared_oracle_expected_value_is_falsifiable(tmp_path: Path) -> None:
    target = fixture_copy(tmp_path)
    payload = json.loads((target / "oracles.json").read_text(encoding="utf-8"))
    payload["oracles"][0]["expected"] = "deliberately-wrong"
    rewrite_payload(target, "oracles.json", payload)

    with pytest.raises(CurriculumError, match="fixture_oracle_expected_mismatch"):
        load_italian_curriculum_fixture(target)


def test_dialogue_lines_and_references_are_executed_not_counted(tmp_path: Path) -> None:
    target = fixture_copy(tmp_path)
    payload = json.loads((target / "dialogues.json").read_text(encoding="utf-8"))
    payload["dialogues"][0]["lines"] = ["contenu sans rapport"]
    payload["dialogues"][0]["grammar_refs"] = ["grammar:missing"]
    payload["dialogues"][0]["lexicon_refs"] = ["sense:missing"]
    rewrite_payload(target, "dialogues.json", payload)

    with pytest.raises(CurriculumError, match="module_target_unresolved"):
        load_italian_curriculum_fixture(target)


def test_module_rights_provenance_and_review_gates_cannot_be_overridden(tmp_path: Path) -> None:
    target = fixture_copy(tmp_path)
    payload = json.loads((target / "module.json").read_text(encoding="utf-8"))
    payload["rights"] = []
    payload["provenance"] = ""
    payload["linguistic_review"] = "approved"
    payload["pedagogical_review"] = "approved"
    rewrite_payload(target, "module.json", payload)

    with pytest.raises(
        CurriculumError,
        match=r"module_rights_missing|module_provenance_missing|module_human_review_required",
    ):
        load_italian_curriculum_fixture(target)
