import json
import socket
from pathlib import Path

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
MANIFEST_SCHEMA = json.loads(
    (ROOT / "contracts/fixtures/manifest.schema.json").read_text()
)
REGISTERED_ERRORS = set(
    json.loads((ROOT / "contracts/registry/errors.yaml").read_text())["errors"]
)


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
