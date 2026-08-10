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
    assert {case.case for case in fixture.negative_oracles} >= {
        "identical_key_identical_payload",
        "concurrent_same_if_match",
        "failure_after_event",
        "service_editorial_command",
        "actor_outside_pack",
        "blocking_finding_in_passed_report",
        "late_manifest_entry",
        "rejected_revision_publish",
        "rejected_revision_replay",
        "rejected_revision_revise_in_place",
    }
    assert {case.validation_status for case in fixture.validation_oracles} == {
        "passed",
        "failed",
        "human_required",
    }
    assert sum("author" in actor.roles for actor in fixture.actors) == 3
    assert sum("reviewer" in actor.roles for actor in fixture.actors) == 2
    assert any(set(actor.roles) == {"author", "reviewer"} for actor in fixture.actors)
    assert {case.case for case in fixture.linguistic_oracles} == {
        "pronunciation_reduced_to_vocabulary",
        "subject_pronoun_always_before_verb",
        "essere_stare_confusion",
        "correction_outage_counted_correct",
        "artificial_grazie_prego_same_speaker",
        "andare_infinitive_as_general_near_future",
    }
    assert all(
        case.expected_outcome == "human_required"
        for case in fixture.linguistic_oracles
    )
    assert len(fixture.historical_references) == 1
    historical = fixture.historical_references[0]
    assert historical.content_revision_id in {
        revision.content_revision_id
        for revision in fixture.revisions
        if revision.status in {"published", "superseded", "retired"}
    }
    assert {decision.decision for decision in fixture.review_decisions} == {
        "approved",
        "rejected",
    }
    assert all(decision.author_id != decision.reviewer_id for decision in fixture.review_decisions)
    assert all(item.source_ref.startswith("FX-CONTENT") for item in fixture.provenance)

    metadata = json.loads((FIXTURE / "fixture-metadata.json").read_text())
    assert {
        "idempotent_replay_single_effect",
        "concurrent_if_match_conflict",
        "injected_failure_rolls_back",
        "service_actor_forbidden",
        "pack_scope_enforced",
        "sealed_validation_report",
        "sealed_publication_manifest",
        "rejection_event_outbox_idempotent_new_revision",
    } <= set(metadata["oracles"])


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
