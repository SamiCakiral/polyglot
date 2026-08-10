from uuid import UUID

from fastapi.testclient import TestClient

from polyglot.interfaces.http.app import create_app
from polyglot.modules.catalogue.core.persistence import (
    CatalogueTarget,
    LanguagePackSummary,
    LexicalAnalysisSummary,
    LexicalSenseSummary,
    LexiconSearchItem,
    Page,
)


class StubCatalogueReader:
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
                    target_language_tag="it-IT",
                    support_language_tags=("fr-FR",),
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
                            sense_revision_id=UUID(
                                "019fe900-6000-7000-8002-000000000004"
                            ),
                            sense_code="ability",
                            definition="pouvoir ou permission",
                        ),
                    ),
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
