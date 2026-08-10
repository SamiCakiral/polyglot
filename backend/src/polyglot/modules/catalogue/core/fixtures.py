import hashlib
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from polyglot.modules.catalogue.core.domain import (
    CommunicativeFunctionRevision,
    ContentRevisionStatus,
    FormAnalysis,
    FoundationCheckerKind,
    GrammarPattern,
    GrammarStructureRevision,
    LanguagePack,
    LanguagePackRevision,
    LanguageVariety,
    LexicalSenseRevision,
    LexicalUnitRevision,
    LexicalUnitType,
    PrerequisiteEdgeType,
    PublishedFoundationBlock,
    PublishedFoundationCatalogue,
    PublishedFoundationDefinition,
    PublishedFoundationGate,
    PublishedFoundationItem,
    SkillPrerequisiteEdge,
    SkillRevision,
)
from polyglot.modules.catalogue.core.graph import SkillGraph
from polyglot.platform.errors import DomainError, ErrorCode


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _ManifestData(_StrictModel):
    id: str
    kind: Literal["positive", "negative"]
    expected_status: Literal["accepted", "rejected"]
    expected_error: str | None = None


class _MetadataData(_StrictModel):
    schema_version: Literal[1]
    synthetic: Literal[True]
    seed: int
    clock: datetime
    payloads: dict[str, str]
    oracles: tuple[str, ...]
    network_dependencies: tuple[str, ...]
    linguistic_review: Literal["pending_human"]


class _VarietyData(_StrictModel):
    variety_id: UUID
    language_tag: str
    region_code: str | None
    script_codes: tuple[str, ...]
    text_direction: Literal["ltr", "rtl"]
    segmentation_policy_revision_id: UUID
    media_capabilities: tuple[str, ...]
    normalization_policy_revision_id: UUID


class _PackData(_StrictModel):
    pack_id: UUID
    pack_revision_id: UUID
    pack_code: str
    pack_revision_code: str
    revision_no: int
    target: _VarietyData
    supports: tuple[_VarietyData, ...]
    status: ContentRevisionStatus
    engine_min_version: str
    engine_max_version: str
    capabilities: tuple[str, ...]
    checksum_manifest: dict[str, str]
    license_refs: tuple[str, ...]
    provenance_id: UUID
    published_at: datetime | None


class _FunctionData(_StrictModel):
    function_revision_id: UUID
    function_id: UUID
    revision_no: int
    function_code: str
    label: str
    realizations: tuple[str, ...]
    status: ContentRevisionStatus
    provenance_id: UUID


class _PatternData(_StrictModel):
    pattern_id: UUID
    pattern_code: str
    template: str
    slots: tuple[str, ...]
    instantiation_rules: dict[str, str]
    examples: tuple[str, ...]
    counterexamples: tuple[str, ...]


class _StructureData(_StrictModel):
    structure_revision_id: UUID
    structure_id: UUID
    revision_no: int
    structure_code: str
    function_code: str
    constraints: dict[str, str]
    contrasts: tuple[str, ...]
    typical_errors: tuple[str, ...]
    variants: tuple[str, ...]
    patterns: tuple[_PatternData, ...]
    status: ContentRevisionStatus
    provenance_id: UUID


class _SkillData(_StrictModel):
    skill_revision_id: UUID
    skill_id: UUID
    revision_no: int
    skill_code: str
    skill_type: str
    modality: str
    operation: str
    target_ref: str
    scope: tuple[str, ...]
    evidence_protocol_ids: tuple[UUID, ...]
    load_profile: dict[str, int]
    status: ContentRevisionStatus
    provenance_id: UUID


class _EdgeData(_StrictModel):
    edge_id: UUID
    from_skill_revision_id: UUID
    to_skill_revision_id: UUID
    edge_type: PrerequisiteEdgeType
    provenance_id: UUID


class _SenseData(_StrictModel):
    sense_revision_id: UUID
    sense_id: UUID
    revision_no: int
    sense_code: str
    definition: str
    domains: tuple[str, ...]
    register_value: str | None = Field(alias="register")
    status: ContentRevisionStatus
    provenance_id: UUID


class _FormData(_StrictModel):
    form_analysis_id: UUID
    surface: str
    features: dict[str, str]
    pronunciation_refs: tuple[UUID, ...]
    normalization_key: str


class _ComponentData(_StrictModel):
    unit_revision_id: UUID
    lemma: str


class _LexicalUnitData(_StrictModel):
    unit_revision_id: UUID
    lexical_unit_id: UUID
    revision_no: int
    lemma: str
    unit_type: LexicalUnitType
    part_of_speech: str
    register_value: str | None = Field(alias="register")
    senses: tuple[_SenseData, ...]
    forms: tuple[_FormData, ...]
    components: tuple[_ComponentData, ...]
    status: ContentRevisionStatus
    provenance_id: UUID


class _FoundationItemData(_StrictModel):
    item_revision_id: UUID
    block_revision_id: UUID
    pack_revision_id: UUID
    item_code: str
    ordinal: int
    target_refs: tuple[str, ...]
    response_kind: Literal["raw"]
    checker_kind: FoundationCheckerKind
    checker_values: tuple[str, ...]
    modalities: tuple[str, ...]
    status: ContentRevisionStatus
    checksum: str


class _FoundationBlockData(_StrictModel):
    block_revision_id: UUID
    foundation_revision_id: UUID
    pack_revision_id: UUID
    block_code: str
    ordinal: int
    component_type: str
    prerequisite_refs: tuple[str, ...]
    items: tuple[_FoundationItemData, ...]
    modalities: tuple[str, ...]
    backend_criteria: tuple[str, ...]
    waiver_policy_ref: str
    status: ContentRevisionStatus
    checksum: str


class _FoundationGateData(_StrictModel):
    gate_revision_id: UUID
    foundation_revision_id: UUID
    pack_revision_id: UUID
    gate_code: str
    blocking_target_refs: tuple[str, ...]
    blocking_facet_refs: tuple[str, ...]
    coverage_threshold: float
    confidence_threshold: float
    minimum_distinct_sessions: int
    delayed_control_hours: int
    grapheme_sound_minimum: int
    grapheme_sound_total: int
    targeted_reading_minimum: int
    targeted_reading_total: int
    survival_exchange_minimum: int
    survival_exchange_total: int
    oral_policy: Literal["not_evaluable_non_blocking"]
    status: ContentRevisionStatus
    checksum: str


class _FoundationData(_StrictModel):
    foundation_id: UUID
    foundation_revision_id: UUID
    pack_revision_id: UUID
    foundation_code: str
    revision_no: int
    blocks: tuple[_FoundationBlockData, ...]
    gate: _FoundationGateData
    status: ContentRevisionStatus
    checksum: str


class _CataloguePayload(_StrictModel):
    schema_version: Literal[1]
    fixture_id: str
    pilot_days: tuple[int, ...]
    linguistic_review: Literal["pending_human"]
    pack: _PackData
    communicative_functions: tuple[_FunctionData, ...]
    grammar_structures: tuple[_StructureData, ...]
    skills: tuple[_SkillData, ...]
    prerequisites: tuple[_EdgeData, ...]
    lexical_units: tuple[_LexicalUnitData, ...]
    foundations: _FoundationData


class _NegativeGraphPayload(_StrictModel):
    schema_version: Literal[1]
    fixture_id: str
    skills: tuple[_SkillData, ...]
    prerequisites: tuple[_EdgeData, ...]


@dataclass(frozen=True, slots=True)
class FixtureManifestVerification:
    fixture_id: str
    payload_names: tuple[str, ...]
    network_dependencies: tuple[str, ...]
    linguistic_review: str


@dataclass(frozen=True, slots=True)
class LexicalFormMatch:
    unit_revision_id: UUID
    lemma: str
    surface: str
    features: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class CatalogueFixture:
    fixture_id: str
    pack: LanguagePack
    pack_revision_code: str
    target_variety: LanguageVariety
    support_varieties: tuple[LanguageVariety, ...]
    pack_revision: LanguagePackRevision
    pilot_days: tuple[int, ...]
    linguistic_review: str
    communicative_functions: tuple[CommunicativeFunctionRevision, ...]
    grammar_structures: tuple[GrammarStructureRevision, ...]
    lexical_units: tuple[LexicalUnitRevision, ...]
    skills: tuple[SkillRevision, ...]
    skill_graph: SkillGraph
    foundations: PublishedFoundationCatalogue

    @property
    def pack_code(self) -> str:
        return self.pack.pack_code

    @property
    def target_language_tag(self) -> str:
        return self.target_variety.language_tag

    @property
    def support_language_tags(self) -> tuple[str, ...]:
        return tuple(variety.language_tag for variety in self.support_varieties)

    def search_forms(self, query: str) -> tuple[LexicalFormMatch, ...]:
        key = unicodedata.normalize("NFC", query).casefold()
        matches = (
            LexicalFormMatch(
                unit_revision_id=unit.unit_revision_id,
                lemma=unit.lemma,
                surface=form.surface,
                features=form.features,
            )
            for unit in self.lexical_units
            for form in unit.forms
            if form.normalization_key == key
        )
        return tuple(
            sorted(
                matches,
                key=lambda item: (item.lemma, item.surface, str(item.unit_revision_id)),
            )
        )

    def lexical_unit(self, lemma: str) -> LexicalUnitRevision:
        matches = tuple(unit for unit in self.lexical_units if unit.lemma == lemma)
        if len(matches) != 1:
            raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
        return matches[0]

    def skill_revision_id(self, skill_code: str) -> UUID:
        matches = tuple(
            skill.skill_revision_id for skill in self.skills if skill.skill_code == skill_code
        )
        if len(matches) != 1:
            raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
        return matches[0]


def _validation_error(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


def _load_manifest(root: Path) -> _ManifestData:
    try:
        return _ManifestData.model_validate_json((root / "manifest.json").read_text())
    except (OSError, ValidationError) as error:
        raise _validation_error("invalid fixture manifest") from error


def verify_fixture_manifest(root: Path) -> FixtureManifestVerification:
    manifest = _load_manifest(root)
    if manifest.kind != "positive" or manifest.expected_status != "accepted":
        raise _validation_error("offline verification requires a positive fixture")
    try:
        metadata = _MetadataData.model_validate_json((root / "fixture-metadata.json").read_text())
    except (OSError, ValidationError) as error:
        raise _validation_error("invalid fixture metadata") from error
    if metadata.network_dependencies:
        raise _validation_error("canonical catalogue fixture must be offline")
    if not metadata.payloads:
        raise _validation_error("fixture manifest has no payload")
    for payload_name, expected in metadata.payloads.items():
        if Path(payload_name).name != payload_name:
            raise _validation_error("fixture payload path must be local")
        try:
            actual = f"sha256:{hashlib.sha256((root / payload_name).read_bytes()).hexdigest()}"
        except OSError as error:
            raise _validation_error("fixture payload is missing") from error
        if actual != expected:
            raise _validation_error("fixture payload checksum mismatch")
    return FixtureManifestVerification(
        fixture_id=manifest.id,
        payload_names=tuple(sorted(metadata.payloads)),
        network_dependencies=metadata.network_dependencies,
        linguistic_review=metadata.linguistic_review,
    )


def _skill(data: _SkillData) -> SkillRevision:
    return SkillRevision(
        skill_revision_id=data.skill_revision_id,
        skill_id=data.skill_id,
        revision_no=data.revision_no,
        skill_code=data.skill_code,
        skill_type=data.skill_type,
        modality=data.modality,
        operation=data.operation,
        target_ref=data.target_ref,
        scope=data.scope,
        evidence_protocol_ids=data.evidence_protocol_ids,
        load_profile=tuple(sorted(data.load_profile.items())),
        status=data.status,
        provenance_id=data.provenance_id,
    )


def _edge(data: _EdgeData) -> SkillPrerequisiteEdge:
    return SkillPrerequisiteEdge(
        edge_id=data.edge_id,
        from_skill_revision_id=data.from_skill_revision_id,
        to_skill_revision_id=data.to_skill_revision_id,
        edge_type=data.edge_type,
        provenance_id=data.provenance_id,
    )


def _variety(data: _VarietyData) -> LanguageVariety:
    return LanguageVariety(
        variety_id=data.variety_id,
        language_tag=data.language_tag,
        region_code=data.region_code,
        script_codes=data.script_codes,
        text_direction=data.text_direction,
        segmentation_policy_revision_id=data.segmentation_policy_revision_id,
        media_capabilities=data.media_capabilities,
        normalization_policy_revision_id=data.normalization_policy_revision_id,
    )


def _function(data: _FunctionData) -> CommunicativeFunctionRevision:
    return CommunicativeFunctionRevision(
        function_revision_id=data.function_revision_id,
        function_id=data.function_id,
        revision_no=data.revision_no,
        function_code=data.function_code,
        label=data.label,
        realizations=data.realizations,
        status=data.status,
        provenance_id=data.provenance_id,
    )


def _structure(data: _StructureData) -> GrammarStructureRevision:
    patterns = tuple(
        GrammarPattern(
            pattern_id=item.pattern_id,
            pattern_code=item.pattern_code,
            template=item.template,
            slots=item.slots,
            instantiation_rules=tuple(sorted(item.instantiation_rules.items())),
            examples=item.examples,
            counterexamples=item.counterexamples,
        )
        for item in data.patterns
    )
    return GrammarStructureRevision(
        structure_revision_id=data.structure_revision_id,
        structure_id=data.structure_id,
        revision_no=data.revision_no,
        structure_code=data.structure_code,
        function_code=data.function_code,
        constraints=tuple(sorted(data.constraints.items())),
        contrasts=data.contrasts,
        typical_errors=data.typical_errors,
        variants=data.variants,
        patterns=tuple(sorted(patterns, key=lambda item: item.pattern_code)),
        status=data.status,
        provenance_id=data.provenance_id,
    )


def _lexical_unit(data: _LexicalUnitData) -> LexicalUnitRevision:
    senses = tuple(
        LexicalSenseRevision(
            sense_revision_id=item.sense_revision_id,
            sense_id=item.sense_id,
            revision_no=item.revision_no,
            sense_code=item.sense_code,
            definition=item.definition,
            domains=item.domains,
            register=item.register_value,
            status=item.status,
            provenance_id=item.provenance_id,
        )
        for item in data.senses
    )
    forms = tuple(
        FormAnalysis(
            form_analysis_id=item.form_analysis_id,
            surface=item.surface,
            features=tuple(sorted(item.features.items())),
            pronunciation_refs=item.pronunciation_refs,
            normalization_key=item.normalization_key,
        )
        for item in data.forms
    )
    return LexicalUnitRevision(
        unit_revision_id=data.unit_revision_id,
        lexical_unit_id=data.lexical_unit_id,
        revision_no=data.revision_no,
        lemma=data.lemma,
        unit_type=data.unit_type,
        part_of_speech=data.part_of_speech,
        register=data.register_value,
        senses=tuple(sorted(senses, key=lambda item: item.sense_code)),
        forms=tuple(sorted(forms, key=lambda item: (item.surface, item.features))),
        components=tuple(component.lemma for component in data.components),
        status=data.status,
        provenance_id=data.provenance_id,
    )


def _foundations(data: _FoundationData) -> PublishedFoundationCatalogue:
    blocks = tuple(
        PublishedFoundationBlock(
            block_revision_id=block.block_revision_id,
            foundation_revision_id=block.foundation_revision_id,
            pack_revision_id=block.pack_revision_id,
            block_code=block.block_code,
            ordinal=block.ordinal,
            component_type=block.component_type,
            prerequisite_refs=block.prerequisite_refs,
            items=tuple(
                PublishedFoundationItem(
                    item_revision_id=item.item_revision_id,
                    block_revision_id=item.block_revision_id,
                    pack_revision_id=item.pack_revision_id,
                    item_code=item.item_code,
                    ordinal=item.ordinal,
                    target_refs=item.target_refs,
                    response_kind=item.response_kind,
                    checker_kind=item.checker_kind,
                    checker_values=item.checker_values,
                    modalities=item.modalities,
                    status=item.status,
                    checksum=item.checksum,
                )
                for item in block.items
            ),
            modalities=block.modalities,
            backend_criteria=block.backend_criteria,
            waiver_policy_ref=block.waiver_policy_ref,
            status=block.status,
            checksum=block.checksum,
        )
        for block in data.blocks
    )
    gate = data.gate
    return PublishedFoundationCatalogue(
        definition=PublishedFoundationDefinition(
            foundation_id=data.foundation_id,
            foundation_revision_id=data.foundation_revision_id,
            pack_revision_id=data.pack_revision_id,
            foundation_code=data.foundation_code,
            revision_no=data.revision_no,
            blocks=blocks,
            gate=PublishedFoundationGate(
                gate_revision_id=gate.gate_revision_id,
                foundation_revision_id=gate.foundation_revision_id,
                pack_revision_id=gate.pack_revision_id,
                gate_code=gate.gate_code,
                blocking_target_refs=gate.blocking_target_refs,
                blocking_facet_refs=gate.blocking_facet_refs,
                coverage_threshold=gate.coverage_threshold,
                confidence_threshold=gate.confidence_threshold,
                minimum_distinct_sessions=gate.minimum_distinct_sessions,
                delayed_control_hours=gate.delayed_control_hours,
                grapheme_sound_minimum=gate.grapheme_sound_minimum,
                grapheme_sound_total=gate.grapheme_sound_total,
                targeted_reading_minimum=gate.targeted_reading_minimum,
                targeted_reading_total=gate.targeted_reading_total,
                survival_exchange_minimum=gate.survival_exchange_minimum,
                survival_exchange_total=gate.survival_exchange_total,
                oral_policy=gate.oral_policy,
                status=gate.status,
                checksum=gate.checksum,
            ),
            status=data.status,
            checksum=data.checksum,
        )
    )


def _validate_references(
    functions: tuple[CommunicativeFunctionRevision, ...],
    structures: tuple[GrammarStructureRevision, ...],
    lexical_units: tuple[LexicalUnitRevision, ...],
    skills: tuple[SkillRevision, ...],
    payload_units: tuple[_LexicalUnitData, ...],
) -> None:
    identity_values = (
        *(item.function_id for item in functions),
        *(item.function_revision_id for item in functions),
        *(item.structure_id for item in structures),
        *(item.structure_revision_id for item in structures),
        *(pattern.pattern_id for item in structures for pattern in item.patterns),
        *(item.skill_id for item in skills),
        *(item.skill_revision_id for item in skills),
        *(item.lexical_unit_id for item in lexical_units),
        *(item.unit_revision_id for item in lexical_units),
        *(sense.sense_id for item in lexical_units for sense in item.senses),
        *(sense.sense_revision_id for item in lexical_units for sense in item.senses),
        *(form.form_analysis_id for item in lexical_units for form in item.forms),
    )
    if len(set(identity_values)) != len(identity_values):
        raise _validation_error("fixture identities must be globally unique")
    function_codes = {item.function_code for item in functions}
    structure_codes = {item.structure_code for item in structures}
    if len(function_codes) != len(functions) or len(structure_codes) != len(structures):
        raise _validation_error("fixture content codes must be unique")
    pattern_codes = {pattern.pattern_code for item in structures for pattern in item.patterns}
    sense_codes = {sense.sense_code for item in lexical_units for sense in item.senses}
    content_code_values = (
        *(item.function_code for item in functions),
        *(item.structure_code for item in structures),
        *(pattern.pattern_code for item in structures for pattern in item.patterns),
        *(sense.sense_code for item in lexical_units for sense in item.senses),
    )
    if (
        len(pattern_codes) != sum(len(item.patterns) for item in structures)
        or len(sense_codes) != sum(len(item.senses) for item in lexical_units)
        or len(set(content_code_values)) != len(content_code_values)
    ):
        raise _validation_error("fixture content codes must be globally unique")
    if function_codes & structure_codes:
        raise _validation_error("fixture content code namespaces must not collide")
    if any(item.function_code not in function_codes for item in structures):
        raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
    skill_codes = {item.skill_code for item in skills}
    if len(skill_codes) != len(skills):
        raise _validation_error("fixture skill codes must be unique")
    allowed_target_refs = {
        "communicative_function": function_codes,
        "grammar_structure": structure_codes,
    }
    if any(
        skill.skill_type not in allowed_target_refs
        or skill.target_ref not in allowed_target_refs[skill.skill_type]
        for skill in skills
    ):
        raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)

    unit_by_revision_id = {item.unit_revision_id: item for item in payload_units}
    if len(unit_by_revision_id) != len(payload_units):
        raise _validation_error("fixture lexical unit revision ids must be unique")
    lemmas = {item.lemma for item in lexical_units}
    if len(lemmas) != len(lexical_units):
        raise _validation_error("fixture lexical lemmas must be unique in the pilot")
    if any(
        component.unit_revision_id not in unit_by_revision_id
        or unit_by_revision_id[component.unit_revision_id].lemma != component.lemma
        or component.unit_revision_id == item.unit_revision_id
        for item in payload_units
        for component in item.components
    ):
        raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
    if any(
        sense.status is not ContentRevisionStatus.PUBLISHED
        for item in payload_units
        for sense in item.senses
    ):
        raise _validation_error("canonical fixture nested senses must be published")
    if any(
        component.lemma not in lemmas for item in payload_units for component in item.components
    ):
        raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
    unpublished = (
        any(item.status is not ContentRevisionStatus.PUBLISHED for item in functions)
        or any(item.status is not ContentRevisionStatus.PUBLISHED for item in structures)
        or any(item.status is not ContentRevisionStatus.PUBLISHED for item in lexical_units)
        or any(item.status is not ContentRevisionStatus.PUBLISHED for item in skills)
    )
    if unpublished:
        raise _validation_error("canonical fixture revisions must be published")


def load_catalogue_fixture(root: Path) -> CatalogueFixture:
    manifest = _load_manifest(root)
    try:
        if manifest.kind == "negative":
            if manifest.expected_error != ErrorCode.PREREQUISITE_CYCLE.value:
                raise _validation_error("negative fixture error is not canonical")
            negative_payload = _NegativeGraphPayload.model_validate_json(
                (root / "catalogue.json").read_text()
            )
            skills = tuple(_skill(item) for item in negative_payload.skills)
            SkillGraph(
                skills,
                tuple(_edge(item) for item in negative_payload.prerequisites),
            )
            raise _validation_error("negative fixture did not reproduce its oracle")

        verification = verify_fixture_manifest(root)
        positive_payload = _CataloguePayload.model_validate_json(
            (root / "catalogue.json").read_text()
        )
        if (
            positive_payload.fixture_id != manifest.id
            or positive_payload.fixture_id != verification.fixture_id
        ):
            raise _validation_error("fixture identifiers do not match")
        if positive_payload.pilot_days != (1, 2, 3):
            raise _validation_error("Italian pilot fixture must contain three days")

        pack_data = positive_payload.pack
        target = _variety(pack_data.target)
        supports = tuple(_variety(item) for item in pack_data.supports)
        pack = LanguagePack(pack_data.pack_id, pack_data.pack_code)
        pack_revision = LanguagePackRevision(
            pack_revision_id=pack_data.pack_revision_id,
            pack_id=pack_data.pack_id,
            revision_no=pack_data.revision_no,
            target_variety_id=target.variety_id,
            support_variety_ids=tuple(item.variety_id for item in supports),
            status=pack_data.status,
            engine_min_version=pack_data.engine_min_version,
            engine_max_version=pack_data.engine_max_version,
            capabilities=pack_data.capabilities,
            checksum_manifest=tuple(sorted(pack_data.checksum_manifest.items())),
            license_refs=pack_data.license_refs,
            provenance_id=pack_data.provenance_id,
            published_at=pack_data.published_at,
        )
        functions = tuple(
            sorted(
                (_function(item) for item in positive_payload.communicative_functions),
                key=lambda item: item.function_code,
            )
        )
        structures = tuple(
            sorted(
                (_structure(item) for item in positive_payload.grammar_structures),
                key=lambda item: item.structure_code,
            )
        )
        lexical_units = tuple(
            sorted(
                (_lexical_unit(item) for item in positive_payload.lexical_units),
                key=lambda item: item.lemma,
            )
        )
        skills = tuple(
            sorted(
                (_skill(item) for item in positive_payload.skills),
                key=lambda item: item.skill_code,
            )
        )
        graph = SkillGraph(
            skills,
            tuple(_edge(item) for item in positive_payload.prerequisites),
        )
        _validate_references(
            functions,
            structures,
            lexical_units,
            skills,
            positive_payload.lexical_units,
        )
        foundations = _foundations(positive_payload.foundations)
        return CatalogueFixture(
            fixture_id=positive_payload.fixture_id,
            pack=pack,
            pack_revision_code=pack_data.pack_revision_code,
            target_variety=target,
            support_varieties=supports,
            pack_revision=pack_revision,
            pilot_days=positive_payload.pilot_days,
            linguistic_review=positive_payload.linguistic_review,
            communicative_functions=functions,
            grammar_structures=structures,
            lexical_units=lexical_units,
            skills=skills,
            skill_graph=graph,
            foundations=foundations,
        )
    except DomainError:
        raise
    except (OSError, ValidationError, ValueError) as error:
        raise _validation_error("invalid catalogue fixture payload") from error
