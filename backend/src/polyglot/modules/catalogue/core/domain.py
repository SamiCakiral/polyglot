import unicodedata
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from re import fullmatch
from typing import Any
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode


class ContentRevisionStatus(StrEnum):
    DRAFT = "draft"
    VALIDATING = "validating"
    VALIDATED = "validated"
    APPROVED = "approved"
    PUBLISHED = "published"
    RETIRED = "retired"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    ABANDONED = "abandoned"


class PrerequisiteEdgeType(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    CONTRAST = "contrast"
    TRANSFER = "transfer"


class LexicalUnitType(StrEnum):
    WORD = "word"
    MULTIWORD_EXPRESSION = "multiword_expression"
    PROPER_NAME = "proper_name"
    LEXICALIZED_CONSTRUCTION = "lexicalized_construction"


class FoundationCheckerKind(StrEnum):
    EXACT_CHOICE = "exact_choice"
    EXACT_RECONSTRUCTION = "exact_reconstruction"
    NORMALIZED_ALTERNATIVES = "normalized_alternatives"
    NOT_EVALUABLE = "not_evaluable"


class FoundationReferenceKind(StrEnum):
    TARGET = "target"
    FACET = "facet"
    WAIVER_POLICY = "waiver_policy"


_MODALITIES = frozenset({"reading", "listening", "writing", "speaking"})
_FOUNDATION_BLOCKING_FACETS = (
    "grapheme_sound_discrimination",
    "controlled_reading",
    "greeting_recognition",
    "functional_frame_choice",
    "written_guided_repair",
)
_OPERATIONS = frozenset(
    {
        "recognize",
        "recall",
        "discriminate",
        "transform",
        "produce",
        "interact",
        "repair",
        "transfer",
    }
)
_TRANSITIONS: dict[ContentRevisionStatus, frozenset[ContentRevisionStatus]] = {
    ContentRevisionStatus.DRAFT: frozenset(
        {ContentRevisionStatus.VALIDATING, ContentRevisionStatus.ABANDONED}
    ),
    ContentRevisionStatus.VALIDATING: frozenset(
        {ContentRevisionStatus.VALIDATED, ContentRevisionStatus.REJECTED}
    ),
    ContentRevisionStatus.VALIDATED: frozenset(
        {ContentRevisionStatus.APPROVED, ContentRevisionStatus.REJECTED}
    ),
    ContentRevisionStatus.APPROVED: frozenset(
        {ContentRevisionStatus.PUBLISHED, ContentRevisionStatus.REJECTED}
    ),
}


def _invalid(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


def require_uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise _invalid(f"{field} must be UUIDv7")


def require_revision_number(value: int) -> None:
    if value < 1:
        raise _invalid("revision_no must be positive")


def require_stable_code(value: str, field: str) -> None:
    if fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,119}", value) is None:
        raise _invalid(f"{field} must match the canonical stable code format")


@dataclass(frozen=True, slots=True)
class LanguageVariety:
    variety_id: UUID
    language_tag: str
    region_code: str | None
    script_codes: tuple[str, ...]
    text_direction: str
    segmentation_policy_revision_id: UUID
    media_capabilities: tuple[str, ...]
    normalization_policy_revision_id: UUID

    def __post_init__(self) -> None:
        require_uuid7(self.variety_id, "variety_id")
        require_uuid7(
            self.segmentation_policy_revision_id,
            "segmentation_policy_revision_id",
        )
        require_uuid7(
            self.normalization_policy_revision_id,
            "normalization_policy_revision_id",
        )
        if "-" not in self.language_tag or not self.script_codes:
            raise _invalid("language variety requires a regional tag and script")
        if self.text_direction not in {"ltr", "rtl"}:
            raise _invalid("text direction is not canonical")


@dataclass(frozen=True, slots=True)
class LanguagePack:
    pack_id: UUID
    pack_code: str

    def __post_init__(self) -> None:
        require_uuid7(self.pack_id, "pack_id")
        require_stable_code(self.pack_code, "pack_code")


@dataclass(frozen=True, slots=True)
class LanguagePackRevision:
    pack_revision_id: UUID
    pack_id: UUID
    revision_no: int
    target_variety_id: UUID
    support_variety_ids: tuple[UUID, ...]
    status: ContentRevisionStatus
    engine_min_version: str
    engine_max_version: str
    capabilities: tuple[str, ...]
    checksum_manifest: tuple[tuple[str, str], ...]
    license_refs: tuple[str, ...]
    provenance_id: UUID
    published_at: datetime | None

    def __post_init__(self) -> None:
        for field, value in (
            ("pack_revision_id", self.pack_revision_id),
            ("pack_id", self.pack_id),
            ("target_variety_id", self.target_variety_id),
            ("provenance_id", self.provenance_id),
        ):
            require_uuid7(value, field)
        require_revision_number(self.revision_no)
        if not self.support_variety_ids:
            raise _invalid("at least one support variety is required")
        for variety_id in self.support_variety_ids:
            require_uuid7(variety_id, "support_variety_ids")
        if len(set(self.support_variety_ids)) != len(self.support_variety_ids):
            raise _invalid("support varieties must be unique")
        if not self.engine_min_version or not self.engine_max_version:
            raise _invalid("engine compatibility must be explicit")
        if not self.capabilities or len(set(self.capabilities)) != len(self.capabilities):
            raise _invalid("capabilities must be non-empty and unique")
        if not self.license_refs:
            raise _invalid("at least one license reference is required")
        if not self.checksum_manifest:
            raise _invalid("checksum manifest must be non-empty")
        for name, checksum in self.checksum_manifest:
            invalid_checksum = len(checksum) != 64 or any(
                character not in "0123456789abcdef" for character in checksum
            )
            if not name or invalid_checksum:
                raise _invalid("checksum manifest requires lowercase SHA-256 values")
        if (self.status is ContentRevisionStatus.PUBLISHED) != (self.published_at is not None):
            raise _invalid("published_at is required exactly for published revisions")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def change_status(
        self,
        status: ContentRevisionStatus,
        *,
        published_at: datetime | None = None,
    ) -> "LanguagePackRevision":
        if self.status is ContentRevisionStatus.PUBLISHED:
            raise DomainError(
                ErrorCode.INVALID_TRANSITION,
                detail="published revisions are immutable",
            )
        if status not in _TRANSITIONS.get(self.status, frozenset()):
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return replace(self, status=status, published_at=published_at)

    def retire(self, successor_revision_id: UUID) -> "LanguagePackRevision":
        if self.status is not ContentRevisionStatus.PUBLISHED:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        require_uuid7(successor_revision_id, "successor_revision_id")
        return replace(
            self,
            pack_revision_id=successor_revision_id,
            revision_no=self.revision_no + 1,
            status=ContentRevisionStatus.RETIRED,
            published_at=None,
        )


@dataclass(frozen=True, slots=True)
class SkillRevision:
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
    load_profile: tuple[tuple[str, int], ...]
    status: ContentRevisionStatus
    provenance_id: UUID

    def __post_init__(self) -> None:
        require_uuid7(self.skill_revision_id, "skill_revision_id")
        require_uuid7(self.skill_id, "skill_id")
        require_uuid7(self.provenance_id, "provenance_id")
        require_revision_number(self.revision_no)
        require_stable_code(self.skill_code, "skill_code")
        require_stable_code(self.skill_type, "skill_type")
        require_stable_code(self.target_ref, "target_ref")
        if self.modality not in _MODALITIES:
            raise _invalid("modality is not canonical")
        if self.operation not in _OPERATIONS:
            raise _invalid("operation is not canonical")
        if not self.scope:
            raise _invalid("skill scope must be non-empty")
        for protocol_id in self.evidence_protocol_ids:
            require_uuid7(protocol_id, "evidence_protocol_ids")


@dataclass(frozen=True, slots=True)
class SkillPrerequisiteEdge:
    edge_id: UUID
    from_skill_revision_id: UUID
    to_skill_revision_id: UUID
    edge_type: PrerequisiteEdgeType
    provenance_id: UUID

    def __post_init__(self) -> None:
        require_uuid7(self.edge_id, "edge_id")
        require_uuid7(self.from_skill_revision_id, "from_skill_revision_id")
        require_uuid7(self.to_skill_revision_id, "to_skill_revision_id")
        require_uuid7(self.provenance_id, "provenance_id")
        if self.from_skill_revision_id == self.to_skill_revision_id:
            if self.edge_type is PrerequisiteEdgeType.REQUIRED:
                raise DomainError(ErrorCode.PREREQUISITE_CYCLE)
            raise _invalid("a prerequisite edge cannot reference itself")


@dataclass(frozen=True, slots=True)
class CommunicativeFunctionRevision:
    function_revision_id: UUID
    function_id: UUID
    revision_no: int
    function_code: str
    label: str
    realizations: tuple[str, ...]
    status: ContentRevisionStatus
    provenance_id: UUID

    def __post_init__(self) -> None:
        require_uuid7(self.function_revision_id, "function_revision_id")
        require_uuid7(self.function_id, "function_id")
        require_uuid7(self.provenance_id, "provenance_id")
        require_revision_number(self.revision_no)
        require_stable_code(self.function_code, "function_code")
        if not self.label or not self.realizations:
            raise _invalid("communicative function content must be non-empty")


@dataclass(frozen=True, slots=True)
class GrammarPattern:
    pattern_id: UUID
    pattern_code: str
    template: str
    slots: tuple[str, ...]
    instantiation_rules: tuple[tuple[str, str], ...]
    examples: tuple[str, ...]
    counterexamples: tuple[str, ...]

    def __post_init__(self) -> None:
        require_uuid7(self.pattern_id, "pattern_id")
        require_stable_code(self.pattern_code, "pattern_code")
        if not self.template or not self.examples:
            raise _invalid("grammar pattern requires a template and examples")
        if len(dict(self.instantiation_rules)) != len(self.instantiation_rules):
            raise _invalid("grammar pattern rules must have unique keys")


@dataclass(frozen=True, slots=True)
class GrammarStructureRevision:
    structure_revision_id: UUID
    structure_id: UUID
    revision_no: int
    structure_code: str
    function_code: str
    constraints: tuple[tuple[str, str], ...]
    contrasts: tuple[str, ...]
    typical_errors: tuple[str, ...]
    variants: tuple[str, ...]
    patterns: tuple[GrammarPattern, ...]
    status: ContentRevisionStatus
    provenance_id: UUID

    def __post_init__(self) -> None:
        require_uuid7(self.structure_revision_id, "structure_revision_id")
        require_uuid7(self.structure_id, "structure_id")
        require_uuid7(self.provenance_id, "provenance_id")
        require_revision_number(self.revision_no)
        require_stable_code(self.structure_code, "structure_code")
        require_stable_code(self.function_code, "function_code")
        if not self.patterns:
            raise _invalid("grammar structure requires at least one pattern")
        pattern_codes = {pattern.pattern_code for pattern in self.patterns}
        if len(pattern_codes) != len(self.patterns):
            raise _invalid("grammar pattern codes must be unique per structure")


@dataclass(frozen=True, slots=True)
class LexicalSenseRevision:
    sense_revision_id: UUID
    sense_id: UUID
    revision_no: int
    sense_code: str
    definition: str
    domains: tuple[str, ...]
    register: str | None
    status: ContentRevisionStatus
    provenance_id: UUID

    def __post_init__(self) -> None:
        require_uuid7(self.sense_revision_id, "sense_revision_id")
        require_uuid7(self.sense_id, "sense_id")
        require_uuid7(self.provenance_id, "provenance_id")
        require_revision_number(self.revision_no)
        require_stable_code(self.sense_code, "sense_code")
        if not self.definition or not self.domains:
            raise _invalid("lexical sense requires a definition and domain")


@dataclass(frozen=True, slots=True)
class FormAnalysis:
    form_analysis_id: UUID
    surface: str
    features: tuple[tuple[str, str], ...]
    pronunciation_refs: tuple[UUID, ...]
    normalization_key: str

    def __post_init__(self) -> None:
        require_uuid7(self.form_analysis_id, "form_analysis_id")
        if not self.surface:
            raise _invalid("surface form must be non-empty")
        expected_key = unicodedata.normalize("NFC", self.surface).casefold()
        if self.normalization_key != expected_key:
            raise _invalid("normalization key must preserve NFC diacritics")
        if len(dict(self.features)) != len(self.features):
            raise _invalid("morphological feature keys must be unique")
        for pronunciation_ref in self.pronunciation_refs:
            require_uuid7(pronunciation_ref, "pronunciation_refs")


@dataclass(frozen=True, slots=True)
class LexicalUnitRevision:
    unit_revision_id: UUID
    lexical_unit_id: UUID
    revision_no: int
    lemma: str
    unit_type: LexicalUnitType
    part_of_speech: str
    register: str | None
    senses: tuple[LexicalSenseRevision, ...]
    forms: tuple[FormAnalysis, ...]
    components: tuple[str, ...]
    status: ContentRevisionStatus
    provenance_id: UUID

    def __post_init__(self) -> None:
        require_uuid7(self.unit_revision_id, "unit_revision_id")
        require_uuid7(self.lexical_unit_id, "lexical_unit_id")
        require_uuid7(self.provenance_id, "provenance_id")
        require_revision_number(self.revision_no)
        if not self.lemma or not self.part_of_speech or not self.senses or not self.forms:
            raise _invalid("lexical unit revision is incomplete")
        if self.unit_type is LexicalUnitType.MULTIWORD_EXPRESSION:
            if len(self.components) < 2:
                raise _invalid("multiword expressions require ordered components")
        elif self.components:
            raise _invalid("only multiword expressions may have components")
        if len({sense.sense_code for sense in self.senses}) != len(self.senses):
            raise _invalid("lexical sense codes must be unique per unit")
        form_keys = {(form.surface, form.features) for form in self.forms}
        if len(form_keys) != len(self.forms):
            raise _invalid("form analyses must be unique per unit")


def _require_published(status: ContentRevisionStatus, field: str) -> None:
    if status is not ContentRevisionStatus.PUBLISHED:
        raise _invalid(f"{field} must be published")


def _require_checksum(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise _invalid(f"{field} must be a lowercase SHA-256 checksum")


def _foundation_checksum_part(value: object) -> str:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".15g")
    if isinstance(value, (tuple, list)):
        return "\x1e".join(_foundation_checksum_part(item) for item in value)
    return str(value)


def foundation_content_checksum(kind: str, *parts: object) -> str:
    payload = "\x1f".join((kind, *(_foundation_checksum_part(part) for part in parts)))
    return sha256(payload.encode()).hexdigest()


def _require_content_checksum(value: str, kind: str, *parts: object) -> None:
    _require_checksum(value, f"{kind} checksum")
    if value != foundation_content_checksum(kind, *parts):
        raise _invalid("foundation checksum does not match content")


@dataclass(frozen=True, slots=True)
class PublishedFoundationReference:
    reference_revision_id: UUID
    pack_revision_id: UUID
    reference_code: str
    reference_kind: FoundationReferenceKind
    status: ContentRevisionStatus
    checksum: str

    def __post_init__(self) -> None:
        require_uuid7(self.reference_revision_id, "reference_revision_id")
        require_uuid7(self.pack_revision_id, "pack_revision_id")
        require_stable_code(self.reference_code, "foundation reference_code")
        _require_published(self.status, "foundation reference")
        _require_content_checksum(
            self.checksum,
            "foundation_reference_v1",
            self.reference_revision_id,
            self.pack_revision_id,
            self.reference_code,
            self.reference_kind,
            self.status,
        )


@dataclass(frozen=True, slots=True)
class PublishedFoundationItem:
    item_revision_id: UUID
    block_revision_id: UUID
    pack_revision_id: UUID
    item_code: str
    ordinal: int
    target_refs: tuple[str, ...]
    response_kind: str
    checker_kind: FoundationCheckerKind
    checker_values: tuple[str, ...]
    modalities: tuple[str, ...]
    status: ContentRevisionStatus
    checksum: str

    def __post_init__(self) -> None:
        for field in ("item_revision_id", "block_revision_id", "pack_revision_id"):
            require_uuid7(getattr(self, field), field)
        require_stable_code(self.item_code, "item_code")
        if self.ordinal < 1:
            raise _invalid("foundation item ordinal must be positive")
        if not self.target_refs:
            raise _invalid("foundation item requires targets")
        for target_ref in self.target_refs:
            require_stable_code(target_ref, "foundation item target_ref")
        if self.response_kind != "raw":
            raise _invalid("foundation items accept raw answers only")
        if not self.modalities or any(item not in _MODALITIES for item in self.modalities):
            raise _invalid("foundation item modalities are not canonical")
        if self.checker_kind is FoundationCheckerKind.NOT_EVALUABLE:
            if self.checker_values:
                raise _invalid("not evaluable foundation items cannot declare checker values")
        elif not self.checker_values:
            raise _invalid("evaluable foundation items require a deterministic checker")
        _require_published(self.status, "foundation item")
        _require_content_checksum(
            self.checksum,
            "foundation_item_v1",
            self.item_revision_id,
            self.block_revision_id,
            self.pack_revision_id,
            self.item_code,
            self.ordinal,
            self.target_refs,
            self.response_kind,
            self.checker_kind,
            self.checker_values,
            self.modalities,
            self.status,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PublishedFoundationBlock:
    block_revision_id: UUID
    foundation_revision_id: UUID
    pack_revision_id: UUID
    block_code: str
    ordinal: int
    component_type: str
    prerequisite_refs: tuple[str, ...]
    items: tuple[PublishedFoundationItem, ...]
    modalities: tuple[str, ...]
    backend_criteria: tuple[str, ...]
    waiver_policy_ref: str
    status: ContentRevisionStatus
    checksum: str

    def __post_init__(self) -> None:
        for field in ("block_revision_id", "foundation_revision_id", "pack_revision_id"):
            require_uuid7(getattr(self, field), field)
        if fullmatch(r"F[1-5]", self.block_code) is None:
            raise _invalid("foundation block code must be F1 through F5")
        require_stable_code(self.component_type, "component_type")
        require_stable_code(self.waiver_policy_ref, "waiver_policy_ref")
        if self.ordinal < 1 or not self.items or not self.modalities or not self.backend_criteria:
            raise _invalid("foundation block is incomplete")
        if any(item not in _MODALITIES for item in self.modalities):
            raise _invalid("foundation block modalities are not canonical")
        if any(
            item.block_revision_id != self.block_revision_id
            or item.pack_revision_id != self.pack_revision_id
            for item in self.items
        ):
            raise _invalid("foundation items must belong to their published block")
        item_codes = {item.item_code for item in self.items}
        ordinals = {item.ordinal for item in self.items}
        if len(item_codes) != len(self.items) or len(ordinals) != len(self.items):
            raise _invalid("foundation item codes and ordinals must be unique per block")
        _require_published(self.status, "foundation block")
        _require_content_checksum(
            self.checksum,
            "foundation_block_v1",
            self.block_revision_id,
            self.foundation_revision_id,
            self.pack_revision_id,
            self.block_code,
            self.ordinal,
            self.component_type,
            self.prerequisite_refs,
            self.modalities,
            self.backend_criteria,
            self.waiver_policy_ref,
            self.status,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PublishedFoundationGate:
    gate_revision_id: UUID
    foundation_revision_id: UUID
    pack_revision_id: UUID
    gate_code: str
    blocking_target_refs: tuple[str, ...]
    blocking_facet_refs: tuple[str, ...]
    blocking_facet_minimum_status: str
    coverage_threshold: float
    confidence_threshold: float
    minimum_distinct_sessions: int
    delayed_control_block_code: str
    delayed_control_hours: int
    grapheme_sound_minimum: int
    grapheme_sound_total: int
    targeted_reading_minimum: int
    targeted_reading_total: int
    survival_exchange_minimum: int
    survival_exchange_total: int
    survival_exchange_without_reveal: bool
    oral_policy: str
    status: ContentRevisionStatus
    checksum: str

    def __post_init__(self) -> None:
        for field in ("gate_revision_id", "foundation_revision_id", "pack_revision_id"):
            require_uuid7(getattr(self, field), field)
        require_stable_code(self.gate_code, "gate_code")
        if not self.blocking_target_refs or not self.blocking_facet_refs:
            raise _invalid("foundation gate requires blocking targets and facets")
        for target_ref in self.blocking_target_refs:
            require_stable_code(target_ref, "foundation gate target_ref")
        if self.blocking_facet_refs != _FOUNDATION_BLOCKING_FACETS:
            raise _invalid("foundation gate must pin every blocking facet exactly")
        if self.blocking_facet_minimum_status != "reliable":
            raise _invalid("every blocking foundation facet must be reliable")
        if self.coverage_threshold != 1.0 or self.confidence_threshold != 0.6:
            raise _invalid("foundation gate aggregate thresholds are not canonical")
        if self.minimum_distinct_sessions != 2:
            raise _invalid("foundation gate requires exactly two distinct sessions")
        if self.delayed_control_block_code != "F1" or self.delayed_control_hours != 24:
            raise _invalid("foundation gate requires the F1 control after 24 hours")
        if (self.grapheme_sound_minimum, self.grapheme_sound_total) != (8, 10):
            raise _invalid("foundation gate requires 8/10 grapheme-sound discriminations")
        if (self.targeted_reading_minimum, self.targeted_reading_total) != (8, 10):
            raise _invalid("foundation gate requires 8/10 targeted readings")
        if (self.survival_exchange_minimum, self.survival_exchange_total) != (4, 5):
            raise _invalid("foundation gate requires 4/5 survival exchanges")
        if self.survival_exchange_without_reveal is not True:
            raise _invalid("survival exchanges must be completed without reveal")
        if self.oral_policy != "not_evaluable_non_blocking":
            raise _invalid("foundation oral policy is not canonical")
        _require_published(self.status, "foundation gate")
        _require_content_checksum(
            self.checksum,
            "foundation_gate_v1",
            self.gate_revision_id,
            self.foundation_revision_id,
            self.pack_revision_id,
            self.gate_code,
            self.blocking_target_refs,
            self.blocking_facet_refs,
            self.blocking_facet_minimum_status,
            self.coverage_threshold,
            self.confidence_threshold,
            self.minimum_distinct_sessions,
            self.delayed_control_block_code,
            self.delayed_control_hours,
            self.grapheme_sound_minimum,
            self.grapheme_sound_total,
            self.targeted_reading_minimum,
            self.targeted_reading_total,
            self.survival_exchange_minimum,
            self.survival_exchange_total,
            self.survival_exchange_without_reveal,
            self.oral_policy,
            self.status,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PublishedFoundationDefinition:
    foundation_id: UUID
    foundation_revision_id: UUID
    pack_revision_id: UUID
    foundation_code: str
    revision_no: int
    blocks: tuple[PublishedFoundationBlock, ...]
    gate: PublishedFoundationGate
    status: ContentRevisionStatus
    checksum: str

    def __post_init__(self) -> None:
        for field in ("foundation_id", "foundation_revision_id", "pack_revision_id"):
            require_uuid7(getattr(self, field), field)
        require_stable_code(self.foundation_code, "foundation_code")
        require_revision_number(self.revision_no)
        _require_published(self.status, "foundation definition")
        _require_content_checksum(
            self.checksum,
            "foundation_definition_v1",
            self.foundation_revision_id,
            self.foundation_id,
            self.pack_revision_id,
            self.foundation_code,
            self.revision_no,
            self.status,
        )
        if tuple((item.block_code, item.ordinal) for item in self.blocks) != (
            ("F1", 1),
            ("F2", 2),
            ("F3", 3),
            ("F4", 4),
            ("F5", 5),
        ):
            raise _invalid("Italian foundations require complete ordered blocks F1 through F5")
        if any(
            item.foundation_revision_id != self.foundation_revision_id
            or item.pack_revision_id != self.pack_revision_id
            for item in self.blocks
        ):
            raise _invalid("foundation blocks must belong to their published definition")
        if (
            self.gate.foundation_revision_id != self.foundation_revision_id
            or self.gate.pack_revision_id != self.pack_revision_id
            or self.gate.gate_code != self.foundation_code
        ):
            raise _invalid("foundation gate must belong to its published definition")
        targets = {
            target_ref
            for block in self.blocks
            for item in block.items
            if item.checker_kind is not FoundationCheckerKind.NOT_EVALUABLE
            for target_ref in item.target_refs
        }
        if set(self.gate.blocking_target_refs) != targets:
            raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PublishedFoundationCatalogue:
    definition: PublishedFoundationDefinition
    references: tuple[PublishedFoundationReference, ...]

    def __post_init__(self) -> None:
        if not self.references:
            raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
        reference_by_code = {item.reference_code: item for item in self.references}
        if len(reference_by_code) != len(self.references):
            raise _invalid("foundation reference codes must be unique per pack")
        if any(
            item.pack_revision_id != self.definition.pack_revision_id
            or item.status is not ContentRevisionStatus.PUBLISHED
            for item in self.references
        ):
            raise _invalid("foundation references must belong to the published pack")

        expected_kinds: dict[str, FoundationReferenceKind] = {}
        for block in self.definition.blocks:
            for reference in block.prerequisite_refs:
                expected_kinds[reference] = FoundationReferenceKind.TARGET
            for item in block.items:
                for reference in item.target_refs:
                    expected_kinds[reference] = FoundationReferenceKind.TARGET
            expected_kinds[block.waiver_policy_ref] = FoundationReferenceKind.WAIVER_POLICY
        for reference in self.definition.gate.blocking_target_refs:
            expected_kinds[reference] = FoundationReferenceKind.TARGET
        for reference in self.definition.gate.blocking_facet_refs:
            expected_kinds[reference] = FoundationReferenceKind.FACET

        if set(reference_by_code) != set(expected_kinds) or any(
            reference_by_code[code].reference_kind is not kind
            for code, kind in expected_kinds.items()
            if code in reference_by_code
        ):
            raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
