from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID

from .bindings import (
    CurriculumError,
    ExerciseBinding,
    GrammarTargetBinding,
    LexiconTargetBinding,
    MorphologyTargetBinding,
    PronunciationTargetBinding,
    RecallSpec,
    SkillTargetBinding,
    _require_unique,
    _require_uuid7,
)


class ModuleStatus(StrEnum):
    DRAFT = "draft"
    MACHINE_VALID = "machine_valid"
    PUBLISHED = "published"
    RETIRED = "retired"


class ArcType(StrEnum):
    DISCOVERY = "discovery"
    GUIDED_USE = "guided_use"
    INTEGRATION = "integration"
    TRANSFER = "transfer"
    CONSOLIDATION = "consolidation"


@dataclass(frozen=True, slots=True)
class ModuleDay:
    module_day_id: UUID
    ordinal: int
    arc_type: ArcType
    objective_codes: tuple[str, ...]
    modality_objectives: tuple[tuple[str, str], ...]
    primary_target_refs: tuple[str, ...]
    encountered_target_refs: tuple[str, ...]
    output_target_refs: tuple[str, ...]
    minimum_useful_minutes: int
    novelty_budget: float
    required_block_roles: tuple[str, ...]
    new_grammar_family_codes: tuple[str, ...] = ()
    explained_grammar_family_codes: tuple[str, ...] = ()
    gym_grammar_family_codes: tuple[str, ...] = ()
    content_revision_ids: tuple[UUID, ...] = ()
    exercise_definition_revision_ids: tuple[UUID, ...] = ()
    recall_source_day_ordinals: tuple[int, ...] = ()
    secondary_target_refs: tuple[str, ...] = ()
    context_revision_ids: tuple[UUID, ...] = ()
    skill_bindings: tuple[SkillTargetBinding, ...] = ()
    lexicon_bindings: tuple[LexiconTargetBinding, ...] = ()
    grammar_bindings: tuple[GrammarTargetBinding, ...] = ()
    morphology_bindings: tuple[MorphologyTargetBinding, ...] = ()
    pronunciation_bindings: tuple[PronunciationTargetBinding, ...] = ()
    exercise_bindings: tuple[ExerciseBinding, ...] = ()
    recall_specs: tuple[RecallSpec, ...] = ()
    fallback_revision_ids: tuple[UUID, ...] = ()
    final_output_spec: str = ""
    validator_revision_ids: tuple[UUID, ...] = ()
    prerequisite_day_ordinals: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _require_uuid7(self.module_day_id, "module_day_id")
        canonical_string_fields = (
            "objective_codes",
            "primary_target_refs",
            "encountered_target_refs",
            "output_target_refs",
            "required_block_roles",
            "new_grammar_family_codes",
            "explained_grammar_family_codes",
            "gym_grammar_family_codes",
            "secondary_target_refs",
        )
        for field in canonical_string_fields:
            values = tuple(getattr(self, field))
            _require_unique(values, field)
            object.__setattr__(self, field, tuple(sorted(values)))
        modality_objectives = tuple(self.modality_objectives)
        _require_unique(modality_objectives, "modality_objectives")
        object.__setattr__(self, "modality_objectives", tuple(sorted(modality_objectives)))
        uuid_fields = (
            "content_revision_ids",
            "exercise_definition_revision_ids",
            "context_revision_ids",
            "fallback_revision_ids",
            "validator_revision_ids",
        )
        for field in uuid_fields:
            values = tuple(getattr(self, field))
            _require_unique(values, field)
            for value in values:
                _require_uuid7(value, field)
            object.__setattr__(self, field, values)
        binding_fields = (
            "skill_bindings",
            "lexicon_bindings",
            "grammar_bindings",
            "morphology_bindings",
            "pronunciation_bindings",
            "exercise_bindings",
            "recall_specs",
        )
        for field in binding_fields:
            values = tuple(getattr(self, field))
            _require_unique(values, field)
            object.__setattr__(self, field, values)
        recall_ordinals = tuple(self.recall_source_day_ordinals)
        _require_unique(recall_ordinals, "recall_source_day_ordinals")
        object.__setattr__(self, "recall_source_day_ordinals", recall_ordinals)
        prerequisites = tuple(self.prerequisite_day_ordinals)
        _require_unique(prerequisites, "prerequisite_day_ordinals")
        if any(value < 1 or value >= self.ordinal for value in prerequisites):
            raise CurriculumError("module_prerequisite_cycle")
        object.__setattr__(self, "prerequisite_day_ordinals", prerequisites)
        if self.ordinal < 1 or not self.objective_codes or not self.modality_objectives:
            raise CurriculumError("module_exit_unmeasurable")
        if not self.primary_target_refs:
            raise CurriculumError("module_target_uncovered")
        if not set(self.primary_target_refs).issubset(self.encountered_target_refs):
            raise CurriculumError("module_target_uncovered")
        if not set(self.primary_target_refs).issubset(self.output_target_refs):
            raise CurriculumError("module_target_uncovered")
        if self.minimum_useful_minutes < 10 or self.minimum_useful_minutes > 60:
            raise CurriculumError("module_load_budget_exceeded")
        if not math.isfinite(self.novelty_budget) or self.novelty_budget < 0 or (
            self.arc_type in {ArcType.TRANSFER, ArcType.CONSOLIDATION} and self.novelty_budget > 0
        ):
            raise CurriculumError("module_novelty_budget_exceeded")
        if len(self.new_grammar_family_codes) > 1:
            raise CurriculumError("module_multiple_new_grammar_families")
        if not set(self.new_grammar_family_codes).issubset(self.explained_grammar_family_codes):
            raise CurriculumError("module_new_structure_without_explanation")
        if not set(self.gym_grammar_family_codes).issubset(self.explained_grammar_family_codes):
            raise CurriculumError("module_new_structure_without_explanation")

    def as_dict(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class LearningModuleRevision:
    module_revision_id: UUID
    module_id: UUID
    revision_no: int
    status: ModuleStatus
    pack_revision_id: UUID
    target_variety_id: UUID
    support_variety_ids: tuple[UUID, ...]
    primary_intention: str
    final_mission_revision_id: UUID
    entry_profile_codes: tuple[str, ...]
    nominal_days: int
    max_days: int
    prerequisite_skill_revision_ids: tuple[UUID, ...]
    target_skill_revision_ids: tuple[UUID, ...]
    exit_policy_revision_id: UUID
    recall_policy_revision_id: UUID
    provenance_id: str
    rights_refs: tuple[str, ...]
    validator_set_revision_id: UUID
    schema_version: int
    compatibility_range: str
    days: tuple[ModuleDay, ...]
    reference_manifest_checksum: str = ""
    supersedes_revision_id: UUID | None = None
    payload_checksum: str = ""

    def __post_init__(self) -> None:
        for field in (
            "module_revision_id",
            "module_id",
            "pack_revision_id",
            "target_variety_id",
            "final_mission_revision_id",
            "exit_policy_revision_id",
            "recall_policy_revision_id",
            "validator_set_revision_id",
        ):
            _require_uuid7(getattr(self, field), field)
        for field in (
            "support_variety_ids",
            "prerequisite_skill_revision_ids",
            "target_skill_revision_ids",
        ):
            values = tuple(getattr(self, field))
            object.__setattr__(self, field, values)
            _require_unique(values, field)
            for value in values:
                _require_uuid7(value, field)
        _require_unique(self.entry_profile_codes, "entry_profile_codes")
        _require_unique(self.rights_refs, "rights_refs")
        object.__setattr__(self, "entry_profile_codes", tuple(sorted(self.entry_profile_codes)))
        object.__setattr__(self, "rights_refs", tuple(sorted(self.rights_refs)))
        object.__setattr__(self, "days", tuple(self.days))
        if self.supersedes_revision_id is not None:
            _require_uuid7(self.supersedes_revision_id, "supersedes_revision_id")
        if self.revision_no < 1 or self.schema_version < 1:
            raise CurriculumError("module_target_unresolved")
        if not 3 <= self.nominal_days <= self.max_days <= 30:
            raise CurriculumError("module_duration_out_of_range")
        if len(self.days) != self.nominal_days:
            raise CurriculumError("module_duration_out_of_range")
        if tuple(item.ordinal for item in self.days) != tuple(range(1, self.nominal_days + 1)):
            raise CurriculumError("module_day_ordinal_gap")
        if not self.primary_intention or not self.target_skill_revision_ids:
            raise CurriculumError("module_exit_unmeasurable")
        if not self.provenance_id:
            raise CurriculumError("module_provenance_missing")
        if not self.rights_refs:
            raise CurriculumError("module_rights_missing")
        object.__setattr__(self, "payload_checksum", self._checksum())

    def _checksum(self) -> str:
        payload = {
            "module_revision_id": str(self.module_revision_id),
            "module_id": str(self.module_id),
            "revision_no": self.revision_no,
            "status": self.status.value,
            "pack_revision_id": str(self.pack_revision_id),
            "target_variety_id": str(self.target_variety_id),
            "support_variety_ids": sorted(map(str, self.support_variety_ids)),
            "primary_intention": self.primary_intention,
            "final_mission_revision_id": str(self.final_mission_revision_id),
            "entry_profile_codes": sorted(self.entry_profile_codes),
            "nominal_days": self.nominal_days,
            "max_days": self.max_days,
            "prerequisite_skill_revision_ids": sorted(
                map(str, self.prerequisite_skill_revision_ids)
            ),
            "target_skill_revision_ids": sorted(map(str, self.target_skill_revision_ids)),
            "exit_policy_revision_id": str(self.exit_policy_revision_id),
            "recall_policy_revision_id": str(self.recall_policy_revision_id),
            "provenance_id": self.provenance_id,
            "rights_refs": sorted(self.rights_refs),
            "validator_set_revision_id": str(self.validator_set_revision_id),
            "schema_version": self.schema_version,
            "compatibility_range": self.compatibility_range,
            "reference_manifest_checksum": self.reference_manifest_checksum,
            "supersedes_revision_id": str(self.supersedes_revision_id)
            if self.supersedes_revision_id
            else None,
            "days": [
                {key: self._json_value(item) for key, item in day.as_dict().items()}
                for day in self.days
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    @staticmethod
    def _json_value(value: object) -> object:
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, tuple):
            return [LearningModuleRevision._json_value(item) for item in value]
        return value

    def recanonicalized(self) -> LearningModuleRevision:
        return replace(self, payload_checksum="")

    def all_reference_keys(self) -> tuple[str, ...]:
        values = {
            f"pack:{self.pack_revision_id}",
            f"variety:{self.target_variety_id}",
            f"mission:{self.final_mission_revision_id}",
            f"policy:{self.exit_policy_revision_id}",
            f"policy:{self.recall_policy_revision_id}",
            f"validator:{self.validator_set_revision_id}",
            *(f"variety:{value}" for value in self.support_variety_ids),
            *(f"skill:{value}" for value in self.prerequisite_skill_revision_ids),
            *(f"skill:{value}" for value in self.target_skill_revision_ids),
        }
        for day in self.days:
            values.update(day.primary_target_refs)
            values.update(day.secondary_target_refs)
            values.update(f"content:{value}" for value in day.content_revision_ids)
            values.update(f"exercise:{value}" for value in day.exercise_definition_revision_ids)
            values.update(f"context:{value}" for value in day.context_revision_ids)
            values.update(f"fallback:{value}" for value in day.fallback_revision_ids)
            values.update(f"validator:{value}" for value in day.validator_revision_ids)
            for skill_binding in day.skill_bindings:
                values.add(f"skill:{skill_binding.skill_revision_id}")
                values.update(
                    f"evidence:{value}"
                    for value in skill_binding.evidence_protocol_ids
                )
            for lexicon_binding in day.lexicon_bindings:
                values.add(f"sense:{lexicon_binding.sense_revision_id}")
                values.update(
                    f"form:{value}"
                    for value in lexicon_binding.required_form_revision_ids
                )
                values.update(
                    f"usage:{value}"
                    for value in lexicon_binding.usage_frame_revision_ids
                )
            for grammar_binding in day.grammar_bindings:
                values.add(f"grammar:{grammar_binding.structure_revision_id}")
                values.add(f"skill:{grammar_binding.function_skill_id}")
                values.update(
                    f"pattern:{value}" for value in grammar_binding.pattern_ids
                )
            for morphology_binding in day.morphology_bindings:
                values.add(f"analysis:{morphology_binding.form_analysis_id}")
            for pronunciation_binding in day.pronunciation_bindings:
                values.add(
                    f"pronunciation:{pronunciation_binding.target_revision_id}"
                )
                values.add(f"transcript:{pronunciation_binding.transcript_revision_id}")
                values.add(f"media:{pronunciation_binding.media_revision_id}")
            for exercise_binding in day.exercise_bindings:
                values.add(f"exercise:{exercise_binding.definition_revision_id}")
                values.add(
                    f"policy:{exercise_binding.correction_policy_revision_id}"
                )
            for recall in day.recall_specs:
                values.add(f"exercise:{recall.source_exercise_binding_id}")
        return tuple(sorted(values))
