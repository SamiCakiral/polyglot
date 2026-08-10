from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from polyglot.modules.exercises.core.domain import CORE_PRIMITIVE_IDS


def _is_gym_operation(value: str) -> bool:
    prefix, separator, number = value.partition("-")
    return prefix == "GYM" and separator == "-" and number.isdigit() and 1 <= int(number) <= 15


class CurriculumError(ValueError):
    pass


def _require_uuid7(value: UUID, field: str) -> None:
    if value.version != 7:
        raise CurriculumError(f"{field}: uuid7_required")


def _require_unique(values: tuple[object, ...], field: str) -> None:
    if len(values) != len(set(values)):
        raise CurriculumError(f"{field}: duplicate_reference")


class BindingRole(StrEnum):
    NEW = "new"
    DUE = "due"
    TARGET = "target"
    SUPPORT = "support"
    CONTRAST = "contrast"
    DISTRACTOR = "distractor"
    RESCUE = "rescue"
    EXTENSION = "extension"

    @property
    def credit_eligible(self) -> bool:
        return self in {self.NEW, self.DUE, self.TARGET, self.CONTRAST}


class PronunciationEvaluability(StrEnum):
    PERCEPTION = "perception"
    NOT_EVALUABLE = "not_evaluable"
    HUMAN_REVIEW = "human_review"


@dataclass(frozen=True, slots=True)
class SkillTargetBinding:
    skill_revision_id: UUID
    role: BindingRole
    modalities: tuple[str, ...]
    operations: tuple[str, ...]
    evidence_protocol_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        _require_uuid7(self.skill_revision_id, "skill_revision_id")
        object.__setattr__(self, "modalities", tuple(sorted(set(self.modalities))))
        object.__setattr__(self, "operations", tuple(sorted(set(self.operations))))
        object.__setattr__(self, "evidence_protocol_ids", tuple(self.evidence_protocol_ids))
        for value in self.evidence_protocol_ids:
            _require_uuid7(value, "evidence_protocol_id")
        if not self.modalities or not self.operations:
            raise CurriculumError("module_target_uncovered")
        if not self.role.credit_eligible and any(value == "credit" for value in self.operations):
            raise CurriculumError("module_support_lexicon_miscredited")

    @property
    def credit_eligible(self) -> bool:
        return self.role.credit_eligible


@dataclass(frozen=True, slots=True)
class LexiconTargetBinding:
    sense_revision_id: UUID
    role: BindingRole
    required_form_revision_ids: tuple[UUID, ...]
    usage_frame_revision_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        _require_uuid7(self.sense_revision_id, "sense_revision_id")
        object.__setattr__(
            self, "required_form_revision_ids", tuple(self.required_form_revision_ids)
        )
        object.__setattr__(self, "usage_frame_revision_ids", tuple(self.usage_frame_revision_ids))
        _require_unique(self.required_form_revision_ids, "required_form_revision_ids")
        _require_unique(self.usage_frame_revision_ids, "usage_frame_revision_ids")
        for value in (*self.required_form_revision_ids, *self.usage_frame_revision_ids):
            _require_uuid7(value, "lexicon_reference_id")

    @property
    def credit_eligible(self) -> bool:
        return self.role.credit_eligible


@dataclass(frozen=True, slots=True)
class GrammarTargetBinding:
    structure_revision_id: UUID
    pattern_ids: tuple[UUID, ...]
    function_skill_id: UUID
    role: BindingRole
    family_code: str
    allowed_operations: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_uuid7(self.structure_revision_id, "structure_revision_id")
        _require_uuid7(self.function_skill_id, "function_skill_id")
        object.__setattr__(self, "pattern_ids", tuple(self.pattern_ids))
        object.__setattr__(self, "allowed_operations", tuple(sorted(set(self.allowed_operations))))
        for value in self.pattern_ids:
            _require_uuid7(value, "pattern_id")
        if not self.family_code or not self.pattern_ids:
            raise CurriculumError("module_target_unresolved")
        if not self.allowed_operations or not all(
            _is_gym_operation(value) for value in self.allowed_operations
        ):
            raise CurriculumError("module_gym_without_w10_contract")

    @property
    def credit_eligible(self) -> bool:
        return self.role.credit_eligible


@dataclass(frozen=True, slots=True)
class MorphologyTargetBinding:
    form_analysis_id: UUID
    paradigm_code: str
    feature_bundle: tuple[tuple[str, str], ...]
    role: BindingRole
    allowed_operations: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_uuid7(self.form_analysis_id, "form_analysis_id")
        object.__setattr__(self, "feature_bundle", tuple(sorted(self.feature_bundle)))
        object.__setattr__(self, "allowed_operations", tuple(sorted(set(self.allowed_operations))))
        if not self.paradigm_code or not self.feature_bundle:
            raise CurriculumError("module_morphology_oracle_missing")
        if not set(self.allowed_operations).issubset(CORE_PRIMITIVE_IDS):
            raise CurriculumError("module_morphology_oracle_missing")

    @property
    def credit_eligible(self) -> bool:
        return self.role.credit_eligible


@dataclass(frozen=True, slots=True)
class PronunciationTargetBinding:
    target_revision_id: UUID
    contrast_code: str
    transcript_revision_id: UUID
    media_revision_id: UUID
    role: BindingRole
    evaluability: PronunciationEvaluability

    def __post_init__(self) -> None:
        for field, value in (
            ("target_revision_id", self.target_revision_id),
            ("transcript_revision_id", self.transcript_revision_id),
            ("media_revision_id", self.media_revision_id),
        ):
            _require_uuid7(value, field)
        if not self.contrast_code:
            raise CurriculumError("module_pronunciation_asset_incoherent")

    @property
    def credit_eligible(self) -> bool:
        return (
            self.role.credit_eligible and self.evaluability is PronunciationEvaluability.PERCEPTION
        )


@dataclass(frozen=True, slots=True)
class ExerciseBinding:
    definition_revision_id: UUID
    primitive_id: str
    target_bindings: tuple[str, ...]
    correction_policy_revision_id: UUID
    estimated_p50_ms: int
    estimated_p80_ms: int

    def __post_init__(self) -> None:
        _require_uuid7(self.definition_revision_id, "definition_revision_id")
        _require_uuid7(self.correction_policy_revision_id, "correction_policy_revision_id")
        object.__setattr__(self, "target_bindings", tuple(self.target_bindings))
        if self.primitive_id not in CORE_PRIMITIVE_IDS:
            raise CurriculumError("module_target_unresolved")
        if not self.target_bindings or not 0 < self.estimated_p50_ms <= self.estimated_p80_ms:
            raise CurriculumError("module_load_budget_exceeded")


@dataclass(frozen=True, slots=True)
class RecallSpec:
    target_ref: str
    due_rule: str
    source_day_ordinal: int
    source_exercise_binding_id: UUID
    minimum_help_level: str

    def __post_init__(self) -> None:
        _require_uuid7(self.source_exercise_binding_id, "source_exercise_binding_id")
        if (
            not self.target_ref
            or self.source_day_ordinal < 1
            or self.due_rule not in {"j+1", "spaced"}
        ):
            raise CurriculumError("module_recall_source_missing")
