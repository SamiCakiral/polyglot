from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from polyglot.modules.curriculum import CurriculumError
from polyglot.modules.curriculum.fixtures import load_italian_curriculum_fixture

FIXTURE = Path(__file__).parents[4] / "fixtures" / "canonical" / "FX-MODULE-IT"
Mutation = Callable[[dict[str, object]], None]


def rewrite_payload(root: Path, name: str, mutate: Mutation) -> None:
    path = root / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
    path.write_bytes(data)
    metadata_path = root / "fixture-metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["payloads"][name] = f"sha256:{hashlib.sha256(data).hexdigest()}"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def corrupt_exercise(payload: dict[str, object]) -> None:
    payload["exercises"][0]["targets"] = ["skill:does-not-exist"]  # type: ignore[index]


def corrupt_morphology(payload: dict[str, object]) -> None:
    payload["morphology"][0]["features"] = {"banana": "yes"}  # type: ignore[index]


def corrupt_pronunciation(payload: dict[str, object]) -> None:
    item = payload["pronunciation"][0]  # type: ignore[index]
    transcript = "contenu sans rapport"
    checksum = f"sha256:{hashlib.sha256(transcript.encode()).hexdigest()}"
    item["transcript"] = transcript
    item["transcript_checksum"] = checksum
    item["media_transcript_checksum"] = checksum


def corrupt_lexicon(payload: dict[str, object]) -> None:
    payload["lexicon_sets"][0]["senses"][0]["surface"] = "WRONG"  # type: ignore[index]


def corrupt_dialogue_day(payload: dict[str, object]) -> None:
    payload["dialogues"][0]["day"] = 3  # type: ignore[index]


def corrupt_budget(payload: dict[str, object]) -> None:
    plans = payload["budget_plans"]  # type: ignore[assignment]
    day_three_exercise = next(
        exercise
        for exercise in json.loads((FIXTURE / "exercises.json").read_text())["exercises"]
        if exercise["day"] == 3
    )
    plans[0]["exercise_ids"] = [day_three_exercise["id"]]  # type: ignore[index]


def corrupt_nan(payload: dict[str, object]) -> None:
    day = payload["days"][0]  # type: ignore[index]
    day["novelty_points"] = float("nan")
    day["novelty_budget"] = float("nan")


@pytest.mark.parametrize(
    ("name", "mutate"),
    (
        ("exercises.json", corrupt_exercise),
        ("bindings.json", corrupt_morphology),
        ("bindings.json", corrupt_pronunciation),
        ("bindings.json", corrupt_lexicon),
        ("dialogues.json", corrupt_dialogue_day),
        ("module.json", corrupt_budget),
        ("days.json", corrupt_nan),
    ),
)
def test_normative_bundle_rejects_semantic_corruption(
    tmp_path: Path, name: str, mutate: Mutation
) -> None:
    target = tmp_path / "FX-MODULE-IT"
    shutil.copytree(FIXTURE, target)
    rewrite_payload(target, name, mutate)

    with pytest.raises(CurriculumError):
        load_italian_curriculum_fixture(target)
