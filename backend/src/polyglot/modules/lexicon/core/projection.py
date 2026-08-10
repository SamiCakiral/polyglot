from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
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
    by_sense: dict[UUID, list[Evidence]] = {}
    for item in evidence:
        by_sense.setdefault(item.sense_id, []).append(item)
    result = []
    for sense_id in reference:
        facts = tuple(by_sense.get(sense_id, ()))
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


@dataclass(frozen=True, slots=True)
class RebuiltLexicalProjection:
    projection: LexicalProjection
    plan: LexicalPlanItem
    sprint_snapshot: SprintSnapshot
    debt: LexicalDebt | None
    gym: GymCredit
    learning_targets: tuple[UUID, ...]
    diagnostic_estimate: tuple[float, float] | None
    assessment: AssessmentScope
    recommendation: Recommendation | None


def rebuild_word_bank_projection(
    reference: tuple[UUID, ...],
    evidence: tuple[Evidence, ...],
    *,
    as_of: date,
    algorithm_version: str = "lexicon-v1",
) -> tuple[RebuiltLexicalProjection, ...]:
    """Rebuild every WB contract from immutable lexical facts."""
    projected = project_reference(
        reference, evidence, algorithm_version=algorithm_version
    )
    grouped_evidence: dict[UUID, list[Evidence]] = {}
    for item in evidence:
        grouped_evidence.setdefault(item.sense_id, []).append(item)
    evidence_by_sense = {
        sense_id: tuple(items) for sense_id, items in grouped_evidence.items()
    }
    plans = tuple(
        LexicalPlanItem(
            item.sense_id,
            "new" if "absence_of_evidence" in item.gap_reasons else (
                "debt" if item.gap_reasons else "target"
            ),
            item.gap_reasons[0] if item.gap_reasons else "consolidate",
        )
        for item in projected
    )
    snapshot = freeze_sprint_snapshot(
        plans,
        max_new=sum(item.role == "new" for item in plans),
        budget_minutes=60,
    )
    rebuilt: list[RebuiltLexicalProjection] = []
    for projection, plan in zip(projected, plans, strict=True):
        facts = evidence_by_sense.get(projection.sense_id, ())
        debt = (
            schedule_debt(projection.sense_id, due_on=as_of.isoformat())
            if projection.gap_reasons
            else None
        )
        if debt is not None:
            for fact in facts:
                debt = apply_debt_evidence(debt, fact)
        structure_success = any(
            fact.operation == "gym"
            and fact.result_state == "success"
            and fact.help_state == "none"
            for fact in facts
        )
        support_recalled = any(
            fact.role == "support"
            and fact.result_state == "success"
            and fact.help_state == "none"
            for fact in facts
        )
        selected_targets = validate_learning_targets(
            tokens=tuple(fact.sense_id for fact in facts),
            discriminant=tuple(
                dict.fromkeys(
                    fact.sense_id for fact in facts if fact.role == "target"
                )
            ),
            required=tuple(
                dict.fromkeys(
                    fact.sense_id for fact in facts if fact.role == "required"
                )
            ),
        )
        tested = (
            {
                projection.sense_id: (
                    sum(f.result_state == "success" for f in facts) / len(facts),
                    min(1.0, len(facts) / 3),
                )
            }
            if facts
            else {}
        )
        estimate = diagnostic_estimates(
            reference=reference, tested=tested
        ).get(projection.sense_id)
        assessment = AssessmentScope(
            tuple(modality for modality in _MODALITIES if any(
                fact.modality == modality for fact in facts
            )),
            ("form", "context", "retention") if facts else (),
        )
        recommendation = (
            Recommendation(
                projection.sense_id,
                plan.reason,
                projection.gap_reasons[0],
                as_of.isoformat(),
                "lexical_recall",
            )
            if projection.gap_reasons
            else None
        )
        rebuilt.append(
            RebuiltLexicalProjection(
                projection,
                plan,
                snapshot,
                debt,
                gym_credit(
                    structure_success=structure_success,
                    support_recalled=support_recalled,
                ),
                selected_targets,
                estimate,
                assessment,
                recommendation,
            )
        )
    return tuple(rebuilt)
