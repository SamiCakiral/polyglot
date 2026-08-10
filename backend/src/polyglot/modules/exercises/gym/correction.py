from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from polyglot.modules.exercises.core.domain import (
    CorrectionResult,
    CorrectionVerdict,
    HintLevel,
)
from polyglot.modules.exercises.gym.cycle import GymStage
from polyglot.modules.exercises.gym.domain import PrerequisiteGrant, TransformationCase
from polyglot.platform.errors import DomainError, ErrorCode


class TargetRole(StrEnum):
    PRINCIPAL = "principal"
    SECONDARY = "secondary"
    SUPPORT = "support"
    DISTRACTOR = "distractor"


_STAGE_CAPS = {
    GymStage.G0: 0.0,
    GymStage.G1: 0.65,
    GymStage.G2: 0.55,
    GymStage.G3: 0.65,
    GymStage.G4: 1.0,
}
_ROLE_WEIGHTS = {
    TargetRole.PRINCIPAL: 1.0,
    TargetRole.SECONDARY: 0.65,
    TargetRole.SUPPORT: 0.0,
    TargetRole.DISTRACTOR: 0.0,
}


@dataclass(frozen=True, slots=True)
class GymTargetCredit:
    target_id: str
    role: TargetRole
    value: float


@dataclass(frozen=True, slots=True)
class GymCorrectionReport:
    verdict: CorrectionVerdict
    target_credits: tuple[GymTargetCredit, ...]
    explanation: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_credits", tuple(self.target_credits))

    @property
    def total_credit(self) -> float:
        return sum(item.value for item in self.target_credits)

    def credit_for(self, target_id: str) -> float:
        for item in self.target_credits:
            if item.target_id == target_id:
                return item.value
        raise DomainError(ErrorCode.NOT_FOUND, detail=f"Unknown Gym target: {target_id}")


def _result_for(
    *,
    case: TransformationCase,
    proposed_output: str,
    grants: tuple[PrerequisiteGrant, ...],
    correction_available: bool,
    ambiguous: bool,
) -> CorrectionResult:
    if not correction_available:
        return CorrectionResult.not_evaluable("controlled Gym corrector is unavailable")
    if ambiguous:
        return CorrectionResult.ambiguous("published Gym outputs are ambiguous")
    if not proposed_output:
        return CorrectionResult(
            CorrectionVerdict.INVALID_ANSWER,
            1.0,
            0.0,
            "Gym answer is empty",
            "gym_controlled",
        )
    if proposed_output in case.accepted_outputs:
        case.execute(grants=grants, proposed_output=proposed_output)
        verdict = CorrectionVerdict.CORRECT
    else:
        granted_ids = {grant.prerequisite_id for grant in grants}
        missing = set(case.required_prerequisites) - granted_ids
        if missing:
            case.execute(grants=grants, proposed_output=proposed_output)
        verdict = CorrectionVerdict.INCORRECT
    return CorrectionResult(
        verdict=verdict,
        confidence=1.0,
        target_coverage=1.0,
        explanation="controlled published Gym output",
        strategy="gym_controlled",
    )


def correct_transformation(
    *,
    case: TransformationCase,
    proposed_output: str,
    grants: tuple[PrerequisiteGrant, ...],
    stage: GymStage,
    hint_level: HintLevel,
    target_roles: Mapping[str, TargetRole],
    correction_available: bool = True,
    ambiguous: bool = False,
) -> GymCorrectionReport:
    frozen_roles = tuple(
        sorted((target_id, TargetRole(role)) for target_id, role in target_roles.items())
    )
    if case.grammar_target_id not in target_roles:
        raise DomainError(ErrorCode.OBSERVATION_TARGET_NOT_DISCRIMINANT)
    for support_id in case.lexical_support_ids:
        role = target_roles.get(support_id)
        if role is not None and role is not TargetRole.SUPPORT:
            raise DomainError(
                ErrorCode.EVIDENCE_SCOPE_FORBIDDEN,
                detail="Lexical support cannot be promoted by a Gym correction",
            )
    result = _result_for(
        case=case,
        proposed_output=proposed_output,
        grants=grants,
        correction_available=correction_available,
        ambiguous=ambiguous,
    )
    credits = tuple(
        GymTargetCredit(
            target_id=target_id,
            role=role,
            value=(
                result.credit_value(
                    operation_cap=_STAGE_CAPS[stage],
                    target_weight=_ROLE_WEIGHTS[role],
                    hint_level=hint_level.value,
                )
                or 0.0
            ),
        )
        for target_id, role in frozen_roles
    )
    return GymCorrectionReport(result.verdict, credits, result.explanation)
