"""Catalogue HTTP contracts."""

from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from polyglot.interfaces.http.app import create_app
from polyglot.modules.catalogue.core.fixtures import load_catalogue_fixture
from polyglot.modules.catalogue.core.persistence import (
    CatalogueTarget,
    LanguagePackSummary,
    LexicalAnalysisSummary,
    LexicalSenseSummary,
    LexiconSearchItem,
    Page,
)

CATALOGUE_FIXTURE_ROOT = Path(__file__).resolve().parents[4] / "fixtures/canonical/FX-CATALOGUE-IT"
JAPANESE_FIXTURE_ROOT = Path(__file__).resolve().parents[4] / "fixtures/canonical/FX-CATALOGUE-JA"


class StubCatalogueReader:
    async def get_language_pack(self, *, pack_revision_id: UUID):
        page = await self.list_language_packs(limit=20, cursor=None)
        return next(
            (item for item in page.items if item.pack_revision_id == pack_revision_id),
            None,
        )

    async def read_foundations(self, *, pack_revision_id: UUID):
        fixture = load_catalogue_fixture(CATALOGUE_FIXTURE_ROOT)
        assert pack_revision_id == fixture.pack_revision.pack_revision_id
        return fixture.foundations

    async def list_language_packs(
        self,
        *,
        limit: int,
        cursor: str | None,
    ) -> Page[LanguagePackSummary]:
        assert limit == 20
        assert cursor is None
        return Page(
            (
                LanguagePackSummary(
                    pack_id=UUID("019fe900-6000-7000-8000-000000000001"),
                    pack_revision_id=UUID("019fe900-6000-7000-8000-000000000002"),
                    pack_code="it-IT__fr-FR",
                    revision_no=1,
                    target_variety_id=UUID("019fe900-6000-7000-8000-000000000003"),
                    target_language_tag="it-IT",
                    target_script_codes=("Latn",),
                    text_direction="ltr",
                    segmentation_policy_revision_id=UUID("019fe900-6000-7000-8000-000000000006"),
                    media_capabilities={"schema_version": 1, "tts": True},
                    capability_manifest={"schema_version": 1, "grammar": True},
                    support_variety_ids=(UUID("019fe900-6000-7000-8000-000000000004"),),
                    support_language_tags=("fr-FR",),
                    foundation_revision_id=UUID("019fe900-6000-7000-8000-000000000005"),
                    channel="stable",
                    compatibility_range=">=2.0.0,<2.1.0",
                ),
            ),
            "next-pack-cursor",
        )

    async def list_targets(
        self,
        *,
        pack_code: str,
        limit: int,
        cursor: str | None,
    ) -> Page[CatalogueTarget]:
        assert (pack_code, limit, cursor) == ("it-IT__fr-FR", 20, None)
        return Page(
            (
                CatalogueTarget(
                    skill_id=UUID("019fe900-6000-7000-8001-000000000001"),
                    skill_revision_id=UUID("019fe900-6000-7000-8001-000000000002"),
                    skill_code="IT-GRAM-004",
                    skill_type="grammar",
                    modality="speaking",
                    operation="produce",
                    target_ref="IT-GRAM-004",
                    required_prerequisite_codes=("IT-GRAM-002",),
                ),
            ),
            None,
        )

    async def search_lexicon(
        self,
        *,
        query: str,
        language_tag: str,
        limit: int,
        cursor: str | None,
    ) -> Page[LexiconSearchItem]:
        assert (query, language_tag, limit, cursor) == ("può", "it-IT", 20, None)
        return Page(
            (
                LexiconSearchItem(
                    surface="può",
                    analysis=LexicalAnalysisSummary(
                        form_analysis_id=UUID("019fe900-6000-7000-8002-000000000001"),
                        unit_revision_id=UUID("019fe900-6000-7000-8002-000000000002"),
                        lemma="potere",
                        unit_type="word",
                        part_of_speech="verb",
                        morphological_features={"accepted_reference": True},
                    ),
                    senses=(
                        LexicalSenseSummary(
                            sense_id=UUID("019fe900-6000-7000-8002-000000000003"),
                            sense_revision_id=UUID("019fe900-6000-7000-8002-000000000004"),
                            sense_code="ability",
                            definition="pouvoir ou permission",
                        ),
                    ),
                ),
            ),
            None,
        )


class JapaneseCatalogueReader(StubCatalogueReader):
    async def read_foundations(self, *, pack_revision_id: UUID):
        fixture = load_catalogue_fixture(JAPANESE_FIXTURE_ROOT)
        assert pack_revision_id == fixture.pack_revision.pack_revision_id
        return fixture.foundations

    async def list_language_packs(
        self,
        *,
        limit: int,
        cursor: str | None,
    ) -> Page[LanguagePackSummary]:
        del limit, cursor
        fixture = load_catalogue_fixture(JAPANESE_FIXTURE_ROOT)
        return Page(
            (
                LanguagePackSummary(
                    pack_id=fixture.pack.pack_id,
                    pack_revision_id=fixture.pack_revision.pack_revision_id,
                    pack_code=fixture.pack.pack_code,
                    revision_no=fixture.pack_revision.revision_no,
                    target_variety_id=fixture.target_variety.variety_id,
                    target_language_tag=fixture.target_variety.language_tag,
                    target_script_codes=fixture.target_variety.script_codes,
                    text_direction=fixture.target_variety.text_direction,
                    segmentation_policy_revision_id=(
                        fixture.target_variety.segmentation_policy_revision_id
                    ),
                    media_capabilities={"schema_version": 1, "tts": True},
                    capability_manifest={"schema_version": 1, "grammar": True},
                    support_variety_ids=tuple(
                        item.variety_id for item in fixture.support_varieties
                    ),
                    support_language_tags=tuple(
                        item.language_tag for item in fixture.support_varieties
                    ),
                    foundation_revision_id=(fixture.foundations.definition.foundation_revision_id),
                    channel="stable",
                    compatibility_range=">=2.0.0,<2.1.0",
                ),
            ),
            None,
        )


def test_canonical_catalogue_reads_are_public_paginated_and_closed() -> None:
    app = create_app(test_mode=True, catalogue_service=StubCatalogueReader())

    with TestClient(app, raise_server_exceptions=False) as client:
        packs = client.get("/api/v1/language-packs")
        targets = client.get(
            "/api/v1/catalogue/targets",
            params={"pack_code": "it-IT__fr-FR"},
        )
        lexicon = client.get(
            "/api/v1/lexicon/search",
            params={"q": "può", "language_tag": "it-IT"},
        )

    assert packs.status_code == 200
    assert packs.json()["next_cursor"] == "next-pack-cursor"
    assert packs.json()["items"][0]["pack_code"] == "it-IT__fr-FR"
    assert packs.json()["items"][0]["target_variety_id"].endswith("0003")
    assert packs.json()["items"][0]["support_variety_ids"][0].endswith("0004")
    assert packs.json()["items"][0]["foundation_revision_id"].endswith("0005")
    assert packs.json()["items"][0]["target_script_codes"] == ["Latn"]
    assert packs.json()["items"][0]["text_direction"] == "ltr"
    assert targets.status_code == 200
    assert targets.json()["items"][0]["required_prerequisite_codes"] == ["IT-GRAM-002"]
    assert lexicon.status_code == 200
    item = lexicon.json()["items"][0]
    assert item["surface"] == "può"
    assert item["analysis"]["lemma"] == "potere"
    assert item["senses"][0]["sense_code"] == "ability"
    assert all("security" not in response.request.headers for response in (packs, targets, lexicon))


def test_catalogue_query_validation_uses_correlated_rfc9457() -> None:
    app = create_app(test_mode=True, catalogue_service=StubCatalogueReader())

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/lexicon/search", params={"language_tag": "it-IT"})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "validation_failed"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert response.json()["correlation_id"] == response.headers["X-Correlation-ID"]


def test_fixed_placement_manifest_is_removed() -> None:
    app = create_app(test_mode=True, catalogue_service=StubCatalogueReader())
    pack_revision_id = "019b0000-0000-7000-8000-000000000009"

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/v1/language-packs/{pack_revision_id}/placement-manifest")

    assert response.status_code == 404


def test_foundation_manifest_exposes_all_teaching_activities() -> None:
    app = create_app(test_mode=True, catalogue_service=StubCatalogueReader())
    pack_revision_id = "019b0000-0000-7000-8000-000000000009"

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/v1/language-packs/{pack_revision_id}/foundation-manifest")

    assert response.status_code == 200
    assert len(response.json()["activities"]) == 32
    assert {item["block_code"] for item in response.json()["activities"]} == {
        "F1",
        "F2",
        "F3",
        "F4",
        "F5",
    }
    assert "checker_values" not in response.text


def test_grammar_toolbox_exposes_functions_and_italian_realizations_separately() -> None:
    app = create_app(test_mode=True, catalogue_service=StubCatalogueReader())
    pack_revision_id = "019fe900-6000-7000-8000-000000000002"

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            f"/api/v1/language-packs/{pack_revision_id}/grammar-functions",
            params={"support_language_tag": "fr-FR"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "it-grammar-1.0.0"
    assert len(payload["families"]) == 18
    assert len(payload["realizations"]) == 30
    assert payload["realizations"][0]["function_code"] == "express_will"
    assert payload["realizations"][0]["realization_code"] == "IT-GRAM-001"


def test_japanese_manifests_and_grammar_are_executable_without_italian_assumptions() -> None:
    reader = JapaneseCatalogueReader()
    fixture = load_catalogue_fixture(JAPANESE_FIXTURE_ROOT)
    app = create_app(test_mode=True, catalogue_service=reader)
    revision = fixture.pack_revision.pack_revision_id

    with TestClient(app, raise_server_exceptions=False) as client:
        foundations = client.get(f"/api/v1/language-packs/{revision}/foundation-manifest")
        grammar = client.get(
            f"/api/v1/language-packs/{revision}/grammar-functions",
            params={"support_language_tag": "fr-FR"},
        )

    assert foundations.status_code == 200
    assert len(foundations.json()["activities"]) == 30
    assert "hiragana" in foundations.text.lower()
    assert grammar.status_code == 200
    assert grammar.json()["target_language_tag"] == "ja-JP"
    assert len(grammar.json()["realizations"]) == 8
