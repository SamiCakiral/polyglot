from __future__ import annotations

# ruff: noqa: E501
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.assessments.application import (
    AssessmentItemView,
    AssessmentResultView,
    AssessmentRunView,
    AssessmentSectionView,
    PrepareAssessment,
    ResolveAssessmentReview,
    SaveAssessmentResponse,
)
from polyglot.modules.assessments.domain import (
    AssessmentDomainError,
    AssessmentModality,
    AssessmentResponse,
    AssessmentRun,
    AssessmentRunStatus,
)
from polyglot.modules.assessments.scoring import (
    AssessmentScore,
    ScoreUnit,
    normalize_multiple_choice,
    score_assessment,
)
from polyglot.modules.assessments.selection import (
    AssessmentFormCandidate,
    AssessmentFormUnavailable,
    FormExposure,
    select_assessment_form,
)
from polyglot.platform.clock import Clock, SystemClock
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.json_types import JsonValue
from polyglot.platform.persistence.records import CommandReceipt
from polyglot.platform.persistence.repositories import SqlCommandReceiptStore


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _uuid(value: object) -> UUID:
    return UUID(str(value))


class SqlAssessmentService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        clock: Clock | None = None,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._sessions = sessions
        self._clock = clock or SystemClock()
        self._ids = id_generator or Uuid7Generator(self._clock)

    async def prepare(
        self,
        actor_id: UUID,
        profile_id: UUID,
        command: PrepareAssessment,
        *,
        idempotency_key: str,
    ) -> AssessmentRunView:
        now = self._clock.now()
        payload: dict[str, JsonValue] = {
            "profile_id": str(profile_id),
            "run_id": str(command.run_id),
            "modality": command.modality.value,
            "seed": command.seed,
            "target_snapshot": command.target_snapshot,
            "capabilities": list(command.capabilities),
        }
        fingerprint = canonical_json_fingerprint(payload)
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            existing = (
                (
                    await session.execute(
                        text(
                            "SELECT assessment_run_id,request_fingerprint FROM assessments.assessment_runs "
                            "WHERE profile_id=:profile AND idempotency_key=:key"
                        ),
                        {"profile": profile_id, "key": idempotency_key},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint:
                    raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
                view = await self._read_view(session, _uuid(existing["assessment_run_id"]), now)
                assert view is not None
                return view

            profile_exists = await session.scalar(
                text(
                    "SELECT 1 FROM language_profiles.learner_language_profiles "
                    "WHERE profile_id=:profile"
                ),
                {"profile": profile_id},
            )
            if profile_exists is None:
                raise DomainError(ErrorCode.NOT_FOUND)

            rows = (
                await session.execute(
                    text(
                        "SELECT f.form_id,f.assessment_revision_id,f.current_band_weight,"
                        "f.lower_anchor_weight,f.transfer_weight,f.calibration_uncertainty,"
                        "f.media_cost,f.coverage_targets,f.required_capabilities,f.status,"
                        "d.modality,array_agg(i.item_id ORDER BY s.ordinal,i.ordinal) AS item_ids "
                        "FROM assessments.assessment_forms f "
                        "JOIN assessments.assessment_definition_revisions r "
                        "ON r.assessment_revision_id=f.assessment_revision_id "
                        "JOIN assessments.assessment_definitions d "
                        "ON d.assessment_definition_id=r.assessment_definition_id "
                        "AND d.current_revision_id=r.assessment_revision_id "
                        "JOIN assessments.assessment_section_definitions s ON s.form_id=f.form_id "
                        "JOIN assessments.assessment_items i ON i.section_definition_id=s.section_definition_id "
                        "WHERE d.modality=:modality AND d.status='published' AND r.status='published' "
                        "GROUP BY f.form_id,f.assessment_revision_id,d.modality"
                    ),
                    {"modality": command.modality.value},
                )
            ).mappings()
            candidates = tuple(
                AssessmentFormCandidate(
                    form_id=_uuid(row["form_id"]),
                    modality=AssessmentModality(str(row["modality"])),
                    item_ids=tuple(_uuid(value) for value in row["item_ids"]),
                    current_band_weight=int(row["current_band_weight"]),
                    lower_anchor_weight=int(row["lower_anchor_weight"]),
                    transfer_weight=int(row["transfer_weight"]),
                    calibration_uncertainty=float(row["calibration_uncertainty"]),
                    media_cost=int(row["media_cost"]),
                    coverage_targets=frozenset(row["coverage_targets"]),
                    required_capabilities=frozenset(row["required_capabilities"]),
                    published=row["status"] == "published",
                )
                for row in rows
            )
            exposure_rows = (
                await session.execute(
                    text(
                        "SELECT form_id,item_ids,exposed_at FROM assessments.form_exposures "
                        "WHERE profile_id=:profile"
                    ),
                    {"profile": profile_id},
                )
            ).mappings()
            exposures = tuple(
                FormExposure(
                    form_id=_uuid(row["form_id"]),
                    item_ids=frozenset(_uuid(value) for value in row["item_ids"]),
                    exposed_at=cast(datetime, row["exposed_at"]),
                )
                for row in exposure_rows
            )
            required_targets = frozenset(
                str(value) for value in cast(list[JsonValue], command.target_snapshot.get("required_targets", []))
            )
            try:
                selected = select_assessment_form(
                    candidates=candidates,
                    modality=command.modality,
                    required_targets=required_targets,
                    capabilities=frozenset(command.capabilities),
                    exposures=exposures,
                    now=now,
                    seed=command.seed,
                )
            except AssessmentFormUnavailable as error:
                raise DomainError(ErrorCode.ASSESSMENT_UNAVAILABLE) from error

            form = await self._form_snapshot(session, selected.form_id, command.seed)
            revision_id = _uuid(form["assessment_revision_id"])
            time_limit_ms = cast(int, form["time_limit_ms"])
            pause_policy = cast(dict[str, JsonValue], form["pause_policy"])
            pause_allowed = bool(pause_policy.get("allowed", False))
            resume_window_ms = cast(int, pause_policy.get("resume_window_ms", 0))
            item_order = tuple(_uuid(value) for value in cast(list[str], form["item_order"]))
            AssessmentRun.prepare(
                run_id=command.run_id,
                profile_id=profile_id,
                assessment_revision_id=revision_id,
                form_id=selected.form_id,
                modality=command.modality,
                item_ids=item_order,
                time_limit_ms=time_limit_ms,
                pause_allowed=pause_allowed,
                resume_window_ms=resume_window_ms,
                prepared_at=now,
            )
            await session.execute(
                text(
                    "INSERT INTO assessments.assessment_runs "
                    "(assessment_run_id,profile_id,assessment_revision_id,form_id,modality,status,"
                    "target_snapshot,item_order,form_snapshot,time_limit_ms,pause_allowed,resume_window_ms,"
                    "prepared_at,remaining_time_ms,integrity_incidents,version,idempotency_key,"
                    "request_fingerprint,updated_at) VALUES "
                    "(:run,:profile,:revision,:form,:modality,'prepared',CAST(:target AS jsonb),"
                    ":items,CAST(:snapshot AS jsonb),:limit,:pause,:resume,:now,:limit,'[]',1,:key,:fingerprint,:now)"
                ),
                {
                    "run": command.run_id,
                    "profile": profile_id,
                    "revision": revision_id,
                    "form": selected.form_id,
                    "modality": command.modality.value,
                    "target": _json(command.target_snapshot),
                    "items": list(item_order),
                    "snapshot": _json(form),
                    "limit": time_limit_ms,
                    "pause": pause_allowed,
                    "resume": resume_window_ms,
                    "now": now,
                    "key": idempotency_key,
                    "fingerprint": fingerprint,
                },
            )
            for section in cast(list[dict[str, JsonValue]], form["sections"]):
                await session.execute(
                    text(
                        "INSERT INTO assessments.assessment_section_runs "
                        "(section_run_id,assessment_run_id,profile_id,section_definition_id,status,version) "
                        "VALUES (:section_run,:run,:profile,:section,'pending',1)"
                    ),
                    {
                        "section_run": self._ids.new(),
                        "run": command.run_id,
                        "profile": profile_id,
                        "section": UUID(str(section["section_id"])),
                    },
                )
            await session.execute(
                text(
                    "INSERT INTO assessments.form_exposures "
                    "(exposure_id,profile_id,assessment_run_id,form_id,item_ids,exposed_at) "
                    "VALUES (:exposure,:profile,:run,:form,:items,:now)"
                ),
                {
                    "exposure": self._ids.new(),
                    "profile": profile_id,
                    "run": command.run_id,
                    "form": selected.form_id,
                    "items": list(item_order),
                    "now": now,
                },
            )
            view = await self._read_view(session, command.run_id, now)
            assert view is not None
            return view

    async def get_run(self, actor_id: UUID, run_id: UUID) -> AssessmentRunView:
        now = self._clock.now()
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            await self._expire_locked(session, run_id, now)
            view = await self._read_view(session, run_id, now)
            if view is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            return view

    async def start(
        self, actor_id: UUID, run_id: UUID, *, expected_version: int, idempotency_key: str
    ) -> AssessmentRunView:
        return await self._transition(
            actor_id, run_id, expected_version, "start", idempotency_key
        )

    async def pause(
        self, actor_id: UUID, run_id: UUID, *, expected_version: int, idempotency_key: str
    ) -> AssessmentRunView:
        return await self._transition(
            actor_id, run_id, expected_version, "pause", idempotency_key
        )

    async def resume(
        self, actor_id: UUID, run_id: UUID, *, expected_version: int, idempotency_key: str
    ) -> AssessmentRunView:
        return await self._transition(
            actor_id, run_id, expected_version, "resume", idempotency_key
        )

    async def save_response(
        self,
        actor_id: UUID,
        run_id: UUID,
        item_id: UUID,
        command: SaveAssessmentResponse,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AssessmentRunView:
        now = self._clock.now()
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            command_id, replayed = await self._reserve_command(
                session,
                actor_id=actor_id,
                run_id=run_id,
                command_type="SaveAssessmentResponse",
                idempotency_key=idempotency_key,
                expected_version=expected_version,
                payload={
                    "item_id": str(item_id),
                    "answer": command.answer,
                    "expected_response_version": command.expected_response_version,
                },
                now=now,
            )
            if replayed:
                view = await self._read_view(session, run_id, now)
                if view is None:
                    raise DomainError(ErrorCode.NOT_FOUND)
                return view
            run = await self._load_domain(session, run_id, lock=True)
            if run is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            self._require_version(run.version, expected_version)
            try:
                updated = run.save_response(
                    item_id, command.answer, command.expected_response_version, now
                )
            except AssessmentDomainError as error:
                raise self._map_error(error) from error
            response = next(value for value in updated.responses if value.item_id == item_id)
            await session.execute(
                text(
                    "INSERT INTO assessments.assessment_responses "
                    "(response_id,assessment_run_id,profile_id,item_id,answer,version,saved_at) "
                    "VALUES (:response,:run,:profile,:item,CAST(:answer AS jsonb),1,:now) "
                    "ON CONFLICT (assessment_run_id,item_id) DO UPDATE SET "
                    "answer=EXCLUDED.answer,version=assessments.assessment_responses.version+1,"
                    "saved_at=EXCLUDED.saved_at"
                ),
                {
                    "response": self._ids.new(),
                    "run": run_id,
                    "profile": run.profile_id,
                    "item": item_id,
                    "answer": _json(dict(response.answer)),
                    "now": now,
                },
            )
            await self._persist_run(session, updated, now)
            view = await self._read_view(session, run_id, now)
            assert view is not None
            await self._complete_command(session, command_id, view)
            return view

    async def submit(
        self, actor_id: UUID, run_id: UUID, *, expected_version: int, idempotency_key: str
    ) -> AssessmentRunView:
        now = self._clock.now()
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            command_id, replayed = await self._reserve_command(
                session,
                actor_id=actor_id,
                run_id=run_id,
                command_type="SubmitAssessment",
                idempotency_key=idempotency_key,
                expected_version=expected_version,
                payload={},
                now=now,
            )
            if replayed:
                view = await self._read_view(session, run_id, now)
                if view is None:
                    raise DomainError(ErrorCode.NOT_FOUND)
                return view
            run = await self._load_domain(session, run_id, lock=True)
            if run is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if run.status in {
                AssessmentRunStatus.SUBMITTED,
                AssessmentRunStatus.SCORING,
                AssessmentRunStatus.REVIEW_REQUIRED,
                AssessmentRunStatus.COMPLETED,
                AssessmentRunStatus.EXPIRED,
            }:
                view = await self._read_view(session, run_id, now)
                assert view is not None
                await self._complete_command(session, command_id, view)
                return view
            self._require_version(run.version, expected_version)
            try:
                submitted = run.submit(now)
            except AssessmentDomainError as error:
                raise self._map_error(error) from error
            await session.execute(
                text(
                    "UPDATE assessments.assessment_responses SET submitted_at=:submitted "
                    "WHERE assessment_run_id=:run"
                ),
                {"submitted": submitted.submitted_at, "run": run_id},
            )
            await self._persist_run(session, submitted, now)
            await session.execute(
                text(
                    "UPDATE assessments.assessment_section_runs SET status=:status,"
                    "completed_at=:now,version=version+1 WHERE assessment_run_id=:run "
                    "AND status IN ('pending','in_progress')"
                ),
                {
                    "status": (
                        "expired"
                        if submitted.status is AssessmentRunStatus.EXPIRED
                        else "completed"
                    ),
                    "run": run_id,
                    "now": submitted.submitted_at or now,
                },
            )
            await self._score_submitted(session, submitted, now)
            view = await self._read_view(session, run_id, now)
            assert view is not None
            await self._complete_command(session, command_id, view)
            return view

    async def resolve_review(
        self,
        actor_id: UUID,
        run_id: UUID,
        command: ResolveAssessmentReview,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AssessmentRunView:
        now = self._clock.now()
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            command_id, replayed = await self._reserve_command(
                session,
                actor_id=actor_id,
                run_id=run_id,
                command_type="ResolveAssessmentReview",
                idempotency_key=idempotency_key,
                expected_version=expected_version,
                payload={
                    "rubric_revision": command.rubric_revision,
                    "criterion_scores": command.criterion_scores,
                    "annotations": list(command.annotations),
                },
                now=now,
            )
            if replayed:
                view = await self._read_view(session, run_id, now)
                if view is None:
                    raise DomainError(ErrorCode.NOT_FOUND)
                return view
            run = await self._load_domain(session, run_id, lock=True)
            if run is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            self._require_version(run.version, expected_version)
            if run.status is not AssessmentRunStatus.REVIEW_REQUIRED:
                raise DomainError(ErrorCode.REVIEW_CONFLICT)
            rubric = "WRITING_RUBRIC_V0" if run.modality is AssessmentModality.WRITING else "SPEAKING_RUBRIC_V0"
            if command.rubric_revision != rubric:
                raise DomainError(ErrorCode.RUBRIC_STALE)
            units = self._rubric_units(run.modality, command.criterion_scores)
            result = score_assessment(
                run.modality,
                units,
                minimum_units=len(units),
                planned_weight=sum(unit.weight for unit in units),
            )
            review_id = self._ids.new()
            await session.execute(
                text(
                    "INSERT INTO assessments.assessment_reviews "
                    "(review_id,assessment_run_id,profile_id,reviewer_id,rubric_revision,"
                    "criterion_scores,annotations,qualified,created_at) VALUES "
                    "(:review,:run,:profile,:reviewer,:rubric,CAST(:scores AS jsonb),"
                    "CAST(:annotations AS jsonb),true,:now)"
                ),
                {
                    "review": review_id,
                    "run": run_id,
                    "profile": run.profile_id,
                    "reviewer": actor_id,
                    "rubric": rubric,
                    "scores": _json(command.criterion_scores),
                    "annotations": _json(command.annotations),
                    "now": now,
                },
            )
            await self._insert_result(session, run, result, now)
            completed = replace(
                run,
                status=AssessmentRunStatus.COMPLETED,
                completed_at=now,
                version=run.version + 1,
            )
            await self._persist_run(session, completed, now)
            view = await self._read_view(session, run_id, now)
            assert view is not None
            await self._complete_command(session, command_id, view)
            return view

    async def _transition(
        self,
        actor_id: UUID,
        run_id: UUID,
        expected_version: int,
        action: str,
        idempotency_key: str,
    ) -> AssessmentRunView:
        now = self._clock.now()
        async with self._sessions() as session, session.begin():
            await self._set_actor(session, actor_id)
            command_id, replayed = await self._reserve_command(
                session,
                actor_id=actor_id,
                run_id=run_id,
                command_type=f"{action.title()}Assessment",
                idempotency_key=idempotency_key,
                expected_version=expected_version,
                payload={},
                now=now,
            )
            if replayed:
                view = await self._read_view(session, run_id, now)
                if view is None:
                    raise DomainError(ErrorCode.NOT_FOUND)
                return view
            run = await self._load_domain(session, run_id, lock=True)
            if run is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            self._require_version(run.version, expected_version)
            try:
                updated = cast(AssessmentRun, getattr(run, action)(now))
            except AssessmentDomainError as error:
                raise self._map_error(error) from error
            await self._persist_run(session, updated, now)
            if action == "start":
                await session.execute(
                    text(
                        "UPDATE assessments.assessment_section_runs SET status='in_progress',"
                        "started_at=:now,version=version+1 WHERE section_run_id=("
                        "SELECT sr.section_run_id FROM assessments.assessment_section_runs sr "
                        "JOIN assessments.assessment_section_definitions sd "
                        "ON sd.section_definition_id=sr.section_definition_id "
                        "WHERE sr.assessment_run_id=:run ORDER BY sd.ordinal LIMIT 1)"
                    ),
                    {"run": run_id, "now": now},
                )
            view = await self._read_view(session, run_id, now)
            assert view is not None
            await self._complete_command(session, command_id, view)
            return view

    async def _score_submitted(
        self, session: AsyncSession, run: AssessmentRun, now: datetime
    ) -> None:
        if run.status is AssessmentRunStatus.EXPIRED:
            pass
        elif run.status is not AssessmentRunStatus.SUBMITTED:
            return
        if run.modality is AssessmentModality.WRITING:
            await session.execute(
                text(
                    "UPDATE assessments.assessment_runs SET status='review_required',version=version+1,"
                    "updated_at=:now WHERE assessment_run_id=:run"
                ),
                {"run": run.run_id, "now": now},
            )
            return
        if run.modality is AssessmentModality.SPEAKING:
            result = score_assessment(
                run.modality,
                (ScoreUnit("self", "self_assessment", 1, None, None, False, True),),
                minimum_units=1,
                planned_weight=1,
            )
        else:
            rows = (
                await session.execute(
                    text(
                        "SELECT i.item_id,i.weight,i.coverage_targets,i.solution_snapshot,i.defective,"
                        "r.answer FROM assessments.assessment_items i "
                        "LEFT JOIN assessments.assessment_responses r "
                        "ON r.item_id=i.item_id AND r.assessment_run_id=:run "
                        "WHERE i.item_id=ANY(:items)"
                    ),
                    {"run": run.run_id, "items": list(run.item_ids)},
                )
            ).mappings()
            units: list[ScoreUnit] = []
            planned_weight = 0.0
            for row in rows:
                if row["defective"]:
                    continue
                weight = float(row["weight"])
                planned_weight += weight
                answer = cast(dict[str, JsonValue] | None, row["answer"])
                solution = cast(dict[str, JsonValue], row["solution_snapshot"])
                accepted = cast(list[JsonValue], solution.get("accepted", []))
                value = None if answer is None else answer.get("value")
                raw = 1.0 if value in accepted else 0.0
                option_count = cast(int, solution.get("option_count", 0))
                normalized = normalize_multiple_choice(raw, option_count=option_count) if option_count else raw
                units.append(
                    ScoreUnit(
                        key=str(row["item_id"]),
                        facet=str(row["coverage_targets"][0]),
                        weight=weight,
                        normalized_score=normalized if answer is not None else None,
                        correction_confidence=1 if answer is not None else None,
                        evaluable=True,
                        answered=answer is not None,
                    )
                )
            result = score_assessment(
                run.modality,
                tuple(units),
                minimum_units=12 if run.modality is AssessmentModality.READING else 10,
                planned_weight=planned_weight,
            )
        await self._insert_result(session, run, result, now)
        await session.execute(
            text(
                "UPDATE assessments.assessment_runs SET status='completed',completed_at=:now,"
                "version=version+1,updated_at=:now WHERE assessment_run_id=:run"
            ),
            {"run": run.run_id, "now": now},
        )

    async def _insert_result(
        self,
        session: AsyncSession,
        run: AssessmentRun,
        score: AssessmentScore,
        now: datetime,
    ) -> None:
        result_id = self._ids.new()
        await session.execute(
            text(
                "INSERT INTO assessments.assessment_results "
                "(result_id,assessment_run_id,profile_id,modality,result_status,score,band,confidence,"
                "coverage,integrity_factor,limiting_criteria,policy_revision,score_payload,created_at) "
                "VALUES (:result,:run,:profile,:modality,:status,:score,:band,:confidence,:coverage,"
                ":integrity,:limiting,'ASSESSMENT_BANDS_V0',CAST(:payload AS jsonb),:now)"
            ),
            {
                "result": result_id,
                "run": run.run_id,
                "profile": run.profile_id,
                "modality": run.modality.value,
                "status": score.status.value,
                "score": score.score,
                "band": None if score.band is None else score.band.value,
                "confidence": score.confidence,
                "coverage": score.coverage,
                "integrity": score.integrity_factor,
                "limiting": list(score.limiting_criteria),
                "payload": _json({"evaluable_units": score.evaluable_units}),
                "now": now,
            },
        )
        if score.status.value == "not_evaluable":
            return
        item_rows = (
            await session.execute(
                text(
                    "SELECT item_id,coverage_targets FROM assessments.assessment_items "
                    "WHERE item_id=ANY(:items) AND defective=false"
                ),
                {"items": list(run.item_ids)},
            )
        ).mappings()
        for row in item_rows:
            for facet in row["coverage_targets"]:
                await session.execute(
                    text(
                        "INSERT INTO assessments.assessment_evidence "
                        "(assessment_evidence_id,result_id,assessment_run_id,profile_id,item_id,"
                        "observation_id,modality,facet_key,created_at) VALUES "
                        "(:evidence,:result,:run,:profile,:item,NULL,:modality,:facet,:now)"
                    ),
                    {
                        "evidence": self._ids.new(),
                        "result": result_id,
                        "run": run.run_id,
                        "profile": run.profile_id,
                        "item": row["item_id"],
                        "modality": run.modality.value,
                        "facet": facet,
                        "now": now,
                    },
                )

    @staticmethod
    def _rubric_units(
        modality: AssessmentModality, values: dict[str, JsonValue]
    ) -> tuple[ScoreUnit, ...]:
        weights = (
            {
                "task_achievement": 0.25,
                "coherence": 0.25,
                "grammar": 0.20,
                "range": 0.15,
                "lexis_register": 0.15,
            }
            if modality is AssessmentModality.WRITING
            else {
                "interaction": 0.25,
                "intelligibility": 0.25,
                "fluency": 0.20,
                "grammar": 0.15,
                "range_lexis_register": 0.15,
            }
        )
        if set(values) != set(weights):
            raise DomainError(ErrorCode.RUBRIC_MISMATCH)
        critical = {"task_achievement"} if modality is AssessmentModality.WRITING else {"interaction", "intelligibility"}
        units = []
        for criterion, weight in weights.items():
            raw = values[criterion]
            if not isinstance(raw, (int, float)) or isinstance(raw, bool) or not 0 <= raw <= 4:
                raise DomainError(ErrorCode.RUBRIC_MISMATCH)
            units.append(
                ScoreUnit(
                    criterion,
                    criterion,
                    weight,
                    float(raw) / 4,
                    1,
                    True,
                    True,
                    criterion in critical,
                )
            )
        return tuple(units)

    async def _form_snapshot(
        self, session: AsyncSession, form_id: UUID, seed: str
    ) -> dict[str, JsonValue]:
        header = (
            (
                await session.execute(
                    text(
                        "SELECT f.form_id,f.form_code,f.assessment_revision_id,r.protocol_code,"
                        "r.time_limit_ms,r.pause_policy FROM assessments.assessment_forms f "
                        "JOIN assessments.assessment_definition_revisions r "
                        "ON r.assessment_revision_id=f.assessment_revision_id WHERE f.form_id=:form"
                    ),
                    {"form": form_id},
                )
            )
            .mappings()
            .one()
        )
        rows = (
            await session.execute(
                text(
                    "SELECT s.section_definition_id,s.ordinal AS section_ordinal,s.section_type,"
                    "s.weight AS section_weight,s.title,s.instructions,i.item_id,i.ordinal,"
                    "i.item_kind,i.answer_kind,i.weight,i.coverage_targets,i.prompt_snapshot,"
                    "i.media_ref,i.max_plays FROM assessments.assessment_section_definitions s "
                    "JOIN assessments.assessment_items i ON i.section_definition_id=s.section_definition_id "
                    "WHERE s.form_id=:form ORDER BY s.ordinal,i.ordinal"
                ),
                {"form": form_id},
            )
        ).mappings()
        sections: dict[UUID, dict[str, JsonValue]] = {}
        item_ids: list[UUID] = []
        for row in rows:
            section_id = _uuid(row["section_definition_id"])
            section = sections.setdefault(
                section_id,
                {
                    "section_id": str(section_id),
                    "ordinal": int(row["section_ordinal"]),
                    "section_type": str(row["section_type"]),
                    "weight": float(row["section_weight"]),
                    "title": str(row["title"]),
                    "instructions": str(row["instructions"]),
                    "items": [],
                },
            )
            item_id = _uuid(row["item_id"])
            item_ids.append(item_id)
            cast(list[JsonValue], section["items"]).append(
                {
                    "item_id": str(item_id),
                    "ordinal": int(row["ordinal"]),
                    "item_kind": str(row["item_kind"]),
                    "answer_kind": str(row["answer_kind"]),
                    "weight": float(row["weight"]),
                    "coverage_targets": list(row["coverage_targets"]),
                    "prompt": cast(dict[str, JsonValue], row["prompt_snapshot"]),
                    "media_ref": row["media_ref"],
                    "max_plays": row["max_plays"],
                }
            )
        item_ids.sort(key=lambda item: hashlib.sha256(f"{seed}:{item}".encode()).hexdigest())
        return {
            "form_id": str(header["form_id"]),
            "form_code": str(header["form_code"]),
            "assessment_revision_id": str(header["assessment_revision_id"]),
            "protocol_code": str(header["protocol_code"]),
            "time_limit_ms": int(header["time_limit_ms"]),
            "pause_policy": cast(dict[str, JsonValue], header["pause_policy"]),
            "item_order": [str(value) for value in item_ids],
            "sections": list(sections.values()),
        }

    async def _load_domain(
        self, session: AsyncSession, run_id: UUID, *, lock: bool
    ) -> AssessmentRun | None:
        suffix = " FOR UPDATE" if lock else ""
        row = (
            (
                await session.execute(
                    text("SELECT * FROM assessments.assessment_runs WHERE assessment_run_id=:run" + suffix),
                    {"run": run_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        response_rows = (
            await session.execute(
                text(
                    "SELECT item_id,answer,version,saved_at FROM assessments.assessment_responses "
                    "WHERE assessment_run_id=:run"
                ),
                {"run": run_id},
            )
        ).mappings()
        responses = tuple(
            AssessmentResponse(
                item_id=_uuid(value["item_id"]),
                answer=cast(dict[str, JsonValue], value["answer"]),
                version=int(value["version"]),
                saved_at=cast(datetime, value["saved_at"]),
            )
            for value in response_rows
        )
        return AssessmentRun(
            run_id=_uuid(row["assessment_run_id"]),
            profile_id=_uuid(row["profile_id"]),
            assessment_revision_id=_uuid(row["assessment_revision_id"]),
            form_id=_uuid(row["form_id"]),
            modality=AssessmentModality(str(row["modality"])),
            item_ids=tuple(_uuid(value) for value in row["item_order"]),
            time_limit_ms=int(row["time_limit_ms"]),
            pause_allowed=bool(row["pause_allowed"]),
            resume_window_ms=int(row["resume_window_ms"]),
            status=AssessmentRunStatus(str(row["status"])),
            prepared_at=cast(datetime, row["prepared_at"]),
            started_at=cast(datetime | None, row["started_at"]),
            deadline_at=cast(datetime | None, row["deadline_at"]),
            paused_at=cast(datetime | None, row["paused_at"]),
            remaining_time_ms=cast(int | None, row["remaining_time_ms"]),
            submitted_at=cast(datetime | None, row["submitted_at"]),
            completed_at=cast(datetime | None, row["completed_at"]),
            responses=responses,
            version=int(row["version"]),
        )

    async def _persist_run(
        self, session: AsyncSession, run: AssessmentRun, now: datetime
    ) -> None:
        await session.execute(
            text(
                "UPDATE assessments.assessment_runs SET status=:status,started_at=:started,"
                "deadline_at=:deadline,paused_at=:paused,remaining_time_ms=:remaining,"
                "submitted_at=:submitted,completed_at=:completed,version=:version,updated_at=:now "
                "WHERE assessment_run_id=:run"
            ),
            {
                "status": run.status.value,
                "started": run.started_at,
                "deadline": run.deadline_at,
                "paused": run.paused_at,
                "remaining": run.remaining_time_ms,
                "submitted": run.submitted_at,
                "completed": run.completed_at,
                "version": run.version,
                "now": now,
                "run": run.run_id,
            },
        )

    async def _expire_locked(self, session: AsyncSession, run_id: UUID, now: datetime) -> None:
        run = await self._load_domain(session, run_id, lock=True)
        if run is None:
            return
        expired = run.expire_if_due(now)
        if expired is run:
            return
        await self._persist_run(session, expired, now)
        await session.execute(
            text(
                "UPDATE assessments.assessment_section_runs SET status='expired',"
                "completed_at=:completed,version=version+1 WHERE assessment_run_id=:run "
                "AND status IN ('pending','in_progress')"
            ),
            {"run": run_id, "completed": expired.submitted_at or now},
        )
        await self._score_submitted(session, expired, now)

    async def _read_view(
        self, session: AsyncSession, run_id: UUID, now: datetime
    ) -> AssessmentRunView | None:
        row = (
            (
                await session.execute(
                    text("SELECT * FROM assessments.assessment_runs WHERE assessment_run_id=:run"),
                    {"run": run_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        snapshot = cast(dict[str, JsonValue], row["form_snapshot"])
        response_rows = {
            _uuid(value["item_id"]): value
            for value in (
                await session.execute(
                    text(
                        "SELECT item_id,answer,version,saved_at FROM assessments.assessment_responses "
                        "WHERE assessment_run_id=:run"
                    ),
                    {"run": run_id},
                )
            ).mappings()
        }
        section_statuses = {
            _uuid(value["section_definition_id"]): str(value["status"])
            for value in (
                await session.execute(
                    text(
                        "SELECT section_definition_id,status FROM assessments.assessment_section_runs "
                        "WHERE assessment_run_id=:run"
                    ),
                    {"run": run_id},
                )
            ).mappings()
        }
        sections = []
        for section in cast(list[dict[str, JsonValue]], snapshot["sections"]):
            section_id = UUID(str(section["section_id"]))
            items = []
            for item in cast(list[dict[str, JsonValue]], section["items"]):
                item_id = UUID(str(item["item_id"]))
                response = response_rows.get(item_id)
                items.append(
                    AssessmentItemView(
                        item_id=item_id,
                        section_id=section_id,
                        ordinal=cast(int, item["ordinal"]),
                        item_kind=str(item["item_kind"]),
                        answer_kind=str(item["answer_kind"]),
                        weight=float(cast(int | float, item["weight"])),
                        coverage_targets=tuple(str(value) for value in cast(list[JsonValue], item["coverage_targets"])),
                        prompt=cast(dict[str, JsonValue], item["prompt"]),
                        media_ref=cast(str | None, item["media_ref"]),
                        max_plays=cast(int | None, item["max_plays"]),
                        answer=None if response is None else cast(dict[str, JsonValue], response["answer"]),
                        response_version=0 if response is None else int(response["version"]),
                        saved_at=None if response is None else cast(datetime, response["saved_at"]),
                    )
                )
            sections.append(
                AssessmentSectionView(
                    section_id=section_id,
                    ordinal=cast(int, section["ordinal"]),
                    section_type=str(section["section_type"]),
                    title=str(section["title"]),
                    instructions=str(section["instructions"]),
                    weight=float(cast(int | float, section["weight"])),
                    status=section_statuses[section_id],
                    items=tuple(items),
                )
            )
        result_row = (
            (
                await session.execute(
                    text("SELECT * FROM assessments.assessment_results WHERE assessment_run_id=:run"),
                    {"run": run_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        result = None
        if result_row is not None:
            result = AssessmentResultView(
                result_id=_uuid(result_row["result_id"]),
                modality=str(result_row["modality"]),
                status=str(result_row["result_status"]),
                score=None if result_row["score"] is None else float(result_row["score"]),
                band=cast(str | None, result_row["band"]),
                confidence=float(result_row["confidence"]),
                coverage=float(result_row["coverage"]),
                integrity_factor=float(result_row["integrity_factor"]),
                limiting_criteria=tuple(result_row["limiting_criteria"]),
                policy_revision=str(result_row["policy_revision"]),
                created_at=cast(datetime, result_row["created_at"]),
            )
        deadline_at = cast(datetime | None, row["deadline_at"])
        remaining_time_ms = cast(int | None, row["remaining_time_ms"])
        if row["status"] == "in_progress" and deadline_at is not None:
            remaining_time_ms = max(int((deadline_at - now).total_seconds() * 1000), 0)
        return AssessmentRunView(
            run_id=_uuid(row["assessment_run_id"]),
            profile_id=_uuid(row["profile_id"]),
            modality=str(row["modality"]),
            status=str(row["status"]),
            protocol_code=str(snapshot["protocol_code"]),
            form_code=str(snapshot["form_code"]),
            time_limit_ms=int(row["time_limit_ms"]),
            pause_allowed=bool(row["pause_allowed"]),
            prepared_at=cast(datetime, row["prepared_at"]),
            started_at=cast(datetime | None, row["started_at"]),
            deadline_at=deadline_at,
            paused_at=cast(datetime | None, row["paused_at"]),
            remaining_time_ms=remaining_time_ms,
            submitted_at=cast(datetime | None, row["submitted_at"]),
            completed_at=cast(datetime | None, row["completed_at"]),
            server_now=now,
            sections=tuple(sections),
            result=result,
            version=int(row["version"]),
        )

    async def _reserve_command(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        run_id: UUID,
        command_type: str,
        idempotency_key: str,
        expected_version: int,
        payload: dict[str, JsonValue],
        now: datetime,
    ) -> tuple[UUID, bool]:
        fingerprint_payload: dict[str, JsonValue] = {
            "run_id": str(run_id),
            "payload": payload,
        }
        receipt = CommandReceipt(
            command_id=self._ids.new(),
            command_type=command_type,
            actor_id=actor_id,
            aggregate_type="assessment_run",
            aggregate_id=run_id,
            idempotency_key=idempotency_key,
            request_fingerprint=canonical_json_fingerprint(fingerprint_payload),
            expected_version=expected_version,
            received_at=now,
            result_ref=None,
            result_payload=None,
            status="started",
            expires_at=now + timedelta(hours=24),
        )
        reservation = await SqlCommandReceiptStore(session).reserve(receipt)
        if reservation.created:
            return reservation.receipt.command_id, False
        if reservation.receipt.status != "succeeded":
            raise DomainError(ErrorCode.RESPONSE_CONFLICT)
        return reservation.receipt.command_id, True

    @staticmethod
    async def _complete_command(
        session: AsyncSession, command_id: UUID, view: AssessmentRunView
    ) -> None:
        await SqlCommandReceiptStore(session).complete(
            command_id=command_id,
            status="succeeded",
            result_ref=view.run_id,
            result_payload={"resource_id": str(view.run_id), "version": view.version},
        )

    @staticmethod
    async def _set_actor(session: AsyncSession, actor_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"), {"actor": str(actor_id)}
        )

    @staticmethod
    def _require_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise DomainError(ErrorCode.VERSION_CONFLICT)

    @staticmethod
    def _map_error(error: AssessmentDomainError) -> DomainError:
        value = str(error)
        mapping = {
            "assessment_expired": ErrorCode.ASSESSMENT_EXPIRED,
            "pause_not_allowed": ErrorCode.PAUSE_NOT_ALLOWED,
            "response_stale": ErrorCode.RESPONSE_STALE,
            "response_conflict": ErrorCode.RESPONSE_CONFLICT,
            "not_found": ErrorCode.NOT_FOUND,
        }
        return DomainError(mapping.get(value, ErrorCode.INVALID_TRANSITION))
