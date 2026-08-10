from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID

from .bindings import CurriculumError, _require_unique, _require_uuid7


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

    def __post_init__(self) -> None:
        _require_uuid7(self.module_day_id, "module_day_id")
        for field in (
            "objective_codes",
            "primary_target_refs",
            "encountered_target_refs",
            "output_target_refs",
            "required_block_roles",
            "new_grammar_family_codes",
            "explained_grammar_family_codes",
            "gym_grammar_family_codes",
        ):
            object.__setattr__(self, field, tuple(sorted(set(getattr(self, field)))))
        object.__setattr__(self, "modality_objectives", tuple(sorted(self.modality_objectives)))
        object.__setattr__(self, "content_revision_ids", tuple(self.content_revision_ids))
        object.__setattr__(
            self,
            "exercise_definition_revision_ids",
            tuple(self.exercise_definition_revision_ids),
        )
        object.__setattr__(
            self, "recall_source_day_ordinals", tuple(self.recall_source_day_ordinals)
        )
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
        if self.novelty_budget < 0 or (
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
        object.__setattr__(
            self, "entry_profile_codes", tuple(sorted(set(self.entry_profile_codes)))
        )
        object.__setattr__(self, "rights_refs", tuple(sorted(set(self.rights_refs))))
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
            values.update(f"content:{value}" for value in day.content_revision_ids)
            values.update(f"exercise:{value}" for value in day.exercise_definition_revision_ids)
        return tuple(sorted(values))
