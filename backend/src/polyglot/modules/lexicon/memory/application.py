from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from polyglot.modules.lexicon.memory.domain import (
    MemoryAggregate,
    MemoryPrompt,
    MemoryPromptLineage,
    MemoryReview,
    MemoryScheduleReset,
    MemoryScheduleState,
    PromptStatus,
)
from polyglot.modules.lexicon.memory.policy import (
    HintLevel,
    ReviewVerdict,
    SchedulerPolicy,
    allowed_ratings,
)
from polyglot.modules.lexicon.memory.ports import (
    MemoryRating,
    MemorySchedulerPort,
    ScheduledState,
)
from polyglot.platform.errors import DomainError, ErrorCode


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, detail="datetime must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class CreateMemoryPrompt:
    prompt_id: UUID
    profile_id: UUID
    target_ref: UUID
    target_revision_id: UUID
    direction: str
    modality: str
    operation: str
    protocol_id: str
    protocol_revision: int
    rating_semantics_id: str
    scheduler_policy_id: UUID
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SubmitMemoryReview:
    review_id: UUID
    opportunity_id: UUID
    attempt_id: UUID | None
    response_ref: str | None
    correction_ref: str | None
    verdict: ReviewVerdict
    highest_hint: HintLevel
    rating: MemoryRating
    certified_recall: bool
    answer_revealed: bool
    exposure_only: bool
    incidental_production: bool
    self_reported: bool
    active_duration_ms: int
    scheduled_at: datetime
    reviewed_at: datetime
    idempotency_key: str
    certification_ref: str
    certified_operation: str
    certified_protocol_id: str
    certified_protocol_revision: int
    certified_target_revision_id: UUID

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResetMemoryPrompt:
    reset_id: UUID
    reason: str
    reset_at: datetime


@dataclass(frozen=True, slots=True)
class ArchiveMemoryPrompt:
    archived_at: datetime


@dataclass(frozen=True, slots=True)
class RestoreMemoryPrompt:
    restored_at: datetime
    target_revision_available: bool


@dataclass(frozen=True, slots=True)
class DeleteMemoryPrompt:
    deleted_at: datetime
    reauthenticated: bool


@dataclass(frozen=True, slots=True)
class MergeMemoryPrompts:
    canonical_prompt_id: UUID
    sources: tuple[MemoryAggregate, ...]
    merged_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    aggregate: MemoryAggregate
    review_created: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class MergeResult:
    canonical: MemoryAggregate
    sources: tuple[MemoryAggregate, ...]


def _projection(
    *,
    prompt_id: UUID,
    state: ScheduledState,
    policy: SchedulerPolicy,
    scheduler: MemorySchedulerPort,
    projection_version: int,
    computed_at: datetime,
    last_rating: MemoryRating | None,
    last_review_id: UUID | None,
    checkpoint: str,
) -> MemoryScheduleState:
    return MemoryScheduleState(
        prompt_id=prompt_id,
        scheduler_kind=scheduler.identity.kind,
        scheduler_version=scheduler.identity.version,
        parameter_set_id=policy.parameter_set_id,
        policy_revision=policy.revision,
        state=state.state,
        difficulty=state.difficulty,
        stability=state.stability,
        desired_retention=policy.desired_retention,
        last_review_at=state.last_review_at,
        due_at=state.due_at,
        reps=state.reps,
        lapses=state.lapses,
        last_rating=last_rating,
        last_review_id=last_review_id,
        projection_version=projection_version,
        computed_at=_utc(computed_at),
        causal_checkpoint=checkpoint,
        step=state.step,
    )


class MemoryLifecycle:
    def __init__(self, scheduler: MemorySchedulerPort) -> None:
        self._scheduler = scheduler

    def create(self, command: CreateMemoryPrompt, policy: SchedulerPolicy) -> MemoryAggregate:
        created_at = _utc(command.created_at)
        identity = self._scheduler.identity
        if identity.parameter_set_id != policy.parameter_set_id:
            raise DomainError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                detail="scheduler does not provide the requested parameter set",
            )
        prompt = MemoryPrompt(
            prompt_id=command.prompt_id,
            profile_id=command.profile_id,
            target_ref=command.target_ref,
            target_revision_id=command.target_revision_id,
            direction=command.direction,
            modality=command.modality,
            operation=command.operation,
            protocol_id=command.protocol_id,
            protocol_revision=command.protocol_revision,
            rating_semantics_id=command.rating_semantics_id,
            scheduler_policy_id=command.scheduler_policy_id,
            scheduler_kind=identity.kind,
            scheduler_version=identity.version,
            parameter_set_id=policy.parameter_set_id,
            policy_revision=policy.revision,
            status=PromptStatus.ACTIVE,
            version=1,
            created_at=created_at,
            updated_at=created_at,
        )
        initial = self._scheduler.initial_state(policy, created_at)
        schedule = _projection(
            prompt_id=prompt.prompt_id,
            state=initial,
            policy=policy,
            scheduler=self._scheduler,
            projection_version=1,
            computed_at=created_at,
            last_rating=None,
            last_review_id=None,
            checkpoint="created",
        )
        return MemoryAggregate(prompt, schedule)

    def submit_review(
        self,
        aggregate: MemoryAggregate,
        command: SubmitMemoryReview,
        policy: SchedulerPolicy,
    ) -> ReviewDecision:
        self._require_status(aggregate, {PromptStatus.ACTIVE})
        self._require_binding(aggregate, policy)
        if not self._certification_matches(aggregate.prompt, command):
            return ReviewDecision(aggregate, False, "operation_not_certified")
        if command.answer_revealed:
            return ReviewDecision(aggregate, False, "answer_revealed")
        if command.exposure_only:
            return ReviewDecision(aggregate, False, "exposure_only")
        if command.incidental_production:
            return ReviewDecision(aggregate, False, "incidental_production")
        ratings = allowed_ratings(command.verdict, command.highest_hint)
        if not ratings:
            return ReviewDecision(aggregate, False, "not_evaluable")
        if command.rating not in ratings:
            raise DomainError(ErrorCode.RATING_NOT_ALLOWED)
        if any(
            review.opportunity_id == command.opportunity_id
            or review.idempotency_key == command.idempotency_key
            for review in aggregate.reviews
        ):
            return ReviewDecision(aggregate, False, "duplicate")
        if _utc(command.reviewed_at) < aggregate.schedule.computed_at:
            raise DomainError(
                ErrorCode.REVIEW_CONFLICT,
                detail="review predates the current causal checkpoint",
            )

        transition = self._scheduler.review(
            aggregate.schedule.scheduled_state(),
            command.rating,
            command.reviewed_at,
            policy,
        )
        identity = self._scheduler.identity
        review = MemoryReview(
            review_id=command.review_id,
            prompt_id=aggregate.prompt.prompt_id,
            opportunity_id=command.opportunity_id,
            attempt_id=command.attempt_id,
            response_ref=command.response_ref,
            correction_ref=command.correction_ref,
            highest_hint=int(command.highest_hint),
            active_duration_ms=command.active_duration_ms,
            scheduled_at=command.scheduled_at,
            reviewed_at=command.reviewed_at,
            rating=command.rating,
            state_before=transition.before,
            state_after=transition.after,
            scheduler_kind=identity.kind,
            scheduler_version=identity.version,
            parameter_set_id=policy.parameter_set_id,
            policy_revision=policy.revision,
            idempotency_key=command.idempotency_key,
            low_confidence=command.self_reported,
            certification_ref=command.certification_ref,
            certified_operation=command.certified_operation,
            certified_protocol_id=command.certified_protocol_id,
            certified_protocol_revision=command.certified_protocol_revision,
            certified_target_revision_id=command.certified_target_revision_id,
        )
        schedule = _projection(
            prompt_id=aggregate.prompt.prompt_id,
            state=transition.after,
            policy=policy,
            scheduler=self._scheduler,
            projection_version=aggregate.schedule.projection_version + 1,
            computed_at=command.reviewed_at,
            last_rating=command.rating,
            last_review_id=command.review_id,
            checkpoint=f"review:{command.review_id}",
        )
        return ReviewDecision(
            replace(
                aggregate,
                prompt=replace(
                    aggregate.prompt,
                    version=aggregate.prompt.version + 1,
                    updated_at=_utc(command.reviewed_at),
                ),
                schedule=schedule,
                reviews=(*aggregate.reviews, review),
            ),
            True,
        )

    def suspend(self, aggregate: MemoryAggregate, at: datetime) -> MemoryAggregate:
        self._require_status(aggregate, {PromptStatus.ACTIVE})
        return replace(aggregate, prompt=aggregate.prompt.transition(PromptStatus.SUSPENDED, at))

    def resume(
        self,
        aggregate: MemoryAggregate,
        at: datetime,
        policy: SchedulerPolicy,
    ) -> MemoryAggregate:
        self._require_status(aggregate, {PromptStatus.SUSPENDED})
        resumed = self._scheduler.resume(aggregate.schedule.scheduled_state(), at, policy)
        schedule = _projection(
            prompt_id=aggregate.prompt.prompt_id,
            state=resumed,
            policy=policy,
            scheduler=self._scheduler,
            projection_version=aggregate.schedule.projection_version + 1,
            computed_at=at,
            last_rating=aggregate.schedule.last_rating,
            last_review_id=aggregate.schedule.last_review_id,
            checkpoint=aggregate.schedule.causal_checkpoint,
        )
        return replace(
            aggregate,
            prompt=aggregate.prompt.transition(PromptStatus.ACTIVE, at),
            schedule=schedule,
        )

    def reset(
        self,
        aggregate: MemoryAggregate,
        command: ResetMemoryPrompt,
        policy: SchedulerPolicy,
    ) -> MemoryAggregate:
        self._require_status(aggregate, {PromptStatus.ACTIVE, PromptStatus.SUSPENDED})
        fact = MemoryScheduleReset(
            reset_id=command.reset_id,
            prompt_id=aggregate.prompt.prompt_id,
            reason=command.reason,
            reset_at=command.reset_at,
            previous_checkpoint=aggregate.schedule.causal_checkpoint,
        )
        initial = self._scheduler.initial_state(policy, command.reset_at)
        schedule = _projection(
            prompt_id=aggregate.prompt.prompt_id,
            state=initial,
            policy=policy,
            scheduler=self._scheduler,
            projection_version=aggregate.schedule.projection_version + 1,
            computed_at=command.reset_at,
            last_rating=None,
            last_review_id=None,
            checkpoint=f"reset:{command.reset_id}",
        )
        return replace(
            aggregate,
            prompt=replace(
                aggregate.prompt,
                version=aggregate.prompt.version + 1,
                updated_at=_utc(command.reset_at),
            ),
            schedule=schedule,
            resets=(*aggregate.resets, fact),
        )

    def archive(
        self,
        aggregate: MemoryAggregate,
        command: ArchiveMemoryPrompt,
    ) -> MemoryAggregate:
        self._require_status(aggregate, {PromptStatus.ACTIVE, PromptStatus.SUSPENDED})
        return replace(
            aggregate,
            prompt=aggregate.prompt.transition(PromptStatus.ARCHIVED, command.archived_at),
        )

    def restore(
        self,
        aggregate: MemoryAggregate,
        command: RestoreMemoryPrompt,
        policy: SchedulerPolicy,
    ) -> MemoryAggregate:
        self._require_status(aggregate, {PromptStatus.ARCHIVED})
        if not command.target_revision_available:
            raise DomainError(ErrorCode.TARGET_REVISION_UNAVAILABLE)
        resumed = self._scheduler.resume(
            aggregate.schedule.scheduled_state(),
            command.restored_at,
            policy,
        )
        schedule = _projection(
            prompt_id=aggregate.prompt.prompt_id,
            state=resumed,
            policy=policy,
            scheduler=self._scheduler,
            projection_version=aggregate.schedule.projection_version + 1,
            computed_at=command.restored_at,
            last_rating=aggregate.schedule.last_rating,
            last_review_id=aggregate.schedule.last_review_id,
            checkpoint=aggregate.schedule.causal_checkpoint,
        )
        return replace(
            aggregate,
            prompt=aggregate.prompt.transition(PromptStatus.ACTIVE, command.restored_at),
            schedule=schedule,
        )

    def delete(
        self,
        aggregate: MemoryAggregate,
        command: DeleteMemoryPrompt,
    ) -> MemoryAggregate:
        self._require_status(
            aggregate,
            {PromptStatus.ACTIVE, PromptStatus.SUSPENDED, PromptStatus.ARCHIVED},
        )
        if not command.reauthenticated:
            raise DomainError(ErrorCode.FORBIDDEN, detail="recent reauthentication required")
        return replace(
            aggregate,
            prompt=aggregate.prompt.transition(PromptStatus.DELETED, command.deleted_at),
        )

    def merge(
        self,
        command: MergeMemoryPrompts,
        policy: SchedulerPolicy,
    ) -> MergeResult:
        if len(command.sources) < 2:
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="merge requires two prompts")
        for source in command.sources:
            self._require_status(source, {PromptStatus.ACTIVE, PromptStatus.SUSPENDED})
        first = command.sources[0]
        if any(
            source.prompt.compatibility_key != first.prompt.compatibility_key
            for source in command.sources
        ):
            raise DomainError(ErrorCode.INCOMPATIBLE_PROTOCOLS)

        reviews = self._deduplicated_reviews(command.sources)
        canonical_prompt = replace(
            first.prompt,
            prompt_id=command.canonical_prompt_id,
            status=PromptStatus.ACTIVE,
            version=1,
            created_at=_utc(command.merged_at),
            updated_at=_utc(command.merged_at),
        )
        lineages = tuple(
            MemoryPromptLineage(
                source_prompt_id=source.prompt.prompt_id,
                canonical_prompt_id=command.canonical_prompt_id,
                merged_at=command.merged_at,
            )
            for source in command.sources
        )
        initial = self._scheduler.initial_state(policy, canonical_prompt.created_at)
        state = initial
        for review in reviews:
            state = self._scheduler.review(state, review.rating, review.reviewed_at, policy).after
        last = reviews[-1] if reviews else None
        schedule = _projection(
            prompt_id=canonical_prompt.prompt_id,
            state=state,
            policy=policy,
            scheduler=self._scheduler,
            projection_version=1 + len(reviews),
            computed_at=canonical_prompt.created_at if last is None else last.reviewed_at,
            last_rating=None if last is None else last.rating,
            last_review_id=None if last is None else last.review_id,
            checkpoint="merged" if last is None else f"review:{last.review_id}",
        )
        canonical = MemoryAggregate(
            prompt=canonical_prompt,
            schedule=schedule,
            reviews=reviews,
            resets=tuple(reset for source in command.sources for reset in source.resets),
            lineages=lineages,
        )
        sources = tuple(
            replace(
                source,
                prompt=source.prompt.transition(PromptStatus.SUPERSEDED, command.merged_at),
            )
            for source in command.sources
        )
        return MergeResult(canonical, sources)

    @staticmethod
    def _deduplicated_reviews(
        sources: tuple[MemoryAggregate, ...],
    ) -> tuple[MemoryReview, ...]:
        ordered = sorted(
            (review for source in sources for review in source.reviews),
            key=lambda review: (review.reviewed_at, review.review_id.int),
        )
        seen_opportunities: set[UUID] = set()
        seen_receipts: set[str] = set()
        result: list[MemoryReview] = []
        for review in ordered:
            if (
                review.opportunity_id in seen_opportunities
                or review.idempotency_key in seen_receipts
            ):
                continue
            seen_opportunities.add(review.opportunity_id)
            seen_receipts.add(review.idempotency_key)
            result.append(review)
        return tuple(result)

    @staticmethod
    def _require_status(
        aggregate: MemoryAggregate,
        allowed: set[PromptStatus],
    ) -> None:
        if aggregate.prompt.status not in allowed:
            raise DomainError(ErrorCode.INVALID_TRANSITION)

    def _require_binding(
        self,
        aggregate: MemoryAggregate,
        policy: SchedulerPolicy,
    ) -> None:
        identity = self._scheduler.identity
        prompt = aggregate.prompt
        schedule = aggregate.schedule
        if (
            identity.kind != prompt.scheduler_kind
            or identity.version != prompt.scheduler_version
            or identity.parameter_set_id != prompt.parameter_set_id
            or policy.parameter_set_id != prompt.parameter_set_id
            or policy.revision != prompt.policy_revision
            or schedule.scheduler_kind != prompt.scheduler_kind
            or schedule.scheduler_version != prompt.scheduler_version
            or schedule.parameter_set_id != prompt.parameter_set_id
            or schedule.policy_revision != prompt.policy_revision
        ):
            raise DomainError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                detail="pinned scheduler policy is unavailable",
            )

    @staticmethod
    def _certification_matches(
        prompt: MemoryPrompt,
        command: SubmitMemoryReview,
    ) -> bool:
        return (
            command.certified_recall
            and bool(command.certification_ref.strip())
            and prompt.operation == "recall"
            and command.certified_operation == prompt.operation
            and command.certified_protocol_id == prompt.protocol_id
            and command.certified_protocol_revision == prompt.protocol_revision
            and command.certified_target_revision_id == prompt.target_revision_id
        )
