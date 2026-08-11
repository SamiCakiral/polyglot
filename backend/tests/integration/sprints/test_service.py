from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.curriculum.application import EnrollInModule
from polyglot.modules.curriculum.persistence import SqlCurriculumService
from polyglot.modules.exercises.core.application import CorrectAttempt, OpenAttempt, SubmitAttempt
from polyglot.modules.exercises.core.domain import AnswerKind, CorrectionResult
from polyglot.modules.exercises.core.persistence import SqlExerciseService
from polyglot.modules.identity.application import RequestContext
from polyglot.modules.sprints.application import (
    ComposeDailySession,
    ComposeFreePractice,
    InterruptSprintRun,
    StartSprintRun,
)
from polyglot.modules.sprints.domain import DelayedRecodeSpec
from polyglot.modules.sprints.persistence import (
    SqlDelayedRecodeRepository,
    SqlSprintService,
)
from polyglot.platform.clock import FrozenClock
from polyglot.platform.errors import DomainError, ErrorCode
from polyglot.platform.ids import Uuid7Generator
from tests.integration.curriculum.conftest import (
    ACCOUNT_ID,
    MODULE_REVISION_ID,
    NOW,
    PACK_REVISION_ID,
    PROFILE_ID,
    seed_curriculum_dependencies,
    uid,
)

PRIMITIVES = (
    "EX-RECALL-01",
    "EX-EXPOSE-01",
    "EX-TRANSFORM-01",
    "EX-COMP-02",
    "EX-PROD-01",
)


def new_id() -> UUID:
    return Uuid7Generator(FrozenClock(NOW)).new()


def context() -> RequestContext:
    return RequestContext(uid(390), uid(391), "127.0.0")


def sprint_service(factory: async_sessionmaker[AsyncSession]) -> SqlSprintService:
    return SqlSprintService(
        factory,
        clock=FrozenClock(NOW),
        id_generator=Uuid7Generator(FrozenClock(NOW)),
    )


async def seed_sprint_dependencies(session: AsyncSession) -> None:
    revisions = tuple(uid(410 + ordinal) for ordinal in range(1, len(PRIMITIVES) + 1))
    await seed_curriculum_dependencies(
        session,
        exercise_definition_revision_ids=revisions,
        primary_target_ref="grammar:near_future",
        grammar_family_code="near_future",
    )
    await session.execute(
        text(
            "INSERT INTO identity.user_preferences "
            "(account_id,interface_locale,timezone,day_cutover_local_time,"
            "preferred_sprint_minutes,accessibility_preferences,media_preferences,version,"
            "created_at,updated_at) VALUES "
            "(:account,'fr-FR','Europe/Paris','04:00',30,"
            "CAST(:preferences AS jsonb),CAST(:preferences AS jsonb),1,:now,:now)"
        ),
        {"account": ACCOUNT_ID, "preferences": '{"schema_version":1}', "now": NOW},
    )
    await session.execute(
        text(
            "INSERT INTO identity.account_roles "
            "(role_grant_id,account_id,role,granted_at,granted_by_actor_id) VALUES "
            "(:grant,:account,'worker',:now,:account)"
        ),
        {"grant": uid(399), "account": ACCOUNT_ID, "now": NOW},
    )
    for ordinal, primitive in enumerate(PRIMITIVES, start=1):
        definition_id = uid(400 + ordinal)
        revision_id = uid(410 + ordinal)
        await session.execute(
            text(
                "INSERT INTO exercises.exercise_definitions "
                "(definition_id,definition_code,status,version,created_at,updated_at) VALUES "
                "(:definition,:code,'published',1,:now,:now)"
            ),
            {
                "definition": definition_id,
                "code": f"sprint.{ordinal}",
                "now": NOW,
            },
        )
        await session.execute(
            text(
                "INSERT INTO exercises.exercise_definition_revisions "
                "(definition_revision_id,definition_id,revision_no,schema_version,primitive_id,"
                "status,response_kinds,language_certification_ids,modes,target_weights,"
                "response_contract,stimulus_contract,target_contract,difficulty_profile,"
                "prerequisite_skill_revision_ids,correction_policy_id,hint_policy_id,"
                "observation_policy_id,accessibility_features,min_duration_ms,p50_duration_ms,"
                "p80_duration_ms,example_revision_ids,provenance_id,created_at) VALUES "
                "(:revision,:definition,1,1,:primitive,'published','[\"text\"]','[]',"
                "'[\"guided\"]','[[\"grammar\",1]]','{}','{}','[]','{}','[]',"
                "'correction:v1','hint:v1','observation:v1','[\"keyboard\"]',"
                "30000,60000,90000,'[]',:provenance,:now)"
            ),
            {
                "revision": revision_id,
                "definition": definition_id,
                "primitive": primitive,
                "provenance": uid(9),
                "now": NOW,
            },
        )
        await session.execute(
            text(
                "UPDATE exercises.exercise_definitions SET current_revision_id=:revision "
                "WHERE definition_id=:definition"
            ),
            {"revision": revision_id, "definition": definition_id},
        )


async def enroll(factory: async_sessionmaker[AsyncSession]) -> None:
    service = SqlCurriculumService(
        factory,
        clock=FrozenClock(NOW),
        id_generator=Uuid7Generator(FrozenClock(NOW)),
    )
    enrollment_id = new_id()
    await service.enroll(
        ACCOUNT_ID,
        PROFILE_ID,
        EnrollInModule(enrollment_id, MODULE_REVISION_ID, NOW.date()),
        idempotency_key=f"enroll:{enrollment_id}",
        context=context(),
    )


async def complete_planned_session(
    service: SqlSprintService,
    exercises: SqlExerciseService,
    plan_id: UUID,
    plan_version: int,
    suffix: str,
    at: datetime,
) -> None:
    await service.prepare(
        ACCOUNT_ID,
        plan_id,
        expected_version=plan_version,
        idempotency_key=f"prepare:{suffix}",
        context=context(),
    )
    run = await service.start_run(
        ACCOUNT_ID,
        plan_id,
        StartSprintRun(new_id()),
        idempotency_key=f"start:{suffix}",
        context=context(),
    )
    current = run
    for block in run.blocks:
        for instance_id in block.exercise_instance_ids:
            attempt = await exercises.open_attempt(
                ACCOUNT_ID,
                instance_id,
                OpenAttempt(new_id(), PROFILE_ID, 1, at),
                idempotency_key=f"open:{suffix}:{instance_id}",
            )
            submitted = await exercises.submit_attempt(
                ACCOUNT_ID,
                attempt.attempt_id,
                SubmitAttempt(AnswerKind.TEXT, "risposta", "keyboard", "it-IT", at),
                expected_version=attempt.version,
                idempotency_key=f"submit:{suffix}:{instance_id}",
            )
            await exercises.correct_attempt(
                ACCOUNT_ID,
                attempt.attempt_id,
                CorrectAttempt(
                    correction_id=new_id(),
                    result=CorrectionResult.correct(confidence=1),
                    provenance_id=uid(9),
                    rubric_revision_id=None,
                    proposed_answer="risposta",
                    requires_review=False,
                    created_at=at,
                ),
                expected_version=submitted.version,
                idempotency_key=f"correct:{suffix}:{instance_id}",
            )
            current = await service.get_run(ACCOUNT_ID, run.run_id)
    completed = await service.complete_run(
        ACCOUNT_ID,
        run.run_id,
        expected_version=current.version,
        idempotency_key=f"complete:{suffix}",
        context=context(),
    )
    assert completed.status == "completed"


async def test_daily_plan_is_replayable_preparable_and_resumable(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_sprint_dependencies(migration_session)
    await migration_session.commit()
    await enroll(runtime_factory)
    service = sprint_service(runtime_factory)
    command = ComposeDailySession(new_id(), new_id(), NOW.date(), 30)

    plan = await service.compose_daily(
        ACCOUNT_ID,
        PROFILE_ID,
        command,
        idempotency_key="daily-plan",
        context=context(),
    )
    replay = await service.compose_daily(
        ACCOUNT_ID,
        PROFILE_ID,
        command,
        idempotency_key="daily-plan",
        context=context(),
    )
    assert replay == plan
    assert plan.status == "draft"
    assert {"activation", "primary_objective", "reflection"} <= {
        role for block in plan.blocks for role in block.roles
    }


    ready = await service.prepare(
        ACCOUNT_ID,
        plan.plan_id,
        expected_version=plan.version,
        idempotency_key="prepare-plan",
        context=context(),
    )
    assert ready.status == "ready"
    assert all(
        block.exercise_instance_ids or block.family == "reflection_close" for block in ready.blocks
    )

    run = await service.start_run(
        ACCOUNT_ID,
        ready.plan_id,
        StartSprintRun(new_id()),
        idempotency_key="start-run",
        context=context(),
    )
    assert run.status == "in_progress"
    assert run.blocks[0].status == "available"
    with pytest.raises(DomainError) as started:
        await service.cancel_plan(
            ACCOUNT_ID,
            ready.plan_id,
            expected_version=ready.version,
            idempotency_key="cancel-started-plan",
            context=context(),
        )
    assert started.value.code is ErrorCode.RUN_ALREADY_STARTED

    first_instance = run.blocks[0].exercise_instance_ids[0]
    exercises = SqlExerciseService(runtime_factory)
    attempt = await exercises.open_attempt(
        ACCOUNT_ID,
        first_instance,
        OpenAttempt(new_id(), PROFILE_ID, 1, NOW),
        idempotency_key="open-first-planned-exercise",
    )
    active = await service.get_run(ACCOUNT_ID, run.run_id)
    assert active.current_block_id == run.blocks[0].block_id
    assert active.blocks[0].status == "in_progress"
    submitted = await exercises.submit_attempt(
        ACCOUNT_ID,
        attempt.attempt_id,
        SubmitAttempt(AnswerKind.TEXT, "risposta", "keyboard", "it-IT", NOW),
        expected_version=attempt.version,
        idempotency_key="submit-first-planned-exercise",
    )
    first_attempt = attempt
    first_correction_id = new_id()
    await exercises.correct_attempt(
        ACCOUNT_ID,
        attempt.attempt_id,
        CorrectAttempt(
            correction_id=first_correction_id,
            result=CorrectionResult.correct(confidence=1),
            provenance_id=uid(9),
            rubric_revision_id=None,
            proposed_answer="risposta",
            requires_review=False,
            created_at=NOW,
        ),
        expected_version=submitted.version,
        idempotency_key="correct-first-planned-exercise",
    )
    recode_id = new_id()
    recode = DelayedRecodeSpec(
        delayed_recode_id=recode_id,
        profile_id=PROFILE_ID,
        source_attempt_id=first_attempt.attempt_id,
        source_correction_revision_id=first_correction_id,
        source_exercise_instance_id=first_instance,
        target_stimulus="Vorrei un biglietto.",
        corrected_support_text="Je voudrais un billet.",
        accepted_target_answers=("Vorrei un biglietto.",),
        target_language_tag="it-IT",
        support_language_tag="fr-FR",
        target_refs=("grammar:near_future",),
        correction_policy_revision_id=uid(430),
        content_revision_ids=(uid(411),),
        source_corrected_at=NOW,
        not_before=NOW + timedelta(hours=24),
        due_after_24h=True,
    )
    recodes = SqlDelayedRecodeRepository(
        runtime_factory,
        clock=FrozenClock(NOW),
        id_generator=Uuid7Generator(FrozenClock(NOW)),
    )
    assert await recodes.schedule(ACCOUNT_ID, recode) == recode_id
    assert await recodes.schedule(ACCOUNT_ID, recode) == recode_id
    advanced = await service.get_run(ACCOUNT_ID, run.run_id)
    assert advanced.current_block_id is None
    assert advanced.blocks[0].status == "completed"
    assert advanced.blocks[1].status == "available"

    interrupted = await service.interrupt_run(
        ACCOUNT_ID,
        run.run_id,
        InterruptSprintRun("user_pause"),
        expected_version=advanced.version,
        idempotency_key="interrupt-run",
        context=context(),
    )
    assert interrupted.status == "interrupted"
    resumed = await service.resume_run(
        ACCOUNT_ID,
        run.run_id,
        expected_version=interrupted.version,
        idempotency_key="resume-run",
        context=context(),
    )
    assert resumed.status == "in_progress"

    with pytest.raises(DomainError) as incomplete:
        await service.complete_run(
            ACCOUNT_ID,
            run.run_id,
            expected_version=resumed.version,
            idempotency_key="complete-too-early",
            context=context(),
        )
    assert incomplete.value.code is ErrorCode.REQUIRED_BLOCK_INCOMPLETE

    current = resumed
    for block in current.blocks:
        if not block.exercise_instance_ids or block.status == "completed":
            continue
        instance_id = block.exercise_instance_ids[0]
        attempt = await exercises.open_attempt(
            ACCOUNT_ID,
            instance_id,
            OpenAttempt(new_id(), PROFILE_ID, 1, NOW),
            idempotency_key=f"open:{instance_id}",
        )
        submitted = await exercises.submit_attempt(
            ACCOUNT_ID,
            attempt.attempt_id,
            SubmitAttempt(AnswerKind.TEXT, "risposta", "keyboard", "it-IT", NOW),
            expected_version=attempt.version,
            idempotency_key=f"submit:{instance_id}",
        )
        await exercises.correct_attempt(
            ACCOUNT_ID,
            attempt.attempt_id,
            CorrectAttempt(
                correction_id=new_id(),
                result=CorrectionResult.correct(confidence=1),
                provenance_id=uid(9),
                rubric_revision_id=None,
                proposed_answer="risposta",
                requires_review=False,
                created_at=NOW,
            ),
            expected_version=submitted.version,
            idempotency_key=f"correct:{instance_id}",
        )
        current = await service.get_run(ACCOUNT_ID, run.run_id)

    completed = await service.complete_run(
        ACCOUNT_ID,
        run.run_id,
        expected_version=current.version,
        idempotency_key="complete-run",
        context=context(),
    )
    assert completed.status == "completed"
    assert completed.consumes_module_day is True

    future_service = SqlSprintService(
        runtime_factory,
        clock=FrozenClock(NOW + timedelta(hours=24)),
        id_generator=Uuid7Generator(FrozenClock(NOW + timedelta(hours=24))),
    )
    next_plan = await future_service.compose_daily(
        ACCOUNT_ID,
        PROFILE_ID,
        ComposeDailySession(new_id(), new_id(), NOW.date() + timedelta(days=3), 30),
        idempotency_key="next-active-day",
        context=context(),
    )
    await migration_session.execute(
        text("SELECT set_config('app.user_id',:actor,true)"),
        {"actor": str(ACCOUNT_ID)},
    )
    next_ordinal = await migration_session.scalar(
        text(
            "SELECT day.ordinal FROM planning.planning_snapshots snapshot "
            "JOIN curriculum.module_days day ON day.module_day_id=snapshot.module_day_id "
            "WHERE snapshot.snapshot_id=:snapshot"
        ),
        {"snapshot": next_plan.snapshot_id},
    )
    assert next_ordinal == 2
    assert recode_id in {
        block.delayed_recode_id for block in next_plan.blocks if block.family == "delayed_recode"
    }
    task_count = await migration_session.scalar(
        text("SELECT count(*) FROM planning.delayed_recode_tasks WHERE delayed_recode_id=:recode"),
        {"recode": recode_id},
    )
    assert task_count == 1
    await complete_planned_session(
        future_service,
        exercises,
        next_plan.plan_id,
        next_plan.version,
        "day-2",
        NOW + timedelta(hours=24),
    )

    third_service = SqlSprintService(
        runtime_factory,
        clock=FrozenClock(NOW + timedelta(hours=48)),
        id_generator=Uuid7Generator(FrozenClock(NOW + timedelta(hours=48))),
    )
    third_plan = await third_service.compose_daily(
        ACCOUNT_ID,
        PROFILE_ID,
        ComposeDailySession(new_id(), new_id(), NOW.date() + timedelta(days=4), 30),
        idempotency_key="third-active-day",
        context=context(),
    )
    await complete_planned_session(
        third_service,
        exercises,
        third_plan.plan_id,
        third_plan.version,
        "day-3",
        NOW + timedelta(hours=48),
    )
    completed_days = await migration_session.scalar(
        text(
            "SELECT count(*) FROM planning.sprint_runs "
            "WHERE profile_id=:profile AND plan_kind='daily' AND status='completed'"
        ),
        {"profile": PROFILE_ID},
    )
    assert completed_days == 3


async def test_free_practice_never_consumes_a_module_day(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_sprint_dependencies(migration_session)
    await migration_session.commit()
    service = sprint_service(runtime_factory)
    command = ComposeFreePractice(
        plan_id=new_id(),
        snapshot_id=new_id(),
        pedagogical_day=NOW.date(),
        budget_minutes=20,
        target_refs=("grammar:near_future",),
        primitive_ids=("EX-RECALL-01", "EX-TRANSFORM-01"),
        modalities=("writing",),
        challenge="matched",
        allow_novelty=False,
    )

    plan = await service.compose_free(
        ACCOUNT_ID,
        PROFILE_ID,
        command,
        idempotency_key="free-plan",
        context=context(),
    )
    ready = await service.prepare(
        ACCOUNT_ID,
        plan.plan_id,
        expected_version=plan.version,
        idempotency_key="prepare-free",
        context=context(),
    )
    run = await service.start_run(
        ACCOUNT_ID,
        ready.plan_id,
        StartSprintRun(new_id()),
        idempotency_key="start-free",
        context=context(),
    )

    assert run.plan_kind == "free"
    assert run.consumes_module_day is False
    enrollment_count = await migration_session.scalar(
        text("SELECT count(*) FROM curriculum.module_enrollments")
    )
    assert enrollment_count == 0
    assert PACK_REVISION_ID is not None


async def test_free_practice_never_silently_drops_an_unavailable_primitive(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_sprint_dependencies(migration_session)
    await migration_session.commit()

    with pytest.raises(DomainError) as rejected:
        await sprint_service(runtime_factory).compose_free(
            ACCOUNT_ID,
            PROFILE_ID,
            ComposeFreePractice(
                plan_id=new_id(),
                snapshot_id=new_id(),
                pedagogical_day=NOW.date(),
                budget_minutes=20,
                target_refs=("lexicon:review",),
                primitive_ids=("EX-RECALL-01", "EX-DISC-02"),
                modalities=("reading",),
                challenge="matched",
                allow_novelty=False,
            ),
            idempotency_key="free-missing-primitive",
            context=context(),
        )

    assert rejected.value.code is ErrorCode.PRIMITIVE_UNKNOWN


async def test_daily_composition_without_enrollment_returns_foundation_session(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_sprint_dependencies(migration_session)
    await migration_session.commit()

    plan = await sprint_service(runtime_factory).compose_daily(
        ACCOUNT_ID,
        PROFILE_ID,
        ComposeDailySession(new_id(), new_id(), NOW.date(), 10),
        idempotency_key="foundation-without-enrollment",
        context=context(),
    )

    assert plan.plan_kind == "foundation"
    assert len(plan.blocks) <= 4
    families = {block.family for block in plan.blocks}
    assert {"recall_warmup", "grammar_toolbox", "transformation_gym"} <= families
    assert families & {"version_input", "listening"}


async def test_daily_snapshot_consumes_pending_personal_stack_injection(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_sprint_dependencies(migration_session)
    await migration_session.execute(
        text("SELECT set_config('app.user_id',:actor,true)"),
        {"actor": str(ACCOUNT_ID)},
    )
    await migration_session.execute(
        text(
            "INSERT INTO practice.practice_stacks "
            "(stack_id,profile_id,language_pack_revision_id,name,stack_kind,pedagogical_day,"
            "source_refs,member_count,checksum,created_at) VALUES "
            "(:stack,:profile,:pack,'Pile injectée','selection',NULL,'[]',1,:checksum,:now)"
        ),
        {
            "stack": uid(480),
            "profile": PROFILE_ID,
            "pack": PACK_REVISION_ID,
            "checksum": "a" * 64,
            "now": NOW,
        },
    )
    await migration_session.execute(
        text(
            "INSERT INTO practice.sprint_stack_injections "
            "(injection_id,profile_id,stack_id,status,requested_at,version) "
            "VALUES (:injection,:profile,:stack,'pending',:now,1)"
        ),
        {"injection": uid(481), "profile": PROFILE_ID, "stack": uid(480), "now": NOW},
    )
    await migration_session.commit()

    plan = await sprint_service(runtime_factory).compose_daily(
        ACCOUNT_ID,
        PROFILE_ID,
        ComposeDailySession(new_id(), new_id(), NOW.date(), 10),
        idempotency_key="daily-with-injected-stack",
        context=context(),
    )

    await migration_session.execute(
        text("SELECT set_config('app.user_id',:actor,true)"),
        {"actor": str(ACCOUNT_ID)},
    )
    snapshot_stack_ids = await migration_session.scalar(
        text(
            "SELECT word_bank_snapshot_ids FROM planning.planning_snapshots "
            "WHERE snapshot_id=:snapshot"
        ),
        {"snapshot": plan.snapshot_id},
    )
    injection = (
        await migration_session.execute(
            text(
                "SELECT status,consumed_by_plan_revision_id FROM practice.sprint_stack_injections "
                "WHERE injection_id=:injection"
            ),
            {"injection": uid(481)},
        )
    ).mappings().one()
    assert uid(480) in snapshot_stack_ids
    assert injection == {
        "status": "consumed",
        "consumed_by_plan_revision_id": plan.plan_revision_id,
    }
