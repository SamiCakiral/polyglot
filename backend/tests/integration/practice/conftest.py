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

NOW = datetime(2026, 8, 11, 9, 0, tzinfo=UTC)
ACCOUNT_ID = UUID("019fec10-0000-7000-8000-000000000001")
PROFILE_ID = UUID("019fec10-0000-7000-8000-000000000002")
PROVENANCE_ID = UUID("019fec10-0000-7000-8001-000000000001")
TARGET_VARIETY_ID = UUID("019fec10-0000-7000-8002-000000000001")
SUPPORT_VARIETY_ID = UUID("019fec10-0000-7000-8002-000000000002")
PACK_ID = UUID("019fec10-0000-7000-8003-000000000001")
PACK_REVISION_ID = UUID("019fec10-0000-7000-8003-000000000002")


@pytest.fixture
async def migration_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migration_database_url_from_environment())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_practice_database() -> AsyncIterator[None]:
    engine = create_async_engine(migration_database_url_from_environment())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE practice.practice_stacks,practice.practice_presets CASCADE"
            )
        )
        await connection.execute(text("TRUNCATE platform.command_receipts CASCADE"))
        await connection.execute(text("TRUNCATE platform.domain_events CASCADE"))
        await connection.execute(text("TRUNCATE platform.outbox_messages CASCADE"))
        await connection.execute(
            text(
                "DELETE FROM language_profiles.learner_language_profiles WHERE profile_id=:profile"
            ),
            {"profile": PROFILE_ID},
        )
        await connection.execute(
            text("DELETE FROM identity.accounts WHERE account_id=:account"),
            {"account": ACCOUNT_ID},
        )
    await engine.dispose()
    yield


async def _seed_catalogue(connection) -> tuple[tuple[UUID, UUID, str, str], ...]:
    await connection.execute(
        text(
            "INSERT INTO platform.provenance_records "
            "(provenance_id,source_type,source_ref,transformation_chain,input_fingerprint,"
            "created_at) VALUES (:id,'project_authored','practice-test','[]',:fingerprint,:now) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": PROVENANCE_ID, "fingerprint": "b" * 64, "now": NOW},
    )
    for index, (variety_id, tag) in enumerate(
        ((TARGET_VARIETY_ID, "zz-TT"), (SUPPORT_VARIETY_ID, "yy-YY")), 1
    ):
        await connection.execute(
            text(
                "INSERT INTO catalogue.language_varieties "
                "(variety_id,language_tag,script_codes,text_direction,"
                "segmentation_policy_revision_id,media_capabilities,"
                "normalization_policy_revision_id) VALUES "
                "(:id,:tag,ARRAY['Latn'],'ltr',:segmentation,"
                "CAST(:media AS jsonb),:normalization) ON CONFLICT DO NOTHING"
            ),
            {
                "id": variety_id,
                "tag": tag,
                "segmentation": UUID(f"019fec10-0000-7000-8004-{index:012x}"),
                "normalization": UUID(f"019fec10-0000-7000-8005-{index:012x}"),
                "media": '{"schema_version":1}',
            },
        )
    await connection.execute(
        text(
            "INSERT INTO catalogue.language_packs (pack_id,pack_code) "
            "VALUES (:id,'practice-test-pack') ON CONFLICT DO NOTHING"
        ),
        {"id": PACK_ID},
    )
    await connection.execute(
        text(
            "INSERT INTO catalogue.language_pack_revisions "
            "(pack_revision_id,pack_id,revision_no,target_variety_id,status,engine_min_version,"
            "engine_max_version,capability_manifest,checksum_manifest,license_refs,"
            "provenance_id,published_at) VALUES "
            "(:revision,:pack,1,:target,'approved','0.1.0','0.1.x',"
            "CAST(:capabilities AS jsonb),CAST(:checksums AS jsonb),"
            "ARRAY['test'],:provenance,NULL) ON CONFLICT DO NOTHING"
        ),
        {
            "revision": PACK_REVISION_ID,
            "pack": PACK_ID,
            "target": TARGET_VARIETY_ID,
            "provenance": PROVENANCE_ID,
            "now": NOW,
            "capabilities": '{"schema_version":1}',
            "checksums": '{"fixture":"ok"}',
        },
    )
    await connection.execute(
        text(
            "INSERT INTO catalogue.language_pack_support_varieties "
            "(pack_revision_id,variety_id) VALUES (:pack,:support) ON CONFLICT DO NOTHING"
        ),
        {"pack": PACK_REVISION_ID, "support": SUPPORT_VARIETY_ID},
    )
    senses: list[tuple[UUID, UUID, str, str]] = []
    for index, (lemma, definition) in enumerate(
        (("uno", "un"), ("due", "deux"), ("tre", "trois")), 1
    ):
        unit_id = UUID(f"019fec10-0000-7000-8010-{index:012x}")
        unit_revision_id = UUID(f"019fec10-0000-7000-8011-{index:012x}")
        sense_id = UUID(f"019fec10-0000-7000-8012-{index:012x}")
        sense_revision_id = UUID(f"019fec10-0000-7000-8013-{index:012x}")
        await connection.execute(
            text(
                "INSERT INTO catalogue.lexical_units "
                "(lexical_unit_id,variety_id,unit_type,visibility) "
                "VALUES (:id,:variety,'word','shared') ON CONFLICT DO NOTHING"
            ),
            {"id": unit_id, "variety": TARGET_VARIETY_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO catalogue.lexical_unit_revisions "
                "(unit_revision_id,lexical_unit_id,pack_revision_id,revision_no,lemma,"
                "part_of_speech,status,provenance_id) VALUES "
                "(:revision,:unit,:pack,1,:lemma,'numeral','published',:provenance) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "revision": unit_revision_id,
                "unit": unit_id,
                "pack": PACK_REVISION_ID,
                "lemma": lemma,
                "provenance": PROVENANCE_ID,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO catalogue.lexical_senses (sense_id,lexical_unit_id,sense_code) "
                "VALUES (:sense,:unit,:code) ON CONFLICT DO NOTHING"
            ),
            {"sense": sense_id, "unit": unit_id, "code": f"number.{index}"},
        )
        await connection.execute(
            text(
                "INSERT INTO catalogue.lexical_sense_revisions "
                "(sense_revision_id,sense_id,pack_revision_id,revision_no,definition,domains,"
                "status,provenance_id) VALUES "
                "(:revision,:sense,:pack,1,:definition,ARRAY['general'],'published',:provenance) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "revision": sense_revision_id,
                "sense": sense_id,
                "pack": PACK_REVISION_ID,
                "definition": definition,
                "provenance": PROVENANCE_ID,
            },
        )
        senses.append((sense_id, sense_revision_id, lemma, definition))
    return tuple(senses)


@pytest.fixture
async def seeded_practice() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], UUID, tuple[tuple[UUID, UUID, str, str], ...]]
]:
    migration_engine = create_async_engine(migration_database_url_from_environment())
    async with migration_engine.begin() as connection:
        senses = await _seed_catalogue(connection)
        await connection.execute(
            text(
                "INSERT INTO identity.accounts "
                "(account_id,status,security_version,session_version,version,created_at,"
                "security_last_activity_at) VALUES (:account,'active',1,1,1,:now,:now)"
            ),
            {"account": ACCOUNT_ID, "now": NOW},
        )
        await connection.execute(
            text(
                "INSERT INTO language_profiles.learner_language_profiles "
                "(profile_id,account_id,target_variety_id,native_variety_id,status,current_phase,"
                "goals,interests,excluded_themes,correction_preference,availability_pattern,"
                "version,created_at,updated_at) VALUES "
                "(:profile,:account,:target,:support,'active','module_learning','[]','[]','[]',"
                "'{}','{}',1,:now,:now)"
            ),
            {
                "profile": PROFILE_ID,
                "account": ACCOUNT_ID,
                "target": TARGET_VARIETY_ID,
                "support": SUPPORT_VARIETY_ID,
                "now": NOW,
            },
        )
    await migration_engine.dispose()
    runtime_engine = create_async_engine(database_url_from_environment())
    try:
        yield (
            async_sessionmaker(runtime_engine, expire_on_commit=False),
            PACK_REVISION_ID,
            senses,
        )
    finally:
        await runtime_engine.dispose()
