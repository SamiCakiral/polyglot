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
    required_parameters: tuple[str, ...]


_FORMS = ("before_form", "after_form")
_OPERATION_SPECS = (
    GymOperationSpec(
        "GYM-01",
        "lexical_substitution",
        "compatible_usage_frame",
        "structure",
        ("slot_id", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-02",
        "person",
        "required_paradigm",
        "intention",
        ("from_person", "to_person", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-03",
        "number_or_gender",
        "required_agreement",
        "referent",
        ("from_number", "to_number", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-04",
        "polarity",
        "acquired_negation",
        "proposition",
        ("marker", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-05",
        "interrogation",
        "acquired_question_type",
        "requested_info",
        ("question_type", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-06",
        "tense_or_aspect",
        "two_acquired_forms",
        "event",
        ("from_tense", "to_tense", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-07",
        "modality",
        "acquired_modal_frames",
        "central_action",
        ("from_modality", "to_modality", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-08",
        "register_or_politeness",
        "acquired_pragmatic_contrast",
        "request",
        ("from_register", "to_register", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-09",
        "point_of_view",
        "acquired_persons_and_deictics",
        "situation",
        ("from_viewpoint", "to_viewpoint", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-10",
        "pronominalization",
        "acquired_complement_function",
        "referent",
        ("from_reference", "to_reference", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-11",
        "combination",
        "acquired_connector_or_relative",
        "two_propositions",
        ("connector_id", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-12",
        "reduction_or_expansion",
        "acquired_variant",
        "semantic_core",
        ("direction", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-13",
        "idiomatic_reformulation",
        "published_contrast",
        "intention",
        ("source_frame", "target_frame", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-14",
        "calque_repair",
        "published_typed_error",
        "l1_intention",
        ("calque_id", "repair_frame", *_FORMS),
    ),
    GymOperationSpec(
        "GYM-15",
        "controlled_chain",
        "all_steps_acquired",
        "declared_invariants",
        ("step_operation_ids",),
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
class OperationSemantics:
    kind: str
    prerequisite_kind: str
    invariant_kind: str
    parameters: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parameters",
            tuple(sorted((str(name), str(value)) for name, value in self.parameters)),
        )
        names = tuple(name for name, _ in self.parameters)
        if not all((self.kind, self.prerequisite_kind, self.invariant_kind)):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Gym semantics are incomplete")
        if len(set(names)) != len(names) or any(
            not name or not value for name, value in self.parameters
        ):
            raise DomainError(
                ErrorCode.VALIDATION_FAILED, detail="Gym semantic parameters are invalid"
            )

    @classmethod
    def create(
        cls,
        *,
        kind: str,
        prerequisite_kind: str,
        invariant_kind: str,
        parameters: dict[str, str],
    ) -> OperationSemantics:
        return cls(kind, prerequisite_kind, invariant_kind, tuple(parameters.items()))

    def parameter(self, name: str) -> str:
        for key, value in self.parameters:
            if key == name:
                return value
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail=f"Missing semantic parameter: {name}")


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
    executed_semantic: str


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
    semantics: OperationSemantics
    secondary_target_ids: tuple[str, ...] = ()
    distractor_target_ids: tuple[str, ...] = ()

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
        object.__setattr__(self, "secondary_target_ids", tuple(self.secondary_target_ids))
        object.__setattr__(self, "distractor_target_ids", tuple(self.distractor_target_ids))
        spec = operation_spec(self.operation_id)
        if not all((self.case_id, self.revision_id, self.source_text, self.grammar_target_id)):
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
        _validate_semantics(self, spec)

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
            executed_semantic=self.semantics.kind,
        )


def execute_transformation(
    case: TransformationCase,
    *,
    grants: tuple[PrerequisiteGrant, ...],
) -> TransformationResult:
    return case.execute(grants=grants)


def _apply_edits(source: str, edits: tuple[tuple[str, str], ...]) -> str:
    output = source
    for before, after in edits:
        if before not in output:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                detail=f"Published edit source is absent: {before}",
            )
        output = output.replace(before, after, 1)
    return output


def _validate_semantics(case: TransformationCase, spec: GymOperationSpec) -> None:
    semantics = case.semantics
    if (
        semantics.kind != spec.name
        or semantics.prerequisite_kind != spec.prerequisite_kind
        or semantics.invariant_kind != spec.primary_invariant
    ):
        raise DomainError(
            ErrorCode.VALIDATION_FAILED,
            detail=f"{case.operation_id} semantic family does not match its registry contract",
        )
    parameter_names = {name for name, _ in semantics.parameters}
    if parameter_names != set(spec.required_parameters):
        raise DomainError(
            ErrorCode.VALIDATION_FAILED,
            detail=f"{case.operation_id} semantic parameters do not match its contract",
        )
    if case.operation_id == "GYM-15":
        step_ids = tuple(semantics.parameter("step_operation_ids").split(","))
        if (
            len(case.edits) < 2
            or len(step_ids) != len(case.edits)
            or any(step_id == "GYM-15" or step_id not in GYM_OPERATION_IDS for step_id in step_ids)
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Controlled chain is invalid")
    else:
        if len(case.edits) != 1:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                detail=f"{case.operation_id} requires exactly one semantic edit",
            )
        before, after = case.edits[0]
        if (
            semantics.parameter("before_form") != before
            or semantics.parameter("after_form") != after
        ):
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                detail=f"{case.operation_id} edit does not match semantic forms",
            )
    generated = _apply_edits(case.source_text, case.edits)
    if generated not in case.accepted_outputs:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED,
            detail=f"{case.operation_id} semantic execution has no published accepted output",
        )
    _validate_operation_constraints(case, semantics, generated)


def _validate_operation_constraints(
    case: TransformationCase,
    semantics: OperationSemantics,
    generated: str,
) -> None:
    paired_dimensions = {
        "GYM-02": ("from_person", "to_person"),
        "GYM-03": ("from_number", "to_number"),
        "GYM-06": ("from_tense", "to_tense"),
        "GYM-07": ("from_modality", "to_modality"),
        "GYM-08": ("from_register", "to_register"),
        "GYM-09": ("from_viewpoint", "to_viewpoint"),
        "GYM-10": ("from_reference", "to_reference"),
        "GYM-13": ("source_frame", "target_frame"),
    }
    pair = paired_dimensions.get(case.operation_id)
    if pair is not None and semantics.parameter(pair[0]) == semantics.parameter(pair[1]):
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Semantic dimension did not change")
    if case.operation_id == "GYM-04":
        marker = semantics.parameter("marker")
        before = semantics.parameter("before_form")
        after = semantics.parameter("after_form")
        if marker in before or marker not in after:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Polarity marker is invalid")
    elif case.operation_id == "GYM-05" and not generated.rstrip().endswith("?"):
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Interrogation must be executable")
    elif case.operation_id == "GYM-11":
        if semantics.parameter("connector_id").casefold() not in generated.casefold():
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Combination connector is absent")
    elif case.operation_id == "GYM-12":
        direction = semantics.parameter("direction")
        before = semantics.parameter("before_form")
        after = semantics.parameter("after_form")
        if direction == "expansion" and len(after) <= len(before):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Expansion did not expand")
        if direction == "reduction" and len(after) >= len(before):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Reduction did not reduce")
        if direction not in {"expansion", "reduction"}:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Variant direction is invalid")
    elif case.operation_id == "GYM-14":
        if not semantics.parameter("calque_id") or not semantics.parameter("repair_frame"):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="Calque repair is incomplete")
