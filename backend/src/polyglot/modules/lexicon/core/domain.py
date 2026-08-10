import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode


def _invalid(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


def _uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise _invalid(f"{field} must be UUIDv7")


def _confidence(value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise _invalid("confidence must be between zero and one")


def normalize_surface(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).casefold().strip()
    if not normalized:
        raise _invalid("lexical surface must not be empty")
    return normalized


class LexicalUnitType(StrEnum):
    WORD = "word"
    MULTIWORD_EXPRESSION = "multiword_expression"
    PROPER_NAME = "proper_name"
    LEXICALIZED_CONSTRUCTION = "lexicalized_construction"


class LexicalRelationType(StrEnum):
    SYNONYM = "synonym"
    ANTONYM = "antonym"
    HYPERNYM = "hypernym"
    DERIVED = "derived"
    COMPOUND = "compound"
    CONFUSABLE = "confusable"
    TRANSLATION = "translation"
    REGISTER = "register"
    GRAMMAR_ASSOCIATION = "grammar_association"


@dataclass(frozen=True, slots=True)
class LexicalUnit:
    lexical_unit_id: UUID
    variety_id: UUID
    unit_type: LexicalUnitType
    lemma: str
    components: tuple[UUID, ...]
    visibility: str
    owner_profile_id: UUID | None = None

    def __post_init__(self) -> None:
        _uuid7(self.lexical_unit_id, "lexical_unit_id")
        _uuid7(self.variety_id, "variety_id")
        if self.visibility not in {"shared", "private"}:
            raise _invalid("lexical visibility is not canonical")
        if self.visibility == "shared" and self.owner_profile_id is not None:
            raise _invalid("shared units cannot have an owner")
        if self.visibility == "private" and self.owner_profile_id is None:
            raise _invalid("private units require an owner profile")
        if self.owner_profile_id is not None:
            _uuid7(self.owner_profile_id, "owner_profile_id")
        if self.unit_type is LexicalUnitType.MULTIWORD_EXPRESSION:
            if len(self.components) < 2:
                raise _invalid("multiword expressions require ordered components")
        elif self.components:
            raise _invalid("only multiword expressions may declare components")
        for component in self.components:
            _uuid7(component, "component lexical_unit_id")
        normalize_surface(self.lemma)

    @property
    def normalization_key(self) -> str:
        return normalize_surface(self.lemma)

    @property
    def identity_key(self) -> str:
        return f"unit:{self.lexical_unit_id}"


@dataclass(frozen=True, slots=True)
class LexicalSense:
    sense_id: UUID
    lexical_unit_id: UUID
    sense_code: str
    definition: str

    def __post_init__(self) -> None:
        _uuid7(self.sense_id, "sense_id")
        _uuid7(self.lexical_unit_id, "lexical_unit_id")
        if not self.sense_code or not self.definition:
            raise _invalid("lexical sense must be complete")

    @property
    def identity_key(self) -> str:
        return f"sense:{self.sense_id}"

    @property
    def normalized_label(self) -> str:
        return normalize_surface(self.sense_code.split(".", 1)[0])


@dataclass(frozen=True, slots=True)
class LexicalForm:
    form_id: UUID
    surface: str
    normalization_key: str
    analysis_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        _uuid7(self.form_id, "form_id")
        if self.normalization_key != normalize_surface(self.surface):
            raise _invalid("normalization key must match the exact surface")
        if not self.analysis_keys or len(set(self.analysis_keys)) != len(self.analysis_keys):
            raise _invalid("form analyses must be non-empty and unique")


@dataclass(frozen=True, slots=True)
class CandidateSense:
    candidate_id: UUID
    sense_id: UUID
    confidence: float
    source: str

    def __post_init__(self) -> None:
        _uuid7(self.candidate_id, "candidate_id")
        _uuid7(self.sense_id, "sense_id")
        _confidence(self.confidence)
        if not self.source:
            raise _invalid("candidate source is required")


@dataclass(frozen=True, slots=True)
class LexicalMention:
    mention_id: UUID
    encounter_id: UUID
    exact_surface: str
    form_id: UUID | None
    candidates: tuple[CandidateSense, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        _uuid7(self.mention_id, "mention_id")
        _uuid7(self.encounter_id, "encounter_id")
        if self.form_id is not None:
            _uuid7(self.form_id, "form_id")
        normalize_surface(self.exact_surface)
        candidate_ids = {item.candidate_id for item in self.candidates}
        if len(candidate_ids) != len(self.candidates):
            raise _invalid("candidate identifiers must be unique")
        if self.created_at.tzinfo is None:
            raise _invalid("mention timestamp must be timezone-aware")

    @property
    def is_ambiguous(self) -> bool:
        return len(self.candidates) != 1


@dataclass(frozen=True, slots=True)
class MentionResolution:
    resolution_id: UUID
    mention_id: UUID
    sense_id: UUID
    candidate_id: UUID | None
    resolver_type: str
    confidence: float
    created_at: datetime

    def __post_init__(self) -> None:
        _uuid7(self.resolution_id, "resolution_id")
        _uuid7(self.mention_id, "mention_id")
        _uuid7(self.sense_id, "sense_id")
        if self.candidate_id is not None:
            _uuid7(self.candidate_id, "candidate_id")
        if self.resolver_type not in {"user", "author", "deterministic", "import"}:
            raise _invalid("resolver type is not canonical")
        _confidence(self.confidence)
        if self.created_at.tzinfo is None:
            raise _invalid("resolution timestamp must be timezone-aware")

    def validate_against(self, mention: LexicalMention) -> None:
        if self.mention_id != mention.mention_id:
            raise _invalid("resolution does not belong to mention")
        candidates = {item.candidate_id: item.sense_id for item in mention.candidates}
        if self.candidate_id is None or candidates.get(self.candidate_id) != self.sense_id:
            raise _invalid("resolution must select a valid candidate")


@dataclass(frozen=True, slots=True)
class LexicalRelation:
    relation_id: UUID
    source_sense_id: UUID
    target_sense_id: UUID
    relation_type: LexicalRelationType
    direction: str
    provenance_ref: str
    confidence: float

    def __post_init__(self) -> None:
        _uuid7(self.relation_id, "relation_id")
        _uuid7(self.source_sense_id, "source_sense_id")
        _uuid7(self.target_sense_id, "target_sense_id")
        if self.source_sense_id == self.target_sense_id:
            raise _invalid("lexical relation cannot reference itself")
        if self.direction not in {"directed", "bidirectional"}:
            raise _invalid("relation direction is not canonical")
        if not self.provenance_ref:
            raise _invalid("relation provenance is required")
        _confidence(self.confidence)
