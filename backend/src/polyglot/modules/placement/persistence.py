from __future__ import annotations

# ruff: noqa: E501
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.language_profiles.onboarding import EntryPath
from polyglot.modules.placement.domain import (
    ObservationStatus,
    PlacementCandidate,
    PlacementObservation,
    PlacementState,
    PlacementStatus,
    ScoringKind,
    SkillDimension,
    SkillEstimate,
)
from polyglot.modules.placement.evaluator import EvaluationTask, PlacementEvaluator
from polyglot.modules.placement.policy import PlacementPolicyV1
from polyglot.modules.placement.scoring import FrozenPlacementItem, PlacementAnswer, scorer_for
from polyglot.platform.clock import Clock, SystemClock
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.json_types import JsonValue

MEASURABLE_SKILLS = tuple(
    skill.value for skill in SkillDimension if skill is not SkillDimension.SPEAKING
)


@dataclass(frozen=True, slots=True)
class PlacementItemView:
    item_instance_id: UUID
    ordinal: int
    primitive_ref: str
    primary_skill_ref: str
    payload: dict[str, JsonValue]
    estimated_seconds: int


@dataclass(frozen=True, slots=True)
class PlacementRunView:
    run_id: UUID
    profile_id: UUID
    status: PlacementStatus
    version: int
    elapsed_seconds: int
    current_item: PlacementItemView | None
    estimates: tuple[SkillEstimate, ...]
    stop_reason: str | None
    provider_status: str | None = None


class SqlPlacementService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        evaluator: PlacementEvaluator,
        *,
        ids: IdGenerator | None = None,
        clock: Clock | None = None,
        policy: PlacementPolicyV1 | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._evaluator = evaluator
        self._ids = ids or Uuid7Generator()
        self._clock = clock or SystemClock()
        self._policy = policy or PlacementPolicyV1()

    async def _set_actor(self, session: AsyncSession, actor_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"), {"actor": str(actor_id)}
        )

    async def _assert_owner(self, session: AsyncSession, actor_id: UUID, profile_id: UUID) -> None:
        owned = await session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles "
                "WHERE profile_id=:profile AND account_id=:actor AND status <> 'deleted')"
            ),
            {"profile": profile_id, "actor": actor_id},
        )
        if owned is not True:
            raise DomainError(ErrorCode.NOT_FOUND)

    async def start(
        self,
        *,
        actor_id: UUID,
        profile_id: UUID,
        pack_revision_id: UUID,
        entry_path: EntryPath,
        seed: str,
    ) -> PlacementRunView:
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._assert_owner(session, actor_id, profile_id)
            existing = await session.scalar(
                text("SELECT run_id FROM placement.runs WHERE profile_id=:profile AND status='active'"),
                {"profile": profile_id},
            )
            if existing is not None:
                return await self._view(session, UUID(str(existing)))
            policy_revision_id = await session.scalar(
                text(
                    "SELECT policy_revision_id FROM placement.policy_revisions "
                    "WHERE policy_code='adaptive-placement-v1' AND status='published'"
                )
            )
            if policy_revision_id is None:
                raise DomainError(ErrorCode.CONTENT_UNAVAILABLE)
            valid_pack = await session.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM placement.item_blueprint_revisions "
                    "WHERE language_pack_revision_id=:pack)"
                ),
                {"pack": pack_revision_id},
            )
            if valid_pack is not True:
                raise DomainError(ErrorCode.CONTENT_UNAVAILABLE)
            run_id = self._ids.new()
            now = self._clock.now()
            await session.execute(
                text(
                    "INSERT INTO placement.runs "
                    "(run_id,profile_id,policy_revision_id,entry_path,status,seed,started_at,version) "
                    "VALUES (:run,:profile,:policy,:entry,'active',:seed,:now,1)"
                ),
                {
                    "run": run_id,
                    "profile": profile_id,
                    "policy": policy_revision_id,
                    "entry": entry_path.value,
                    "seed": seed,
                    "now": now,
                },
            )
            state = self._policy.initial_state(entry_path, MEASURABLE_SKILLS)
            await self._persist_estimates(session, run_id, state.estimates, now)
            await self._select_and_freeze(session, run_id, pack_revision_id, state, seed, 1, now)
            return await self._view(session, run_id)

    async def get_run(self, *, actor_id: UUID, run_id: UUID) -> PlacementRunView:
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            return await self._view(session, run_id)

    async def submit(
        self,
        *,
        actor_id: UUID,
        run_id: UUID,
        item_instance_id: UUID,
        answer: dict[str, JsonValue],
        elapsed_seconds: int,
        idempotency_key: str,
        expected_version: int,
    ) -> PlacementRunView:
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            run = (
                (
                    await session.execute(
                        text(
                            "SELECT run_id,profile_id,status,seed,entry_path,version FROM placement.runs "
                            "WHERE run_id=:run FOR UPDATE"
                        ),
                        {"run": run_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if run is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            replay = await session.scalar(
                text(
                    "SELECT response_id FROM placement.responses "
                    "WHERE run_id=:run AND idempotency_key=:key"
                ),
                {"run": run_id, "key": idempotency_key},
            )
            if replay is not None:
                return await self._view(session, run_id)
            if run["version"] != expected_version:
                raise DomainError(ErrorCode.RESPONSE_STALE)
            item = (
                (
                    await session.execute(
                        text(
                            "SELECT instance.item_instance_id,instance.ordinal,instance.variant_revision_id,"
                            "instance.frozen_payload,revision.primitive_ref,revision.primary_skill_ref,"
                            "revision.level,revision.scorer_kind,variant.variant_pool_id,variant.answer_key,"
                            "variant.rubric_revision_id,revision.language_pack_revision_id "
                            "FROM placement.item_instances instance "
                            "JOIN placement.variant_revisions variant USING(variant_revision_id) "
                            "JOIN placement.item_blueprint_revisions revision USING(blueprint_revision_id) "
                            "WHERE instance.run_id=:run AND instance.item_instance_id=:item "
                            "AND NOT EXISTS (SELECT 1 FROM placement.responses response "
                            "WHERE response.item_instance_id=instance.item_instance_id)"
                        ),
                        {"run": run_id, "item": item_instance_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if item is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            now = self._clock.now()
            response_id = self._ids.new()
            await session.execute(
                text(
                    "INSERT INTO placement.responses "
                    "(response_id,run_id,item_instance_id,idempotency_key,response_payload,elapsed_seconds,submitted_at) "
                    "VALUES (:id,:run,:item,:key,CAST(:payload AS jsonb),:elapsed,:now)"
                ),
                {
                    "id": response_id,
                    "run": run_id,
                    "item": item_instance_id,
                    "key": idempotency_key,
                    "payload": json.dumps(answer, ensure_ascii=False),
                    "elapsed": elapsed_seconds,
                    "now": now,
                },
            )
            scorer_kind = ScoringKind(item["scorer_kind"])
            provider_status: str | None = None
            if scorer_kind is ScoringKind.STRUCTURED_LM:
                try:
                    judgement = await self._evaluator.evaluate(
                        EvaluationTask(
                            prompt=str(item["frozen_payload"]["prompt"]),
                            learner_response=str(answer.get("value", "")),
                            criteria=("task", "grammar", "vocabulary", "coherence"),
                            allowed_skill_refs=(item["primary_skill_ref"],),
                        )
                    )
                    score = sum(value for _, value in judgement.criterion_scores) / (
                        4 * len(judgement.criterion_scores)
                    )
                    confidence = judgement.confidence
                    evaluable = True
                    detail = {"criteria": dict(judgement.criterion_scores), "errors": [asdict(error) for error in judgement.error_observations]}
                    provider_status = "available"
                except DomainError:
                    score, confidence, evaluable = None, 0.0, False
                    detail = {"error": "provider_unavailable"}
                    provider_status = "unavailable"
            else:
                draft = scorer_for(scorer_kind).score(
                    FrozenPlacementItem(
                        str(item["frozen_payload"]["response_kind"]),
                        (item["primary_skill_ref"],),
                        dict(item["answer_key"] or {}),
                    ),
                    PlacementAnswer(answer),
                )
                score, confidence, evaluable = draft.score, draft.confidence, draft.evaluable
                detail = {"errors": draft.error_codes}
            interpretation_id = self._ids.new()
            await session.execute(
                text(
                    "INSERT INTO placement.scoring_interpretations "
                    "(interpretation_id,run_id,response_id,scorer_kind,score,confidence,evaluable,interpretation,provider_status,created_at) "
                    "VALUES (:id,:run,:response,:kind,:score,:confidence,:evaluable,CAST(:detail AS jsonb),:provider,:now)"
                ),
                {
                    "id": interpretation_id,
                    "run": run_id,
                    "response": response_id,
                    "kind": scorer_kind.value,
                    "score": score,
                    "confidence": confidence,
                    "evaluable": evaluable,
                    "detail": json.dumps(detail, ensure_ascii=False),
                    "provider": provider_status,
                    "now": now,
                },
            )
            state = await self._state(session, run_id)
            if evaluable and score is not None:
                observation = PlacementObservation(
                    self._ids.new(),
                    item["variant_pool_id"],
                    item["primitive_ref"],
                    item["primary_skill_ref"],
                    item["level"],
                    float(score),
                    float(confidence),
                    elapsed_seconds,
                    scorer_kind,
                    True,
                )
                await session.execute(
                    text(
                        "INSERT INTO placement.observations "
                        "(observation_id,run_id,interpretation_id,skill_ref,level,score,confidence,independent,created_at) "
                        "VALUES (:id,:run,:interpretation,:skill,:level,:score,:confidence,true,:now)"
                    ),
                    {
                        "id": observation.item_instance_id,
                        "run": run_id,
                        "interpretation": interpretation_id,
                        "skill": observation.skill_ref,
                        "level": observation.level,
                        "score": observation.score,
                        "confidence": observation.confidence,
                        "now": now,
                    },
                )
                state = self._policy.update(state, observation)
                await self._persist_estimates(session, run_id, state.estimates, now)
            total_elapsed = int(
                await session.scalar(
                    text("SELECT COALESCE(sum(elapsed_seconds),0) FROM placement.responses WHERE run_id=:run"),
                    {"run": run_id},
                )
                or 0
            )
            provider_failure_count = int(
                await session.scalar(
                    text(
                        "SELECT count(*) FROM placement.scoring_interpretations "
                        "WHERE run_id=:run AND provider_status='unavailable'"
                    ),
                    {"run": run_id},
                )
                or 0
            )
            stop = self._policy.should_stop(
                state,
                elapsed_seconds=total_elapsed,
                provider_failure_count=provider_failure_count,
            )
            next_ordinal = int(item["ordinal"]) + 1
            if stop.should_stop:
                await self._complete(session, run_id, state, stop.status, stop.reason, now)
            else:
                selected = await self._select_and_freeze(
                    session,
                    run_id,
                    item["language_pack_revision_id"],
                    state,
                    run["seed"],
                    next_ordinal,
                    now,
                    seconds_remaining=max(1, self._policy.maximum_seconds - total_elapsed),
                )
                if not selected:
                    await self._complete(
                        session, run_id, state, PlacementStatus.PARTIAL, "bank_exhausted", now
                    )
                else:
                    await session.execute(
                        text("UPDATE placement.runs SET version=version+1 WHERE run_id=:run"),
                        {"run": run_id},
                    )
            view = await self._view(session, run_id)
            return replace(view, provider_status=provider_status)

    async def choose(
        self,
        *,
        actor_id: UUID,
        run_id: UUID,
        choice: str,
        idempotency_key: str,
        expected_version: int,
    ) -> PlacementRunView:
        async with self._session_factory() as session, session.begin():
            await self._set_actor(session, actor_id)
            replay = await session.scalar(
                text(
                    "SELECT decision_id FROM placement.decisions "
                    "WHERE run_id=:run AND idempotency_key=:key"
                ),
                {"run": run_id, "key": idempotency_key},
            )
            if replay is not None:
                return await self._view(session, run_id)
            run = (
                (
                    await session.execute(
                        text(
                            "SELECT profile_id,version FROM placement.runs "
                            "WHERE run_id=:run FOR UPDATE"
                        ),
                        {"run": run_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if run is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if run["version"] != expected_version:
                raise DomainError(ErrorCode.RESPONSE_STALE)
            source = (
                (
                    await session.execute(
                        text(
                            "SELECT status,result_snapshot FROM placement.decisions "
                            "WHERE run_id=:run AND learner_choice IS NULL "
                            "ORDER BY created_at DESC LIMIT 1"
                        ),
                        {"run": run_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if source is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            await session.execute(
                text(
                    "INSERT INTO placement.decisions "
                    "(decision_id,run_id,status,result_snapshot,learner_choice,idempotency_key,created_at) "
                    "VALUES (:id,:run,:status,CAST(:snapshot AS jsonb),:choice,:key,:now)"
                ),
                {
                    "id": self._ids.new(),
                    "choice": choice,
                    "key": idempotency_key,
                    "run": run_id,
                    "status": source["status"],
                    "snapshot": json.dumps(source["result_snapshot"], default=str),
                    "now": self._clock.now(),
                },
            )
            now = self._clock.now()
            changed = await session.scalar(
                text(
                    "UPDATE language_profiles.learner_language_profiles "
                    "SET status='active',current_phase='module_learning',version=version+1,updated_at=:now "
                    "WHERE profile_id=:profile AND account_id=:actor "
                    "AND status IN ('onboarding','foundations') RETURNING profile_id"
                ),
                {"profile": run["profile_id"], "actor": actor_id, "now": now},
            )
            if changed is None:
                active = await session.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles "
                        "WHERE profile_id=:profile AND account_id=:actor AND status='active')"
                    ),
                    {"profile": run["profile_id"], "actor": actor_id},
                )
                if active is not True:
                    raise DomainError(ErrorCode.INVALID_TRANSITION)
            await session.execute(
                text(
                    "INSERT INTO placement.calibration_cycles "
                    "(calibration_cycle_id,profile_id,source_run_id,phase,completed_daily_runs,status,created_at,updated_at) "
                    "VALUES (:id,:profile,:run,'P0',0,'active',:now,:now) "
                    "ON CONFLICT (source_run_id) DO NOTHING"
                ),
                {
                    "id": self._ids.new(),
                    "profile": run["profile_id"],
                    "run": run_id,
                    "now": now,
                },
            )
            await session.execute(
                text("UPDATE placement.runs SET version=version+1 WHERE run_id=:run"),
                {"run": run_id},
            )
            return await self._view(session, run_id)

    async def _state(self, session: AsyncSession, run_id: UUID) -> PlacementState:
        run = (
            (
                await session.execute(
                    text("SELECT entry_path,status FROM placement.runs WHERE run_id=:run"),
                    {"run": run_id},
                )
            )
            .mappings()
            .one()
        )
        estimates = tuple(
            SkillEstimate(
                row["skill_ref"],
                ObservationStatus(row["status"]),
                row["lower_bound"],
                row["probable_level"],
                row["upper_bound"],
                float(row["confidence"]),
                row["independent_evidence_count"],
                None,
                None,
                tuple(row["unresolved_contradiction_ids"]),
            )
            for row in (
                await session.execute(
                    text(
                        "SELECT DISTINCT ON (skill_ref) * FROM placement.skill_estimate_revisions "
                        "WHERE run_id=:run ORDER BY skill_ref,revision_no DESC"
                    ),
                    {"run": run_id},
                )
            ).mappings()
        )
        pools = tuple(
            (
                await session.execute(
                    text(
                        "SELECT variant.variant_pool_id FROM placement.item_instances instance "
                        "JOIN placement.variant_revisions variant USING(variant_revision_id) "
                        "WHERE instance.run_id=:run"
                    ),
                    {"run": run_id},
                )
            ).scalars()
        )
        return PlacementState(
            EntryPath(run["entry_path"]),
            estimates,
            used_variant_pool_ids=pools,
            status=PlacementStatus(run["status"]),
        )

    async def _candidates(
        self, session: AsyncSession, pack_revision_id: UUID
    ) -> tuple[PlacementCandidate, ...]:
        rows = (
            await session.execute(
                text(
                    "SELECT variant.variant_revision_id,variant.variant_pool_id,revision.primitive_ref,"
                    "revision.primary_skill_ref,revision.level,revision.estimated_seconds,revision.scorer_kind,"
                    "(variant.payload->>'tts_text') IS NOT NULL AS requires_media "
                    "FROM placement.variant_revisions variant JOIN placement.item_blueprint_revisions revision "
                    "USING(blueprint_revision_id) WHERE revision.language_pack_revision_id=:pack "
                    "AND variant.status='published'"
                ),
                {"pack": pack_revision_id},
            )
        ).mappings()
        return tuple(
            PlacementCandidate(
                row["variant_revision_id"],
                row["variant_pool_id"],
                row["primitive_ref"],
                row["primary_skill_ref"],
                row["level"],
                row["estimated_seconds"],
                ScoringKind(row["scorer_kind"]),
                requires_media=row["requires_media"],
                media_available=True,
            )
            for row in rows
        )

    async def _select_and_freeze(
        self,
        session: AsyncSession,
        run_id: UUID,
        pack_revision_id: UUID,
        state: PlacementState,
        seed: str,
        ordinal: int,
        now: datetime,
        *,
        seconds_remaining: int = 1200,
    ) -> bool:
        decision = self._policy.select(
            state,
            await self._candidates(session, pack_revision_id),
            seconds_remaining=seconds_remaining,
            seed=seed,
        )
        if decision.candidate is None:
            return False
        payload = await session.scalar(
            text("SELECT payload FROM placement.variant_revisions WHERE variant_revision_id=:id"),
            {"id": decision.candidate.variant_revision_id},
        )
        await session.execute(
            text(
                "INSERT INTO placement.item_instances "
                "(item_instance_id,run_id,variant_revision_id,ordinal,frozen_payload,selected_reason,presented_at) "
                "VALUES (:id,:run,:variant,:ordinal,CAST(:payload AS jsonb),CAST(:reason AS jsonb),:now)"
            ),
            {
                "id": self._ids.new(),
                "run": run_id,
                "variant": decision.candidate.variant_revision_id,
                "ordinal": ordinal,
                "payload": json.dumps(payload, ensure_ascii=False),
                "reason": json.dumps({"primary": decision.reason}),
                "now": now,
            },
        )
        return True

    async def _persist_estimates(
        self,
        session: AsyncSession,
        run_id: UUID,
        estimates: tuple[SkillEstimate, ...],
        now: datetime,
    ) -> None:
        for estimate in estimates:
            revision = int(
                await session.scalar(
                    text(
                        "SELECT COALESCE(max(revision_no),0)+1 FROM placement.skill_estimate_revisions "
                        "WHERE run_id=:run AND skill_ref=:skill"
                    ),
                    {"run": run_id, "skill": estimate.skill_ref},
                )
                or 1
            )
            await session.execute(
                text(
                    "INSERT INTO placement.skill_estimate_revisions "
                    "(estimate_revision_id,run_id,skill_ref,revision_no,status,lower_bound,probable_level,upper_bound,confidence,independent_evidence_count,unresolved_contradiction_ids,created_at) "
                    "VALUES (:id,:run,:skill,:revision,:status,:lower,:probable,:upper,:confidence,:count,:contradictions,:now)"
                ),
                {
                    "id": self._ids.new(),
                    "run": run_id,
                    "skill": estimate.skill_ref,
                    "revision": revision,
                    "status": estimate.status.value,
                    "lower": estimate.lower_bound,
                    "probable": estimate.probable_level,
                    "upper": estimate.upper_bound,
                    "confidence": estimate.confidence,
                    "count": estimate.independent_evidence_count,
                    "contradictions": list(estimate.unresolved_contradiction_ids),
                    "now": now,
                },
            )

    async def _complete(
        self,
        session: AsyncSession,
        run_id: UUID,
        state: PlacementState,
        status: PlacementStatus,
        reason: str,
        now: datetime,
    ) -> None:
        snapshot = {item.skill_ref: asdict(item) for item in state.estimates}
        await session.execute(
            text(
                "INSERT INTO placement.decisions "
                "(decision_id,run_id,status,result_snapshot,created_at) "
                "VALUES (:id,:run,:status,CAST(:snapshot AS jsonb),:now)"
            ),
            {
                "id": self._ids.new(),
                "run": run_id,
                "status": status.value,
                "snapshot": json.dumps(snapshot, default=str),
                "now": now,
            },
        )
        await session.execute(
            text(
                "UPDATE placement.runs SET status=:status,completed_at=:now,version=version+1 "
                "WHERE run_id=:run"
            ),
            {"run": run_id, "status": status.value, "now": now},
        )

    async def _view(self, session: AsyncSession, run_id: UUID) -> PlacementRunView:
        run = (
            (
                await session.execute(
                    text(
                        "SELECT run_id,profile_id,status,version FROM placement.runs WHERE run_id=:run"
                    ),
                    {"run": run_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if run is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        current = (
            (
                await session.execute(
                    text(
                        "SELECT instance.item_instance_id,instance.ordinal,instance.frozen_payload,"
                        "revision.primitive_ref,revision.primary_skill_ref,revision.estimated_seconds "
                        "FROM placement.item_instances instance JOIN placement.variant_revisions variant "
                        "USING(variant_revision_id) JOIN placement.item_blueprint_revisions revision "
                        "USING(blueprint_revision_id) WHERE instance.run_id=:run AND NOT EXISTS "
                        "(SELECT 1 FROM placement.responses response WHERE response.item_instance_id=instance.item_instance_id) "
                        "ORDER BY instance.ordinal DESC LIMIT 1"
                    ),
                    {"run": run_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        item = None
        if current is not None:
            item = PlacementItemView(
                current["item_instance_id"],
                current["ordinal"],
                current["primitive_ref"],
                current["primary_skill_ref"],
                dict(current["frozen_payload"]),
                current["estimated_seconds"],
            )
        estimates = (await self._state(session, run_id)).estimates
        elapsed = int(
            await session.scalar(
                text("SELECT COALESCE(sum(elapsed_seconds),0) FROM placement.responses WHERE run_id=:run"),
                {"run": run_id},
            )
            or 0
        )
        decision = (
            (
                await session.execute(
                    text(
                        "SELECT result_snapshot FROM placement.decisions WHERE run_id=:run "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"run": run_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return PlacementRunView(
            run["run_id"],
            run["profile_id"],
            PlacementStatus(run["status"]),
            run["version"],
            elapsed,
            item,
            estimates,
            "completed" if decision is not None else None,
        )
