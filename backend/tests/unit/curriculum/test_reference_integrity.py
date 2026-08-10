from __future__ import annotations

from dataclasses import replace

from polyglot.modules.curriculum.validation import validate_curriculum
from tests.unit.curriculum.test_validation import base_input


def test_resolved_reference_must_match_pinned_kind_pack_variety_and_checksum() -> None:
    data = base_input()
    first = data.resolved_references[0]
    hostile = replace(
        first,
        kind="wrong-kind",
        pack_revision_id="wrong-pack",
        variety_id="wrong-variety",
        checksum=f"sha256:{'f' * 64}",
    )
    report = validate_curriculum(
        replace(data, resolved_references=(hostile, *data.resolved_references[1:]))
    )

    assert {
        "module_reference_kind_mismatch",
        "module_reference_pack_mismatch",
        "module_reference_variety_mismatch",
        "module_reference_checksum_mismatch",
    }.issubset({item.message_code for item in report.findings})
