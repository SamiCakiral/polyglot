from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from polyglot.interfaces.http.routes.identity import ProblemResponse
from polyglot.modules.catalogue.core.grammar_registry import grammar_toolbox_for
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
    target_variety_id: UUID
    target_language_tag: str
    target_script_codes: tuple[str, ...]
    text_direction: str
    segmentation_policy_revision_id: UUID
    media_capabilities: dict[str, JsonValue]
    capability_manifest: dict[str, JsonValue]
    support_variety_ids: tuple[UUID, ...]
    support_language_tags: tuple[str, ...]
    foundation_revision_id: UUID | None
    channel: str
    compatibility_range: str


class LanguagePackPageResponse(ClosedResponse):
    items: tuple[LanguagePackResponse, ...]
    next_cursor: str | None


class PlacementChoiceResponse(ClosedResponse):
    value: str
    label: str


class PlacementItemResponse(ClosedResponse):
    item_revision_id: UUID
    item_code: str
    block_code: str
    ordinal: int
    prompt: str
    response_kind: str
    choices: tuple[PlacementChoiceResponse, ...]


class PlacementManifestResponse(ClosedResponse):
    pack_revision_id: UUID
    foundation_revision_id: UUID
    items: tuple[PlacementItemResponse, ...]


class FoundationActivityResponse(ClosedResponse):
    item_revision_id: UUID
    item_code: str
    block_code: str
    block_title: str
    ordinal: int
    prompt: str
    response_kind: str
    modality: str
    teaching_value: str | None
    choices: tuple[PlacementChoiceResponse, ...]


class FoundationManifestResponse(ClosedResponse):
    pack_revision_id: UUID
    foundation_revision_id: UUID
    activities: tuple[FoundationActivityResponse, ...]


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


class GrammarFamilyResponse(ClosedResponse):
    code: str
    label: str
    realization_codes: tuple[str, ...]


class GrammarRealizationResponse(ClosedResponse):
    realization_code: str
    function_code: str
    family_code: str
    support_template: str
    target_template: str
    examples: tuple[str, ...]
    prerequisite_codes: tuple[str, ...]
    variants: tuple[str, ...]
    pitfalls: tuple[str, ...]
    compatible_primitives: tuple[str, ...]
    transformations: tuple[str, ...]


class GrammarToolboxResponse(ClosedResponse):
    pack_revision_id: UUID
    target_language_tag: str
    support_language_tag: str
    version: str
    families: tuple[GrammarFamilyResponse, ...]
    realizations: tuple[GrammarRealizationResponse, ...]
    priority_realization_codes: tuple[str, ...]


CATALOGUE_PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    problem_status: {
        "model": ProblemResponse,
        "content": {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemResponse"}}
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
        "/api/v1/language-packs/{pack_revision_id}/placement-manifest",
        operation_id="get_placement_manifest",
        response_model=PlacementManifestResponse,
        responses=CATALOGUE_PROBLEM_RESPONSES,
    )
    async def get_placement_manifest(pack_revision_id: UUID) -> PlacementManifestResponse:
        catalogue = await reader().read_foundations(pack_revision_id=pack_revision_id)
        if catalogue is None:
            raise DomainError(ErrorCode.FOUNDATION_PACK_MISSING)
        presentations: dict[str, tuple[str, str, tuple[tuple[str, str], ...]]] = {
            "ITF-F1-01": (
                "Quel couple commence par un son c ou g dur ?",
                "single_choice",
                (("casa_gatto", "casa / gatto"), ("cena_gelato", "cena / gelato")),
            ),
            "ITF-F1-01-S02": (
                "Quel couple commence par un son c ou g doux ?",
                "single_choice",
                (("cena_gelato", "cena / gelato"), ("casa_gatto", "casa / gatto")),
            ),
            "ITF-F3-01": (
                "Vous entrez dans une boutique. Quelle ouverture convient ?",
                "single_choice",
                (("formal_greeting", "Buongiorno"), ("informal_greeting", "Ciao")),
            ),
            "ITF-F3-02": (
                "Présentez-vous comme Luca en commençant par buongiorno.",
                "text",
                (),
            ),
            "ITF-F4-01": (
                "Complétez : ___ due binari alla stazione.",
                "single_choice",
                (("ci_sono", "Ci sono"), ("ce", "C'è")),
            ),
            "ITF-F5-01": (
                "Demandez poliment à quelqu'un de répéter.",
                "text",
                (),
            ),
        }
        items: list[PlacementItemResponse] = []
        ordinal = 1
        for block in catalogue.definition.blocks:
            for item in block.items:
                presentation = presentations.get(item.item_code)
                if presentation is None:
                    continue
                prompt, response_kind, choices = presentation
                items.append(
                    PlacementItemResponse(
                        item_revision_id=item.item_revision_id,
                        item_code=item.item_code,
                        block_code=block.block_code,
                        ordinal=ordinal,
                        prompt=prompt,
                        response_kind=response_kind,
                        choices=tuple(
                            PlacementChoiceResponse(value=value, label=label)
                            for value, label in choices
                        ),
                    )
                )
                ordinal += 1
        if len(items) != 6:
            raise DomainError(ErrorCode.CONTENT_UNAVAILABLE)
        return PlacementManifestResponse(
            pack_revision_id=pack_revision_id,
            foundation_revision_id=catalogue.definition.foundation_revision_id,
            items=tuple(items),
        )

    @router.get(
        "/api/v1/language-packs/{pack_revision_id}/foundation-manifest",
        operation_id="get_foundation_manifest",
        response_model=FoundationManifestResponse,
        responses=CATALOGUE_PROBLEM_RESPONSES,
    )
    async def get_foundation_manifest(pack_revision_id: UUID) -> FoundationManifestResponse:
        catalogue = await reader().read_foundations(pack_revision_id=pack_revision_id)
        if catalogue is None:
            raise DomainError(ErrorCode.FOUNDATION_PACK_MISSING)
        block_titles = {
            "F1": "Sons et lecture",
            "F2": "Accent et rythme",
            "F3": "Saluer et se présenter",
            "F4": "Construire une phrase simple",
            "F5": "Réparer un échange",
        }
        prompts = {
            "F1": "Lisez ou écoutez la forme italienne, puis restituez-la exactement.",
            "F2": "Repérez l'accent tonique, puis répétez la forme à voix haute.",
            "F3": "Produisez la formule adaptée pour saluer ou vous présenter.",
            "F4": "Complétez la structure italienne demandée.",
            "F5": "Produisez une formule courte pour maintenir l'échange.",
        }
        choice_decoys = {
            "casa_gatto": "cena_gelato",
            "cena_gelato": "casa_gatto",
            "stress_marked": "stress_unmarked",
            "formal_greeting": "informal_greeting",
            "ci_sono": "ce",
        }
        labels = {
            "formal_greeting": "Buongiorno",
            "informal_greeting": "Ciao",
            "stress_marked": "Accent repéré",
            "stress_unmarked": "Accent non repéré",
            "ci_sono": "Ci sono",
            "ce": "C'è",
        }
        teaching_surfaces = {
            "chi_giro": "chi / giro",
            "coro_gomma": "coro / gomma",
            "cane_gente": "cane / gente",
            "cibo_gufo": "cibo / gufo",
            "che_gemma": "che / gemma",
            "cuore_gioco": "cuore / gioco",
            "camera_giacca": "camera / giacca",
            "coda_giorno": "coda / giorno",
            "buongiorno_sono_luca": "Buongiorno, sono Luca.",
            "puo_ripetere": "Può ripetere?",
            "non_capisco": "Non capisco.",
            "puo_parlare_piu_lentamente": "Può parlare più lentamente?",
            "come_si_dice": "Come si dice?",
            "puo_scriverlo": "Può scriverlo?",
        }
        activities: list[FoundationActivityResponse] = []
        global_ordinal = 1
        for block in catalogue.definition.blocks:
            for item in block.items:
                teaching_value = item.checker_values[0] if item.checker_values else None
                choices: tuple[PlacementChoiceResponse, ...] = ()
                if teaching_value in choice_decoys:
                    values = (teaching_value, choice_decoys[teaching_value])
                    choices = tuple(
                        PlacementChoiceResponse(
                            value=value,
                            label=labels.get(value, value.replace("_", " / ")),
                        )
                        for value in values
                    )
                activities.append(
                    FoundationActivityResponse(
                        item_revision_id=item.item_revision_id,
                        item_code=item.item_code,
                        block_code=block.block_code,
                        block_title=block_titles[block.block_code],
                        ordinal=global_ordinal,
                        prompt=prompts[block.block_code],
                        response_kind="choice" if choices else "text",
                        modality=item.modalities[0],
                        teaching_value=(
                            teaching_surfaces.get(teaching_value, teaching_value)
                            if teaching_value is not None
                            else None
                        ),
                        choices=choices,
                    )
                )
                global_ordinal += 1
        if len(activities) != 32:
            raise DomainError(ErrorCode.CONTENT_UNAVAILABLE)
        return FoundationManifestResponse(
            pack_revision_id=pack_revision_id,
            foundation_revision_id=catalogue.definition.foundation_revision_id,
            activities=tuple(activities),
        )

    @router.get(
        "/api/v1/language-packs/{pack_revision_id}/grammar-functions",
        operation_id="get_grammar_toolbox",
        response_model=GrammarToolboxResponse,
        responses=CATALOGUE_PROBLEM_RESPONSES,
    )
    async def get_grammar_toolbox(
        pack_revision_id: UUID,
        support_language_tag: Annotated[str, Query(min_length=4, max_length=35)],
    ) -> GrammarToolboxResponse:
        pack = await reader().get_language_pack(pack_revision_id=pack_revision_id)
        if pack is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        if support_language_tag not in pack.support_language_tags:
            raise DomainError(ErrorCode.CONTENT_UNAVAILABLE)
        toolbox = grammar_toolbox_for(pack.target_language_tag, support_language_tag)
        if toolbox is None:
            raise DomainError(ErrorCode.CONTENT_UNAVAILABLE)
        return GrammarToolboxResponse(
            pack_revision_id=pack_revision_id,
            target_language_tag=toolbox.target_language_tag,
            support_language_tag=toolbox.support_language_tag,
            version=toolbox.version,
            families=tuple(
                GrammarFamilyResponse(
                    code=family.code,
                    label=family.label,
                    realization_codes=tuple(
                        item.realization_code
                        for item in toolbox.realizations
                        if item.family_code == family.code
                    ),
                )
                for family in toolbox.families
            ),
            realizations=tuple(
                GrammarRealizationResponse.model_validate(item) for item in toolbox.realizations
            ),
            priority_realization_codes=toolbox.priority_realization_codes,
        )

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
