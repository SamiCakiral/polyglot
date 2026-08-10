from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from polyglot.modules.exercises.core.domain import ExerciseInstance
from polyglot.modules.exercises.gym.persistence import SqlGymPlanRepository
from polyglot.modules.exercises.gym.planning import GymPlan, GymStep

from .conftest import (
    ACCOUNT_ID,
    GRAMMAR_REVISION_ID,
    INSTANCE_ID,
    NOW,
    PACK_REVISION_ID,
    PLAN_ID,
    PLAN_REVISION_ID,
    PROFILE_ID,
    PROVENANCE_ID,
    SNAPSHOT_ID,
    domain_definition,
    seed_gym_dependencies,
    uid,
)


async def test_sql_repository_persists_plan_and_ordered_steps_through_rls(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_gym_dependencies(migration_session)
    await migration_session.commit()
    instance = ExerciseInstance.create(
        instance_id=INSTANCE_ID,
        definition=domain_definition(),
        language_pack_revision_id=PACK_REVISION_ID,
        seed=42,
        stimulus_revision_ids=(uid(22),),
    )
    plan = GymPlan(
        plan_id=PLAN_ID,
        revision_id=PLAN_REVISION_ID,
        profile_id=PROFILE_ID,
        grammar_target_revision_id=GRAMMAR_REVISION_ID,
        policy_revision_id=uid(20),
        language_pack_revision_id=PACK_REVISION_ID,
        lexical_support_snapshot_id=SNAPSHOT_ID,
        seed=42,
        invariants=("polite_request",),
        exit_evidence_spec="g1_complete",
        steps=(GymStep(1, "it:vorrei", "it:vorrei:v1", "GYM-01", 42, instance),),
    )

    await SqlGymPlanRepository(runtime_factory).add(
        ACCOUNT_ID,
        plan,
        provenance_id=PROVENANCE_ID,
        created_at=NOW,
    )

    async with runtime_factory() as session:
        await session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"),
            {"actor": str(ACCOUNT_ID)},
        )
        row = (
            (
                await session.execute(
                    text(
                        "SELECT plan.current_revision_id,revision.seed,step.ordinal,"
                        "step.case_revision_ref,step.gym_operation,step.instance_id "
                        "FROM exercises.gym_plans plan "
                        "JOIN exercises.gym_plan_revisions revision "
                        "ON revision.gym_plan_id=plan.gym_plan_id "
                        "JOIN exercises.gym_steps step "
                        "ON step.gym_plan_revision_id=revision.gym_plan_revision_id "
                        "WHERE plan.gym_plan_id=:plan"
                    ),
                    {"plan": PLAN_ID},
                )
            )
            .tuples()
            .one()
        )
    assert row == (PLAN_REVISION_ID, 42, 1, "it:vorrei:v1", "GYM-01", INSTANCE_ID)
