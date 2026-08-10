from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

_PLAN_ROLES = frozenset(
    {"new", "due", "debt", "target", "support", "distractor", "rescue"}
)
_MODALITIES = ("reading", "listening", "writing", "speaking")


@dataclass(frozen=True, slots=True)
class Evidence:
    sense_id: UUID
    role: str
    modality: str
    operation: str
    help_state: str
    result_state: str
    context_ref: str
    correction_ref: str
    correction_confidence: float
    form_correct: bool
    context_correct: bool
    retention_correct: bool
    contradiction: bool

    def __post_init__(self) -> None:
        required = (
            self.role,
            self.modality,
            self.operation,
            self.help_state,
            self.result_state,
            self.context_ref,
            self.correction_ref,
        )
        if not all(required) or self.modality not in _MODALITIES:
            raise ValueError("incomplete lexical evidence")
        if not 0 <= self.correction_confidence <= 1:
            raise ValueError("invalid correction confidence")


@dataclass(frozen=True, slots=True)
class ModalityEvidence:
    observation_count: int
    success_count: int


@dataclass(frozen=True, slots=True)
class LexicalProjection:
    sense_id: UUID
    algorithm_version: str
    modalities: Mapping[str, ModalityEvidence]
    gap_reasons: tuple[str, ...]


def _gap_reasons(items: tuple[Evidence, ...]) -> tuple[str, ...]:
    if not items:
        return ("absence_of_evidence",)
    reasons: set[str] = set()
    if any(item.help_state != "none" for item in items):
        reasons.add("help_used")
    if any(item.result_state != "success" for item in items):
        reasons.add("result_gap")
    if any(not item.form_correct for item in items):
        reasons.add("form_gap")
    if any(not item.context_correct for item in items):
        reasons.add("context_gap")
    if any(not item.retention_correct for item in items):
        reasons.add("retention_gap")
    if any(item.contradiction for item in items):
        reasons.add("contradiction")
    return tuple(sorted(reasons))


def project_reference(
    reference: tuple[UUID, ...],
    evidence: tuple[Evidence, ...],
    *,
    algorithm_version: str,
) -> tuple[LexicalProjection, ...]:
    if not algorithm_version or len(set(reference)) != len(reference):
        raise ValueError("invalid reference projection")
    result = []
    for sense_id in reference:
        facts = tuple(item for item in evidence if item.sense_id == sense_id)
        modalities = {
            modality: ModalityEvidence(
                observation_count=sum(item.modality == modality for item in facts),
                success_count=sum(
                    item.modality == modality
                    and item.result_state == "success"
                    and item.help_state == "none"
                    for item in facts
                ),
            )
            for modality in _MODALITIES
        }
        result.append(
            LexicalProjection(
                sense_id,
                algorithm_version,
                MappingProxyType(modalities),
                _gap_reasons(facts),
            )
        )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class LexicalPlanItem:
    sense_id: UUID
    role: str
    reason: str

    def __post_init__(self) -> None:
        if self.role not in _PLAN_ROLES or not self.reason:
            raise ValueError("invalid lexical plan item")


@dataclass(frozen=True, slots=True)
class SprintSnapshot:
    items: tuple[LexicalPlanItem, ...]
    budget_minutes: int
    frozen: bool = True


def freeze_sprint_snapshot(
    items: tuple[LexicalPlanItem, ...], *, max_new: int, budget_minutes: int
) -> SprintSnapshot:
    if not 1 <= budget_minutes <= 60 or max_new < 0:
        raise ValueError("invalid sprint bounds")
    if sum(item.role == "new" for item in items) > max_new:
        raise ValueError("new lexical target bound exceeded")
    return SprintSnapshot(tuple(items), budget_minutes)


@dataclass(frozen=True, slots=True)
class LexicalDebt:
    sense_id: UUID
    due_on: str
    resolved: bool


def schedule_debt(sense_id: UUID, *, due_on: str) -> LexicalDebt:
    if not due_on:
        raise ValueError("due date required")
    return LexicalDebt(sense_id, due_on, False)


def apply_debt_evidence(debt: LexicalDebt, item: Evidence) -> LexicalDebt:
    resolved = (
        item.sense_id == debt.sense_id
        and item.result_state == "success"
        and item.help_state == "none"
    )
    return LexicalDebt(debt.sense_id, debt.due_on, resolved)


@dataclass(frozen=True, slots=True)
class GymCredit:
    structure: bool
    support_lexicon: bool


def gym_credit(*, structure_success: bool, support_recalled: bool) -> GymCredit:
    return GymCredit(structure_success, support_recalled)


def validate_learning_targets(
    *, tokens: tuple[UUID, ...], discriminant: tuple[UUID, ...], required: tuple[UUID, ...]
) -> tuple[UUID, ...]:
    token_set = set(tokens)
    selected = tuple(dict.fromkeys((*discriminant, *required)))
    if not set(selected) <= token_set:
        raise ValueError("learning target is absent from stimulus")
    return selected


def diagnostic_estimates(
    *, reference: tuple[UUID, ...], tested: Mapping[UUID, tuple[float, float]]
) -> Mapping[UUID, tuple[float, float]]:
    reference_set = set(reference)
    return MappingProxyType(
        {
            sense_id: estimate
            for sense_id, estimate in tested.items()
            if sense_id in reference_set
        }
    )


@dataclass(frozen=True, slots=True)
class AssessmentScope:
    modalities: tuple[str, ...]
    facets: tuple[str, ...]

    def accepts(self, modality: str, facet: str) -> bool:
        return modality in self.modalities and facet in self.facets


@dataclass(frozen=True, slots=True)
class Recommendation:
    target_id: UUID
    reason: str
    missing_evidence: str
    due_on: str
    proposed_activity: str

    def __post_init__(self) -> None:
        if not all(
            (self.reason, self.missing_evidence, self.due_on, self.proposed_activity)
        ):
            raise ValueError("recommendation explanation is incomplete")
