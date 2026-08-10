import json
import socket
from hashlib import sha256
from pathlib import Path
from shutil import copytree

import pytest
from jsonschema import Draft202012Validator

from polyglot.modules.catalogue.core.domain import (
    ContentRevisionStatus,
    LexicalUnitType,
)
from polyglot.modules.catalogue.core.fixtures import (
    load_catalogue_fixture,
    verify_fixture_manifest,
)
from polyglot.platform.errors import DomainError, ErrorCode

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures/canonical/FX-CATALOGUE-IT"
MANIFEST_SCHEMA = json.loads((ROOT / "contracts/fixtures/manifest.schema.json").read_text())
REGISTERED_ERRORS = set(json.loads((ROOT / "contracts/registry/errors.yaml").read_text())["errors"])


def test_manifests_use_the_real_w00_schema_and_verify_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests = (
        json.loads((FIXTURE / "manifest.json").read_text()),
        json.loads((FIXTURE / "invalid-cycle/manifest.json").read_text()),
    )
    validator = Draft202012Validator(MANIFEST_SCHEMA)
    for manifest in manifests:
        validator.validate(manifest)

    assert manifests == (
        {
            "id": "FX-CATALOGUE-IT",
            "kind": "positive",
            "expected_status": "accepted",
        },
        {
            "id": "FX-CATALOGUE-IT-CYCLE",
            "kind": "negative",
            "expected_status": "rejected",
            "expected_error": "prerequisite_cycle",
        },
    )
    assert manifests[1]["expected_error"] in REGISTERED_ERRORS

    def deny_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("fixture verification must not use the network")

    monkeypatch.setattr(socket, "socket", deny_network)
    verification = verify_fixture_manifest(FIXTURE)
    assert verification.fixture_id == "FX-CATALOGUE-IT"
    assert verification.payload_names == ("catalogue.json",)
    assert verification.network_dependencies == ()
    assert verification.linguistic_review == "pending_human"


def test_italian_pilot_fixture_loads_revisioned_catalogue_domain() -> None:
    fixture = load_catalogue_fixture(FIXTURE)

    assert fixture.pack_code == "it-IT__fr-FR"
    assert fixture.pack_revision_code == "pilot-1.0.0"
    assert fixture.target_language_tag == "it-IT"
    assert fixture.support_language_tags == ("fr-FR",)
    assert fixture.pack_revision.status is ContentRevisionStatus.PUBLISHED
    assert fixture.pilot_days == (1, 2, 3)
    assert hasattr(fixture, "foundations"), "W04F foundation fixture contract is missing"
    assert [block.block_code for block in fixture.foundations.definition.blocks] == [
        "F1",
        "F2",
        "F3",
        "F4",
        "F5",
    ]
    assert fixture.foundations.definition.gate.gate_code == "FOUNDATIONS_IT_V0"
    assert fixture.foundations.definition.gate.oral_policy == "not_evaluable_non_blocking"

    assert {item.function_code for item in fixture.communicative_functions} >= {
        "IT-PRAG-001",
        "IT-ID-001",
        "IT-POLITE-002",
        "IT-REPAIR-001",
    }
    structures = {item.structure_code: item for item in fixture.grammar_structures}
    assert set(structures) == {
        "IT-GRAM-002",
        "IT-GRAM-004",
        "IT-GRAM-027",
        "IT-GRAM-028",
    }
    assert all(item.status is ContentRevisionStatus.PUBLISHED for item in structures.values())
    assert {pattern.template for item in structures.values() for pattern in item.patterns} >= {
        "vorrei + nom/infinitif",
        "può + infinitif?",
        "c'è/ci sono + nom",
        "è + nom/adjectif?",
    }


def test_fixture_preserves_surface_analyses_senses_and_multiword_components() -> None:
    fixture = load_catalogue_fixture(FIXTURE)

    assert fixture.search_forms("sono")[0].lemma == "essere"
    assert fixture.search_forms("puo")[0].surface == "puo"
    assert fixture.search_forms("può")[0].surface == "può"
    assert fixture.search_forms("puo") != fixture.search_forms("può")
    assert fixture.search_forms("puo")[0].features == (("orthography", "missing_accent"),)
    assert fixture.search_forms("può")[0].features == (
        ("mood", "indicative"),
        ("number", "singular"),
        ("person", "3"),
        ("tense", "present"),
    )

    piano = fixture.lexical_unit("piano")
    assert {sense.sense_code for sense in piano.senses} == {
        "IT-SENSE-PIANO-ADV-SLOWLY",
        "IT-SENSE-PIANO-N-FLOOR",
    }
    expression = fixture.lexical_unit("per favore")
    assert expression.unit_type is LexicalUnitType.MULTIWORD_EXPRESSION
    assert expression.components == ("per", "favore")


def test_positive_graph_is_bounded_and_negative_cycle_uses_canonical_error() -> None:
    fixture = load_catalogue_fixture(FIXTURE)
    polite = fixture.skill_revision_id("IT-POLITE-002")
    first = fixture.skill_graph.prerequisites_for(polite, max_depth=8, max_nodes=32)
    second = fixture.skill_graph.prerequisites_for(polite, max_depth=8, max_nodes=32)
    assert first == second
    assert first.truncated is False
    assert len(first.skill_revision_ids) <= 32

    negative = FIXTURE / "invalid-cycle"
    with pytest.raises(DomainError) as rejected:
        load_catalogue_fixture(negative)
    assert rejected.value.code is ErrorCode.PREREQUISITE_CYCLE


def _fixture_with_payload(tmp_path: Path, mutate: object) -> Path:
    root = tmp_path / "fixture"
    copytree(FIXTURE, root)
    payload_path = root / "catalogue.json"
    payload = json.loads(payload_path.read_text())
    mutate(payload)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    payload_path.write_text(serialized)
    metadata_path = root / "fixture-metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["payloads"]["catalogue.json"] = f"sha256:{sha256(serialized.encode()).hexdigest()}"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    return root


@pytest.mark.parametrize(
    "mutate",
    (
        lambda payload: payload["skills"][0].update({"target_ref": "IT-MISSING-999"}),
        lambda payload: payload["lexical_units"][0]["senses"][0].update({"status": "draft"}),
        lambda payload: payload["lexical_units"][-1]["components"][0].update(
            {"unit_revision_id": "019b0000-0000-7000-8000-000000009999"}
        ),
        lambda payload: payload["skills"][0].update({"skill_id": payload["skills"][1]["skill_id"]}),
    ),
)
def test_fixture_rejects_unresolved_refs_unpublished_nested_content_and_duplicate_ids(
    tmp_path: Path,
    mutate: object,
) -> None:
    fixture = _fixture_with_payload(tmp_path, mutate)
    with pytest.raises(DomainError) as rejected:
        load_catalogue_fixture(fixture)
    assert rejected.value.code in {ErrorCode.REFERENCE_NOT_FOUND, ErrorCode.VALIDATION_FAILED}


@pytest.mark.parametrize(
    "mutate",
    (
        lambda payload: payload["foundations"].update(
            {"blocks": payload["foundations"]["blocks"][:-1]}
        ),
        lambda payload: payload["foundations"]["blocks"][0]["items"][0].update(
            {"checker_values": []}
        ),
        lambda payload: payload["foundations"]["gate"].update(
            {"blocking_target_refs": ["IT-MISSING-999"]}
        ),
        lambda payload: payload["foundations"]["blocks"][1].update({"ordinal": 1}),
        lambda payload: payload["foundations"]["gate"].update({"grapheme_sound_minimum": 11}),
    ),
)
def test_fixture_rejects_incoherent_foundation_definitions(
    tmp_path: Path,
    mutate: object,
) -> None:
    fixture = _fixture_with_payload(tmp_path, mutate)
    with pytest.raises(DomainError) as rejected:
        load_catalogue_fixture(fixture)
    assert rejected.value.code in {ErrorCode.REFERENCE_NOT_FOUND, ErrorCode.VALIDATION_FAILED}
