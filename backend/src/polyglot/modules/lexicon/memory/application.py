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
    MemoryScheduleResumption,
    PromptStatus,
    ResumptionKind,
    schedule_projection,
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
)
from polyglot.modules.lexicon.memory.rebuild import (
    MemoryReplayBinding,
    MemoryReplayResolver,
    StaticMemoryReplayResolver,
    rebuild_schedule,
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
class SuspendMemoryPrompt:
    suspended_at: datetime


@dataclass(frozen=True, slots=True)
class ResetMemoryPrompt:
    reset_id: UUID
    reason: str
    reset_at: datetime


@dataclass(frozen=True, slots=True)
class ResumeMemoryPrompt:
    resumption_id: UUID
    resumed_at: datetime


@dataclass(frozen=True, slots=True)
class ArchiveMemoryPrompt:
    archived_at: datetime


@dataclass(frozen=True, slots=True)
class RestoreMemoryPrompt:
    resumption_id: UUID
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


class MemoryLifecycle:
    def __init__(
        self,
        scheduler: MemorySchedulerPort,
        *,
        replay_resolver: MemoryReplayResolver | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._replay_resolver = replay_resolver

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
        schedule = schedule_projection(
            prompt_id=prompt.prompt_id,
            state=initial,
            policy=policy,
            scheduler=self._scheduler,
            projection_version=1,
            computed_at=created_at,
            last_rating=None,
            last_review_id=None,
            checkpoint=prompt.creation_checkpoint,
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
        if not self._retrieval_certification_matches(aggregate.prompt, command):
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
            previous_checkpoint=aggregate.schedule.causal_checkpoint,
        )
        schedule = schedule_projection(
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
        command: ResumeMemoryPrompt,
        policy: SchedulerPolicy,
    ) -> MemoryAggregate:
        self._require_status(aggregate, {PromptStatus.SUSPENDED})
        self._require_binding(aggregate, policy)
        resumed_at = _utc(command.resumed_at)
        self._require_not_backdated(aggregate, resumed_at)
        before = aggregate.schedule.scheduled_state()
        resumed = self._scheduler.resume(before, resumed_at, policy)
        identity = self._scheduler.identity
        fact = MemoryScheduleResumption(
            resumption_id=command.resumption_id,
            prompt_id=aggregate.prompt.prompt_id,
            kind=ResumptionKind.RESUME,
            resumed_at=resumed_at,
            previous_checkpoint=aggregate.schedule.causal_checkpoint,
            scheduler_kind=identity.kind,
            scheduler_version=identity.version,
            parameter_set_id=policy.parameter_set_id,
            policy_revision=policy.revision,
            state_before=before,
            state_after=resumed,
        )
        schedule = schedule_projection(
            prompt_id=aggregate.prompt.prompt_id,
            state=resumed,
            policy=policy,
            scheduler=self._scheduler,
            projection_version=aggregate.schedule.projection_version + 1,
            computed_at=resumed_at,
            last_rating=aggregate.schedule.last_rating,
            last_review_id=aggregate.schedule.last_review_id,
            checkpoint=fact.checkpoint,
        )
        return replace(
            aggregate,
            prompt=aggregate.prompt.transition(PromptStatus.ACTIVE, resumed_at),
            schedule=schedule,
            resumptions=(*aggregate.resumptions, fact),
        )

    def reset(
        self,
        aggregate: MemoryAggregate,
        command: ResetMemoryPrompt,
        policy: SchedulerPolicy,
    ) -> MemoryAggregate:
        self._require_status(aggregate, {PromptStatus.ACTIVE, PromptStatus.SUSPENDED})
        self._require_binding(aggregate, policy)
        reset_at = _utc(command.reset_at)
        self._require_not_backdated(aggregate, reset_at)
        identity = self._scheduler.identity
        fact = MemoryScheduleReset(
            reset_id=command.reset_id,
            prompt_id=aggregate.prompt.prompt_id,
            reason=command.reason,
            reset_at=reset_at,
            previous_checkpoint=aggregate.schedule.causal_checkpoint,
            scheduler_kind=identity.kind,
            scheduler_version=identity.version,
            parameter_set_id=policy.parameter_set_id,
            policy_revision=policy.revision,
        )
        initial = self._scheduler.initial_state(policy, reset_at)
        schedule = schedule_projection(
            prompt_id=aggregate.prompt.prompt_id,
            state=initial,
            policy=policy,
            scheduler=self._scheduler,
            projection_version=aggregate.schedule.projection_version + 1,
            computed_at=reset_at,
            last_rating=None,
            last_review_id=None,
            checkpoint=fact.checkpoint,
        )
        return replace(
            aggregate,
            prompt=replace(
                aggregate.prompt,
                version=aggregate.prompt.version + 1,
                updated_at=reset_at,
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
        self._require_binding(aggregate, policy)
        restored_at = _utc(command.restored_at)
        self._require_not_backdated(aggregate, restored_at)
        before = aggregate.schedule.scheduled_state()
        resumed = self._scheduler.resume(
            before,
            restored_at,
            policy,
        )
        identity = self._scheduler.identity
        fact = MemoryScheduleResumption(
            resumption_id=command.resumption_id,
            prompt_id=aggregate.prompt.prompt_id,
            kind=ResumptionKind.RESTORE,
            resumed_at=restored_at,
            previous_checkpoint=aggregate.schedule.causal_checkpoint,
            scheduler_kind=identity.kind,
            scheduler_version=identity.version,
            parameter_set_id=policy.parameter_set_id,
            policy_revision=policy.revision,
            state_before=before,
            state_after=resumed,
        )
        schedule = schedule_projection(
            prompt_id=aggregate.prompt.prompt_id,
            state=resumed,
            policy=policy,
            scheduler=self._scheduler,
            projection_version=aggregate.schedule.projection_version + 1,
            computed_at=restored_at,
            last_rating=aggregate.schedule.last_rating,
            last_review_id=aggregate.schedule.last_review_id,
            checkpoint=fact.checkpoint,
        )
        return replace(
            aggregate,
            prompt=aggregate.prompt.transition(PromptStatus.ACTIVE, restored_at),
            schedule=schedule,
            resumptions=(*aggregate.resumptions, fact),
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

        merged_at = _utc(command.merged_at)
        if any(
            merged_at < source.prompt.updated_at or merged_at < source.schedule.computed_at
            for source in command.sources
        ):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="merge is backdated")
        identity = self._scheduler.identity
        if identity.parameter_set_id != policy.parameter_set_id:
            raise DomainError(ErrorCode.DEPENDENCY_UNAVAILABLE)
        reviews = tuple(review for source in command.sources for review in source.reviews)
        resets = tuple(reset for source in command.sources for reset in source.resets)
        resumptions = tuple(
            resumption for source in command.sources for resumption in source.resumptions
        )
        canonical_prompt = replace(
            first.prompt,
            prompt_id=command.canonical_prompt_id,
            scheduler_kind=identity.kind,
            scheduler_version=identity.version,
            parameter_set_id=policy.parameter_set_id,
            policy_revision=policy.revision,
            status=PromptStatus.ACTIVE,
            version=1,
            created_at=min(source.prompt.created_at for source in command.sources),
            updated_at=merged_at,
        )
        facts: tuple[
            MemoryReview | MemoryScheduleReset | MemoryScheduleResumption,
            ...,
        ] = (*reviews, *resets, *resumptions)
        source_prompt_ids = {fact.prompt_id for fact in facts}
        source_prompt_ids.update(source.prompt.prompt_id for source in command.sources)
        source_origins: dict[UUID, tuple[datetime, str, str, str, int]] = {}
        for source in command.sources:
            prompt = source.prompt
            source_origins[prompt.prompt_id] = (
                prompt.created_at,
                prompt.scheduler_kind,
                prompt.scheduler_version,
                prompt.parameter_set_id,
                prompt.policy_revision,
            )
            for lineage in source.lineages:
                origin = (
                    lineage.source_created_at,
                    lineage.source_scheduler_kind,
                    lineage.source_scheduler_version,
                    lineage.source_parameter_set_id,
                    lineage.source_policy_revision,
                )
                previous = source_origins.setdefault(lineage.source_prompt_id, origin)
                if previous != origin:
                    raise DomainError(
                        ErrorCode.VALIDATION_FAILED,
                        detail="conflicting source lineage metadata",
                    )
        lineages = tuple(
            MemoryPromptLineage(
                source_prompt_id=source_prompt_id,
                canonical_prompt_id=command.canonical_prompt_id,
                merged_at=merged_at,
                source_created_at=source_origins[source_prompt_id][0],
                source_scheduler_kind=source_origins[source_prompt_id][1],
                source_scheduler_version=source_origins[source_prompt_id][2],
                source_parameter_set_id=source_origins[source_prompt_id][3],
                source_policy_revision=source_origins[source_prompt_id][4],
            )
            for source_prompt_id in sorted(source_prompt_ids, key=lambda item: item.int)
        )
        initial = self._scheduler.initial_state(policy, canonical_prompt.created_at)
        schedule = schedule_projection(
            prompt_id=canonical_prompt.prompt_id,
            state=initial,
            policy=policy,
            scheduler=self._scheduler,
            projection_version=1,
            computed_at=merged_at,
            last_rating=None,
            last_review_id=None,
            checkpoint=f"merge:{canonical_prompt.prompt_id}",
        )
        canonical = MemoryAggregate(
            prompt=canonical_prompt,
            schedule=schedule,
            reviews=reviews,
            resets=resets,
            resumptions=resumptions,
            lineages=lineages,
        )
        canonical = replace(
            canonical,
            schedule=rebuild_schedule(canonical, self._resolver_for(policy)),
        )
        sources = tuple(
            replace(
                source,
                prompt=source.prompt.transition(PromptStatus.SUPERSEDED, merged_at),
            )
            for source in command.sources
        )
        return MergeResult(canonical, sources)

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

    def _resolver_for(self, policy: SchedulerPolicy) -> MemoryReplayResolver:
        if self._replay_resolver is not None:
            return self._replay_resolver
        return StaticMemoryReplayResolver((MemoryReplayBinding(self._scheduler, policy),))

    @staticmethod
    def _require_not_backdated(
        aggregate: MemoryAggregate,
        occurred_at: datetime,
    ) -> None:
        if occurred_at < aggregate.schedule.computed_at:
            raise DomainError(
                ErrorCode.REVIEW_CONFLICT,
                detail="schedule fact predates the current causal checkpoint",
            )

    @staticmethod
    def _retrieval_certification_matches(
        prompt: MemoryPrompt,
        command: SubmitMemoryReview,
    ) -> bool:
        return (
            command.certified_recall
            and bool(command.certification_ref.strip())
            and prompt.operation in {"recall", "recognition"}
            and command.certified_operation == prompt.operation
            and command.certified_protocol_id == prompt.protocol_id
            and command.certified_protocol_revision == prompt.protocol_revision
            and command.certified_target_revision_id == prompt.target_revision_id
        )
