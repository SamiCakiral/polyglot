# ruff: noqa: E501

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.exercises.core.domain import (
    CorrectionResult,
    CorrectionVerdict,
    primitive_spec,
)
from polyglot.modules.progress.domain import (
    DelayBand,
    EvidenceSource,
    HelpLevel,
    LearningEvidence,
    LearningObservation,
    MasteryProjection,
    MasteryStatus,
    Modality,
    ObservationResult,
    ObservationRole,
    evidence_from_observation,
    project_mastery,
    projection_fingerprint,
)
from polyglot.modules.progress.recommendations import (
    RecommendationFactors,
    open_learning_need,
    recommend_for_need,
)
from polyglot.platform.clock import Clock, SystemClock
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator

MASTERY_POLICY_ID = UUID("019fab00-0000-7000-8000-000000000001")
CONSUMER_CODE = "progress-projector-v1"


@dataclass(frozen=True, slots=True)
class ProjectionUpdateResult:
    processed: bool
    profile_id: UUID
    projection_count: int
    need_count: int
    recommendation_count: int
    fingerprint: str


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _evidence_from_row(row: object) -> LearningEvidence:
    item = cast(dict[str, object], row)
    return LearningEvidence(
        evidence_id=UUID(str(item["evidence_id"])),
        observation_id=UUID(str(item["observation_id"])),
        profile_id=UUID(str(item["profile_id"])),
        target_type=str(item["target_type"]),
        target_id=str(item["target_id"]),
        facet_key=str(item["facet_key"]),
        modality=Modality(str(item["modality"])),
        operation=str(item["operation"]),
        evidence_score=float(str(item["evidence_score"])),
        evidence_mass=float(str(item["evidence_mass"])),
        source_weight=float(str(item["source_weight"])),
        independence_weight=float(str(item["independence_weight"])),
        opportunity_id=UUID(str(item["opportunity_id"])),
        pedagogical_session_id=str(item["pedagogical_session_id"]),
        context_family_id=str(item["context_family_id"]),
        delay_band=DelayBand(str(item["delay_band"])),
        transfer=bool(item["transfer"]),
        policy_revision_id="MASTERY_V0",
        created_at=cast(datetime, item["created_at"]),
        eligible=bool(item["eligible"]),
        direct=bool(item["direct"]),
        invalidated_at=cast(datetime | None, item.get("effective_invalidated_at")),
        replacement_evidence_id=(
            None
            if item.get("replacement_fact_id") is None
            else UUID(str(item["replacement_fact_id"]))
        ),
    )


class SqlProgressRepository:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        id_generator: IdGenerator | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._sessions = sessions
        self._ids = id_generator or Uuid7Generator()
        self._clock = clock or SystemClock()

    async def consume_event(
        self,
        *,
        actor_id: UUID,
        event_id: UUID,
    ) -> ProjectionUpdateResult:
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            event = (
                (
                    await session.execute(
                        text(
                            "SELECT event_type,aggregate_id,profile_id FROM platform.domain_events "
                            "WHERE event_id=:event"
                        ),
                        {"event": event_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if event is None or event["profile_id"] is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if event["event_type"] not in {
                "exercise_attempt_corrected",
                "attempt_not_evaluable",
            }:
                raise DomainError(ErrorCode.VALIDATION_FAILED, detail="unsupported progress event")
            source = (
                (
                    await session.execute(
                        text(
                            "SELECT attempt.attempt_id,attempt.profile_id,attempt.instance_id,"
                            "attempt.answer_kind,correction.correction_id,correction.verdict,"
                            "correction.confidence,correction.target_coverage,correction.created_at,"
                            "instance.target_bindings,definition.primitive_id,definition.target_weights,"
                            "block.modalities,block.family,plan.plan_kind,plan_revision.plan_revision_id,"
                            "COALESCE((SELECT max(hint.level) FROM exercises.exercise_hint_uses hint "
                            "WHERE hint.attempt_id=attempt.attempt_id),'h0') AS help_level "
                            "FROM exercises.exercise_attempts attempt "
                            "JOIN exercises.exercise_corrections correction "
                            "ON correction.attempt_id=attempt.attempt_id AND correction.is_current "
                            "JOIN exercises.exercise_instances instance ON instance.instance_id=attempt.instance_id "
                            "JOIN exercises.exercise_definition_revisions definition "
                            "ON definition.definition_revision_id=instance.definition_revision_id "
                            "LEFT JOIN planning.session_plan_exercise_instances link "
                            "ON link.instance_id=instance.instance_id "
                            "LEFT JOIN planning.session_plan_blocks block "
                            "ON block.session_plan_block_id=link.session_plan_block_id "
                            "LEFT JOIN planning.session_plan_revisions plan_revision "
                            "ON plan_revision.plan_revision_id=link.plan_revision_id "
                            "LEFT JOIN planning.session_plans plan ON plan.plan_id=plan_revision.plan_id "
                            "WHERE attempt.attempt_id=:attempt"
                        ),
                        {"attempt": event["aggregate_id"]},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if source is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        observations = self._observations_from_correction(dict(source))
        if not observations:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED,
                detail="corrected exercise has no explicit learning target",
            )
        return await self.ingest_observations(
            actor_id=actor_id,
            event_id=event_id,
            observations=observations,
        )

    def _observations_from_correction(
        self,
        source: dict[str, object],
    ) -> tuple[LearningObservation, ...]:
        primitive_id = str(source["primitive_id"])
        spec = primitive_spec(primitive_id)
        verdict = CorrectionVerdict(str(source["verdict"]))
        result = CorrectionResult(
            verdict=verdict,
            confidence=float(str(source["confidence"])),
            target_coverage=float(str(source["target_coverage"])),
            explanation="persisted exercise correction",
        )
        target_weights = cast(list[list[object]], source["target_weights"])
        target_weight = max((float(str(item[1])) for item in target_weights), default=1.0)
        help_level = HelpLevel(str(source["help_level"]))
        value = result.credit_value(
            operation_cap=spec.operation_cap,
            target_weight=target_weight,
            hint_level=help_level.value,
        )
        observation_result = {
            CorrectionVerdict.CORRECT: ObservationResult.SUCCESS,
            CorrectionVerdict.PARTIALLY_CORRECT: ObservationResult.PARTIAL_SUCCESS,
            CorrectionVerdict.INCORRECT: ObservationResult.FAILURE,
        }.get(verdict, ObservationResult.INCONCLUSIVE)
        operation = self._operation_for_primitive(primitive_id)
        modality = self._modality_for(
            primitive_id,
            cast(list[str] | None, source.get("modalities")),
            str(source.get("answer_kind") or ""),
        )
        plan_kind = str(source.get("plan_kind") or "free")
        evidence_source = (
            EvidenceSource.PLANNED_SPRINT if plan_kind == "daily" else EvidenceSource.FREE_PRACTICE
        )
        session_ref = str(source.get("plan_revision_id") or source["instance_id"])
        context_ref = str(source.get("family") or primitive_id)
        observations: list[LearningObservation] = []
        for raw_target in cast(list[object], source["target_bindings"]):
            target_type, target_id, facet_key, target_modality = self._target_contract(
                raw_target,
                operation=operation,
                default_modality=modality,
            )
            observations.append(
                LearningObservation(
                    observation_id=self._ids.new(),
                    profile_id=UUID(str(source["profile_id"])),
                    attempt_id=UUID(str(source["attempt_id"])),
                    correction_id=UUID(str(source["correction_id"])),
                    target_type=target_type,
                    target_id=target_id,
                    facet_key=facet_key,
                    modality=target_modality,
                    operation=operation,
                    role=ObservationRole.PRIMARY,
                    result=observation_result,
                    observation_value=0.0 if value is None else value,
                    correction_confidence=float(str(source["confidence"])),
                    target_coverage=float(str(source["target_coverage"])),
                    help_level=help_level,
                    opportunity_id=UUID(str(source["attempt_id"])),
                    pedagogical_session_id=session_ref,
                    context_family_id=context_ref,
                    source=evidence_source,
                    delay_band=(
                        DelayBand.ONE_TO_SIX_DAYS
                        if source.get("family") == "delayed_recode"
                        else DelayBand.SAME_SESSION
                    ),
                    policy_revision_id="OBSERVATION_V0",
                    created_at=cast(datetime, source["created_at"]),
                    transfer=operation == "transfer",
                )
            )
        return tuple(observations)

    @staticmethod
    def _operation_for_primitive(primitive_id: str) -> str:
        if primitive_id.startswith("EX-COMP"):
            return "recognize"
        if primitive_id.startswith("EX-DISC"):
            return "discriminate"
        if primitive_id.startswith("EX-TRANSFORM"):
            return "transform"
        if primitive_id.startswith("EX-PROD"):
            return "produce"
        if primitive_id.startswith("EX-ORAL"):
            return "interact"
        if primitive_id.startswith("EX-REPAIR"):
            return "repair"
        return "recall"

    @staticmethod
    def _modality_for(
        primitive_id: str,
        planned: list[str] | None,
        answer_kind: str,
    ) -> Modality:
        available = tuple(Modality(item) for item in (planned or ()))
        if answer_kind == "audio_ref" or primitive_id.startswith("EX-ORAL"):
            return Modality.SPEAKING
        if primitive_id == "EX-COMP-02" and Modality.LISTENING in available:
            return Modality.LISTENING
        if primitive_id.startswith(("EX-COMP", "EX-DISC")):
            return Modality.READING
        if Modality.WRITING in available or not available:
            return Modality.WRITING
        return available[0]

    @staticmethod
    def _target_contract(
        raw: object,
        *,
        operation: str,
        default_modality: Modality,
    ) -> tuple[str, str, str, Modality]:
        if isinstance(raw, dict):
            target_id = str(raw.get("target_id") or raw.get("ref") or "")
            if not target_id:
                raise DomainError(ErrorCode.VALIDATION_FAILED, detail="empty target binding")
            return (
                str(raw.get("target_type") or "skill"),
                target_id,
                str(raw.get("facet_key") or operation),
                Modality(str(raw.get("modality") or default_modality.value)),
            )
        target_ref = str(raw)
        prefix, separator, identifier = target_ref.partition(":")
        if not separator or not identifier:
            return "skill", target_ref, operation, default_modality
        target_type = {
            "grammar": "grammar_structure",
            "skill": "skill",
            "lexical": "lexical_sense",
            "form": "lexical_form",
            "pronunciation": "pronunciation_target",
        }.get(prefix, "skill")
        return target_type, identifier, operation, default_modality

    async def ingest_observations(
        self,
        *,
        actor_id: UUID,
        event_id: UUID,
        observations: tuple[LearningObservation, ...],
    ) -> ProjectionUpdateResult:
        if not observations:
            raise ValueError("at least one observation is required")
        profile_ids = {item.profile_id for item in observations}
        if len(profile_ids) != 1:
            raise ValueError("one event cannot update multiple profiles")
        profile_id = next(iter(profile_ids))
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
                {"scope": f"{CONSUMER_CODE}:{event_id}"},
            )
            receipt = await session.scalar(
                text(
                    "SELECT result_checksum FROM platform.inbox_receipts "
                    "WHERE consumer_code=:consumer AND event_id=:event"
                ),
                {"consumer": CONSUMER_CODE, "event": event_id},
            )
            if receipt is not None:
                current = await self._summary(session, profile_id, processed=False)
                if current.fingerprint != str(receipt):
                    raise DomainError(ErrorCode.RESPONSE_CONFLICT)
                return current
            for observation in observations:
                evidence_id = self._ids.new()
                evidence, reasons = evidence_from_observation(
                    observation,
                    evidence_id=evidence_id,
                )
                await self._invalidate_superseded_facts(
                    session,
                    observation=observation,
                    replacement_evidence_id=evidence_id,
                    source_event_id=event_id,
                )
                await self._insert_observation(session, observation)
                await self._insert_evidence(session, evidence, reasons)
            await self._rebuild(session, profile_id, event_id=event_id)
            result = await self._summary(session, profile_id, processed=True)
            await session.execute(
                text(
                    "INSERT INTO platform.inbox_receipts "
                    "(consumer_code,event_id,processed_at,result_checksum) "
                    "VALUES (:consumer,:event,:processed,:checksum)"
                ),
                {
                    "consumer": CONSUMER_CODE,
                    "event": event_id,
                    "processed": self._clock.now(),
                    "checksum": result.fingerprint,
                },
            )
            return result

    async def _invalidate_superseded_facts(
        self,
        session: AsyncSession,
        *,
        observation: LearningObservation,
        replacement_evidence_id: UUID,
        source_event_id: UUID,
    ) -> None:
        previous = (
            (
                await session.execute(
                    text(
                        "SELECT old.observation_id,evidence.evidence_id "
                        "FROM progress.learning_observations old "
                        "JOIN progress.learning_evidence evidence "
                        "ON evidence.observation_id=old.observation_id "
                        "LEFT JOIN progress.fact_invalidations invalidation "
                        "ON invalidation.fact_type='observation' "
                        "AND invalidation.fact_id=old.observation_id "
                        "WHERE old.profile_id=:profile AND old.opportunity_id=:opportunity "
                        "AND old.target_type=:target_type AND old.target_id=:target "
                        "AND old.facet_key=:facet AND old.modality=:modality "
                        "AND old.operation=:operation AND old.correction_id<>:correction "
                        "AND invalidation.invalidation_id IS NULL "
                        "ORDER BY old.created_at DESC LIMIT 1"
                    ),
                    {
                        "profile": observation.profile_id,
                        "opportunity": observation.opportunity_id,
                        "target_type": observation.target_type,
                        "target": observation.target_id,
                        "facet": observation.facet_key,
                        "modality": observation.modality.value,
                        "operation": observation.operation,
                        "correction": observation.correction_id,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        if previous is None:
            return
        for fact_type, fact_id, replacement_id in (
            (
                "observation",
                previous["observation_id"],
                observation.observation_id,
            ),
            ("evidence", previous["evidence_id"], replacement_evidence_id),
        ):
            await session.execute(
                text(
                    "INSERT INTO progress.fact_invalidations "
                    "(invalidation_id,profile_id,fact_type,fact_id,replacement_fact_id,"
                    "reason_code,invalidated_at,source_event_id) VALUES "
                    "(:invalidation,:profile,:type,:fact,:replacement,'correction_revised',"
                    ":invalidated,:event)"
                ),
                {
                    "invalidation": self._ids.new(),
                    "profile": observation.profile_id,
                    "type": fact_type,
                    "fact": fact_id,
                    "replacement": replacement_id,
                    "invalidated": observation.created_at,
                    "event": source_event_id,
                },
            )

    async def rebuild_profile(
        self,
        *,
        actor_id: UUID,
        profile_id: UUID,
    ) -> ProjectionUpdateResult:
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
                {"scope": f"{CONSUMER_CODE}:rebuild:{profile_id}"},
            )
            await self._rebuild(session, profile_id, event_id=None)
            return await self._summary(session, profile_id, processed=True)

    async def _rebuild(
        self,
        session: AsyncSession,
        profile_id: UUID,
        *,
        event_id: UUID | None,
    ) -> None:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT evidence.*,invalidation.invalidated_at AS effective_invalidated_at,"
                        "invalidation.replacement_fact_id FROM progress.learning_evidence evidence "
                        "LEFT JOIN progress.fact_invalidations invalidation "
                        "ON invalidation.fact_type='evidence' AND invalidation.fact_id=evidence.evidence_id "
                        "WHERE evidence.profile_id=:profile ORDER BY evidence.created_at,evidence.evidence_id"
                    ),
                    {"profile": profile_id},
                )
            )
            .mappings()
            .all()
        )
        grouped: dict[tuple[str, str, str, Modality, str], list[LearningEvidence]] = defaultdict(
            list
        )
        for row in rows:
            evidence = _evidence_from_row(dict(row))
            grouped[
                (
                    evidence.target_type,
                    evidence.target_id,
                    evidence.facet_key,
                    evidence.modality,
                    evidence.operation,
                )
            ].append(evidence)
        await session.execute(
            text("DELETE FROM progress.personal_sense_facets WHERE profile_id=:profile"),
            {"profile": profile_id},
        )
        existing_keys: set[tuple[str, str, str, str, str]] = set()
        for key in sorted(grouped, key=lambda item: tuple(str(value) for value in item)):
            target_type, target_id, facet_key, modality, operation = key
            existing_status = await session.scalar(
                text(
                    "SELECT status FROM progress.mastery_projections WHERE profile_id=:profile "
                    "AND target_type=:target_type AND target_id=:target AND facet_key=:facet "
                    "AND modality=:modality AND operation=:operation"
                ),
                {
                    "profile": profile_id,
                    "target_type": target_type,
                    "target": target_id,
                    "facet": facet_key,
                    "modality": modality.value,
                    "operation": operation,
                },
            )
            projection = project_mastery(
                tuple(grouped[key]),
                as_of=self._clock.now(),
                modality=modality,
                previous_status=(MasteryStatus(str(existing_status)) if existing_status else None),
            )
            await self._upsert_projection(
                session,
                profile_id=profile_id,
                target_type=target_type,
                target_id=target_id,
                facet_key=facet_key,
                operation=operation,
                projection=projection,
                event_id=event_id,
            )
            await self._insert_personal_sense_facet(
                session,
                profile_id=profile_id,
                target_type=target_type,
                target_id=target_id,
                operation=operation,
                projection=projection,
                event_id=event_id,
            )
            await self._project_need(
                session,
                evidence=tuple(grouped[key]),
                projection=projection,
            )
            existing_keys.add((target_type, target_id, facet_key, modality.value, operation))
        if not existing_keys:
            await session.execute(
                text("DELETE FROM progress.mastery_projections WHERE profile_id=:profile"),
                {"profile": profile_id},
            )
        else:
            clauses = []
            parameters: dict[str, object] = {"profile": profile_id}
            for index, stored_key in enumerate(sorted(existing_keys)):
                clauses.append(
                    f"(target_type=:tt{index} AND target_id=:ti{index} AND facet_key=:fk{index} "
                    f"AND modality=:mo{index} AND operation=:op{index})"
                )
                parameters.update(
                    {
                        f"tt{index}": stored_key[0],
                        f"ti{index}": stored_key[1],
                        f"fk{index}": stored_key[2],
                        f"mo{index}": stored_key[3],
                        f"op{index}": stored_key[4],
                    }
                )
            await session.execute(
                text(
                    "DELETE FROM progress.mastery_projections WHERE profile_id=:profile AND NOT ("
                    + " OR ".join(clauses)
                    + ")"
                ),
                parameters,
            )
        fingerprint = await self._projection_set_fingerprint(session, profile_id)
        now = self._clock.now()
        await session.execute(
            text(
                "INSERT INTO progress.consumer_cursors "
                "(consumer_code,profile_id,last_event_id,last_occurred_at,projection_fingerprint,"
                "version,updated_at) VALUES (:consumer,:profile,:event,:now,:fingerprint,1,:now) "
                "ON CONFLICT (consumer_code,profile_id) DO UPDATE SET "
                "last_event_id=COALESCE(EXCLUDED.last_event_id,progress.consumer_cursors.last_event_id),"
                "last_occurred_at=EXCLUDED.last_occurred_at,"
                "projection_fingerprint=EXCLUDED.projection_fingerprint,"
                "version=progress.consumer_cursors.version+1,updated_at=EXCLUDED.updated_at"
            ),
            {
                "consumer": CONSUMER_CODE,
                "profile": profile_id,
                "event": event_id,
                "now": now,
                "fingerprint": fingerprint,
            },
        )

    async def _insert_personal_sense_facet(
        self,
        session: AsyncSession,
        *,
        profile_id: UUID,
        target_type: str,
        target_id: str,
        operation: str,
        projection: MasteryProjection,
        event_id: UUID | None,
    ) -> None:
        if target_type != "lexical_sense" or projection.modality is None:
            return
        try:
            sense_id = UUID(target_id)
        except ValueError:
            return
        direction = (
            "target_to_support"
            if projection.modality in {Modality.READING, Modality.LISTENING}
            else "support_to_target"
        )
        await session.execute(
            text(
                "INSERT INTO progress.personal_sense_facets "
                "(profile_id,sense_id,modality,operation,direction,mastery_status,score,confidence,"
                "freshness,evidence_count,contradiction_count,last_activity_at,next_verification_at,"
                "projection_version,policy_revision_id,last_event_id) VALUES "
                "(:profile,:sense,:modality,:operation,:direction,:status,:score,:confidence,"
                ":freshness,:evidence_count,:contradictions,:last,:next,1,:policy,:event)"
            ),
            {
                "profile": profile_id,
                "sense": sense_id,
                "modality": projection.modality.value,
                "operation": operation,
                "direction": direction,
                "status": projection.status.value,
                "score": projection.mastery_current,
                "confidence": projection.confidence,
                "freshness": projection.freshness,
                "evidence_count": len(projection.evidence_ids),
                "contradictions": projection.failure_count,
                "last": projection.last_evidence_at,
                "next": projection.next_verification_at,
                "policy": MASTERY_POLICY_ID,
                "event": event_id,
            },
        )

    async def _project_need(
        self,
        session: AsyncSession,
        *,
        evidence: tuple[LearningEvidence, ...],
        projection: MasteryProjection,
    ) -> None:
        current = tuple(
            item
            for item in evidence
            if item.eligible and item.invalidated_at is None and item.evidence_mass > 0
        )
        if not current:
            return
        latest = max(current, key=lambda item: (item.created_at, item.evidence_id.int))
        active = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM progress.learning_needs WHERE profile_id=:profile "
                        "AND target_type=:target_type AND target_id=:target AND facet_key=:facet "
                        "AND status IN ('open','planned') FOR UPDATE"
                    ),
                    {
                        "profile": latest.profile_id,
                        "target_type": latest.target_type,
                        "target": latest.target_id,
                        "facet": latest.facet_key,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        if latest.evidence_score < 0.5 and latest.direct:
            if active is None:
                need = open_learning_need(
                    need_id=self._ids.new(),
                    cause_id=self._ids.new(),
                    evidence=latest,
                    opened_at=latest.created_at,
                    taught=True,
                )
                if need is None:
                    return
                await session.execute(
                    text(
                        "INSERT INTO progress.learning_needs "
                        "(need_id,profile_id,target_type,target_id,facet_key,status,urgency,opened_at,version) "
                        "VALUES (:need,:profile,:target_type,:target,:facet,'open',:urgency,:opened,1)"
                    ),
                    {
                        "need": need.need_id,
                        "profile": need.profile_id,
                        "target_type": need.target_type,
                        "target": need.target_id,
                        "facet": need.facet_key,
                        "urgency": need.urgency,
                        "opened": need.opened_at,
                    },
                )
                cause = need.causes[0]
                await session.execute(
                    text(
                        "INSERT INTO progress.learning_need_causes "
                        "(cause_id,need_id,profile_id,cause_type,source_fact_id,opened_at) "
                        "VALUES (:cause,:need,:profile,:type,:source,:opened)"
                    ),
                    {
                        "cause": cause.cause_id,
                        "need": need.need_id,
                        "profile": need.profile_id,
                        "type": cause.cause_type,
                        "source": cause.source_fact_id,
                        "opened": cause.opened_at,
                    },
                )
                recommendation = recommend_for_need(
                    recommendation_id=self._ids.new(),
                    need=need,
                    projection=projection,
                    factors=RecommendationFactors(0.8, 0.4, 0.8, 1.0, 0.6),
                    created_at=self._clock.now(),
                )
                await session.execute(
                    text(
                        "INSERT INTO progress.recommendations "
                        "(recommendation_id,profile_id,target_type,target_id,facet_key,need_id,"
                        "reason_code,reason_params,missing_evidence_spec,proposed_activity,priority,"
                        "urgency,estimated_duration_ms,policy_revision_id,created_at,expires_at) "
                        "VALUES (:recommendation,:profile,:target_type,:target,:facet,:need,:reason,"
                        "CAST(:params AS jsonb),CAST(:missing AS jsonb),CAST(:activity AS jsonb),"
                        ":priority,:urgency,:duration,:policy,:created,:expires)"
                    ),
                    {
                        "recommendation": recommendation.recommendation_id,
                        "profile": recommendation.profile_id,
                        "target_type": recommendation.target_type,
                        "target": recommendation.target_id,
                        "facet": recommendation.facet_key,
                        "need": recommendation.need_id,
                        "reason": recommendation.reason_code,
                        "params": _json(dict(recommendation.reason_params)),
                        "missing": _json(dict(recommendation.missing_evidence_spec)),
                        "activity": _json(dict(recommendation.proposed_activity)),
                        "priority": recommendation.priority,
                        "urgency": recommendation.urgency,
                        "duration": recommendation.estimated_duration_ms,
                        "policy": MASTERY_POLICY_ID,
                        "created": recommendation.created_at,
                        "expires": recommendation.expires_at,
                    },
                )
            else:
                await session.execute(
                    text(
                        "INSERT INTO progress.learning_need_causes "
                        "(cause_id,need_id,profile_id,cause_type,source_fact_id,opened_at) "
                        "VALUES (:cause,:need,:profile,'direct_failure',:source,:opened) "
                        "ON CONFLICT (need_id,cause_type,source_fact_id) DO NOTHING"
                    ),
                    {
                        "cause": self._ids.new(),
                        "need": active["need_id"],
                        "profile": latest.profile_id,
                        "source": latest.evidence_id,
                        "opened": latest.created_at,
                    },
                )
        elif (
            active is not None
            and latest.evidence_score >= 0.75
            and latest.created_at > active["opened_at"]
        ):
            await session.execute(
                text(
                    "UPDATE progress.learning_needs SET status='resolved',resolved_at=:resolved,"
                    "resolution_policy_revision_id=:policy,resolution_evidence_id=:evidence,"
                    "version=version+1 WHERE need_id=:need"
                ),
                {
                    "resolved": latest.created_at,
                    "policy": MASTERY_POLICY_ID,
                    "evidence": latest.evidence_id,
                    "need": active["need_id"],
                },
            )

    async def _insert_observation(
        self,
        session: AsyncSession,
        observation: LearningObservation,
    ) -> None:
        await session.execute(
            text(
                "INSERT INTO progress.learning_observations "
                "(observation_id,profile_id,attempt_id,correction_id,target_type,target_id,facet_key,"
                "modality,operation,role,result,observation_value,correction_confidence,target_coverage,"
                "help_level,opportunity_id,pedagogical_session_id,context_family_id,source_type,"
                "delay_band,transfer,direct,independence_weight,policy_revision_id,created_at,"
                "invalidated_at,replacement_observation_id,invalidation_reason) VALUES "
                "(:observation,:profile,:attempt,:correction,:target_type,:target,:facet,:modality,"
                ":operation,:role,:result,:value,:confidence,:coverage,:help,:opportunity,:session,"
                ":context,:source,:delay,:transfer,:direct,:independence,:policy,:created,:invalidated,"
                ":replacement,:reason)"
            ),
            {
                "observation": observation.observation_id,
                "profile": observation.profile_id,
                "attempt": observation.attempt_id,
                "correction": observation.correction_id,
                "target_type": observation.target_type,
                "target": observation.target_id,
                "facet": observation.facet_key,
                "modality": observation.modality.value,
                "operation": observation.operation,
                "role": observation.role.value,
                "result": observation.result.value,
                "value": observation.observation_value,
                "confidence": observation.correction_confidence,
                "coverage": observation.target_coverage,
                "help": observation.help_level.value,
                "opportunity": observation.opportunity_id,
                "session": observation.pedagogical_session_id,
                "context": observation.context_family_id,
                "source": observation.source.value,
                "delay": observation.delay_band.value,
                "transfer": observation.transfer,
                "direct": observation.direct,
                "independence": observation.independence_weight,
                "policy": MASTERY_POLICY_ID,
                "created": observation.created_at,
                "invalidated": observation.invalidated_at,
                "replacement": observation.replacement_observation_id,
                "reason": observation.invalidation_reason,
            },
        )

    async def _insert_evidence(
        self,
        session: AsyncSession,
        evidence: LearningEvidence,
        reasons: tuple[str, ...],
    ) -> None:
        await session.execute(
            text(
                "INSERT INTO progress.learning_evidence "
                "(evidence_id,profile_id,observation_id,target_type,target_id,facet_key,modality,"
                "operation,evidence_score,evidence_mass,source_weight,independence_weight,"
                "opportunity_id,pedagogical_session_id,context_family_id,delay_band,eligible,direct,"
                "transfer,ineligibility_reasons,policy_revision_id,created_at,invalidated_at,"
                "replacement_evidence_id) VALUES "
                "(:evidence,:profile,:observation,:target_type,:target,:facet,:modality,:operation,"
                ":score,:mass,:source_weight,:independence,:opportunity,:session,:context,:delay,"
                ":eligible,:direct,:transfer,:reasons,:policy,:created,:invalidated,:replacement)"
            ),
            {
                "evidence": evidence.evidence_id,
                "profile": evidence.profile_id,
                "observation": evidence.observation_id,
                "target_type": evidence.target_type,
                "target": evidence.target_id,
                "facet": evidence.facet_key,
                "modality": evidence.modality.value,
                "operation": evidence.operation,
                "score": evidence.evidence_score,
                "mass": evidence.evidence_mass,
                "source_weight": evidence.source_weight,
                "independence": evidence.independence_weight,
                "opportunity": evidence.opportunity_id,
                "session": evidence.pedagogical_session_id,
                "context": evidence.context_family_id,
                "delay": evidence.delay_band.value,
                "eligible": evidence.eligible,
                "direct": evidence.direct,
                "transfer": evidence.transfer,
                "reasons": list(reasons),
                "policy": MASTERY_POLICY_ID,
                "created": evidence.created_at,
                "invalidated": evidence.invalidated_at,
                "replacement": evidence.replacement_evidence_id,
            },
        )

    async def _upsert_projection(
        self,
        session: AsyncSession,
        *,
        profile_id: UUID,
        target_type: str,
        target_id: str,
        facet_key: str,
        operation: str,
        projection: MasteryProjection,
        event_id: UUID | None,
    ) -> None:
        fingerprint = projection_fingerprint(projection)
        await session.execute(
            text(
                "INSERT INTO progress.mastery_projections "
                "(profile_id,target_type,target_id,facet_key,modality,operation,status,mastery_base,"
                "mastery_current,confidence,freshness,effective_mass,success_count,failure_count,"
                "context_count,session_count,delay_band_count,transfer_count,last_evidence_at,"
                "next_verification_at,policy_revision_id,projection_version,last_event_id,"
                "projection_fingerprint,computed_at) VALUES "
                "(:profile,:target_type,:target,:facet,:modality,:operation,:status,:base,:current,"
                ":confidence,:freshness,:mass,:success,:failure,:contexts,:sessions,:delays,:transfers,"
                ":last,:next,:policy,1,:event,:fingerprint,:computed) "
                "ON CONFLICT (profile_id,target_type,target_id,facet_key,modality,operation) "
                "DO UPDATE SET status=EXCLUDED.status,mastery_base=EXCLUDED.mastery_base,"
                "mastery_current=EXCLUDED.mastery_current,confidence=EXCLUDED.confidence,"
                "freshness=EXCLUDED.freshness,effective_mass=EXCLUDED.effective_mass,"
                "success_count=EXCLUDED.success_count,failure_count=EXCLUDED.failure_count,"
                "context_count=EXCLUDED.context_count,session_count=EXCLUDED.session_count,"
                "delay_band_count=EXCLUDED.delay_band_count,transfer_count=EXCLUDED.transfer_count,"
                "last_evidence_at=EXCLUDED.last_evidence_at,next_verification_at=EXCLUDED.next_verification_at,"
                "policy_revision_id=EXCLUDED.policy_revision_id,"
                "projection_version=progress.mastery_projections.projection_version+1,"
                "last_event_id=COALESCE(EXCLUDED.last_event_id,progress.mastery_projections.last_event_id),"
                "projection_fingerprint=EXCLUDED.projection_fingerprint,computed_at=EXCLUDED.computed_at"
            ),
            {
                "profile": profile_id,
                "target_type": target_type,
                "target": target_id,
                "facet": facet_key,
                "modality": projection.modality.value if projection.modality else "reading",
                "operation": operation,
                "status": projection.status.value,
                "base": projection.mastery_base,
                "current": projection.mastery_current,
                "confidence": projection.confidence,
                "freshness": projection.freshness,
                "mass": projection.effective_mass,
                "success": projection.success_count,
                "failure": projection.failure_count,
                "contexts": projection.context_count,
                "sessions": projection.session_count,
                "delays": projection.delay_band_count,
                "transfers": projection.transfer_count,
                "last": projection.last_evidence_at,
                "next": projection.next_verification_at,
                "policy": MASTERY_POLICY_ID,
                "event": event_id,
                "fingerprint": fingerprint,
                "computed": self._clock.now(),
            },
        )

    async def _projection_set_fingerprint(self, session: AsyncSession, profile_id: UUID) -> str:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT target_type,target_id,facet_key,modality,operation,projection_fingerprint "
                        "FROM progress.mastery_projections WHERE profile_id=:profile "
                        "ORDER BY target_type,target_id,facet_key,modality,operation"
                    ),
                    {"profile": profile_id},
                )
            )
            .mappings()
            .all()
        )
        return canonical_json_fingerprint([dict(row) for row in rows])

    async def _summary(
        self,
        session: AsyncSession,
        profile_id: UUID,
        *,
        processed: bool,
    ) -> ProjectionUpdateResult:
        projection_count = int(
            await session.scalar(
                text("SELECT count(*) FROM progress.mastery_projections WHERE profile_id=:profile"),
                {"profile": profile_id},
            )
            or 0
        )
        need_count = int(
            await session.scalar(
                text(
                    "SELECT count(*) FROM progress.learning_needs WHERE profile_id=:profile "
                    "AND status IN ('open','planned')"
                ),
                {"profile": profile_id},
            )
            or 0
        )
        recommendation_count = int(
            await session.scalar(
                text(
                    "SELECT count(*) FROM progress.recommendations WHERE profile_id=:profile "
                    "AND dismissed_at IS NULL AND (expires_at IS NULL OR expires_at>:now)"
                ),
                {"profile": profile_id, "now": self._clock.now()},
            )
            or 0
        )
        fingerprint = await self._projection_set_fingerprint(session, profile_id)
        return ProjectionUpdateResult(
            processed,
            profile_id,
            projection_count,
            need_count,
            recommendation_count,
            fingerprint,
        )

    @staticmethod
    async def _set_actor(session: AsyncSession, actor_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"),
            {"actor": str(actor_id)},
        )
