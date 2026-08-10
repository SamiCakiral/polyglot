from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from polyglot.modules.curriculum.fixtures import (
    PAYLOAD_NAMES,
    fixture_fingerprint_from_file_order,
)

FIXTURE = Path(__file__).parents[4] / "fixtures" / "canonical" / "FX-MODULE-IT"


def _rewrite_json(path: Path, mutate: Callable[[dict[str, object]], None]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("relative_path", "mutate"),
    (
        ("manifest.json", lambda value: value.update(expected_status="approved")),
        ("fixture-metadata.json", lambda value: value.update(seed=9999)),
        (
            "invalid/load/case.json",
            lambda value: value.update(expected="deliberately-wrong"),
        ),
    ),
)
def test_bundle_fingerprint_covers_every_normative_file(
    tmp_path: Path,
    relative_path: str,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    target = tmp_path / "FX-MODULE-IT"
    shutil.copytree(FIXTURE, target)
    baseline = fixture_fingerprint_from_file_order(target, PAYLOAD_NAMES)

    _rewrite_json(target / relative_path, mutate)

    assert fixture_fingerprint_from_file_order(target, PAYLOAD_NAMES) != baseline
