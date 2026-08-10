from __future__ import annotations

import hashlib
from collections.abc import Iterable
from itertools import chain, combinations
from uuid import UUID

from .domain import (
    CORE_ROLES,
    BlockFamily,
    CandidateBlock,
    PlannedBlock,
    PlanningSnapshot,
    PlanStatus,
    SessionPlan,
    SprintDomainError,
)

_FAMILY_ORDER = {
    BlockFamily.RECALL_WARMUP: 0,
    BlockFamily.DELAYED_RECODE: 0,
    BlockFamily.LEXICAL_ACQUISITION: 1,
    BlockFamily.VERSION_INPUT: 2,
    BlockFamily.LISTENING: 2,
    BlockFamily.GRAMMAR_TOOLBOX: 3,
    BlockFamily.TRANSFORMATION_GYM: 4,
    BlockFamily.SHADOWING: 5,
    BlockFamily.GUIDED_OUTPUT: 6,
    BlockFamily.FREE_WRITING: 6,
    BlockFamily.REFLECTION_CLOSE: 9,
}


def _subsets(
    values: tuple[CandidateBlock, ...], max_size: int
) -> Iterable[tuple[CandidateBlock, ...]]:
    return chain.from_iterable(combinations(values, size) for size in range(1, max_size + 1))


class DailySprintComposer:
    def compose(self, plan_id: UUID, snapshot: PlanningSnapshot) -> SessionPlan:
        candidates = tuple(item for item in snapshot.candidates if item.is_ready)
        best: tuple[tuple[float, int, str], tuple[CandidateBlock, ...]] | None = None
        for subset in _subsets(candidates, snapshot.max_blocks):
            ordered = self._valid_order(subset, snapshot)
            if ordered is None:
                continue
            score = self._score(ordered, snapshot)
            if best is None or score > best[0]:
                best = (score, ordered)
        if best is None:
            raise SprintDomainError("no_valid_composition")
        blocks = tuple(
            PlannedBlock(
                block_id=self._derived_uuid(plan_id, item.candidate_id, ordinal),
                candidate_id=item.candidate_id,
                ordinal=ordinal,
                family=item.family,
                roles=item.roles,
                p50_seconds=item.p50_seconds,
                p80_seconds=item.p80_seconds,
                novelty_points=item.novelty_points,
                modalities=item.modalities,
                reason_codes=self._reasons(item),
                target_refs=tuple(sorted(item.target_refs)),
                delayed_recode_id=item.delayed_recode_id,
                exercise_definition_revision_ids=item.exercise_definition_revision_ids,
                content_revision_ids=item.content_revision_ids,
            )
            for ordinal, item in enumerate(best[1], start=1)
        )
        revision_id = self._derived_uuid(plan_id, snapshot.snapshot_id, 0)
        return SessionPlan(
            plan_id=plan_id,
            revision_id=revision_id,
            snapshot=snapshot,
            blocks=blocks,
            status=PlanStatus.DRAFT,
        )

    def _valid_order(
        self,
        subset: tuple[CandidateBlock, ...],
        snapshot: PlanningSnapshot,
    ) -> tuple[CandidateBlock, ...] | None:
        roles = frozenset(role for item in subset for role in item.roles)
        if not CORE_ROLES.issubset(roles):
            return None
        if sum(item.p50_seconds for item in subset) > snapshot.content_budget_seconds:
            return None
        if sum(item.p80_seconds for item in subset) > snapshot.budget_minutes * 60:
            return None
        if sum(item.novelty_points for item in subset) > snapshot.novelty_limit:
            return None
        grammar_families = {item.grammar_family for item in subset if item.grammar_family}
        if len(grammar_families) > 1:
            return None
        due = set(snapshot.due_delayed_recode_ids)
        if due and not any(item.delayed_recode_id in due for item in subset):
            return None
        available = set(snapshot.mastered_refs)
        remaining = list(subset)
        ordered: list[CandidateBlock] = []
        while remaining:
            admissible = [item for item in remaining if item.requires_refs.issubset(available)]
            if not admissible:
                return None
            chosen = min(
                admissible,
                key=lambda item: (
                    _FAMILY_ORDER[item.family],
                    self._tie(snapshot.seed, item.candidate_id),
                ),
            )
            ordered.append(chosen)
            available.update(chosen.teaches_refs)
            remaining.remove(chosen)
        return tuple(ordered)

    def _score(
        self,
        ordered: tuple[CandidateBlock, ...],
        snapshot: PlanningSnapshot,
    ) -> tuple[float, int, str]:
        due = set(snapshot.due_delayed_recode_ids)
        priority = sum(item.priority for item in ordered)
        priority += 100 * sum(item.delayed_recode_id in due for item in ordered)
        priority += 0.001 * len(frozenset(item.family for item in ordered))
        used_seconds = sum(item.p50_seconds for item in ordered)
        digest = hashlib.sha256(
            (snapshot.seed + ":" + ":".join(str(item.candidate_id) for item in ordered)).encode()
        ).hexdigest()
        return (round(priority, 9), used_seconds, digest)

    @staticmethod
    def _tie(seed: str, candidate_id: UUID) -> str:
        return hashlib.sha256(f"{seed}:{candidate_id}".encode()).hexdigest()

    @staticmethod
    def _derived_uuid(plan_id: UUID, reference_id: UUID, ordinal: int) -> UUID:
        digest = bytearray(
            hashlib.sha256(f"{plan_id}:{reference_id}:{ordinal}".encode()).digest()[:16]
        )
        digest[0:6] = plan_id.bytes[0:6]
        digest[6] = (digest[6] & 0x0F) | 0x70
        digest[8] = (digest[8] & 0x3F) | 0x80
        return UUID(bytes=bytes(digest))

    @staticmethod
    def _reasons(item: CandidateBlock) -> tuple[str, ...]:
        reasons: set[str] = set()
        if item.delayed_recode_id is not None:
            reasons.add("delayed_recode_due")
        if "activation" in item.roles:
            reasons.add("required_activation")
        if "primary_objective" in item.roles:
            reasons.add("module_primary_objective")
        if "unsupported_production" in item.roles:
            reasons.add("unsupported_production")
        if "reflection" in item.roles:
            reasons.add("required_reflection")
        if item.debt_urgency:
            reasons.add("lexical_debt")
        if item.modality_balance:
            reasons.add("modality_balance")
        if not reasons:
            reasons.add("ranked_candidate")
        return tuple(sorted(reasons))


__all__ = ["DailySprintComposer"]
