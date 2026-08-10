import json
import socket
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from polyglot.platform.errors import DomainError, ErrorCode

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures/canonical/FX-CONTENT"
MANIFEST_SCHEMA = json.loads((ROOT / "contracts/fixtures/manifest.schema.json").read_text())


def test_fx_content_manifests_are_canonical_and_verify_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from polyglot.modules.content.fixtures import verify_content_fixture_manifest

    manifests = [
        json.loads(path.read_text())
        for path in sorted(FIXTURE.glob("**/manifest.json"))
    ]
    assert len(manifests) == 5
    validator = Draft202012Validator(MANIFEST_SCHEMA)
    for manifest in manifests:
        validator.validate(manifest)

    def deny_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("FX-CONTENT verification must stay offline")

    monkeypatch.setattr(socket, "socket", deny_network)
    verified = verify_content_fixture_manifest(FIXTURE)
    assert verified.fixture_id == "FX-CONTENT"
    assert verified.payload_names == ("content.json",)
    assert verified.network_dependencies == ()
    assert verified.linguistic_review == "pending_human"


def test_fx_content_positive_fixture_covers_editorial_and_failure_oracles() -> None:
    from polyglot.modules.content.fixtures import load_content_fixture

    fixture = load_content_fixture(FIXTURE)

    assert fixture.synthetic is True
    assert fixture.linguistic_review == "pending_human"
    assert {revision.status for revision in fixture.revisions} >= {
        "draft",
        "validated",
        "approved",
        "published",
        "retired",
        "superseded",
        "rejected",
    }
    assert {case.expected_error for case in fixture.negative_oracles} >= {
        "self_approval_forbidden",
        "version_conflict",
        "idempotency_conflict",
        "reference_not_publishable",
        "historical_rights_conflict",
    }
    assert {case.validation_status for case in fixture.validation_oracles} == {
        "passed",
        "failed",
        "human_required",
    }
    assert all(item.source_ref.startswith("FX-CONTENT") for item in fixture.provenance)


@pytest.mark.parametrize(
    ("folder", "error_code"),
    (
        ("invalid-checksum", ErrorCode.VALIDATION_FAILED),
        ("invalid-provenance", ErrorCode.REFERENCE_NOT_FOUND),
        ("invalid-rights", ErrorCode.LICENSE_MISSING),
        ("corrupt-manifest", ErrorCode.VALIDATION_FAILED),
    ),
)
def test_fx_content_negative_fixtures_are_rejected(
    folder: str,
    error_code: ErrorCode,
) -> None:
    from polyglot.modules.content.fixtures import load_content_fixture

    with pytest.raises(DomainError) as rejected:
        load_content_fixture(FIXTURE / folder)

    assert rejected.value.code is error_code
