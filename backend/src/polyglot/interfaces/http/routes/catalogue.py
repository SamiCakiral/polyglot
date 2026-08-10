from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from polyglot.interfaces.http.routes.identity import ProblemResponse
from polyglot.modules.catalogue.core.persistence import (
    CatalogueTarget,
    LanguagePackSummary,
    LexicalAnalysisSummary,
    LexicalSenseSummary,
    LexiconSearchItem,
    Page,
)
from polyglot.modules.catalogue.core.service import CatalogueReader
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue

PageLimit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(min_length=1, max_length=1024)]


class ClosedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class LanguagePackResponse(ClosedResponse):
    pack_id: UUID
    pack_revision_id: UUID
    pack_code: str
    revision_no: int
    target_language_tag: str
    support_language_tags: tuple[str, ...]
    channel: str
    compatibility_range: str


class LanguagePackPageResponse(ClosedResponse):
    items: tuple[LanguagePackResponse, ...]
    next_cursor: str | None


class CatalogueTargetResponse(ClosedResponse):
    skill_id: UUID
    skill_revision_id: UUID
    skill_code: str
    skill_type: str
    modality: str
    operation: str
    target_ref: str
    required_prerequisite_codes: tuple[str, ...]


class CatalogueTargetPageResponse(ClosedResponse):
    items: tuple[CatalogueTargetResponse, ...]
    next_cursor: str | None


class LexicalAnalysisResponse(ClosedResponse):
    form_analysis_id: UUID
    unit_revision_id: UUID
    lemma: str
    unit_type: str
    part_of_speech: str
    morphological_features: dict[str, JsonValue]


class LexicalSenseResponse(ClosedResponse):
    sense_id: UUID
    sense_revision_id: UUID
    sense_code: str
    definition: str


class LexiconSearchItemResponse(ClosedResponse):
    surface: str
    analysis: LexicalAnalysisResponse
    senses: tuple[LexicalSenseResponse, ...]


class LexiconSearchPageResponse(ClosedResponse):
    items: tuple[LexiconSearchItemResponse, ...]
    next_cursor: str | None


CATALOGUE_PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    problem_status: {
        "model": ProblemResponse,
        "content": {
            "application/problem+json": {
                "schema": {"$ref": "#/components/schemas/ProblemResponse"}
            }
        },
    }
    for problem_status in (409, 422, 503)
}


def _pack_page(page: Page[LanguagePackSummary]) -> LanguagePackPageResponse:
    return LanguagePackPageResponse(
        items=tuple(LanguagePackResponse.model_validate(item) for item in page.items),
        next_cursor=page.next_cursor,
    )


def _target_page(page: Page[CatalogueTarget]) -> CatalogueTargetPageResponse:
    return CatalogueTargetPageResponse(
        items=tuple(CatalogueTargetResponse.model_validate(item) for item in page.items),
        next_cursor=page.next_cursor,
    )


def _analysis(analysis: LexicalAnalysisSummary) -> LexicalAnalysisResponse:
    return LexicalAnalysisResponse.model_validate(analysis)


def _sense(sense: LexicalSenseSummary) -> LexicalSenseResponse:
    return LexicalSenseResponse.model_validate(sense)


def _lexicon_item(item: LexiconSearchItem) -> LexiconSearchItemResponse:
    return LexiconSearchItemResponse(
        surface=item.surface,
        analysis=_analysis(item.analysis),
        senses=tuple(_sense(sense) for sense in item.senses),
    )


def _lexicon_page(page: Page[LexiconSearchItem]) -> LexiconSearchPageResponse:
    return LexiconSearchPageResponse(
        items=tuple(_lexicon_item(item) for item in page.items),
        next_cursor=page.next_cursor,
    )


def catalogue_router(service: CatalogueReader | None) -> APIRouter:
    router = APIRouter()

    def reader() -> CatalogueReader:
        if service is None:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        return service

    @router.get(
        "/api/v1/language-packs",
        operation_id="list_language_packs",
        response_model=LanguagePackPageResponse,
        responses=CATALOGUE_PROBLEM_RESPONSES,
    )
    async def list_language_packs(
        limit: PageLimit = 20,
        cursor: Cursor = None,
    ) -> LanguagePackPageResponse:
        page = await reader().list_language_packs(limit=limit, cursor=cursor)
        return _pack_page(page)

    @router.get(
        "/api/v1/catalogue/targets",
        operation_id="list_catalogue_targets",
        response_model=CatalogueTargetPageResponse,
        responses=CATALOGUE_PROBLEM_RESPONSES,
    )
    async def list_catalogue_targets(
        pack_code: Annotated[str, Query(min_length=3, max_length=120)],
        limit: PageLimit = 20,
        cursor: Cursor = None,
    ) -> CatalogueTargetPageResponse:
        page = await reader().list_targets(
            pack_code=pack_code,
            limit=limit,
            cursor=cursor,
        )
        return _target_page(page)

    @router.get(
        "/api/v1/lexicon/search",
        operation_id="search_lexicon",
        response_model=LexiconSearchPageResponse,
        responses=CATALOGUE_PROBLEM_RESPONSES,
    )
    async def search_lexicon(
        q: Annotated[str, Query(min_length=1, max_length=500)],
        language_tag: Annotated[str, Query(min_length=4, max_length=35)],
        limit: PageLimit = 20,
        cursor: Cursor = None,
    ) -> LexiconSearchPageResponse:
        page = await reader().search_lexicon(
            query=q,
            language_tag=language_tag,
            limit=limit,
            cursor=cursor,
        )
        return _lexicon_page(page)

    return router
