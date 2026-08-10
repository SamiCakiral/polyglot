from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from polyglot.modules.lexicon.memory.domain import (
    MemoryAggregate,
    MemoryReview,
    MemoryScheduleReset,
    MemoryScheduleResumption,
    MemoryScheduleState,
    schedule_projection,
)
from polyglot.modules.lexicon.memory.policy import SchedulerPolicy
from polyglot.modules.lexicon.memory.ports import (
    MemoryRating,
    MemorySchedulerPort,
    ScheduledState,
)
from polyglot.platform.errors import DomainError, ErrorCode

type MemoryFact = MemoryReview | MemoryScheduleReset | MemoryScheduleResumption
type ReplayKey = tuple[str, str, str, int]


@dataclass(frozen=True, slots=True)
class MemoryReplayBinding:
    scheduler: MemorySchedulerPort
    policy: SchedulerPolicy

    def __post_init__(self) -> None:
        identity = self.scheduler.identity
        if identity.parameter_set_id != self.policy.parameter_set_id:
            raise DomainError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                detail="scheduler policy parameter set mismatch",
            )

    @property
    def key(self) -> ReplayKey:
        identity = self.scheduler.identity
        return (
            identity.kind,
            identity.version,
            self.policy.parameter_set_id,
            self.policy.revision,
        )


class MemoryReplayResolver(Protocol):
    def resolve(
        self,
        scheduler_kind: str,
        scheduler_version: str,
        parameter_set_id: str,
        policy_revision: int,
    ) -> MemoryReplayBinding: ...


class StaticMemoryReplayResolver:
    def __init__(self, bindings: tuple[MemoryReplayBinding, ...]) -> None:
        self._bindings: dict[ReplayKey, MemoryReplayBinding] = {}
        for binding in bindings:
            if binding.key in self._bindings:
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED,
                    detail="duplicate replay binding",
                )
            self._bindings[binding.key] = binding

    def resolve(
        self,
        scheduler_kind: str,
        scheduler_version: str,
        parameter_set_id: str,
        policy_revision: int,
    ) -> MemoryReplayBinding:
        key = (scheduler_kind, scheduler_version, parameter_set_id, policy_revision)
        try:
            binding = self._bindings[key]
        except KeyError as error:
            raise DomainError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                detail="pinned scheduler policy is unavailable",
            ) from error
        if binding.key != key:
            raise DomainError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                detail="replay resolver returned a different scheduler policy",
            )
        return binding


def _binding_for_fact(
    resolver: MemoryReplayResolver,
    fact: MemoryFact,
) -> MemoryReplayBinding:
    return resolver.resolve(
        fact.scheduler_kind,
        fact.scheduler_version,
        fact.parameter_set_id,
        fact.policy_revision,
    )


def _fact_at(fact: MemoryFact) -> datetime:
    if isinstance(fact, MemoryReview):
        return fact.reviewed_at
    if isinstance(fact, MemoryScheduleReset):
        return fact.reset_at
    return fact.resumed_at


def _fact_id(fact: MemoryFact) -> UUID:
    if isinstance(fact, MemoryReview):
        return fact.review_id
    if isinstance(fact, MemoryScheduleReset):
        return fact.reset_id
    return fact.resumption_id


def _ordered_chain(
    facts: tuple[MemoryFact, ...],
    root_checkpoint: str,
    earliest_at: datetime | None,
) -> tuple[MemoryFact, ...]:
    by_previous: dict[str, MemoryFact] = {}
    for fact in facts:
        if fact.previous_checkpoint in by_previous:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                detail="causal history branches from one checkpoint",
            )
        by_previous[fact.previous_checkpoint] = fact

    ordered: list[MemoryFact] = []
    checkpoint = root_checkpoint
    previous_at = earliest_at
    while checkpoint in by_previous:
        fact = by_previous.pop(checkpoint)
        occurred_at = _fact_at(fact)
        if previous_at is not None and occurred_at < previous_at:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                detail="causal fact is backdated",
            )
        ordered.append(fact)
        checkpoint = fact.checkpoint
        previous_at = occurred_at
    if by_previous:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED,
            detail="causal checkpoint is missing",
        )
    return tuple(ordered)


def _validate_persisted_transition(
    fact: MemoryFact,
    binding: MemoryReplayBinding,
) -> None:
    if isinstance(fact, MemoryReview):
        transition = binding.scheduler.review(
            fact.state_before,
            fact.rating,
            fact.reviewed_at,
            binding.policy,
        )
        if transition.before != fact.state_before or transition.after != fact.state_after:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                detail="persisted review transition does not replay",
            )
    elif isinstance(fact, MemoryScheduleResumption):
        resumed = binding.scheduler.resume(
            fact.state_before,
            fact.resumed_at,
            binding.policy,
        )
        if resumed != fact.state_after:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                detail="persisted resumption does not replay",
            )


def _validate_chain_continuity(
    chain: tuple[MemoryFact, ...],
    initial_state: ScheduledState,
    resolver: MemoryReplayResolver,
) -> None:
    state = initial_state
    for fact in chain:
        binding = _binding_for_fact(resolver, fact)
        _validate_persisted_transition(fact, binding)
        if isinstance(fact, MemoryScheduleReset):
            state = binding.scheduler.initial_state(binding.policy, fact.reset_at)
            continue
        if fact.state_before != state:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                detail="persisted state is detached from causal checkpoint",
            )
        state = fact.state_after


@dataclass(slots=True)
class _ReplayState:
    state: ScheduledState
    binding: MemoryReplayBinding
    last_rating: MemoryRating | None
    last_review_id: UUID | None
    checkpoint: str
    computed_at: datetime


def _apply_fact(
    replay: _ReplayState,
    fact: MemoryFact,
    resolver: MemoryReplayResolver,
    seen_opportunities: set[UUID],
    seen_receipts: set[str],
) -> None:
    binding = _binding_for_fact(resolver, fact)
    _validate_persisted_transition(fact, binding)
    occurred_at = _fact_at(fact)
    replay.binding = binding
    replay.checkpoint = fact.checkpoint
    replay.computed_at = occurred_at
    if isinstance(fact, MemoryScheduleReset):
        replay.state = binding.scheduler.initial_state(binding.policy, occurred_at)
        replay.last_rating = None
        replay.last_review_id = None
        return
    if isinstance(fact, MemoryScheduleResumption):
        replay.state = binding.scheduler.resume(replay.state, occurred_at, binding.policy)
        return
    if (
        fact.opportunity_id in seen_opportunities
        or fact.idempotency_key in seen_receipts
    ):
        return
    seen_opportunities.add(fact.opportunity_id)
    seen_receipts.add(fact.idempotency_key)
    replay.state = binding.scheduler.review(
        replay.state,
        fact.rating,
        occurred_at,
        binding.policy,
    ).after
    replay.last_rating = fact.rating
    replay.last_review_id = fact.review_id


def rebuild_schedule(
    aggregate: MemoryAggregate,
    resolver: MemoryReplayResolver,
) -> MemoryScheduleState:
    prompt = aggregate.prompt
    prompt_binding = resolver.resolve(
        prompt.scheduler_kind,
        prompt.scheduler_version,
        prompt.parameter_set_id,
        prompt.policy_revision,
    )
    replay = _ReplayState(
        state=prompt_binding.scheduler.initial_state(prompt_binding.policy, prompt.created_at),
        binding=prompt_binding,
        last_rating=None,
        last_review_id=None,
        checkpoint=prompt.creation_checkpoint,
        computed_at=prompt.created_at,
    )
    facts: tuple[MemoryFact, ...] = (
        *aggregate.reviews,
        *aggregate.resets,
        *aggregate.resumptions,
    )
    facts_by_prompt: dict[UUID, list[MemoryFact]] = {}
    for fact in facts:
        facts_by_prompt.setdefault(fact.prompt_id, []).append(fact)

    seen_opportunities: set[UUID] = set()
    seen_receipts: set[str] = set()
    if not aggregate.lineages:
        ordered = _ordered_chain(
            tuple(facts_by_prompt.pop(prompt.prompt_id, ())),
            prompt.creation_checkpoint,
            prompt.created_at,
        )
        if facts_by_prompt:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="unowned causal history")
        _validate_chain_continuity(ordered, replay.state, resolver)
        for fact in ordered:
            _apply_fact(replay, fact, resolver, seen_opportunities, seen_receipts)
    else:
        merged_at_values = {lineage.merged_at for lineage in aggregate.lineages}
        if len(merged_at_values) != 1:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="inconsistent merge boundary")
        merged_at = next(iter(merged_at_values))
        source_events: list[tuple[datetime, int, int, MemoryFact]] = []
        for lineage in aggregate.lineages:
            source_facts = tuple(facts_by_prompt.pop(lineage.source_prompt_id, ()))
            created_checkpoint = f"created:{lineage.source_prompt_id}"
            merge_checkpoint = f"merge:{lineage.source_prompt_id}"
            root_checkpoint = (
                merge_checkpoint
                if any(fact.previous_checkpoint == merge_checkpoint for fact in source_facts)
                else created_checkpoint
            )
            chain = _ordered_chain(
                source_facts,
                root_checkpoint,
                lineage.source_created_at,
            )
            source_binding = resolver.resolve(
                lineage.source_scheduler_kind,
                lineage.source_scheduler_version,
                lineage.source_parameter_set_id,
                lineage.source_policy_revision,
            )
            source_initial = source_binding.scheduler.initial_state(
                source_binding.policy,
                lineage.source_created_at,
            )
            _validate_chain_continuity(chain, source_initial, resolver)
            source_events.extend(
                (_fact_at(fact), lineage.source_prompt_id.int, index, fact)
                for index, fact in enumerate(chain)
            )
        for occurred_at, _, _, fact in sorted(source_events, key=lambda item: item[:3]):
            if occurred_at > merged_at:
                raise DomainError(
                    ErrorCode.VALIDATION_FAILED,
                    detail="source fact occurs after merge",
                )
            _apply_fact(replay, fact, resolver, seen_opportunities, seen_receipts)

        merge_checkpoint = f"merge:{prompt.prompt_id}"
        replay.binding = prompt_binding
        replay.checkpoint = merge_checkpoint
        replay.computed_at = merged_at
        canonical_chain = _ordered_chain(
            tuple(facts_by_prompt.pop(prompt.prompt_id, ())),
            merge_checkpoint,
            merged_at,
        )
        if facts_by_prompt:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="unowned merge history")
        _validate_chain_continuity(canonical_chain, replay.state, resolver)
        for fact in canonical_chain:
            _apply_fact(replay, fact, resolver, seen_opportunities, seen_receipts)

    return schedule_projection(
        prompt_id=prompt.prompt_id,
        state=replay.state,
        policy=replay.binding.policy,
        scheduler=replay.binding.scheduler,
        projection_version=1 + len(facts) + (1 if aggregate.lineages else 0),
        computed_at=replay.computed_at,
        last_rating=replay.last_rating,
        last_review_id=replay.last_review_id,
        checkpoint=replay.checkpoint,
    )
