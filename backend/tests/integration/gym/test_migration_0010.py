from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .conftest import (
    ACCOUNT_ID,
    CYCLE_ID,
    DEFINITION_REVISION_ID,
    GRAMMAR_REVISION_ID,
    INSTANCE_ID,
    NOW,
    OTHER_ACCOUNT_ID,
    PACK_REVISION_ID,
    PLAN_ID,
    PLAN_REVISION_ID,
    PROFILE_ID,
    PROVENANCE_ID,
    SNAPSHOT_ID,
    seed_gym_dependencies,
    uid,
)

EXPECTED_TABLES = {
    "gym_plans",
    "gym_plan_revisions",
    "gym_steps",
    "gym_cycles",
    "gym_cycle_requirements",
    "gym_cycle_records",
}


async def test_migration_creates_versioned_gym_storage(
    migration_session: AsyncSession,
) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='exercises' AND table_name LIKE 'gym_%'"
                )
            )
        ).scalars()
    )

    assert tables == EXPECTED_TABLES


async def test_gym_tables_force_profile_owner_rls(migration_session: AsyncSession) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,count(p.polname) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "LEFT JOIN pg_policy p ON p.polrelid=c.oid "
                "WHERE n.nspname='exercises' AND c.relname=ANY(:tables) "
                "GROUP BY c.relname,c.relrowsecurity,c.relforcerowsecurity"
            ),
            {"tables": sorted(EXPECTED_TABLES)},
        )
    ).all()

    assert {row[0] for row in rows} == EXPECTED_TABLES
    assert all(row[1] is True and row[2] is True and row[3] >= 1 for row in rows)


async def test_gym_revisions_steps_and_cycle_facts_are_append_only(
    migration_session: AsyncSession,
) -> None:
    guarded = set(
        (
            await migration_session.execute(
                text(
                    "SELECT event_object_table || ':' || event_manipulation "
                    "FROM information_schema.triggers "
                    "WHERE trigger_schema='exercises' AND event_object_table LIKE 'gym_%'"
                )
            )
        ).scalars()
    )

    for table in {
        "gym_plan_revisions",
        "gym_steps",
        "gym_cycle_requirements",
        "gym_cycle_records",
    }:
        assert f"{table}:UPDATE" in guarded
        assert f"{table}:DELETE" in guarded


async def test_gym_storage_pins_versioned_cross_module_references(
    migration_session: AsyncSession,
) -> None:
    foreign_keys = set(
        (
            await migration_session.execute(
                text(
                    "SELECT tc.table_name,kcu.column_name,ccu.table_schema,"
                    "ccu.table_name,ccu.column_name "
                    "FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kcu "
                    "ON tc.constraint_name=kcu.constraint_name "
                    "AND tc.constraint_schema=kcu.constraint_schema "
                    "JOIN information_schema.constraint_column_usage ccu "
                    "ON ccu.constraint_name=tc.constraint_name "
                    "AND ccu.constraint_schema=tc.constraint_schema "
                    "WHERE tc.constraint_type='FOREIGN KEY' "
                    "AND tc.table_schema='exercises' AND tc.table_name LIKE 'gym_%'"
                )
            )
        ).tuples()
    )

    assert (
        "gym_plan_revisions",
        "grammar_target_revision_id",
        "catalogue",
        "grammar_structure_revisions",
        "structure_revision_id",
    ) in foreign_keys
    assert (
        "gym_plan_revisions",
        "lexical_support_snapshot_id",
        "lexicon",
        "list_snapshots",
        "snapshot_id",
    ) in foreign_keys
    assert (
        "gym_steps",
        "instance_id",
        "exercises",
        "exercise_instances",
        "instance_id",
    ) in foreign_keys


async def test_runtime_has_no_delete_surface_on_gym_storage(
    migration_session: AsyncSession,
) -> None:
    privileges = (
        await migration_session.execute(
            text(
                "SELECT table_name,has_table_privilege("
                "'polyglot_runtime','exercises.' || table_name,'DELETE') "
                "FROM information_schema.tables "
                "WHERE table_schema='exercises' AND table_name=ANY(:tables)"
            ),
            {"tables": sorted(EXPECTED_TABLES)},
        )
    ).all()

    assert {row[0] for row in privileges} == EXPECTED_TABLES
    assert all(row[1] is False for row in privileges)


async def test_plan_cycle_and_evidence_are_persisted_without_rewriting_facts(
    migration_session: AsyncSession,
    runtime_factory: async_sessionmaker[AsyncSession],
) -> None:
    await seed_gym_dependencies(migration_session)
    await migration_session.execute(
        text(
            "INSERT INTO exercises.gym_plans "
            "(gym_plan_id,profile_id,status,version,created_at,updated_at) "
            "VALUES (:plan,:profile,'ready',1,:now,:now)"
        ),
        {"plan": PLAN_ID, "profile": PROFILE_ID, "now": NOW},
    )
    await migration_session.execute(
        text(
            "INSERT INTO exercises.gym_plan_revisions "
            "(gym_plan_revision_id,gym_plan_id,profile_id,revision_no,"
            "grammar_target_revision_id,policy_revision_id,language_pack_revision_id,"
            "lexical_support_snapshot_id,seed,invariants,exit_evidence_spec,provenance_id,"
            "created_at) VALUES "
            "(:revision,:plan,:profile,1,:grammar,:policy,:pack,:snapshot,42,"
            "'[\"polite_request\"]',CAST(:exit_spec AS jsonb),:provenance,:now)"
        ),
        {
            "revision": PLAN_REVISION_ID,
            "plan": PLAN_ID,
            "profile": PROFILE_ID,
            "grammar": GRAMMAR_REVISION_ID,
            "policy": uid(20),
            "pack": PACK_REVISION_ID,
            "snapshot": SNAPSHOT_ID,
            "exit_spec": '{"stage":"g4"}',
            "provenance": PROVENANCE_ID,
            "now": NOW,
        },
    )
    await migration_session.execute(
        text(
            "UPDATE exercises.gym_plans SET current_revision_id=:revision "
            "WHERE gym_plan_id=:plan"
        ),
        {"revision": PLAN_REVISION_ID, "plan": PLAN_ID},
    )
    await migration_session.execute(
        text(
            "INSERT INTO exercises.gym_steps "
            "(gym_step_id,gym_plan_revision_id,gym_plan_id,profile_id,ordinal,"
            "case_revision_ref,gym_operation,instance_id,instance_seed,created_at) VALUES "
            "(:step,:revision,:plan,:profile,1,'it:vorrei:v1','GYM-01',:instance,42,:now)"
        ),
        {
            "step": uid(23),
            "revision": PLAN_REVISION_ID,
            "plan": PLAN_ID,
            "profile": PROFILE_ID,
            "instance": INSTANCE_ID,
            "now": NOW,
        },
    )
    await migration_session.execute(
        text(
            "INSERT INTO exercises.gym_cycles "
            "(gym_cycle_id,profile_id,gym_plan_revision_id,grammar_target_revision_id,"
            "stage,completed,started_at,completed_g1_requirement_ids,version,updated_at) "
            "VALUES (:cycle,:profile,:revision,:grammar,'g0',false,:now,'[]',1,:now)"
        ),
        {
            "cycle": CYCLE_ID,
            "profile": PROFILE_ID,
            "revision": PLAN_REVISION_ID,
            "grammar": GRAMMAR_REVISION_ID,
            "now": NOW,
        },
    )
    await migration_session.execute(
        text(
            "INSERT INTO exercises.gym_cycle_requirements "
            "(gym_cycle_requirement_id,gym_cycle_id,profile_id,requirement_id,"
            "requirement_kind,definition_revision_id,created_at) VALUES "
            "(:id,:cycle,:profile,'g1:transform','transformation',:definition,:now)"
        ),
        {
            "id": uid(24),
            "cycle": CYCLE_ID,
            "profile": PROFILE_ID,
            "definition": DEFINITION_REVISION_ID,
            "now": NOW,
        },
    )
    await migration_session.execute(
        text(
            "INSERT INTO exercises.gym_cycle_records "
            "(gym_cycle_record_id,gym_cycle_id,profile_id,ordinal,stage,verdict,hint_level,"
            "context_id,scene_id,structure_cued,credit,is_evidence,idempotency_key,"
            "request_fingerprint,recorded_at) VALUES "
            "(:id,:cycle,:profile,1,'g0','correct',4,'intro','intro',true,0,false,"
            "'gym:g0',:fingerprint,:now)"
        ),
        {
            "id": uid(25),
            "cycle": CYCLE_ID,
            "profile": PROFILE_ID,
            "fingerprint": "c" * 64,
            "now": NOW,
        },
    )

    assert await migration_session.scalar(
        text("SELECT count(*) FROM exercises.gym_steps WHERE gym_plan_revision_id=:revision"),
        {"revision": PLAN_REVISION_ID},
    ) == 1
    await migration_session.commit()

    async with runtime_factory() as owner_session:
        await owner_session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"),
            {"actor": str(ACCOUNT_ID)},
        )
        assert await owner_session.scalar(
            text("SELECT count(*) FROM exercises.gym_plans WHERE gym_plan_id=:plan"),
            {"plan": PLAN_ID},
        ) == 1
    async with runtime_factory() as other_session:
        await other_session.execute(
            text("SELECT set_config('app.user_id',:actor,true)"),
            {"actor": str(OTHER_ACCOUNT_ID)},
        )
        assert await other_session.scalar(
            text("SELECT count(*) FROM exercises.gym_plans WHERE gym_plan_id=:plan"),
            {"plan": PLAN_ID},
        ) == 0

    with pytest.raises(DBAPIError, match="exercise fact is append-only"):
        await migration_session.execute(
            text(
                "UPDATE exercises.gym_cycle_records SET context_id='rewritten' "
                "WHERE gym_cycle_id=:cycle"
            ),
            {"cycle": CYCLE_ID},
        )
