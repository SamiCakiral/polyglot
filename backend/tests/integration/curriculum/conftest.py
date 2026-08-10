from __future__ import annotations

# ruff: noqa: E501
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

NOW = datetime(2026, 8, 10, 10, 0, tzinfo=UTC)


def uid(suffix: int) -> UUID:
    return UUID(f"019fe114-0000-7000-8000-{suffix:012d}")


ACCOUNT_ID = uid(1)
OTHER_ACCOUNT_ID = uid(2)
PROFILE_ID = uid(3)
OTHER_PROFILE_ID = uid(4)
TARGET_VARIETY_ID = uid(5)
SUPPORT_VARIETY_ID = uid(6)
PACK_ID = uid(7)
PACK_REVISION_ID = uid(8)
PROVENANCE_ID = uid(9)
MODULE_ID = uid(10)
MODULE_REVISION_ID = uid(11)
SUCCESSOR_REVISION_ID = uid(12)


async def seed_curriculum_dependencies(session: AsyncSession) -> None:
    await session.execute(
        text(
            "INSERT INTO identity.accounts "
            "(account_id,status,security_version,session_version,version,created_at,security_last_activity_at) "
            "VALUES (:owner,'active',1,1,1,:now,:now),(:other,'active',1,1,1,:now,:now) "
            "ON CONFLICT DO NOTHING"
        ),
        {"owner": ACCOUNT_ID, "other": OTHER_ACCOUNT_ID, "now": NOW},
    )
    for variety_id, tag in (
        (TARGET_VARIETY_ID, "it-IT"),
        (SUPPORT_VARIETY_ID, "fr-FR"),
    ):
        await session.execute(
            text(
                "INSERT INTO catalogue.language_varieties "
                "(variety_id,language_tag,script_codes,text_direction,segmentation_policy_revision_id,"
                "media_capabilities,normalization_policy_revision_id) VALUES "
                "(:id,:tag,ARRAY['Latn'],'ltr',:segmentation,CAST(:media AS jsonb),:normalization) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "id": variety_id,
                "tag": tag,
                "segmentation": uid(20 + (1 if tag == "it-IT" else 2)),
                "media": '{"schema_version":1}',
                "normalization": uid(30 + (1 if tag == "it-IT" else 2)),
            },
        )
    await session.execute(
        text(
            "INSERT INTO platform.provenance_records "
            "(provenance_id,source_type,source_ref,transformation_chain,input_fingerprint,created_at) "
            "VALUES (:id,'project_authored','FX-MODULE-IT','[]',:fingerprint,:now) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": PROVENANCE_ID, "fingerprint": "a" * 64, "now": NOW},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_packs (pack_id,pack_code) "
            "VALUES (:id,'it-core') ON CONFLICT DO NOTHING"
        ),
        {"id": PACK_ID},
    )
    await session.execute(
        text(
            "INSERT INTO catalogue.language_pack_revisions "
            "(pack_revision_id,pack_id,revision_no,target_variety_id,status,engine_min_version,"
            "engine_max_version,capability_manifest,checksum_manifest,license_refs,provenance_id,published_at) "
            "VALUES (:revision,:pack,1,:target,'published','2.0.0','2.99.0',"
            "CAST(:capabilities AS jsonb),CAST(:checksums AS jsonb),ARRAY['project-authored'],"
            ":provenance,:now) ON CONFLICT DO NOTHING"
        ),
        {
            "revision": PACK_REVISION_ID,
            "pack": PACK_ID,
            "target": TARGET_VARIETY_ID,
            "capabilities": '{"schema_version":1}',
            "checksums": '{"module":"sha256:test"}',
            "provenance": PROVENANCE_ID,
            "now": NOW,
        },
    )
    for profile_id, account_id in (
        (PROFILE_ID, ACCOUNT_ID),
        (OTHER_PROFILE_ID, OTHER_ACCOUNT_ID),
    ):
        await session.execute(
            text(
                "INSERT INTO language_profiles.learner_language_profiles "
                "(profile_id,account_id,target_variety_id,native_variety_id,status,current_phase,"
                "goals,interests,excluded_themes,correction_preference,availability_pattern,version,"
                "created_at,updated_at) VALUES "
                "(:profile,:account,:target,:support,'active','module_learning','[]','[]','[]',"
                "CAST(:correction AS jsonb),CAST(:availability AS jsonb),1,:now,:now) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "profile": profile_id,
                "account": account_id,
                "target": TARGET_VARIETY_ID,
                "support": SUPPORT_VARIETY_ID,
                "correction": '{"mode":"balanced"}',
                "availability": '{"minutes":30}',
                "now": NOW,
            },
        )
    await session.execute(
        text(
            "INSERT INTO curriculum.learning_modules "
            "(module_id,module_code,pack_id,editorial_owner_id,status,version,created_at,updated_at) "
            "VALUES (:module,'IT-FIRST-AUTONOMOUS-EXCHANGE',:pack,:owner,'published',1,:now,:now)"
        ),
        {"module": MODULE_ID, "pack": PACK_ID, "owner": ACCOUNT_ID, "now": NOW},
    )
    await insert_module_revision(session, MODULE_REVISION_ID, 1)
    await session.execute(
        text(
            "UPDATE curriculum.learning_modules SET current_revision_id=:revision "
            "WHERE module_id=:module"
        ),
        {"revision": MODULE_REVISION_ID, "module": MODULE_ID},
    )


async def insert_module_revision(
    session: AsyncSession,
    revision_id: UUID,
    revision_no: int,
    *,
    supersedes_revision_id: UUID | None = None,
) -> None:
    await session.execute(
        text(
            "INSERT INTO curriculum.module_revisions "
            "(module_revision_id,module_id,revision_no,status,pack_revision_id,target_variety_id,"
            "support_variety_ids,primary_intention,final_mission_revision_id,entry_profile_codes,"
            "nominal_days,max_days,min_minutes,max_minutes,prerequisite_skill_revision_ids,"
            "target_skill_revision_ids,lexicon_set_revision_ids,exit_policy_revision_id,"
            "recall_policy_revision_id,provenance_ref,rights_refs,validator_set_revision_id,"
            "schema_version,compatibility_range,reference_manifest_checksum,supersedes_revision_id,"
            "payload_checksum,created_at) VALUES "
            "(:revision,:module,:number,'published',:pack,:target,ARRAY[:support]::uuid[],"
            "'complete a first autonomous exchange',:mission,ARRAY['P-ABS'],3,3,10,60,ARRAY[]::uuid[],"
            "ARRAY[:skill]::uuid[],ARRAY[]::uuid[],:exit_policy,:recall_policy,'FX-MODULE-IT',"
            "ARRAY['project-authored'],:validators,1,'>=2,<3',:manifest,:supersedes,:checksum,:now)"
        ),
        {
            "revision": revision_id,
            "module": MODULE_ID,
            "number": revision_no,
            "pack": PACK_REVISION_ID,
            "target": TARGET_VARIETY_ID,
            "support": SUPPORT_VARIETY_ID,
            "mission": uid(40 + revision_no),
            "skill": uid(50 + revision_no),
            "exit_policy": uid(60 + revision_no),
            "recall_policy": uid(70 + revision_no),
            "validators": uid(80 + revision_no),
            "manifest": f"sha256:{revision_no:064x}",
            "supersedes": supersedes_revision_id,
            "checksum": f"sha256:{(revision_no + 10):064x}",
            "now": NOW,
        },
    )
    for ordinal, arc, novelty in (
        (1, "discovery", 4),
        (2, "guided_use", 3),
        (3, "transfer", 0),
    ):
        target = f"skill:{ordinal}"
        await session.execute(
            text(
                "INSERT INTO curriculum.module_days "
                "(module_day_id,module_revision_id,ordinal,arc_type,objective_codes,modality_objectives,"
                "primary_target_refs,secondary_target_refs,encountered_target_refs,output_target_refs,"
                "content_revision_ids,exercise_definition_revision_ids,context_revision_ids,target_bindings,"
                "recall_specs,recall_source_day_ordinals,minimum_useful_minutes,novelty_budget,"
                "required_block_roles,new_grammar_family_codes,explained_grammar_family_codes,"
                "gym_grammar_family_codes,fallback_revision_ids,final_output_spec,validator_revision_ids,"
                "prerequisite_day_ordinals,payload_checksum,created_at) VALUES "
                "(:day,:revision,:ordinal,:arc,ARRAY[:objective],CAST(:modalities AS jsonb),ARRAY[:target],"
                "ARRAY[]::varchar[],ARRAY[:target],ARRAY[:target],ARRAY[]::uuid[],ARRAY[]::uuid[],"
                "ARRAY[]::uuid[],CAST(:bindings AS jsonb),'[]',ARRAY[]::smallint[],10,:novelty,"
                "ARRAY['explanation','practice','production'],ARRAY[]::varchar[],ARRAY[]::varchar[],"
                "ARRAY[]::varchar[],ARRAY[]::uuid[],'',ARRAY[]::uuid[],ARRAY[]::smallint[],:checksum,:now)"
            ),
            {
                "day": uid(100 + revision_no * 10 + ordinal),
                "revision": revision_id,
                "ordinal": ordinal,
                "arc": arc,
                "objective": f"objective-{ordinal}",
                "modalities": '[["written_production","produce"]]',
                "target": target,
                "bindings": "{}",
                "novelty": novelty,
                "checksum": f"sha256:{(revision_no * 10 + ordinal):064x}",
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
async def clean_curriculum_storage() -> AsyncIterator[None]:
    async def clean() -> None:
        engine = create_async_engine(migration_database_url_from_environment())
        async with engine.begin() as connection:
            exists = await connection.scalar(
                text("SELECT to_regclass('curriculum.learning_modules') IS NOT NULL")
            )
            if exists:
                tables = tuple(
                    (
                        await connection.execute(
                            text(
                                "SELECT table_name FROM information_schema.tables "
                                "WHERE table_schema='curriculum'"
                            )
                        )
                    ).scalars()
                )
                if tables:
                    qualified = ",".join(f'curriculum."{table}"' for table in tables)
                    await connection.execute(text(f"TRUNCATE {qualified} CASCADE"))
        await engine.dispose()

    await clean()
    yield
    await clean()
