from __future__ import annotations

from dataclasses import replace

from polyglot.modules.curriculum.ports import ReferenceManifest
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


def test_resolver_and_legacy_expectation_cannot_be_forged_together() -> None:
    data = base_input()
    resolved = replace(
        data.resolved_references[0],
        kind="wrong-kind",
        pack_revision_id="wrong-pack",
        variety_id="wrong-variety",
        checksum=f"sha256:{'f' * 64}",
    )
    legacy = replace(
        data.reference_expectations[0],
        kind=resolved.kind,
        pack_revision_id=resolved.pack_revision_id,
        variety_id=resolved.variety_id,
        checksum=resolved.checksum,
    )

    report = validate_curriculum(
        replace(
            data,
            resolved_references=(resolved, *data.resolved_references[1:]),
            reference_expectations=(legacy, *data.reference_expectations[1:]),
        )
    )

    assert "module_reference_manifest_mismatch" in {
        item.message_code for item in report.findings
    }


def test_reference_manifest_is_bound_to_the_module_revision_checksum() -> None:
    data = base_input()
    entries = list(data.reference_manifest.entries)
    entries[0] = replace(entries[0], checksum=f"sha256:{'f' * 64}")
    hostile_manifest = ReferenceManifest(
        source_catalog_id=data.reference_manifest.source_catalog_id,
        entries=tuple(entries),
    )

    report = validate_curriculum(replace(data, reference_manifest=hostile_manifest))

    assert "module_reference_manifest_mismatch" in {
        item.message_code for item in report.findings
    }
