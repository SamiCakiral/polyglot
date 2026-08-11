from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.catalogue.core.grammar_registry import grammar_realization_for
from polyglot.modules.exercises.core.application import (
    AttemptView,
    ContestCorrection,
    CorrectAttempt,
    CorrectionCaseView,
    CorrectionView,
    EvaluateAttempt,
    ExerciseInstanceView,
    MarkCorrectionRead,
    OpenAttempt,
    ResolveCorrectionCase,
    SaveDraft,
    SubmitAttempt,
    UseHint,
)
from polyglot.modules.exercises.core.correction import correct_published_answer
from polyglot.modules.exercises.core.domain import (
    Answer,
    AnswerKind,
    CorrectionResult,
    CorrectionVerdict,
    primitive_spec,
)
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.fingerprint import canonical_json_fingerprint
from polyglot.platform.ids import IdGenerator, Uuid7Generator
from polyglot.platform.json_types import JsonValue


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
    if isinstance(value, Enum):
        return cast(JsonValue, value.value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return cast(JsonValue, value)
    raise TypeError(f"unsupported exercise persistence value: {type(value)!r}")


def _json(value: object) -> str:
    return json.dumps(_encode(value), sort_keys=True, separators=(",", ":"))


def _mapping(value: object) -> dict[str, object]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
    return cast(dict[str, object], value)


def _dt(value: object) -> datetime:
    return datetime.fromisoformat(str(value)).astimezone(UTC)


def _uuid(value: object) -> UUID:
    return UUID(str(value))


def _resolved_stimulus(
    primitive_id: str,
    stimulus: dict[str, JsonValue],
    grammar_bindings: tuple[JsonValue, ...],
) -> dict[str, JsonValue]:
    reference = next(
        (
            value.removeprefix("grammar:")
            for value in grammar_bindings
            if isinstance(value, str) and value.startswith("grammar:")
        ),
        None,
    )
    realization = None if reference is None else grammar_realization_for(reference)
    if realization is None:
        return stimulus
    spec = primitive_spec(primitive_id)
    if spec.learning_operation not in {"exposure", "transformation"}:
        return stimulus
    prompt = (
        f"Comprenez la fonction « {realization.support_template} », puis observez "
        f"le moule « {realization.target_template} »."
        if spec.learning_operation == "exposure"
        else f"Utilisez puis transformez le moule « {realization.target_template} »."
    )
    return {
        **stimulus,
        "prompt": prompt,
        "model_answer": realization.examples[0],
        "grammar_function_code": realization.function_code,
        "grammar_realization_code": realization.realization_code,
        "support_template": realization.support_template,
        "target_template": realization.target_template,
        "examples": list(realization.examples),
        "pitfalls": list(realization.pitfalls),
        "transformations": list(realization.transformations),
    }


def _attempt_from_payload(payload: object) -> AttemptView:
    data = _mapping(payload)
    return AttemptView(
        attempt_id=_uuid(data["attempt_id"]),
        profile_id=_uuid(data["profile_id"]),
        instance_id=_uuid(data["instance_id"]),
        attempt_no=int(str(data["attempt_no"])),
        status=str(data["status"]),
        terminal_reason=str(data["terminal_reason"]),
        answer_kind=None
        if data.get("answer_kind") is None
        else AnswerKind(str(data["answer_kind"])),
        raw_answer=cast(JsonValue, data.get("raw_answer")),
        input_method=None if data.get("input_method") is None else str(data["input_method"]),
        input_locale=None if data.get("input_locale") is None else str(data["input_locale"]),
        submitted_at=None if data.get("submitted_at") is None else _dt(data["submitted_at"]),
        active_duration_ms=int(str(data["active_duration_ms"])),
        correction_reviewed_at=None
        if data.get("correction_reviewed_at") is None
        else _dt(data["correction_reviewed_at"]),
        version=int(str(data["version"])),
        started_at=_dt(data["started_at"]),
        updated_at=_dt(data["updated_at"]),
    )


def _case_from_payload(payload: object) -> CorrectionCaseView:
    data = _mapping(payload)
    return CorrectionCaseView(
        case_id=_uuid(data["case_id"]),
        attempt_id=_uuid(data["attempt_id"]),
        status=str(data["status"]),
        reason_code=str(data["reason_code"]),
        user_comment=None if data.get("user_comment") is None else str(data["user_comment"]),
        resolution_correction_id=None
        if data.get("resolution_correction_id") is None
        else _uuid(data["resolution_correction_id"]),
        version=int(str(data["version"])),
        opened_at=_dt(data["opened_at"]),
        resolved_at=None if data.get("resolved_at") is None else _dt(data["resolved_at"]),
    )


class SqlExerciseService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        id_generator: IdGenerator | None = None,
    ) -> None:
        self._sessions = session_factory
        self._ids = id_generator or Uuid7Generator()

    async def get_instance(self, actor_id: UUID, instance_id: UUID) -> ExerciseInstanceView:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT instance.instance_id,instance.definition_revision_id,"
                            "instance.language_pack_revision_id,instance.seed,"
                            "instance.stimulus_revision_ids,instance.target_bindings,"
                            "instance.lexical_bindings,instance.grammar_bindings,"
                            "revision.primitive_id,revision.schema_version,"
                            "revision.response_kinds,revision.response_contract,"
                            "revision.stimulus_contract "
                            "FROM exercises.exercise_instances instance "
                            "JOIN exercises.exercise_definition_revisions revision ON "
                            "revision.definition_revision_id=instance.definition_revision_id "
                            "WHERE instance.instance_id=:instance"
                        ),
                        {"instance": instance_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            primitive_id = str(row["primitive_id"])
            spec = primitive_spec(primitive_id)
            grammar_bindings = tuple(cast(list[JsonValue], row["grammar_bindings"]))
            stimulus = _resolved_stimulus(
                primitive_id,
                dict(cast(dict[str, JsonValue], row["stimulus_contract"])),
                grammar_bindings,
            )
            return ExerciseInstanceView(
                instance_id=_uuid(row["instance_id"]),
                definition_revision_id=_uuid(row["definition_revision_id"]),
                language_pack_revision_id=_uuid(row["language_pack_revision_id"]),
                primitive_id=primitive_id,
                primitive_version=int(row["schema_version"]),
                reader_adapter=spec.reader_adapter,
                learning_operation=spec.learning_operation,
                evidence_format=spec.evidence_format,
                correction_strategies=spec.correction_strategies,
                response_kinds=tuple(
                    AnswerKind(str(value)) for value in cast(list[object], row["response_kinds"])
                ),
                response_contract=dict(cast(dict[str, JsonValue], row["response_contract"])),
                stimulus_contract=stimulus,
                stimulus_revision_ids=tuple(
                    _uuid(value) for value in cast(list[object], row["stimulus_revision_ids"])
                ),
                target_bindings=tuple(cast(list[JsonValue], row["target_bindings"])),
                lexical_bindings=tuple(cast(list[JsonValue], row["lexical_bindings"])),
                grammar_bindings=grammar_bindings,
                seed=int(str(row["seed"])),
            )

    async def get_attempt(self, actor_id: UUID, attempt_id: UUID) -> AttemptView:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            view = await self._attempt(session, attempt_id)
            if view is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            return view

    async def get_correction(self, actor_id: UUID, correction_id: UUID) -> CorrectionView:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM exercises.exercise_corrections "
                            "WHERE correction_id=:correction"
                        ),
                        {"correction": correction_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            return CorrectionView(
                correction_id=_uuid(row["correction_id"]),
                attempt_id=_uuid(row["attempt_id"]),
                revision_no=int(str(row["revision_no"])),
                verdict=str(row["verdict"]),
                confidence=float(str(row["confidence"])),
                target_coverage=float(str(row["target_coverage"])),
                strategy=str(row["strategy"]),
                proposed_answer=cast(JsonValue, row["proposed_answer"]),
                alternatives=tuple(str(value) for value in row["alternatives"]),
                explanation=str(row["explanation"]),
                error_codes=tuple(str(value) for value in row["error_codes"]),
                criterion_scores={
                    str(key): float(str(value))
                    for key, value in _mapping(row["criterion_scores"]).items()
                },
                requires_review=bool(row["requires_review"]),
                supersedes_correction_id=None
                if row["supersedes_correction_id"] is None
                else _uuid(row["supersedes_correction_id"]),
                is_current=bool(row["is_current"]),
                created_at=cast(datetime, row["created_at"]),
            )

    async def get_correction_case(self, actor_id: UUID, case_id: UUID) -> CorrectionCaseView:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            view, _ = await self._case(session, case_id)
            if view is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            return view

    async def submit_attempt(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: SubmitAttempt,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AttemptView:
        fingerprint = canonical_json_fingerprint(
            _encode(
                {
                    "attempt_id": attempt_id,
                    "command": command,
                    "expected_version": expected_version,
                }
            )
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, "SubmitExerciseAttempt", idempotency_key)
            replay = await self._attempt_replay(
                session,
                actor_id,
                "SubmitExerciseAttempt",
                idempotency_key,
                fingerprint,
            )
            if replay is not None:
                return replay
            before = await self._attempt(session, attempt_id, for_update=True)
            if before is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if before.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if before.status != "draft":
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            allowed = await self._response_kinds(session, before.instance_id)
            answer = Answer.create(
                kind=command.kind,
                raw_value=command.raw_value,
                input_method=command.input_method,
                submitted_at=command.submitted_at,
            )
            if answer.kind not in allowed:
                raise DomainError(ErrorCode.ANSWER_SHAPE_INVALID)
            await session.execute(
                text(
                    "UPDATE exercises.exercise_attempts SET status='submitted',"
                    "answer_kind=:kind,raw_answer=CAST(:answer AS jsonb),"
                    "input_method=:input_method,input_locale=:input_locale,"
                    "submitted_at=:submitted,idempotency_key=:key,"
                    "request_fingerprint=:fingerprint,version=version+1,updated_at=:submitted "
                    "WHERE attempt_id=:attempt"
                ),
                {
                    "kind": answer.kind.value,
                    "answer": _json(answer.raw_value),
                    "input_method": answer.input_method,
                    "input_locale": command.input_locale,
                    "submitted": answer.submitted_at,
                    "key": idempotency_key,
                    "fingerprint": fingerprint,
                    "attempt": attempt_id,
                },
            )
            after = await self._attempt(session, attempt_id)
            if after is None:
                raise DomainError(ErrorCode.INTERNAL_ERROR)
            await self._record_effect(
                session,
                actor_id=actor_id,
                profile_id=after.profile_id,
                command_type="SubmitExerciseAttempt",
                event_type="exercise_attempt_submitted",
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                result_type="attempt",
                result_id=after.attempt_id,
                result_version=after.version,
                result_payload=after,
                occurred_at=answer.submitted_at,
            )
            await session.commit()
            return after

    async def correct_attempt(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: CorrectAttempt,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AttemptView:
        return await self._correct_attempt(
            actor_id,
            attempt_id,
            command,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            trusted_learner_evaluation=False,
        )

    async def evaluate_attempt(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: EvaluateAttempt,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AttemptView:
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT attempt.answer_kind,attempt.raw_answer,"
                            "revision.primitive_id,revision.response_contract,"
                            "revision.stimulus_contract,revision.provenance_id "
                            "FROM exercises.exercise_attempts attempt "
                            "JOIN exercises.exercise_instances instance ON "
                            "instance.instance_id=attempt.instance_id "
                            "JOIN exercises.exercise_definition_revisions revision ON "
                            "revision.definition_revision_id=instance.definition_revision_id "
                            "WHERE attempt.attempt_id=:attempt"
                        ),
                        {"attempt": attempt_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        if row["answer_kind"] is None:
            raise DomainError(ErrorCode.ATTEMPT_NOT_SUBMITTED)
        result = correct_published_answer(
            primitive_id=str(row["primitive_id"]),
            answer_kind=AnswerKind(str(row["answer_kind"])),
            raw_value=cast(JsonValue, row["raw_answer"]),
            response_contract=dict(cast(dict[str, JsonValue], row["response_contract"])),
            stimulus_contract=dict(cast(dict[str, JsonValue], row["stimulus_contract"])),
        )
        return await self._correct_attempt(
            actor_id,
            attempt_id,
            CorrectAttempt(
                correction_id=self._ids.new(),
                result=result,
                provenance_id=_uuid(row["provenance_id"]),
                rubric_revision_id=None,
                proposed_answer=None,
                requires_review=result.verdict
                in {CorrectionVerdict.AMBIGUOUS, CorrectionVerdict.NOT_EVALUABLE},
                created_at=command.evaluated_at,
            ),
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            trusted_learner_evaluation=True,
        )

    async def _correct_attempt(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: CorrectAttempt,
        *,
        expected_version: int,
        idempotency_key: str,
        trusted_learner_evaluation: bool,
    ) -> AttemptView:
        fingerprint = canonical_json_fingerprint(
            _encode(
                {
                    "attempt_id": attempt_id,
                    "command": command,
                    "expected_version": expected_version,
                }
            )
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, "CorrectExerciseAttempt", idempotency_key)
            replay = await self._attempt_replay(
                session,
                actor_id,
                "CorrectExerciseAttempt",
                idempotency_key,
                fingerprint,
            )
            if replay is not None:
                return replay
            before = await self._attempt(session, attempt_id, for_update=True)
            if before is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            authorized = await session.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM identity.account_roles "
                    "WHERE account_id=:actor AND role IN ('worker','reviewer','admin') "
                    "AND revoked_at IS NULL)"
                ),
                {"actor": actor_id},
            )
            owns_profile = await session.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM language_profiles.learner_language_profiles "
                    "WHERE profile_id=:profile AND account_id=:actor)"
                ),
                {"profile": before.profile_id, "actor": actor_id},
            )
            learner_self_assessment = (
                bool(owns_profile) and str(command.result.strategy) == "self_assessment"
            )
            if (
                not authorized
                and not learner_self_assessment
                and not (trusted_learner_evaluation and bool(owns_profile))
            ):
                raise DomainError(ErrorCode.FORBIDDEN)
            if before.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if before.status not in {"submitted", "correcting"}:
                raise DomainError(ErrorCode.ATTEMPT_NOT_SUBMITTED)
            current = (
                (
                    await session.execute(
                        text(
                            "SELECT correction_id,revision_no FROM "
                            "exercises.exercise_corrections WHERE attempt_id=:attempt "
                            "AND is_current FOR UPDATE"
                        ),
                        {"attempt": attempt_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if current is not None:
                await session.execute(
                    text(
                        "UPDATE exercises.exercise_corrections SET is_current=false "
                        "WHERE correction_id=:correction"
                    ),
                    {"correction": current["correction_id"]},
                )
            revision_no = 1 if current is None else int(str(current["revision_no"])) + 1
            result = command.result
            if learner_self_assessment:
                primitive_id = await session.scalar(
                    text(
                        "SELECT revision.primitive_id FROM exercises.exercise_attempts attempt "
                        "JOIN exercises.exercise_instances instance ON "
                        "instance.instance_id=attempt.instance_id "
                        "JOIN exercises.exercise_definition_revisions revision ON "
                        "revision.definition_revision_id=instance.definition_revision_id "
                        "WHERE attempt.attempt_id=:attempt"
                    ),
                    {"attempt": attempt_id},
                )
                if str(primitive_id).startswith("EX-ORAL"):
                    result = CorrectionResult.not_evaluable(
                        "oral self-assessment requires human review"
                    )
            provenance_id = command.provenance_id
            if provenance_id is None:
                raw_provenance_id = await session.scalar(
                    text(
                        "SELECT revision.provenance_id FROM exercises.exercise_attempts attempt "
                        "JOIN exercises.exercise_instances instance ON "
                        "instance.instance_id=attempt.instance_id "
                        "JOIN exercises.exercise_definition_revisions revision ON "
                        "revision.definition_revision_id=instance.definition_revision_id "
                        "WHERE attempt.attempt_id=:attempt"
                    ),
                    {"attempt": attempt_id},
                )
                if raw_provenance_id is None:
                    raise DomainError(ErrorCode.CONTENT_UNAVAILABLE)
                provenance_id = _uuid(raw_provenance_id)
            await session.execute(
                text(
                    "INSERT INTO exercises.exercise_corrections "
                    "(correction_id,attempt_id,profile_id,revision_no,verdict,confidence,"
                    "target_coverage,strategy,rubric_revision_id,proposed_answer,alternatives,"
                    "explanation,error_codes,criterion_scores,provenance_id,requires_review,"
                    "supersedes_correction_id,is_current,result_payload,created_at) VALUES "
                    "(:correction,:attempt,:profile,:revision,:verdict,:confidence,:coverage,"
                    ":strategy,:rubric,CAST(:proposed AS jsonb),CAST(:alternatives AS jsonb),"
                    ":explanation,CAST(:errors AS jsonb),CAST(:criteria AS jsonb),:provenance,"
                    ":requires_review,:supersedes,true,CAST(:result AS jsonb),:created)"
                ),
                {
                    "correction": command.correction_id,
                    "attempt": attempt_id,
                    "profile": before.profile_id,
                    "revision": revision_no,
                    "verdict": result.verdict.value,
                    "confidence": result.confidence,
                    "coverage": result.target_coverage,
                    "strategy": str(result.strategy),
                    "rubric": command.rubric_revision_id,
                    "proposed": _json(command.proposed_answer),
                    "alternatives": _json(result.alternatives),
                    "explanation": result.explanation,
                    "errors": _json(result.errors),
                    "criteria": _json(dict(result.criteria_scores)),
                    "provenance": provenance_id,
                    "requires_review": command.requires_review,
                    "supersedes": None if current is None else current["correction_id"],
                    "result": _json(result),
                    "created": command.created_at,
                },
            )
            status, terminal_reason = {
                CorrectionVerdict.AMBIGUOUS: ("not_evaluable", "correction_ambiguous"),
                CorrectionVerdict.NOT_EVALUABLE: (
                    "not_evaluable",
                    "correction_unavailable",
                ),
                CorrectionVerdict.INVALID_ANSWER: ("not_evaluable", "answer_invalid"),
            }.get(result.verdict, ("corrected", "none"))
            await session.execute(
                text(
                    "UPDATE exercises.exercise_attempts SET status=:status,"
                    "terminal_reason=:reason,corrected_at=:corrected,version=version+1,"
                    "updated_at=:corrected WHERE attempt_id=:attempt"
                ),
                {
                    "status": status,
                    "reason": terminal_reason,
                    "corrected": command.created_at,
                    "attempt": attempt_id,
                },
            )
            await self._complete_planned_block_if_terminal(session, attempt_id, command.created_at)
            after = await self._attempt(session, attempt_id)
            assert after is not None
            await self._record_effect(
                session,
                actor_id=actor_id,
                profile_id=after.profile_id,
                command_type="CorrectExerciseAttempt",
                event_type=(
                    "exercise_attempt_corrected"
                    if status == "corrected"
                    else "attempt_not_evaluable"
                ),
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                result_type="attempt",
                result_id=after.attempt_id,
                result_version=after.version,
                result_payload=after,
                occurred_at=command.created_at,
            )
            await session.commit()
            return after

    async def open_attempt(
        self,
        actor_id: UUID,
        instance_id: UUID,
        command: OpenAttempt,
        *,
        idempotency_key: str,
    ) -> AttemptView:
        fingerprint = canonical_json_fingerprint(
            _encode({"instance_id": instance_id, "command": command})
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, "OpenExerciseAttempt", idempotency_key)
            replay = await self._attempt_replay(
                session,
                actor_id,
                "OpenExerciseAttempt",
                idempotency_key,
                fingerprint,
            )
            if replay is not None:
                return replay
            owns_profile = await session.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM "
                    "language_profiles.learner_language_profiles WHERE profile_id=:profile)"
                ),
                {"profile": command.profile_id},
            )
            instance_profile = await session.scalar(
                text(
                    "SELECT standalone_profile_id FROM exercises.exercise_instances "
                    "WHERE instance_id=:instance"
                ),
                {"instance": instance_id},
            )
            instance_exists = await session.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM exercises.exercise_instances "
                    "WHERE instance_id=:instance)"
                ),
                {"instance": instance_id},
            )
            if not owns_profile or not instance_exists:
                raise DomainError(ErrorCode.NOT_FOUND)
            if instance_profile is not None and _uuid(instance_profile) != command.profile_id:
                raise DomainError(ErrorCode.FORBIDDEN)
            planned_block = await self._planned_block_for_open(
                session, instance_id, command.profile_id
            )
            open_attempt = await session.scalar(
                text(
                    "SELECT attempt_id FROM exercises.exercise_attempts "
                    "WHERE profile_id=:profile AND instance_id=:instance "
                    "AND status IN ('draft','submitted','correcting') FOR UPDATE"
                ),
                {"profile": command.profile_id, "instance": instance_id},
            )
            if open_attempt is not None:
                raise DomainError(ErrorCode.ATTEMPT_ALREADY_OPEN)
            last_no = await session.scalar(
                text(
                    "SELECT COALESCE(MAX(attempt_no),0) FROM exercises.exercise_attempts "
                    "WHERE profile_id=:profile AND instance_id=:instance"
                ),
                {"profile": command.profile_id, "instance": instance_id},
            )
            if command.attempt_no != int(last_no or 0) + 1:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            await session.execute(
                text(
                    "INSERT INTO exercises.exercise_attempts "
                    "(attempt_id,profile_id,instance_id,attempt_no,status,terminal_reason,"
                    "aggregate_payload,version,started_at,updated_at) VALUES "
                    "(:attempt,:profile,:instance,:attempt_no,'draft','none','{}',1,:at,:at)"
                ),
                {
                    "attempt": command.attempt_id,
                    "profile": command.profile_id,
                    "instance": instance_id,
                    "attempt_no": command.attempt_no,
                    "at": command.started_at,
                },
            )
            if planned_block is not None:
                await self._mark_planned_block_in_progress(
                    session,
                    run_id=_uuid(planned_block["sprint_run_id"]),
                    block_id=_uuid(planned_block["block_id"]),
                    started_at=command.started_at,
                )
            after = await self._attempt(session, command.attempt_id)
            if after is None:
                raise DomainError(ErrorCode.INTERNAL_ERROR)
            await self._record_effect(
                session,
                actor_id=actor_id,
                profile_id=after.profile_id,
                command_type="OpenExerciseAttempt",
                event_type="exercise_attempt_opened",
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                result_type="attempt",
                result_id=after.attempt_id,
                result_version=after.version,
                result_payload=after,
                occurred_at=command.started_at,
            )
            await session.commit()
            return after

    @staticmethod
    async def _planned_block_for_open(
        session: AsyncSession,
        instance_id: UUID,
        profile_id: UUID,
    ) -> RowMapping | None:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT runtime.block_id,runtime.sprint_run_id,runtime.status,"
                        "run.status AS run_status FROM "
                        "planning.session_plan_exercise_instances link "
                        "LEFT JOIN exercises.exercise_block_runs runtime "
                        "ON runtime.session_plan_block_id=link.session_plan_block_id "
                        "LEFT JOIN planning.sprint_runs run "
                        "ON run.sprint_run_id=runtime.sprint_run_id "
                        "WHERE link.instance_id=:instance AND link.profile_id=:profile"
                    ),
                    {"instance": instance_id, "profile": profile_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        if row["sprint_run_id"] is None or row["run_status"] != "in_progress":
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        if row["status"] not in {"available", "in_progress"}:
            raise DomainError(ErrorCode.INVALID_TRANSITION)
        return row

    @staticmethod
    async def _mark_planned_block_in_progress(
        session: AsyncSession,
        *,
        run_id: UUID,
        block_id: UUID,
        started_at: datetime,
    ) -> None:
        await session.execute(
            text(
                "UPDATE exercises.exercise_block_runs SET status='in_progress',"
                "version=version+1,updated_at=:at WHERE block_id=:block "
                "AND status='available'"
            ),
            {"block": block_id, "at": started_at},
        )
        await session.execute(
            text(
                "UPDATE planning.sprint_runs SET current_block_id=:block,"
                "version=version+1,updated_at=:at WHERE sprint_run_id=:run "
                "AND status='in_progress'"
            ),
            {"block": block_id, "run": run_id, "at": started_at},
        )

    @staticmethod
    async def _complete_planned_block_if_terminal(
        session: AsyncSession,
        attempt_id: UUID,
        completed_at: datetime,
    ) -> None:
        block = (
            (
                await session.execute(
                    text(
                        "SELECT runtime.block_id,runtime.sprint_run_id,plan.ordinal "
                        "FROM exercises.exercise_attempts attempt "
                        "JOIN planning.session_plan_exercise_instances link "
                        "ON link.instance_id=attempt.instance_id "
                        "JOIN exercises.exercise_block_runs runtime "
                        "ON runtime.session_plan_block_id=link.session_plan_block_id "
                        "JOIN planning.session_plan_blocks plan "
                        "ON plan.session_plan_block_id=link.session_plan_block_id "
                        "WHERE attempt.attempt_id=:attempt"
                    ),
                    {"attempt": attempt_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if block is None:
            return
        all_terminal = await session.scalar(
            text(
                "SELECT NOT EXISTS ("
                "SELECT 1 FROM planning.session_plan_exercise_instances link "
                "WHERE link.session_plan_block_id=("
                "SELECT session_plan_block_id FROM exercises.exercise_block_runs "
                "WHERE block_id=:block) AND NOT EXISTS ("
                "SELECT 1 FROM exercises.exercise_attempts attempt "
                "WHERE attempt.instance_id=link.instance_id "
                "AND attempt.status IN ('corrected','not_evaluable')))"
            ),
            {"block": block["block_id"]},
        )
        if not all_terminal:
            return
        await session.execute(
            text(
                "UPDATE exercises.exercise_block_runs SET status='completed',"
                "version=version+1,updated_at=:at WHERE block_id=:block "
                "AND status IN ('available','in_progress')"
            ),
            {"block": block["block_id"], "at": completed_at},
        )
        await session.execute(
            text(
                "UPDATE exercises.exercise_block_runs runtime SET status='available',"
                "version=version+1,updated_at=:at FROM planning.session_plan_blocks plan "
                "WHERE runtime.session_plan_block_id=plan.session_plan_block_id "
                "AND runtime.sprint_run_id=:run AND plan.ordinal=:ordinal "
                "AND runtime.status='pending'"
            ),
            {
                "run": block["sprint_run_id"],
                "ordinal": int(block["ordinal"]) + 1,
                "at": completed_at,
            },
        )
        await session.execute(
            text(
                "UPDATE planning.sprint_runs SET current_block_id=NULL,"
                "version=version+1,updated_at=:at WHERE sprint_run_id=:run "
                "AND status IN ('in_progress','interrupted')"
            ),
            {"run": block["sprint_run_id"], "at": completed_at},
        )

    async def save_draft(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: SaveDraft,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AttemptView:
        fingerprint = canonical_json_fingerprint(
            _encode(
                {
                    "attempt_id": attempt_id,
                    "command": command,
                    "expected_version": expected_version,
                }
            )
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, "SaveAttemptDraft", idempotency_key)
            replay = await self._attempt_replay(
                session,
                actor_id,
                "SaveAttemptDraft",
                idempotency_key,
                fingerprint,
            )
            if replay is not None:
                return replay
            before = await self._attempt(session, attempt_id, for_update=True)
            self._require_draft_version(before, expected_version)
            assert before is not None
            await session.execute(
                text(
                    "INSERT INTO exercises.attempt_drafts "
                    "(attempt_id,profile_id,draft_payload,version,updated_at) VALUES "
                    "(:attempt,:profile,CAST(:payload AS jsonb),1,:at) "
                    "ON CONFLICT (attempt_id) DO UPDATE SET draft_payload=EXCLUDED.draft_payload,"
                    "version=exercises.attempt_drafts.version+1,updated_at=EXCLUDED.updated_at"
                ),
                {
                    "attempt": attempt_id,
                    "profile": before.profile_id,
                    "payload": _json(command.draft_payload),
                    "at": command.updated_at,
                },
            )
            await self._bump_attempt(session, attempt_id, command.updated_at)
            after = await self._attempt(session, attempt_id)
            assert after is not None
            await self._record_effect(
                session,
                actor_id=actor_id,
                profile_id=after.profile_id,
                command_type="SaveAttemptDraft",
                event_type="attempt_draft_saved",
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                result_type="attempt",
                result_id=after.attempt_id,
                result_version=after.version,
                result_payload=after,
                occurred_at=command.updated_at,
            )
            await session.commit()
            return after

    async def use_hint(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: UseHint,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AttemptView:
        fingerprint = canonical_json_fingerprint(
            _encode(
                {
                    "attempt_id": attempt_id,
                    "command": command,
                    "expected_version": expected_version,
                }
            )
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, "UseExerciseHint", idempotency_key)
            replay = await self._attempt_replay(
                session,
                actor_id,
                "UseExerciseHint",
                idempotency_key,
                fingerprint,
            )
            if replay is not None:
                return replay
            before = await self._attempt(session, attempt_id, for_update=True)
            self._require_draft_version(before, expected_version)
            assert before is not None
            previous = (
                (
                    await session.execute(
                        text(
                            "SELECT sequence_no,level FROM exercises.exercise_hint_uses "
                            "WHERE attempt_id=:attempt ORDER BY sequence_no DESC LIMIT 1"
                        ),
                        {"attempt": attempt_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            sequence_no = 1 if previous is None else int(str(previous["sequence_no"])) + 1
            if previous is not None:
                previous_level = int(str(previous["level"])[1:])
                if int(command.level.value[1:]) < previous_level:
                    raise DomainError(ErrorCode.HINT_NOT_AVAILABLE)
            await session.execute(
                text(
                    "INSERT INTO exercises.exercise_hint_uses "
                    "(hint_use_id,attempt_id,profile_id,sequence_no,"
                    "hint_definition_revision_id,level,reason,answer_state_checksum,"
                    "effect_policy_revision_id,shown_at) VALUES "
                    "(:hint,:attempt,:profile,:sequence,:definition,:level,:reason,"
                    ":checksum,:effect,:shown)"
                ),
                {
                    "hint": command.hint_use_id,
                    "attempt": attempt_id,
                    "profile": before.profile_id,
                    "sequence": sequence_no,
                    "definition": command.hint_definition_revision_id,
                    "level": command.level.value,
                    "reason": command.reason,
                    "checksum": command.answer_state_checksum,
                    "effect": command.effect_policy_revision_id,
                    "shown": command.shown_at,
                },
            )
            await self._bump_attempt(session, attempt_id, command.shown_at)
            after = await self._attempt(session, attempt_id)
            assert after is not None
            await self._record_effect(
                session,
                actor_id=actor_id,
                profile_id=after.profile_id,
                command_type="UseExerciseHint",
                event_type="exercise_hint_used",
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                result_type="attempt",
                result_id=after.attempt_id,
                result_version=after.version,
                result_payload=after,
                occurred_at=command.shown_at,
            )
            await session.commit()
            return after

    async def contest_correction(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: ContestCorrection,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> CorrectionCaseView:
        fingerprint = canonical_json_fingerprint(
            _encode(
                {
                    "attempt_id": attempt_id,
                    "command": command,
                    "expected_version": expected_version,
                }
            )
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, "ContestCorrection", idempotency_key)
            replay = await self._case_replay(
                session, actor_id, "ContestCorrection", idempotency_key, fingerprint
            )
            if replay is not None:
                return replay
            attempt = await self._attempt(session, attempt_id, for_update=True)
            if attempt is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if attempt.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if attempt.status not in {"corrected", "not_evaluable"}:
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            has_correction = await session.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM exercises.exercise_corrections "
                    "WHERE attempt_id=:attempt AND is_current)"
                ),
                {"attempt": attempt_id},
            )
            if not has_correction:
                raise DomainError(ErrorCode.CORRECTION_PATH_MISSING)
            existing = await session.scalar(
                text("SELECT case_id FROM exercises.correction_cases WHERE attempt_id=:attempt"),
                {"attempt": attempt_id},
            )
            if existing is not None:
                raise DomainError(ErrorCode.CASE_ALREADY_OPEN)
            await session.execute(
                text(
                    "INSERT INTO exercises.correction_cases "
                    "(case_id,attempt_id,profile_id,status,opened_by_account_id,reason_code,"
                    "user_comment,opened_at,current_review_no,version) VALUES "
                    "(:case,:attempt,:profile,'contested',:actor,:reason,:comment,:opened,0,1)"
                ),
                {
                    "case": command.case_id,
                    "attempt": attempt_id,
                    "profile": attempt.profile_id,
                    "actor": actor_id,
                    "reason": command.reason_code,
                    "comment": command.user_comment,
                    "opened": command.opened_at,
                },
            )
            case, profile_id = await self._case(session, command.case_id)
            assert case is not None and profile_id is not None
            await self._record_effect(
                session,
                actor_id=actor_id,
                profile_id=profile_id,
                command_type="ContestCorrection",
                event_type="correction_contested",
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                result_type="correction_case",
                result_id=case.case_id,
                result_version=case.version,
                result_payload=case,
                occurred_at=command.opened_at,
            )
            await session.commit()
            return case

    async def mark_correction_read(
        self,
        actor_id: UUID,
        attempt_id: UUID,
        command: MarkCorrectionRead,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> AttemptView:
        fingerprint = canonical_json_fingerprint(
            _encode(
                {
                    "attempt_id": attempt_id,
                    "command": command,
                    "expected_version": expected_version,
                }
            )
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, "ReviewCorrection", idempotency_key)
            replay = await self._attempt_replay(
                session,
                actor_id,
                "ReviewCorrection",
                idempotency_key,
                fingerprint,
            )
            if replay is not None:
                return replay
            before = await self._attempt(session, attempt_id, for_update=True)
            if before is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if before.version != expected_version:
                raise DomainError(ErrorCode.VERSION_CONFLICT)
            if before.status not in {"corrected", "not_evaluable"}:
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            await session.execute(
                text(
                    "UPDATE exercises.exercise_attempts SET correction_reviewed_at=:reviewed,"
                    "version=version+1,updated_at=:reviewed WHERE attempt_id=:attempt"
                ),
                {"reviewed": command.reviewed_at, "attempt": attempt_id},
            )
            after = await self._attempt(session, attempt_id)
            assert after is not None
            await self._record_effect(
                session,
                actor_id=actor_id,
                profile_id=after.profile_id,
                command_type="ReviewCorrection",
                event_type="correction_reviewed",
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                result_type="attempt",
                result_id=after.attempt_id,
                result_version=after.version,
                result_payload=after,
                occurred_at=command.reviewed_at,
            )
            await session.commit()
            return after

    async def resolve_correction_case(
        self,
        actor_id: UUID,
        case_id: UUID,
        command: ResolveCorrectionCase,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> CorrectionCaseView:
        fingerprint = canonical_json_fingerprint(
            _encode(
                {
                    "case_id": case_id,
                    "command": command,
                    "expected_version": expected_version,
                }
            )
        )
        async with self._sessions() as session:
            await self._set_actor(session, actor_id)
            await self._lock_command(session, actor_id, "ReviewCorrectionCase", idempotency_key)
            replay = await self._case_replay(
                session,
                actor_id,
                "ReviewCorrectionCase",
                idempotency_key,
                fingerprint,
            )
            if replay is not None:
                return replay
            reviewer = await session.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM identity.account_roles "
                    "WHERE account_id=:actor AND role IN ('reviewer','admin') "
                    "AND revoked_at IS NULL)"
                ),
                {"actor": actor_id},
            )
            if not reviewer:
                raise DomainError(ErrorCode.FORBIDDEN)
            before, profile_id = await self._case(session, case_id, for_update=True)
            if before is None or profile_id is None:
                raise DomainError(ErrorCode.NOT_FOUND)
            if before.version != expected_version:
                raise DomainError(ErrorCode.REVIEW_CONFLICT)
            if before.status not in {"contested", "review_pending"}:
                raise DomainError(ErrorCode.INVALID_TRANSITION)
            correction_attempt = await session.scalar(
                text(
                    "SELECT attempt_id FROM exercises.exercise_corrections "
                    "WHERE correction_id=:correction AND profile_id=:profile"
                ),
                {"correction": command.correction_id, "profile": profile_id},
            )
            if correction_attempt is None or _uuid(correction_attempt) != before.attempt_id:
                raise DomainError(ErrorCode.REVIEW_CONFLICT)
            review_no = await session.scalar(
                text(
                    "SELECT current_review_no+1 FROM exercises.correction_cases WHERE case_id=:case"
                ),
                {"case": case_id},
            )
            await session.execute(
                text(
                    "INSERT INTO exercises.correction_case_reviews "
                    "(case_review_id,case_id,profile_id,review_no,reviewer_actor_id,decision,"
                    "rationale,correction_id,reviewed_at) VALUES "
                    "(:review,:case,:profile,:review_no,:actor,:decision,:rationale,"
                    ":correction,:reviewed)"
                ),
                {
                    "review": command.case_review_id,
                    "case": case_id,
                    "profile": profile_id,
                    "review_no": int(review_no or 1),
                    "actor": actor_id,
                    "decision": command.decision,
                    "rationale": command.rationale,
                    "correction": command.correction_id,
                    "reviewed": command.reviewed_at,
                },
            )
            await session.execute(
                text(
                    "UPDATE exercises.correction_cases SET status='resolved',"
                    "resolved_at=:reviewed,resolution_correction_id=:correction,"
                    "current_review_no=:review_no,version=version+1 WHERE case_id=:case"
                ),
                {
                    "reviewed": command.reviewed_at,
                    "correction": command.correction_id,
                    "review_no": int(review_no or 1),
                    "case": case_id,
                },
            )
            after, _ = await self._case(session, case_id)
            assert after is not None
            await self._record_effect(
                session,
                actor_id=actor_id,
                profile_id=profile_id,
                command_type="ReviewCorrectionCase",
                event_type="correction_case_resolved",
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                result_type="correction_case",
                result_id=after.case_id,
                result_version=after.version,
                result_payload=after,
                occurred_at=command.reviewed_at,
            )
            await session.commit()
            return after

    async def _attempt(
        self,
        session: AsyncSession,
        attempt_id: UUID,
        *,
        for_update: bool = False,
    ) -> AttemptView | None:
        suffix = " FOR UPDATE" if for_update else ""
        row = (
            (
                await session.execute(
                    text(
                        "SELECT attempt_id,profile_id,instance_id,attempt_no,status,"
                        "terminal_reason,answer_kind,raw_answer,input_method,input_locale,"
                        "submitted_at,active_duration_ms,correction_reviewed_at,version,"
                        "started_at,updated_at FROM exercises.exercise_attempts "
                        "WHERE attempt_id=:attempt" + suffix
                    ),
                    {"attempt": attempt_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return AttemptView(
            attempt_id=_uuid(row["attempt_id"]),
            profile_id=_uuid(row["profile_id"]),
            instance_id=_uuid(row["instance_id"]),
            attempt_no=int(str(row["attempt_no"])),
            status=str(row["status"]),
            terminal_reason=str(row["terminal_reason"]),
            answer_kind=None if row["answer_kind"] is None else AnswerKind(str(row["answer_kind"])),
            raw_answer=cast(JsonValue, row["raw_answer"]),
            input_method=None if row["input_method"] is None else str(row["input_method"]),
            input_locale=None if row["input_locale"] is None else str(row["input_locale"]),
            submitted_at=cast(datetime | None, row["submitted_at"]),
            active_duration_ms=int(str(row["active_duration_ms"])),
            correction_reviewed_at=cast(datetime | None, row["correction_reviewed_at"]),
            version=int(str(row["version"])),
            started_at=cast(datetime, row["started_at"]),
            updated_at=cast(datetime, row["updated_at"]),
        )

    @staticmethod
    def _require_draft_version(attempt: AttemptView | None, expected_version: int) -> None:
        if attempt is None:
            raise DomainError(ErrorCode.NOT_FOUND)
        if attempt.version != expected_version:
            raise DomainError(ErrorCode.VERSION_CONFLICT)
        if attempt.status != "draft":
            raise DomainError(ErrorCode.INVALID_TRANSITION)

    @staticmethod
    async def _bump_attempt(session: AsyncSession, attempt_id: UUID, updated_at: datetime) -> None:
        await session.execute(
            text(
                "UPDATE exercises.exercise_attempts SET version=version+1,updated_at=:at "
                "WHERE attempt_id=:attempt"
            ),
            {"attempt": attempt_id, "at": updated_at},
        )

    async def _response_kinds(
        self, session: AsyncSession, instance_id: UUID
    ) -> tuple[AnswerKind, ...]:
        values = await session.scalar(
            text(
                "SELECT revision.response_kinds FROM exercises.exercise_instances instance "
                "JOIN exercises.exercise_definition_revisions revision ON "
                "revision.definition_revision_id=instance.definition_revision_id "
                "WHERE instance.instance_id=:instance"
            ),
            {"instance": instance_id},
        )
        if not isinstance(values, list):
            raise DomainError(ErrorCode.NOT_FOUND)
        return tuple(AnswerKind(str(value)) for value in values)

    async def _case(
        self,
        session: AsyncSession,
        case_id: UUID,
        *,
        for_update: bool = False,
    ) -> tuple[CorrectionCaseView | None, UUID | None]:
        suffix = " FOR UPDATE" if for_update else ""
        row = (
            (
                await session.execute(
                    text(
                        "SELECT case_id,attempt_id,profile_id,status,reason_code,user_comment,"
                        "resolution_correction_id,version,opened_at,resolved_at "
                        "FROM exercises.correction_cases WHERE case_id=:case" + suffix
                    ),
                    {"case": case_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None, None
        return (
            CorrectionCaseView(
                case_id=_uuid(row["case_id"]),
                attempt_id=_uuid(row["attempt_id"]),
                status=str(row["status"]),
                reason_code=str(row["reason_code"]),
                user_comment=None if row["user_comment"] is None else str(row["user_comment"]),
                resolution_correction_id=None
                if row["resolution_correction_id"] is None
                else _uuid(row["resolution_correction_id"]),
                version=int(str(row["version"])),
                opened_at=cast(datetime, row["opened_at"]),
                resolved_at=cast(datetime | None, row["resolved_at"]),
            ),
            _uuid(row["profile_id"]),
        )

    async def _attempt_replay(
        self,
        session: AsyncSession,
        actor_id: UUID,
        command_type: str,
        idempotency_key: str,
        fingerprint: str,
    ) -> AttemptView | None:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT request_fingerprint,result_type,result_payload "
                        "FROM exercises.exercise_command_receipts WHERE actor_id=:actor "
                        "AND command_type=:command AND idempotency_key=:key"
                    ),
                    {"actor": actor_id, "command": command_type, "key": idempotency_key},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        if row["request_fingerprint"] != fingerprint or row["result_type"] != "attempt":
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return _attempt_from_payload(row["result_payload"])

    async def _case_replay(
        self,
        session: AsyncSession,
        actor_id: UUID,
        command_type: str,
        idempotency_key: str,
        fingerprint: str,
    ) -> CorrectionCaseView | None:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT request_fingerprint,result_type,result_payload "
                        "FROM exercises.exercise_command_receipts WHERE actor_id=:actor "
                        "AND command_type=:command AND idempotency_key=:key"
                    ),
                    {"actor": actor_id, "command": command_type, "key": idempotency_key},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        if row["request_fingerprint"] != fingerprint or row["result_type"] != "correction_case":
            raise DomainError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return _case_from_payload(row["result_payload"])

    async def _record_effect(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        profile_id: UUID,
        command_type: str,
        event_type: str,
        idempotency_key: str,
        fingerprint: str,
        result_type: str,
        result_id: UUID,
        result_version: int,
        result_payload: object,
        occurred_at: datetime,
    ) -> None:
        receipt_id = self._ids.new()
        await session.execute(
            text(
                "INSERT INTO exercises.exercise_command_receipts "
                "(receipt_id,profile_id,actor_id,command_type,idempotency_key,"
                "request_fingerprint,result_type,result_id,result_version,result_payload,"
                "created_at) VALUES (:receipt,:profile,:actor,:command,:key,:fingerprint,"
                ":result_type,:result_id,:version,CAST(:payload AS jsonb),:occurred)"
            ),
            {
                "receipt": receipt_id,
                "profile": profile_id,
                "actor": actor_id,
                "command": command_type,
                "key": idempotency_key,
                "fingerprint": fingerprint,
                "result_type": result_type,
                "result_id": result_id,
                "version": result_version,
                "payload": _json(result_payload),
                "occurred": occurred_at,
            },
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
                "(:event,:event_type,1,:aggregate_type,:aggregate,:version,'account',:actor,"
                ":profile,:occurred,:occurred,:event,NULL,:command,'personal','{}',"
                "jsonb_build_object('resource_id',CAST(:resource AS text)),:expires,"
                "'profile',:profile)"
            ),
            {
                "event": event_id,
                "event_type": event_type,
                "aggregate_type": result_type,
                "aggregate": result_id,
                "resource": str(result_id),
                "version": result_version,
                "actor": actor_id,
                "profile": profile_id,
                "occurred": occurred_at,
                "command": receipt_id,
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

    @staticmethod
    async def _set_actor(session: AsyncSession, actor_id: UUID) -> None:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"),
            {"actor": str(actor_id)},
        )

    @staticmethod
    async def _lock_command(
        session: AsyncSession,
        actor_id: UUID,
        command_type: str,
        idempotency_key: str,
    ) -> None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
            {"scope": f"{actor_id}:{command_type}:{idempotency_key}"},
        )


__all__ = ["SqlExerciseService"]
