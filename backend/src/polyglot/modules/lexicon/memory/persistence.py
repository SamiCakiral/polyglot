from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, is_dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.lexicon.memory.application import (
    CreateMemoryPrompt,
    MemoryLifecycle,
    SubmitMemoryReview,
)
from polyglot.modules.lexicon.memory.domain import (
    MemoryAggregate,
    MemoryPrompt,
    MemoryPromptLineage,
    MemoryReview,
    MemoryScheduleReset,
    MemoryScheduleResumption,
    MemoryScheduleState,
    PromptStatus,
    ResumptionKind,
)
from polyglot.modules.lexicon.memory.policy import SchedulerPolicy
from polyglot.modules.lexicon.memory.ports import (
    MemoryRating,
    MemorySchedulerPort,
    MemoryState,
    ScheduledState,
)
from polyglot.modules.lexicon.memory.rebuild import MemoryReplayResolver, rebuild_schedule
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.json_types import JsonValue

TransactionHook = Callable[[str], Awaitable[None]]


def _encode(value: Any) -> JsonValue:
    if is_dataclass(value) and not isinstance(value, type):
        return _encode(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_encode(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return str(value.value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported memory persistence value: {type(value)!r}")


def _dt(value: object) -> datetime:
    return datetime.fromisoformat(str(value)).astimezone(UTC)


def _uuid(value: object) -> UUID:
    return UUID(str(value))


def _decimal(value: object | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _scheduled(data: Mapping[str, object]) -> ScheduledState:
    return ScheduledState(
        state=MemoryState(str(data["state"])),
        difficulty=_decimal(data.get("difficulty")),
        stability=_decimal(data.get("stability")),
        due_at=_dt(data["due_at"]),
        last_review_at=None
        if data.get("last_review_at") is None
        else _dt(data["last_review_at"]),
        step=None if data.get("step") is None else int(str(data["step"])),
        reps=int(str(data["reps"])),
        lapses=int(str(data["lapses"])),
    )


def _aggregate_from_payload(payload: Mapping[str, object]) -> MemoryAggregate:
    prompt_data = _mapping(payload["prompt"])
    schedule_data = _mapping(payload["schedule"])
    prompt = MemoryPrompt(
        prompt_id=_uuid(prompt_data["prompt_id"]),
        profile_id=_uuid(prompt_data["profile_id"]),
        target_ref=_uuid(prompt_data["target_ref"]),
        target_revision_id=_uuid(prompt_data["target_revision_id"]),
        direction=str(prompt_data["direction"]),
        modality=str(prompt_data["modality"]),
        operation=str(prompt_data["operation"]),
        protocol_id=str(prompt_data["protocol_id"]),
        protocol_revision=int(str(prompt_data["protocol_revision"])),
        rating_semantics_id=str(prompt_data["rating_semantics_id"]),
        scheduler_policy_id=_uuid(prompt_data["scheduler_policy_id"]),
        scheduler_kind=str(prompt_data["scheduler_kind"]),
        scheduler_version=str(prompt_data["scheduler_version"]),
        parameter_set_id=str(prompt_data["parameter_set_id"]),
        policy_revision=int(str(prompt_data["policy_revision"])),
        status=PromptStatus(str(prompt_data["status"])),
        version=int(str(prompt_data["version"])),
        created_at=_dt(prompt_data["created_at"]),
        updated_at=_dt(prompt_data["updated_at"]),
    )
    schedule = MemoryScheduleState(
        prompt_id=_uuid(schedule_data["prompt_id"]),
        scheduler_kind=str(schedule_data["scheduler_kind"]),
        scheduler_version=str(schedule_data["scheduler_version"]),
        parameter_set_id=str(schedule_data["parameter_set_id"]),
        policy_revision=int(str(schedule_data["policy_revision"])),
        state=MemoryState(str(schedule_data["state"])),
        difficulty=_decimal(schedule_data.get("difficulty")),
        stability=_decimal(schedule_data.get("stability")),
        desired_retention=Decimal(str(schedule_data["desired_retention"])),
        last_review_at=None
        if schedule_data.get("last_review_at") is None
        else _dt(schedule_data["last_review_at"]),
        due_at=_dt(schedule_data["due_at"]),
        reps=int(str(schedule_data["reps"])),
        lapses=int(str(schedule_data["lapses"])),
        last_rating=None
        if schedule_data.get("last_rating") is None
        else MemoryRating(str(schedule_data["last_rating"])),
        last_review_id=None
        if schedule_data.get("last_review_id") is None
        else _uuid(schedule_data["last_review_id"]),
        projection_version=int(str(schedule_data["projection_version"])),
        computed_at=_dt(schedule_data["computed_at"]),
        causal_checkpoint=str(schedule_data["causal_checkpoint"]),
        step=None if schedule_data.get("step") is None else int(str(schedule_data["step"])),
    )
    reviews = tuple(_review(_mapping(item)) for item in _sequence(payload.get("reviews", [])))
    resets = tuple(_reset(_mapping(item)) for item in _sequence(payload.get("resets", [])))
    resumptions = tuple(
        _resumption(_mapping(item)) for item in _sequence(payload.get("resumptions", []))
    )
    lineages = tuple(
        _lineage(_mapping(item)) for item in _sequence(payload.get("lineages", []))
    )
    return MemoryAggregate(prompt, schedule, reviews, resets, resumptions, lineages)


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        raise TypeError("memory payload object expected")
    return value


def _json(value: object) -> str:
    return json.dumps(_encode(value), sort_keys=True, separators=(",", ":"))


def _sequence(value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError("memory payload array expected")
    return value


def _review(data: Mapping[str, object]) -> MemoryReview:
    return MemoryReview(
        review_id=_uuid(data["review_id"]),
        prompt_id=_uuid(data["prompt_id"]),
        opportunity_id=_uuid(data["opportunity_id"]),
        attempt_id=None if data.get("attempt_id") is None else _uuid(data["attempt_id"]),
        response_ref=None if data.get("response_ref") is None else str(data["response_ref"]),
        correction_ref=None
        if data.get("correction_ref") is None
        else str(data["correction_ref"]),
        highest_hint=int(str(data["highest_hint"])),
        active_duration_ms=int(str(data["active_duration_ms"])),
        scheduled_at=_dt(data["scheduled_at"]),
        reviewed_at=_dt(data["reviewed_at"]),
        rating=MemoryRating(str(data["rating"])),
        state_before=_scheduled(_mapping(data["state_before"])),
        state_after=_scheduled(_mapping(data["state_after"])),
        scheduler_kind=str(data["scheduler_kind"]),
        scheduler_version=str(data["scheduler_version"]),
        parameter_set_id=str(data["parameter_set_id"]),
        policy_revision=int(str(data["policy_revision"])),
        idempotency_key=str(data["idempotency_key"]),
        low_confidence=bool(data["low_confidence"]),
        certification_ref=str(data["certification_ref"]),
        certified_operation=str(data["certified_operation"]),
        certified_protocol_id=str(data["certified_protocol_id"]),
        certified_protocol_revision=int(str(data["certified_protocol_revision"])),
        certified_target_revision_id=_uuid(data["certified_target_revision_id"]),
        previous_checkpoint=str(data["previous_checkpoint"]),
    )


def _reset(data: Mapping[str, object]) -> MemoryScheduleReset:
    return MemoryScheduleReset(
        reset_id=_uuid(data["reset_id"]),
        prompt_id=_uuid(data["prompt_id"]),
        reason=str(data["reason"]),
        reset_at=_dt(data["reset_at"]),
        previous_checkpoint=str(data["previous_checkpoint"]),
        scheduler_kind=str(data["scheduler_kind"]),
        scheduler_version=str(data["scheduler_version"]),
        parameter_set_id=str(data["parameter_set_id"]),
        policy_revision=int(str(data["policy_revision"])),
    )


def _resumption(data: Mapping[str, object]) -> MemoryScheduleResumption:
    return MemoryScheduleResumption(
        resumption_id=_uuid(data["resumption_id"]),
        prompt_id=_uuid(data["prompt_id"]),
        kind=ResumptionKind(str(data["kind"])),
        resumed_at=_dt(data["resumed_at"]),
        previous_checkpoint=str(data["previous_checkpoint"]),
        scheduler_kind=str(data["scheduler_kind"]),
        scheduler_version=str(data["scheduler_version"]),
        parameter_set_id=str(data["parameter_set_id"]),
        policy_revision=int(str(data["policy_revision"])),
        state_before=_scheduled(_mapping(data["state_before"])),
        state_after=_scheduled(_mapping(data["state_after"])),
    )


def _lineage(data: Mapping[str, object]) -> MemoryPromptLineage:
    return MemoryPromptLineage(
        source_prompt_id=_uuid(data["source_prompt_id"]),
        canonical_prompt_id=_uuid(data["canonical_prompt_id"]),
        merged_at=_dt(data["merged_at"]),
        source_created_at=_dt(data["source_created_at"]),
        source_scheduler_kind=str(data["source_scheduler_kind"]),
        source_scheduler_version=str(data["source_scheduler_version"]),
        source_parameter_set_id=str(data["source_parameter_set_id"]),
        source_policy_revision=int(str(data["source_policy_revision"])),
    )


class SqlMemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, aggregate: MemoryAggregate) -> None:
        await self._insert_prompt(aggregate)
        await self._insert_schedule(aggregate)
        await self._append_facts(aggregate)

    async def get(self, profile_id: UUID, prompt_id: UUID) -> MemoryAggregate | None:
        payload = await self._session.scalar(
            text(
                "SELECT aggregate_payload FROM memory.memory_prompts "
                "WHERE profile_id=:profile AND prompt_id=:prompt"
            ),
            {"profile": profile_id, "prompt": prompt_id},
        )
        if payload is None:
            return None
        aggregate = _aggregate_from_payload(_mapping(payload))
        reviews = await self._fact_payloads(
            "memory_reviews", profile_id, prompt_id, "reviewed_at, review_id"
        )
        resets = await self._fact_payloads(
            "memory_schedule_resets", profile_id, prompt_id, "reset_at, reset_id"
        )
        resumptions = await self._fact_payloads(
            "memory_schedule_resumptions",
            profile_id,
            prompt_id,
            "resumed_at, resumption_id",
        )
        lineages = tuple(
            _lineage(_mapping(item))
            for item in (
                await self._session.execute(
                    text(
                        "SELECT payload FROM memory.memory_prompt_lineages "
                        "WHERE profile_id=:profile AND canonical_prompt_id=:prompt "
                        "ORDER BY merged_at, source_prompt_id"
                    ),
                    {"profile": profile_id, "prompt": prompt_id},
                )
            ).scalars()
        )
        return replace(
            aggregate,
            reviews=tuple(_review(item) for item in reviews),
            resets=tuple(_reset(item) for item in resets),
            resumptions=tuple(_resumption(item) for item in resumptions),
            lineages=lineages,
        )

    async def _fact_payloads(
        self,
        table: str,
        profile_id: UUID,
        prompt_id: UUID,
        order_by: str,
    ) -> tuple[Mapping[str, object], ...]:
        rows = (
            await self._session.execute(
                text(
                    f"SELECT payload FROM memory.{table} "
                    f"WHERE profile_id=:profile AND prompt_id=:prompt ORDER BY {order_by}"
                ),
                {"profile": profile_id, "prompt": prompt_id},
            )
        ).scalars()
        return tuple(_mapping(payload) for payload in rows)

    async def save(
        self,
        aggregate: MemoryAggregate,
        *,
        expected_prompt_version: int,
        expected_projection_version: int,
    ) -> None:
        row = (
            await self._session.execute(
                text(
                    "SELECT version FROM memory.memory_prompts "
                    "WHERE profile_id=:profile AND prompt_id=:prompt FOR UPDATE"
                ),
                {"profile": aggregate.prompt.profile_id, "prompt": aggregate.prompt.prompt_id},
            )
        ).one_or_none()
        projection = await self._session.scalar(
            text(
                "SELECT projection_version FROM memory.memory_schedule_states "
                "WHERE profile_id=:profile AND prompt_id=:prompt FOR UPDATE"
            ),
            {"profile": aggregate.prompt.profile_id, "prompt": aggregate.prompt.prompt_id},
        )
        if row is None or int(row.version) != expected_prompt_version:
            raise DomainError(ErrorCode.VERSION_CONFLICT)
        if projection is None or int(projection) != expected_projection_version:
            raise DomainError(ErrorCode.VERSION_CONFLICT)
        await self._append_facts(aggregate)
        await self._session.execute(
            text(
                "UPDATE memory.memory_prompts SET status=:status,version=:version,"
                "updated_at=:updated,aggregate_payload=CAST(:payload AS jsonb) "
                "WHERE prompt_id=:prompt"
            ),
            {
                "status": aggregate.prompt.status.value,
                "version": aggregate.prompt.version,
                "updated": aggregate.prompt.updated_at,
                "payload": _json(aggregate),
                "prompt": aggregate.prompt.prompt_id,
            },
        )
        await self._replace_schedule(aggregate)

    async def rebuild_projection(
        self,
        profile_id: UUID,
        prompt_id: UUID,
        resolver: MemoryReplayResolver,
        *,
        expected_projection_version: int,
    ) -> MemoryScheduleState:
        aggregate = await self.get(profile_id, prompt_id)
        if aggregate is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        if aggregate.schedule.projection_version != expected_projection_version:
            raise DomainError(ErrorCode.VERSION_CONFLICT)
        rebuilt = rebuild_schedule(aggregate, resolver)
        if rebuilt != aggregate.schedule:
            updated = MemoryAggregate(
                aggregate.prompt,
                rebuilt,
                aggregate.reviews,
                aggregate.resets,
                aggregate.resumptions,
                aggregate.lineages,
            )
            await self.save(
                updated,
                expected_prompt_version=aggregate.prompt.version,
                expected_projection_version=aggregate.schedule.projection_version,
            )
        return rebuilt

    async def _insert_prompt(self, aggregate: MemoryAggregate) -> None:
        prompt = aggregate.prompt
        await self._session.execute(
            text(
                "INSERT INTO memory.memory_prompts "
                "(prompt_id,profile_id,target_ref,target_revision_id,direction,modality,operation,"
                "protocol_id,protocol_revision,rating_semantics_id,scheduler_policy_id,"
                "scheduler_kind,scheduler_version,parameter_set_id,policy_revision,status,"
                "version,created_at,updated_at,aggregate_payload) VALUES "
                "(:prompt,:profile,:target,:revision,:direction,:modality,:operation,:protocol,"
                ":protocol_revision,:semantics,:policy_id,:kind,:scheduler_version,:parameters,"
                ":policy_revision,:status,:version,:created,:updated,CAST(:payload AS jsonb))"
            ),
            {
                "prompt": prompt.prompt_id,
                "profile": prompt.profile_id,
                "target": prompt.target_ref,
                "revision": prompt.target_revision_id,
                "direction": prompt.direction,
                "modality": prompt.modality,
                "operation": prompt.operation,
                "protocol": prompt.protocol_id,
                "protocol_revision": prompt.protocol_revision,
                "semantics": prompt.rating_semantics_id,
                "policy_id": prompt.scheduler_policy_id,
                "kind": prompt.scheduler_kind,
                "scheduler_version": prompt.scheduler_version,
                "parameters": prompt.parameter_set_id,
                "policy_revision": prompt.policy_revision,
                "status": prompt.status.value,
                "version": prompt.version,
                "created": prompt.created_at,
                "updated": prompt.updated_at,
                "payload": _json(aggregate),
            },
        )

    async def _insert_schedule(self, aggregate: MemoryAggregate) -> None:
        await self._session.execute(
            text(
                "INSERT INTO memory.memory_schedule_states "
                "(prompt_id,profile_id,scheduler_kind,scheduler_version,parameter_set_id,"
                "policy_revision,state,difficulty,stability,desired_retention,last_review_at,"
                "due_at,reps,lapses,last_rating,last_review_id,projection_version,computed_at,"
                "causal_checkpoint,step) VALUES "
                "(:prompt,:profile,:kind,:scheduler_version,:parameters,:policy_revision,:state,"
                ":difficulty,:stability,:retention,:last_review_at,:due_at,:reps,:lapses,"
                ":last_rating,:last_review_id,:projection_version,:computed_at,:checkpoint,:step)"
            ),
            self._schedule_values(aggregate),
        )

    async def _replace_schedule(self, aggregate: MemoryAggregate) -> None:
        values = self._schedule_values(aggregate)
        await self._session.execute(
            text(
                "UPDATE memory.memory_schedule_states SET scheduler_kind=:kind,"
                "scheduler_version=:scheduler_version,parameter_set_id=:parameters,"
                "policy_revision=:policy_revision,state=:state,difficulty=:difficulty,"
                "stability=:stability,desired_retention=:retention,last_review_at=:last_review_at,"
                "due_at=:due_at,reps=:reps,lapses=:lapses,last_rating=:last_rating,"
                "last_review_id=:last_review_id,projection_version=:projection_version,"
                "computed_at=:computed_at,causal_checkpoint=:checkpoint,step=:step "
                "WHERE prompt_id=:prompt AND profile_id=:profile"
            ),
            values,
        )

    def _schedule_values(self, aggregate: MemoryAggregate) -> dict[str, object]:
        schedule = aggregate.schedule
        return {
            "prompt": schedule.prompt_id,
            "profile": aggregate.prompt.profile_id,
            "kind": schedule.scheduler_kind,
            "scheduler_version": schedule.scheduler_version,
            "parameters": schedule.parameter_set_id,
            "policy_revision": schedule.policy_revision,
            "state": schedule.state.value,
            "difficulty": schedule.difficulty,
            "stability": schedule.stability,
            "retention": schedule.desired_retention,
            "last_review_at": schedule.last_review_at,
            "due_at": schedule.due_at,
            "reps": schedule.reps,
            "lapses": schedule.lapses,
            "last_rating": None if schedule.last_rating is None else schedule.last_rating.value,
            "last_review_id": schedule.last_review_id,
            "projection_version": schedule.projection_version,
            "computed_at": schedule.computed_at,
            "checkpoint": schedule.causal_checkpoint,
            "step": schedule.step,
        }

    async def _append_facts(self, aggregate: MemoryAggregate) -> None:
        profile = aggregate.prompt.profile_id
        for review in aggregate.reviews:
            await self._session.execute(
                text(
                    "INSERT INTO memory.memory_reviews "
                    "(review_id,prompt_id,profile_id,opportunity_id,reviewed_at,"
                    "previous_checkpoint,payload) VALUES "
                    "(:id,:prompt,:profile,:opportunity,:at,:checkpoint,CAST(:payload AS jsonb)) "
                    "ON CONFLICT (review_id) DO NOTHING"
                ),
                {
                    "id": review.review_id,
                    "prompt": review.prompt_id,
                    "profile": profile,
                    "opportunity": review.opportunity_id,
                    "at": review.reviewed_at,
                    "checkpoint": review.previous_checkpoint,
                    "payload": _json(review),
                },
            )
            await self._assert_fact_payload(
                "memory_reviews", "review_id", review.review_id, review
            )
        for reset in aggregate.resets:
            await self._session.execute(
                text(
                    "INSERT INTO memory.memory_schedule_resets "
                    "(reset_id,prompt_id,profile_id,reset_at,previous_checkpoint,payload) VALUES "
                    "(:id,:prompt,:profile,:at,:checkpoint,CAST(:payload AS jsonb)) "
                    "ON CONFLICT (reset_id) DO NOTHING"
                ),
                {
                    "id": reset.reset_id,
                    "prompt": reset.prompt_id,
                    "profile": profile,
                    "at": reset.reset_at,
                    "checkpoint": reset.previous_checkpoint,
                    "payload": _json(reset),
                },
            )
            await self._assert_fact_payload(
                "memory_schedule_resets", "reset_id", reset.reset_id, reset
            )
        for resumption in aggregate.resumptions:
            await self._session.execute(
                text(
                    "INSERT INTO memory.memory_schedule_resumptions "
                    "(resumption_id,prompt_id,profile_id,resumed_at,previous_checkpoint,payload) "
                    "VALUES (:id,:prompt,:profile,:at,:checkpoint,CAST(:payload AS jsonb)) "
                    "ON CONFLICT (resumption_id) DO NOTHING"
                ),
                {
                    "id": resumption.resumption_id,
                    "prompt": resumption.prompt_id,
                    "profile": profile,
                    "at": resumption.resumed_at,
                    "checkpoint": resumption.previous_checkpoint,
                    "payload": _json(resumption),
                },
            )
            await self._assert_fact_payload(
                "memory_schedule_resumptions",
                "resumption_id",
                resumption.resumption_id,
                resumption,
            )
        for lineage in aggregate.lineages:
            await self._session.execute(
                text(
                    "INSERT INTO memory.memory_prompt_lineages "
                    "(source_prompt_id,canonical_prompt_id,profile_id,merged_at,payload) VALUES "
                    "(:source,:canonical,:profile,:at,CAST(:payload AS jsonb)) "
                    "ON CONFLICT (source_prompt_id) DO NOTHING"
                ),
                {
                    "source": lineage.source_prompt_id,
                    "canonical": lineage.canonical_prompt_id,
                    "profile": profile,
                    "at": lineage.merged_at,
                    "payload": _json(lineage),
                },
            )
            await self._assert_fact_payload(
                "memory_prompt_lineages",
                "source_prompt_id",
                lineage.source_prompt_id,
                lineage,
            )

    async def _assert_fact_payload(
        self,
        table: str,
        identifier_column: str,
        identifier: UUID,
        expected: object,
    ) -> None:
        stored = await self._session.scalar(
            text(
                f"SELECT payload FROM memory.{table} "
                f"WHERE {identifier_column}=:identifier"
            ),
            {"identifier": identifier},
        )
        if stored is None or canonical_json_fingerprint(
            _encode(_mapping(stored))
        ) != canonical_json_fingerprint(_encode(expected)):
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)


class SqlMemoryService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        scheduler: MemorySchedulerPort,
        *,
        id_generator: IdGenerator | None = None,
        transaction_hook: TransactionHook | None = None,
    ) -> None:
        self._sessions = session_factory
        self._scheduler = scheduler
        self._ids = id_generator or Uuid7Generator()
        self._transaction_hook = transaction_hook

    async def create(
        self,
        actor_id: UUID,
        command: CreateMemoryPrompt,
        policy: SchedulerPolicy,
        *,
        idempotency_key: str,
    ) -> MemoryAggregate:
        fingerprint = canonical_json_fingerprint(
            _encode({"command": command, "policy": policy})
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            existing = await self._receipt(
                session, actor_id, "CreateMemoryPrompt", idempotency_key
            )
            if existing is not None:
                stored_fingerprint, payload = existing
                if stored_fingerprint != fingerprint:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return _aggregate_from_payload(payload)
            aggregate = MemoryLifecycle(self._scheduler).create(command, policy)
            async with session.begin_nested():
                repository = SqlMemoryRepository(session)
                await repository.add(aggregate)
                await self._record_effect(
                    session,
                    actor_id=actor_id,
                    aggregate=aggregate,
                    command_type="CreateMemoryPrompt",
                    event_type="memory_prompt_created",
                    idempotency_key=idempotency_key,
                    fingerprint=fingerprint,
                    occurred_at=command.created_at,
                )
                if self._transaction_hook is not None:
                    await self._transaction_hook("before_commit")
            await session.commit()
            if self._transaction_hook is not None:
                await self._transaction_hook("after_commit")
            return aggregate

    async def submit_review(
        self,
        actor_id: UUID,
        prompt_id: UUID,
        command: SubmitMemoryReview,
        policy: SchedulerPolicy,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> MemoryAggregate:
        fingerprint = canonical_json_fingerprint(
            _encode(
                {
                    "prompt_id": prompt_id,
                    "command": command,
                    "policy": policy,
                    "expected_version": expected_version,
                }
            )
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            existing = await self._receipt(
                session, actor_id, "SubmitMemoryReview", idempotency_key
            )
            if existing is not None:
                stored_fingerprint, payload = existing
                if stored_fingerprint != fingerprint:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return _aggregate_from_payload(payload)
            profile_id = await session.scalar(
                text("SELECT profile_id FROM memory.memory_prompts WHERE prompt_id=:prompt"),
                {"prompt": prompt_id},
            )
            if profile_id is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            repository = SqlMemoryRepository(session)
            before = await repository.get(profile_id, prompt_id)
            if before is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if before.prompt.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            decision = MemoryLifecycle(self._scheduler).submit_review(before, command, policy)
            after = decision.aggregate
            if not decision.review_created:
                await self._record_receipt(
                    session,
                    actor_id=actor_id,
                    aggregate=after,
                    command_type="SubmitMemoryReview",
                    idempotency_key=idempotency_key,
                    fingerprint=fingerprint,
                    occurred_at=command.reviewed_at,
                )
                await session.commit()
                return after
            await repository.save(
                after,
                expected_prompt_version=before.prompt.version,
                expected_projection_version=before.schedule.projection_version,
            )
            await self._record_effect(
                session,
                actor_id=actor_id,
                aggregate=after,
                command_type="SubmitMemoryReview",
                event_type="memory_review_recorded",
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                occurred_at=command.reviewed_at,
            )
            await session.commit()
            return after

    async def _set_actor(self, session: AsyncSession, actor_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"),
            {"actor": str(actor_id)},
        )

    async def _receipt(
        self,
        session: AsyncSession,
        actor_id: UUID,
        command_type: str,
        idempotency_key: str,
    ) -> tuple[str, Mapping[str, object]] | None:
        row = (
            await session.execute(
                text(
                    "SELECT request_fingerprint,result_payload "
                    "FROM memory.memory_command_receipts "
                    "WHERE actor_id=:actor AND command_type=:type AND idempotency_key=:key"
                ),
                {"actor": actor_id, "type": command_type, "key": idempotency_key},
            )
        ).one_or_none()
        if row is None:
            return None
        return str(row.request_fingerprint), _mapping(row.result_payload)

    async def _record_effect(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        aggregate: MemoryAggregate,
        command_type: str,
        event_type: str,
        idempotency_key: str,
        fingerprint: str,
        occurred_at: datetime,
    ) -> None:
        receipt_id = await self._record_receipt(
            session,
            actor_id=actor_id,
            aggregate=aggregate,
            command_type=command_type,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            occurred_at=occurred_at,
        )
        event_id = self._ids.new()
        outbox_id = self._ids.new()

        await session.execute(
            text(
                "INSERT INTO platform.domain_events "
                "(event_id,event_type,schema_version,aggregate_type,aggregate_id,"
                "aggregate_version,actor_type,actor_id,profile_id,occurred_at,recorded_at,"
                "correlation_id,causation_id,command_id,privacy_class,policy_versions,payload,"
                "expires_at,subject_type,subject_id) VALUES "
                "(:event,:event_type,1,'memory_prompt',:prompt,:version,'account',:actor,"
                ":profile,:occurred,:occurred,:correlation,NULL,:command,'personal',"
                "CAST(:policies AS jsonb),CAST(:payload AS jsonb),:expires,'profile',:profile)"
            ),
            {
                "event": event_id,
                "event_type": event_type,
                "prompt": aggregate.prompt.prompt_id,
                "version": aggregate.prompt.version,
                "actor": actor_id,
                "profile": aggregate.prompt.profile_id,
                "occurred": occurred_at,
                "correlation": event_id,
                "command": receipt_id,
                "policies": _json({"memory": aggregate.prompt.policy_revision}),
                "payload": _json({"prompt_id": str(aggregate.prompt.prompt_id)}),
                "expires": occurred_at + timedelta(days=3650),
            },
        )
        await session.execute(
            text(
                "INSERT INTO platform.outbox_messages "
                "(outbox_id,event_id,destination,created_at,attempt_count) "
                "VALUES (:outbox,:event,'learning-events',:created,0)"
            ),
            {"outbox": outbox_id, "event": event_id, "created": occurred_at},
        )

    async def _record_receipt(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        aggregate: MemoryAggregate,
        command_type: str,
        idempotency_key: str,
        fingerprint: str,
        occurred_at: datetime,
    ) -> UUID:
        receipt_id = self._ids.new()
        await session.execute(
            text(
                "INSERT INTO memory.memory_command_receipts "
                "(receipt_id,profile_id,actor_id,command_type,idempotency_key,"
                "request_fingerprint,result_prompt_id,result_payload,created_at) VALUES "
                "(:receipt,:profile,:actor,:type,:key,:fingerprint,:prompt,"
                "CAST(:payload AS jsonb),:created)"
            ),
            {
                "receipt": receipt_id,
                "profile": aggregate.prompt.profile_id,
                "actor": actor_id,
                "type": command_type,
                "key": idempotency_key,
                "fingerprint": fingerprint,
                "prompt": aggregate.prompt.prompt_id,
                "payload": _json(aggregate),
                "created": occurred_at,
            },
        )
        return receipt_id
