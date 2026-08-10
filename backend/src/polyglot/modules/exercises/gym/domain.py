from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.json_types import JsonValue


@dataclass(frozen=True, slots=True)
class GymOperationSpec:
    operation_id: str
    name: str
    prerequisite_kind: str
    primary_invariant: str


_OPERATION_SPECS = (
    GymOperationSpec("GYM-01", "lexical_substitution", "compatible_usage_frame", "structure"),
    GymOperationSpec("GYM-02", "person", "required_paradigm", "intention"),
    GymOperationSpec("GYM-03", "number_or_gender", "required_agreement", "referent"),
    GymOperationSpec("GYM-04", "polarity", "acquired_negation", "proposition"),
    GymOperationSpec("GYM-05", "interrogation", "acquired_question_type", "requested_info"),
    GymOperationSpec("GYM-06", "tense_or_aspect", "two_acquired_forms", "event"),
    GymOperationSpec("GYM-07", "modality", "acquired_modal_frames", "central_action"),
    GymOperationSpec(
        "GYM-08", "register_or_politeness", "acquired_pragmatic_contrast", "request"
    ),
    GymOperationSpec("GYM-09", "point_of_view", "acquired_persons_and_deictics", "situation"),
    GymOperationSpec(
        "GYM-10", "pronominalization", "acquired_complement_function", "referent"
    ),
    GymOperationSpec(
        "GYM-11", "combination", "acquired_connector_or_relative", "two_propositions"
    ),
    GymOperationSpec("GYM-12", "reduction_or_expansion", "acquired_variant", "semantic_core"),
    GymOperationSpec(
        "GYM-13", "idiomatic_reformulation", "published_contrast", "intention"
    ),
    GymOperationSpec("GYM-14", "calque_repair", "published_typed_error", "l1_intention"),
    GymOperationSpec(
        "GYM-15", "controlled_chain", "all_steps_acquired", "declared_invariants"
    ),
)
_SPEC_BY_ID = {spec.operation_id: spec for spec in _OPERATION_SPECS}
GYM_OPERATION_IDS = tuple(spec.operation_id for spec in _OPERATION_SPECS)


def operation_spec(operation_id: str) -> GymOperationSpec:
    try:
        return _SPEC_BY_ID[operation_id]
    except KeyError as error:
        raise DomainError(
            ErrorCode.MODE_UNSUPPORTED,
            detail=f"Unknown Gym operation: {operation_id}",
        ) from error


class PrerequisiteMode(StrEnum):
    ACQUIRED = "acquired"
    DISPENSED = "dispensed"
    SUPPORT = "support"


@dataclass(frozen=True, slots=True)
class PrerequisiteGrant:
    prerequisite_id: str
    mode: PrerequisiteMode

    def __post_init__(self) -> None:
        if not self.prerequisite_id:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Prerequisite id is required")

    @classmethod
    def acquired(cls, prerequisite_id: str) -> PrerequisiteGrant:
        return cls(prerequisite_id, PrerequisiteMode.ACQUIRED)

    @classmethod
    def dispensed(cls, prerequisite_id: str) -> PrerequisiteGrant:
        return cls(prerequisite_id, PrerequisiteMode.DISPENSED)

    @classmethod
    def support(cls, prerequisite_id: str) -> PrerequisiteGrant:
        return cls(prerequisite_id, PrerequisiteMode.SUPPORT)


@dataclass(frozen=True, slots=True)
class TransformationResult:
    case_id: str
    operation_id: str
    source_text: str
    output_text: str
    preserved_invariants: tuple[str, ...]
    non_evaluated_support: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TransformationCase:
    case_id: str
    revision_id: str
    operation_id: str
    source_text: str
    edits: tuple[tuple[str, str], ...]
    accepted_outputs: tuple[str, ...]
    rejected_outputs: tuple[str, ...]
    required_prerequisites: tuple[str, ...]
    invariants: tuple[str, ...]
    grammar_target_id: str
    lexical_support_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "edits",
            tuple((str(edit[0]), str(edit[1])) for edit in self.edits),
        )
        object.__setattr__(self, "accepted_outputs", tuple(self.accepted_outputs))
        object.__setattr__(self, "rejected_outputs", tuple(self.rejected_outputs))
        object.__setattr__(self, "required_prerequisites", tuple(self.required_prerequisites))
        object.__setattr__(self, "invariants", tuple(self.invariants))
        object.__setattr__(self, "lexical_support_ids", tuple(self.lexical_support_ids))
        operation_spec(self.operation_id)
        if not all(
            (self.case_id, self.revision_id, self.source_text, self.grammar_target_id)
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Gym case identity is incomplete")
        if not self.edits or not self.accepted_outputs or not self.required_prerequisites:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                detail="Gym case edits, outputs, and prerequisites are required",
            )
        if not self.invariants:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Gym invariants are required")
        for before, after in self.edits:
            if not before or not after or before == after:
                raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Gym edit is invalid")
        if set(self.accepted_outputs) & set(self.rejected_outputs):
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                detail="Accepted and rejected outputs must be disjoint",
            )

    @classmethod
    def published(cls, **values: Any) -> TransformationCase:
        return cls(**values)

    def execute(
        self,
        *,
        grants: tuple[PrerequisiteGrant, ...],
        proposed_output: str | None = None,
    ) -> TransformationResult:
        grant_by_id = {grant.prerequisite_id: grant for grant in grants}
        missing = sorted(set(self.required_prerequisites) - set(grant_by_id))
        if missing:
            missing_details = [cast(JsonValue, item) for item in missing]
            raise DomainError(
                ErrorCode.PREREQUISITE_MISSING,
                details={"missing": missing_details},
            )

        output = self.source_text
        for before, after in self.edits:
            if before not in output:
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED,
                    detail=f"Published edit source is absent: {before}",
                )
            output = output.replace(before, after, 1)
        candidate = output if proposed_output is None else proposed_output
        if candidate in self.rejected_outputs or candidate not in self.accepted_outputs:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                detail="Transformation output is outside the published accepted set",
            )
        support = tuple(
            prerequisite_id
            for prerequisite_id in self.required_prerequisites
            if grant_by_id[prerequisite_id].mode is PrerequisiteMode.SUPPORT
        )
        return TransformationResult(
            case_id=self.case_id,
            operation_id=self.operation_id,
            source_text=self.source_text,
            output_text=candidate,
            preserved_invariants=self.invariants,
            non_evaluated_support=support,
        )


def execute_transformation(
    case: TransformationCase,
    *,
    grants: tuple[PrerequisiteGrant, ...],
) -> TransformationResult:
    return case.execute(grants=grants)
