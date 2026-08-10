from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

from polyglot.modules.exercises.core.domain import CorrectionVerdict, HintLevel
from polyglot.modules.exercises.gym.correction import TargetRole, correct_transformation
from polyglot.modules.exercises.gym.cycle import (
    G1Requirement,
    G1RequirementKind,
    GymCycle,
    GymStage,
)
from polyglot.modules.exercises.gym.domain import (
    GYM_OPERATION_IDS,
    OperationSemantics,
    PrerequisiteGrant,
    TransformationCase,
    operation_spec,
)
from polyglot.platform.errors import DomainError, ErrorCode


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Manifest(_StrictModel):
    id: Literal["FX-GYM-IT"]
    kind: Literal["positive"]
    expected_status: Literal["accepted"]


class _Metadata(_StrictModel):
    schema_version: Literal[1]
    synthetic: Literal[True]
    seed: int
    clock: datetime
    payloads: dict[str, str]
    oracles: tuple[str, ...]
    network_dependencies: tuple[str, ...]
    linguistic_review: Literal["pending_human"]


class _Operation(_StrictModel):
    operation_id: str
    case_id: str
    revision_id: str
    source_text: str
    edits: tuple[tuple[str, str], ...]
    accepted_output: str
    rejected_output: str
    prerequisites: tuple[str, ...]
    invariants: tuple[str, ...]
    grammar_target_id: str
    lexical_support_ids: tuple[str, ...]
    scenarios: tuple[str, ...]
    semantic_kind: str
    prerequisite_kind: str
    invariant_kind: str
    semantic_parameters: dict[str, str]


class _CycleOracle(_StrictModel):
    stage: GymStage
    offset_days: int
    context_id: str
    scene_id: str
    structure_cued: bool
    expected_credit: float
    g1_requirement_id: str | None = None


class _G1Requirement(_StrictModel):
    requirement_id: str
    kind: G1RequirementKind
    revision_id: UUID


class _Payload(_StrictModel):
    schema_version: Literal[1]
    fixture_id: Literal["FX-GYM-IT"]
    seed: int
    clock: datetime
    operations: tuple[_Operation, ...]
    g1_requirements: tuple[_G1Requirement, ...]
    cycle: tuple[_CycleOracle, ...]
    scenarios: frozenset[str]


@dataclass(frozen=True, slots=True)
class GymFixtureReport:
    operation_ids: tuple[str, ...]
    executed_positive: tuple[str, ...]
    executed_negative: tuple[str, ...]
    executed_missing_prerequisite: tuple[str, ...]
    executed_semantic_negative: tuple[str, ...]
    executed_semantic_constraints: tuple[str, ...]
    cycle_stages: tuple[str, ...]
    cycle_credits: tuple[float, ...]
    completed_g1_requirement_ids: tuple[str, ...]
    network_dependencies: tuple[str, ...]
    scenarios: frozenset[str]


def _failed(detail: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, detail=detail)


def _load(root: Path) -> tuple[_Metadata, _Payload]:
    try:
        manifest = _Manifest.model_validate_json((root / "manifest.json").read_text())
        metadata = _Metadata.model_validate_json((root / "fixture-metadata.json").read_text())
        payload_bytes = (root / "gym.json").read_bytes()
        payload = _Payload.model_validate_json(payload_bytes)
    except (OSError, ValidationError, ValueError) as error:
        raise _failed("FX-GYM-IT structure is invalid") from error
    if manifest.id != payload.fixture_id:
        raise _failed("FX-GYM-IT identity does not match")
    if metadata.seed != payload.seed or metadata.clock != payload.clock:
        raise _failed("FX-GYM-IT seed and clock must be pinned")
    if metadata.network_dependencies:
        raise _failed("FX-GYM-IT must be executable offline")
    if set(metadata.payloads) != {"gym.json"}:
        raise _failed("FX-GYM-IT payload manifest is not closed")
    expected_checksum = f"sha256:{hashlib.sha256(payload_bytes).hexdigest()}"
    if metadata.payloads["gym.json"] != expected_checksum:
        raise _failed("FX-GYM-IT payload checksum does not match")
    return metadata, payload


def _semantics(item: _Operation) -> OperationSemantics:
    return OperationSemantics.create(
        kind=item.semantic_kind,
        prerequisite_kind=item.prerequisite_kind,
        invariant_kind=item.invariant_kind,
        parameters=item.semantic_parameters,
    )


def _case(
    item: _Operation,
    *,
    semantics: OperationSemantics | None = None,
) -> TransformationCase:
    return TransformationCase.published(
        case_id=item.case_id,
        revision_id=item.revision_id,
        operation_id=item.operation_id,
        source_text=item.source_text,
        edits=item.edits,
        accepted_outputs=(item.accepted_output,),
        rejected_outputs=(item.rejected_output,),
        required_prerequisites=item.prerequisites,
        invariants=item.invariants,
        grammar_target_id=item.grammar_target_id,
        lexical_support_ids=item.lexical_support_ids,
        semantics=_semantics(item) if semantics is None else semantics,
    )


def _grants(item: _Operation) -> tuple[PrerequisiteGrant, ...]:
    return tuple(PrerequisiteGrant.acquired(value) for value in item.prerequisites)


def _roles(item: _Operation) -> dict[str, TargetRole]:
    return {
        item.grammar_target_id: TargetRole.PRINCIPAL,
        **{value: TargetRole.SUPPORT for value in item.lexical_support_ids},
    }


def _validate_operation(item: _Operation) -> None:
    case = _case(item)
    grants = _grants(item)
    transformed = case.execute(grants=grants)
    if transformed.output_text != item.accepted_output:
        raise _failed(f"{item.operation_id} positive transformation failed")
    try:
        case.execute(grants=grants, proposed_output=item.rejected_output)
    except DomainError as error:
        if error.code is not ErrorCode.VALIDATION_FAILED:
            raise
    else:
        raise _failed(f"{item.operation_id} negative oracle was accepted")
    try:
        case.execute(grants=())
    except DomainError as missing_error:
        if missing_error.code is not ErrorCode.PREREQUISITE_MISSING:
            raise
    else:
        raise _failed(f"{item.operation_id} missing prerequisite was accepted")
    operation_index = GYM_OPERATION_IDS.index(item.operation_id)
    hostile_spec = operation_spec(GYM_OPERATION_IDS[(operation_index + 1) % 15])
    hostile_semantics = OperationSemantics.create(
        kind=hostile_spec.name,
        prerequisite_kind=hostile_spec.prerequisite_kind,
        invariant_kind=hostile_spec.primary_invariant,
        parameters=item.semantic_parameters,
    )
    try:
        _case(item, semantics=hostile_semantics)
    except DomainError as semantic_error:
        if semantic_error.code is not ErrorCode.VALIDATION_FAILED:
            raise
    else:
        raise _failed(f"{item.operation_id} accepted another operation's semantics")
    incomplete_parameters = dict(item.semantic_parameters)
    incomplete_parameters.pop(next(iter(incomplete_parameters)))
    incomplete_semantics = OperationSemantics.create(
        kind=item.semantic_kind,
        prerequisite_kind=item.prerequisite_kind,
        invariant_kind=item.invariant_kind,
        parameters=incomplete_parameters,
    )
    try:
        _case(item, semantics=incomplete_semantics)
    except DomainError as constraint_error:
        if constraint_error.code is not ErrorCode.VALIDATION_FAILED:
            raise
    else:
        raise _failed(f"{item.operation_id} accepted incomplete semantic constraints")

    roles = _roles(item)
    positive = correct_transformation(
        case=case,
        proposed_output=item.accepted_output,
        grants=grants,
        stage=GymStage.G1,
        hint_level=HintLevel.H0,
        target_roles=roles,
    )
    negative = correct_transformation(
        case=case,
        proposed_output=item.rejected_output,
        grants=grants,
        stage=GymStage.G1,
        hint_level=HintLevel.H0,
        target_roles=roles,
    )
    ambiguous = correct_transformation(
        case=case,
        proposed_output=item.accepted_output,
        grants=grants,
        stage=GymStage.G1,
        hint_level=HintLevel.H0,
        target_roles=roles,
        ambiguous=True,
    )
    unavailable = correct_transformation(
        case=case,
        proposed_output=item.accepted_output,
        grants=grants,
        stage=GymStage.G1,
        hint_level=HintLevel.H0,
        target_roles=roles,
        correction_available=False,
    )
    revealed = correct_transformation(
        case=case,
        proposed_output=item.accepted_output,
        grants=grants,
        stage=GymStage.G1,
        hint_level=HintLevel.H4,
        target_roles=roles,
    )
    if (
        positive.verdict is not CorrectionVerdict.CORRECT
        or positive.credit_for(item.grammar_target_id) != 0.65
    ):
        raise _failed(f"{item.operation_id} positive correction oracle failed")
    if (
        negative.verdict is not CorrectionVerdict.INCORRECT
        or negative.credit_for(item.grammar_target_id) != -0.65
    ):
        raise _failed(f"{item.operation_id} negative correction oracle failed")
    if ambiguous.total_credit or unavailable.total_credit or revealed.total_credit:
        raise _failed(f"{item.operation_id} zero-credit policy failed")
    if any(positive.credit_for(value) != 0.0 for value in item.lexical_support_ids):
        raise _failed(f"{item.operation_id} lexical support received credit")


def _validate_cycle(
    payload: _Payload,
) -> tuple[tuple[str, ...], tuple[float, ...], tuple[str, ...]]:
    cycle = GymCycle.start(
        cycle_id=UUID("019fe010-3000-7000-8000-000000000001"),
        plan_revision_id=UUID("019fe010-3000-7000-8000-000000000002"),
        grammar_target_revision_id=UUID("019fe010-3000-7000-8000-000000000003"),
        started_at=payload.clock,
        g1_requirements=tuple(
            G1Requirement(item.requirement_id, item.kind, item.revision_id)
            for item in payload.g1_requirements
        ),
    )
    for index, oracle in enumerate(payload.cycle):
        if cycle.stage is not oracle.stage:
            raise _failed("FX-GYM-IT cycle stage order is invalid")
        cycle = cycle.record(
            verdict=CorrectionVerdict.CORRECT,
            hint_level=HintLevel.H0,
            context_id=oracle.context_id,
            scene_id=oracle.scene_id,
            structure_cued=oracle.structure_cued,
            recorded_at=payload.clock + timedelta(days=oracle.offset_days),
            idempotency_key=f"fixture:{oracle.stage.value}:{index}",
            g1_requirement_id=oracle.g1_requirement_id,
        )
        if cycle.records[-1].credit != oracle.expected_credit:
            raise _failed(f"FX-GYM-IT {oracle.stage.value} credit oracle failed")
    if not cycle.completed:
        raise _failed("FX-GYM-IT cycle did not reach transfer completion")
    return (
        tuple(dict.fromkeys(record.stage.value for record in cycle.records)),
        tuple(record.credit for record in cycle.records),
        cycle.completed_g1_requirement_ids,
    )


def validate_gym_fixture(root: Path) -> GymFixtureReport:
    metadata, payload = _load(root)
    operation_ids = tuple(item.operation_id for item in payload.operations)
    if operation_ids != GYM_OPERATION_IDS or len(set(operation_ids)) != 15:
        raise _failed("FX-GYM-IT must cover GYM-01 through GYM-15 exactly once")
    for item in payload.operations:
        _validate_operation(item)
    stages, credits, completed_g1 = _validate_cycle(payload)
    observed_scenarios = frozenset(
        scenario for item in payload.operations for scenario in item.scenarios
    )
    if not observed_scenarios.issubset(payload.scenarios):
        raise _failed("FX-GYM-IT operation scenarios are not declared")
    return GymFixtureReport(
        operation_ids=operation_ids,
        executed_positive=operation_ids,
        executed_negative=operation_ids,
        executed_missing_prerequisite=operation_ids,
        executed_semantic_negative=operation_ids,
        executed_semantic_constraints=operation_ids,
        cycle_stages=stages,
        cycle_credits=credits,
        completed_g1_requirement_ids=completed_g1,
        network_dependencies=metadata.network_dependencies,
        scenarios=payload.scenarios,
    )
