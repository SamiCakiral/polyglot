from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polyglot.bootstrap.database import (
    database_url_from_environment,
    migration_database_url_from_environment,
)
from polyglot.modules.exercises.core.domain import AnswerKind, ExerciseDefinition

NOW = datetime(2026, 8, 10, 16, 0, tzinfo=UTC)


def uid(value: int) -> UUID:
    return UUID(f"019fed00-0000-7000-8000-{value:012x}")


ACCOUNT_ID = uid(1)
OTHER_ACCOUNT_ID = uid(2)
PROFILE_ID = uid(3)
PROVENANCE_ID = uid(4)
PACK_REVISION_ID = uid(7)
GRAMMAR_REVISION_ID = uid(10)
SNAPSHOT_ID = uid(13)
DEFINITION_REVISION_ID = uid(16)
INSTANCE_ID = uid(17)
PLAN_ID = uid(18)
PLAN_REVISION_ID = uid(19)
CYCLE_ID = uid(21)


def domain_definition() -> ExerciseDefinition:
    return ExerciseDefinition.published(
        definition_id=uid(15),
        revision_id=DEFINITION_REVISION_ID,
        revision_no=1,
        primitive_id="EX-TRANSFORM-01",
        response_kinds=(AnswerKind.TEXT,),
        language_certification_ids=(uid(34),),
        modes=("gym",),
        target_weights=(("grammar:vorrei", 0.65),),
        correction_policy_id="gym:v1",
        hint_policy_id="gym-hint:v1",
        observation_policy_id="gym-observation:v1",
        accessibility_features=("keyboard", "screen_reader", "untimed"),
    )


async def seed_gym_dependencies(session: AsyncSession) -> None:
    for account_id in (ACCOUNT_ID, OTHER_ACCOUNT_ID):
        await session.execute(
            text(
                "INSERT INTO identity.accounts "
                "(account_id,status,security_version,session_version,version,created_at,"
                "security_last_activity_at) VALUES "
                "(:account,'active',1,1,1,:now,:now) ON CONFLICT DO NOTHING"
            ),
            {"account": account_id, "now": NOW},
        )
    await session.execute(
        text(
            "INSERT INTO language_profiles.learner_language_profiles "
            "(profile_id,account_id,target_variety_id,native_variety_id,status,current_phase,"
            "goals,interests,excluded_themes,correction_preference,availability_pattern,"
            "version,created_at,updated_at) VALUES "
            "(:profile,:account,:target,:native,'active','module_learning','[]','[]','[]',"
            "'{}','{}',1,:now,:now) ON CONFLICT DO NOTHING"
        ),
        {
            "profile": PROFILE_ID,
            "account": ACCOUNT_ID,
            "target": uid(30),
            "native": uid(31),
            "now": NOW,
        },
    )
    await session.execute(
        text("SELECT set_config('app.user_id',:actor,false)"),
        {"actor": str(ACCOUNT_ID)},
    )
    await session.execute(
        text(
            "INSERT INTO platform.provenance_records "
            "(provenance_id,source_type,source_ref,transformation_chain,input_fingerprint,"
            "created_at) VALUES (:id,'test','FX-GYM-DB','[]',:fingerprint,:now) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": PROVENANCE_ID, "fingerprint": "a" * 64, "now": NOW},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_varieties "
            "(variety_id,language_tag,script_codes,text_direction,"
            "segmentation_policy_revision_id,media_capabilities,normalization_policy_revision_id) "
            "VALUES (:id,'it-IT-gym',ARRAY['Latn'],'ltr',:segmentation,"
            "CAST(:media AS jsonb),:normalization) ON CONFLICT DO NOTHING"
        ),
        {
            "id": uid(5),
            "segmentation": uid(32),
            "media": '{"schema_version":1}',
            "normalization": uid(33),
        },
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_packs (pack_id,pack_code) "
            "VALUES (:id,'it.gym.test') ON CONFLICT DO NOTHING"
        ),
        {"id": uid(6)},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_pack_revisions "
            "(pack_revision_id,pack_id,revision_no,target_variety_id,status,engine_min_version,"
            "engine_max_version,capability_manifest,checksum_manifest,license_refs,"
            "provenance_id) VALUES "
            "(:revision,:pack,1,:variety,'draft','2.0.0','2.0.0',CAST(:capabilities AS jsonb),"
            "CAST(:checksums AS jsonb),ARRAY['test'],:provenance) "
            "ON CONFLICT DO NOTHING"
        ),
        {
            "revision": PACK_REVISION_ID,
            "pack": uid(6),
            "variety": uid(5),
            "provenance": PROVENANCE_ID,
            "capabilities": '{"schema_version":1}',
            "checksums": '{"fixture":"pinned"}',
        },
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.skills (skill_id,skill_code) "
            "VALUES (:id,'it.gym.polite_request') ON CONFLICT DO NOTHING"
        ),
        {"id": uid(8)},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.grammar_structures "
            "(structure_id,structure_code,function_skill_id) "
            "VALUES (:id,'it.gym.vorrei',:skill) ON CONFLICT DO NOTHING"
        ),
        {"id": uid(9), "skill": uid(8)},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.grammar_structure_revisions "
            "(structure_revision_id,structure_id,pack_revision_id,revision_no,constraints,"
            "contrasts,typical_errors,variants,status,provenance_id) VALUES "
            "(:revision,:structure,:pack,1,'{}','[]','[]','[]','draft',:provenance) "
            "ON CONFLICT DO NOTHING"
        ),
        {
            "revision": GRAMMAR_REVISION_ID,
            "structure": uid(9),
            "pack": PACK_REVISION_ID,
            "provenance": PROVENANCE_ID,
        },
    )
    await session.execute(
        text(
            "INSERT INTO lexicon.vocabulary_lists "
            "(list_id,profile_id,variety_id,list_type,status,version,created_at,updated_at) "
            "VALUES (:list,:profile,:variety,'manual','active',1,:now,:now) "
            "ON CONFLICT DO NOTHING"
        ),
        {"list": uid(11), "profile": PROFILE_ID, "variety": uid(5), "now": NOW},
    )
    await session.execute(
        text(
            "INSERT INTO lexicon.vocabulary_list_revisions "
            "(list_revision_id,list_id,profile_id,revision_no,name,purpose,ordered,tags,"
            "provenance_id,created_at) VALUES "
            "(:revision,:list,:profile,1,'Gym support','Pinned lexical support',false,'[]',"
            ":provenance,:now) ON CONFLICT DO NOTHING"
        ),
        {
            "revision": uid(12),
            "list": uid(11),
            "profile": PROFILE_ID,
            "provenance": PROVENANCE_ID,
            "now": NOW,
        },
    )
    await session.execute(
        text(
            "UPDATE lexicon.vocabulary_lists SET current_revision_id=:revision "
            "WHERE list_id=:list"
        ),
        {"revision": uid(12), "list": uid(11)},
    )
    await session.execute(
        text(
            "INSERT INTO lexicon.list_snapshots "
            "(snapshot_id,list_id,profile_id,source_revision_id,created_at,checksum) "
            "VALUES (:snapshot,:list,:profile,:revision,:now,:checksum) ON CONFLICT DO NOTHING"
        ),
        {
            "snapshot": SNAPSHOT_ID,
            "list": uid(11),
            "profile": PROFILE_ID,
            "revision": uid(12),
            "now": NOW,
            "checksum": "b" * 64,
        },
    )
    await session.execute(
        text(
            "INSERT INTO exercises.exercise_definitions "
            "(definition_id,definition_code,status,version,created_at,updated_at) VALUES "
            "(:definition,'gym.transform.01','published',1,:now,:now) ON CONFLICT DO NOTHING"
        ),
        {"definition": uid(15), "now": NOW},
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
            "(:revision,:definition,1,1,'EX-TRANSFORM-01','published','[\"text\"]','[]',"
            "'[\"gym\"]','[[\"grammar\",1.0]]','{}','{}','[]','{}','[]','gym:v1',"
            "'gym-hint:v1','gym-observation:v1','[\"keyboard\"]',1000,2000,3000,'[]',"
            ":provenance,:now) ON CONFLICT DO NOTHING"
        ),
        {
            "revision": DEFINITION_REVISION_ID,
            "definition": uid(15),
            "provenance": PROVENANCE_ID,
            "now": NOW,
        },
    )
    await session.execute(
        text(
            "UPDATE exercises.exercise_definitions SET current_revision_id=:revision "
            "WHERE definition_id=:definition"
        ),
        {"revision": DEFINITION_REVISION_ID, "definition": uid(15)},
    )
    await session.execute(
        text(
            "INSERT INTO exercises.exercise_instances "
            "(instance_id,standalone_profile_id,definition_revision_id,language_pack_revision_id,"
            "seed,stimulus_revision_ids,target_bindings,lexical_bindings,grammar_bindings,"
            "provenance_id,created_at) VALUES "
            "(:instance,:profile,:revision,:pack,42,'[\"019fed00-0000-7000-8000-000000000022\"]',"
            "'[]','[]','[]',:provenance,:now) ON CONFLICT DO NOTHING"
        ),
        {
            "instance": INSTANCE_ID,
            "profile": PROFILE_ID,
            "revision": DEFINITION_REVISION_ID,
            "pack": PACK_REVISION_ID,
            "provenance": PROVENANCE_ID,
            "now": NOW,
        },
    )


@pytest.fixture
async def migration_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migration_database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.fixture
async def runtime_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url_from_environment())
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_gym_storage() -> AsyncIterator[None]:
    async def clean() -> None:
        engine = create_async_engine(migration_database_url_from_environment())
        async with engine.begin() as connection:
            exists = await connection.scalar(
                text("SELECT to_regclass('exercises.gym_plans') IS NOT NULL")
            )
            if exists:
                await connection.execute(
                    text(
                        "TRUNCATE exercises.gym_cycle_records,"
                        "exercises.gym_cycle_requirements,exercises.gym_cycles,"
                        "exercises.gym_steps,exercises.gym_plan_revisions,"
                        "exercises.gym_plans CASCADE"
                    )
                )
        await engine.dispose()

    await clean()
    yield
    await clean()
