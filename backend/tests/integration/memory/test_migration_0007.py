from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import ACCOUNT_A, NOW, PROFILE_A, seed_profiles, set_actor, uid

EXPECTED_TABLES = {
    "memory_prompts",
    "memory_schedule_states",
    "memory_reviews",
    "memory_schedule_resets",
    "memory_schedule_resumptions",
    "memory_prompt_lineages",
    "memory_command_receipts",
}


async def test_migration_creates_exact_memory_schema(migration_session: AsyncSession) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='memory'"
                )
            )
        ).scalars()
    )
    assert tables == EXPECTED_TABLES


async def test_personal_tables_have_forced_rls_and_owner_policies(
    migration_session: AsyncSession,
) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,count(p.polname) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "LEFT JOIN pg_policy p ON p.polrelid=c.oid "
                "WHERE n.nspname='memory' AND c.relkind='r' "
                "GROUP BY c.relname,c.relrowsecurity,c.relforcerowsecurity"
            )
        )
    ).all()
    protected = {name: (rls, forced, policies) for name, rls, forced, policies in rows}
    assert set(protected) == EXPECTED_TABLES
    assert all(value == (True, True, 1) for value in protected.values())


async def test_append_only_facts_reject_direct_update_and_delete(
    migration_session: AsyncSession,
) -> None:
    triggers = set(
        (
            await migration_session.execute(
                text(
                    "SELECT event_object_table || ':' || event_manipulation "
                    "FROM information_schema.triggers WHERE trigger_schema='memory'"
                )
            )
        ).scalars()
    )
    for table_name in (
        "memory_reviews",
        "memory_schedule_resets",
        "memory_schedule_resumptions",
        "memory_prompt_lineages",
    ):
        assert f"{table_name}:UPDATE" in triggers
        assert f"{table_name}:DELETE" in triggers


async def test_due_index_restrict_fks_and_runtime_grants(
    migration_session: AsyncSession,
) -> None:
    indexes = set(
        (
            await migration_session.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='memory'")
            )
        ).scalars()
    )
    delete_actions = set(
        (
            await migration_session.execute(
                text(
                        "SELECT confdeltype::text FROM pg_constraint constraint_row "
                    "JOIN pg_class table_row ON table_row.oid=constraint_row.conrelid "
                    "JOIN pg_namespace namespace_row ON namespace_row.oid=table_row.relnamespace "
                    "WHERE namespace_row.nspname='memory' AND constraint_row.contype='f'"
                )
            )
        ).scalars()
    )
    assert "ix_memory_due" in indexes
    assert delete_actions == {"r"}
    assert await migration_session.scalar(
        text(
            "SELECT has_table_privilege('polyglot_runtime','memory.memory_reviews','DELETE')"
        )
    ) is False
    assert await migration_session.scalar(
        text(
            "SELECT has_table_privilege("
            "'polyglot_runtime','memory.memory_schedule_states','UPDATE')"
        )
    ) is True


async def test_sql_constraints_reject_non_uuid7_and_invalid_retention(
    migration_session: AsyncSession,
) -> None:
    await seed_profiles(migration_session)
    await set_actor(migration_session, ACCOUNT_A)
    values = {
        "prompt": uuid4(),
        "profile": PROFILE_A,
        "target": uid(300),
        "revision": uid(301),
        "policy": uid(302),
        "now": NOW,
    }
    with pytest.raises(DBAPIError):
        await migration_session.execute(
            text(
                "INSERT INTO memory.memory_prompts "
                "(prompt_id,profile_id,target_ref,target_revision_id,direction,modality,operation,"
                "protocol_id,protocol_revision,rating_semantics_id,scheduler_policy_id,"
                "scheduler_kind,scheduler_version,parameter_set_id,policy_revision,status,"
                "version,created_at,updated_at) VALUES "
                "(:prompt,:profile,:target,:revision,'target_to_support','written','recall',"
                "'certified-recall-v1',1,'polyglot-recall-v1',:policy,'fsrs','6.3.1',"
                "'fsrs-6-default',1,'active',1,:now,:now)"
            ),
            values,
        )
    await migration_session.rollback()
    await seed_profiles(migration_session)
    await set_actor(migration_session, ACCOUNT_A)
    values["prompt"] = uid(310)
    await migration_session.execute(
        text(
            "INSERT INTO memory.memory_prompts "
            "(prompt_id,profile_id,target_ref,target_revision_id,direction,modality,operation,"
            "protocol_id,protocol_revision,rating_semantics_id,scheduler_policy_id,"
            "scheduler_kind,scheduler_version,parameter_set_id,policy_revision,status,"
            "version,created_at,updated_at) VALUES "
            "(:prompt,:profile,:target,:revision,'target_to_support','written','recall',"
            "'certified-recall-v1',1,'polyglot-recall-v1',:policy,'fsrs','6.3.1',"
            "'fsrs-6-default',1,'active',1,:now,:now)"
        ),
        values,
    )
    with pytest.raises(DBAPIError):
        await migration_session.execute(
            text(
                "INSERT INTO memory.memory_schedule_states "
                "(prompt_id,profile_id,scheduler_kind,scheduler_version,parameter_set_id,"
                "policy_revision,state,desired_retention,due_at,reps,lapses,projection_version,"
                "computed_at,causal_checkpoint) VALUES "
                "(:prompt,:profile,'fsrs','6.3.1','fsrs-6-default',1,'new',0.99,:now,0,0,1,"
                ":now,'created:invalid')"
            ),
            values,
        )
