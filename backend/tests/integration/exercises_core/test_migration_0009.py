from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from .conftest import ATTEMPT_ID, NOW, PROFILE_ID, seed_attempt, uid

EXPECTED_TABLES = {
    "exercise_definitions",
    "exercise_definition_revisions",
    "exercise_language_certifications",
    "exercise_instances",
    "exercise_attempts",
    "attempt_drafts",
    "exercise_hint_uses",
    "attempt_media_events",
    "exercise_corrections",
    "correction_cases",
    "correction_case_reviews",
    "exercise_block_runs",
    "exercise_command_receipts",
}
PERSONAL_TABLES = EXPECTED_TABLES - {
    "exercise_definitions",
    "exercise_definition_revisions",
    "exercise_language_certifications",
    "exercise_instances",
}
APPEND_ONLY_TABLES = {
    "exercise_definition_revisions",
    "exercise_instances",
    "exercise_hint_uses",
    "attempt_media_events",
    "exercise_corrections",
    "correction_case_reviews",
    "exercise_command_receipts",
}


async def test_migration_creates_exercise_storage(migration_session: AsyncSession) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='exercises'"
                )
            )
        ).scalars()
    )
    assert tables == EXPECTED_TABLES


async def test_personal_exercise_tables_force_owner_rls(
    migration_session: AsyncSession,
) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,count(p.polname) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "LEFT JOIN pg_policy p ON p.polrelid=c.oid "
                "WHERE n.nspname='exercises' AND c.relname=ANY(:tables) "
                "GROUP BY c.relname,c.relrowsecurity,c.relforcerowsecurity"
            ),
            {"tables": sorted(PERSONAL_TABLES)},
        )
    ).all()
    assert {row[0] for row in rows} == PERSONAL_TABLES
    assert all(row[1] is True and row[2] is True and row[3] >= 1 for row in rows)


async def test_exercise_facts_are_append_only(migration_session: AsyncSession) -> None:
    guarded = set(
        (
            await migration_session.execute(
                text(
                    "SELECT event_object_table || ':' || event_manipulation "
                    "FROM information_schema.triggers WHERE trigger_schema='exercises'"
                )
            )
        ).scalars()
    )
    for table in APPEND_ONLY_TABLES:
        assert f"{table}:UPDATE" in guarded
        assert f"{table}:DELETE" in guarded


async def test_runtime_write_surface_preserves_raw_answers_and_corrections(
    migration_session: AsyncSession,
) -> None:
    assert await migration_session.scalar(
        text(
            "SELECT has_table_privilege('polyglot_runtime',"
            "'exercises.exercise_attempts','UPDATE')"
        )
    ) is True
    assert await migration_session.scalar(
        text(
            "SELECT has_table_privilege('polyglot_runtime',"
            "'exercises.exercise_corrections','UPDATE')"
        )
    ) is False


async def test_attempt_answer_has_a_dedicated_immutability_guard(
    migration_session: AsyncSession,
) -> None:
    trigger_names = set(
        (
            await migration_session.execute(
                text(
                    "SELECT trigger_name FROM information_schema.triggers "
                    "WHERE trigger_schema='exercises' "
                    "AND event_object_table='exercise_attempts' "
                    "AND event_manipulation='UPDATE'"
                )
            )
        ).scalars()
    )
    assert "guard_exercise_attempt_answer" in trigger_names


async def test_instances_allow_shared_reads_but_only_owned_standalone_writes(
    migration_session: AsyncSession,
) -> None:
    row = (
        await migration_session.execute(
            text(
                "SELECT c.relrowsecurity,c.relforcerowsecurity,count(p.polname) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "LEFT JOIN pg_policy p ON p.polrelid=c.oid "
                "WHERE n.nspname='exercises' AND c.relname='exercise_instances' "
                "GROUP BY c.relrowsecurity,c.relforcerowsecurity"
            )
        )
    ).one()
    assert row == (True, True, 2)


async def test_schema_covers_versioned_contracts_and_attempt_evidence(
    migration_session: AsyncSession,
) -> None:
    required_columns = {
        "exercise_definitions": {"definition_code"},
        "exercise_definition_revisions": {
            "schema_version",
            "response_contract",
            "stimulus_contract",
            "target_contract",
            "difficulty_profile",
        },
        "exercise_instances": {
            "target_bindings",
            "lexical_bindings",
            "grammar_bindings",
            "provenance_id",
        },
        "exercise_attempts": {
            "active_duration_ms",
            "input_locale",
            "normalization_policy_revision_id",
            "normalized_answer",
            "idempotency_key",
            "request_fingerprint",
        },
        "exercise_hint_uses": {
            "hint_definition_revision_id",
            "answer_state_checksum",
            "effect_policy_revision_id",
        },
        "exercise_corrections": {
            "provenance_id",
            "requires_review",
            "supersedes_correction_id",
            "is_current",
        },
    }
    rows = (
        await migration_session.execute(
            text(
                "SELECT table_name,column_name FROM information_schema.columns "
                "WHERE table_schema='exercises'"
            )
        )
    ).all()
    actual: dict[str, set[str]] = {}
    for table_name, column_name in rows:
        actual.setdefault(table_name, set()).add(column_name)
    for table_name, columns in required_columns.items():
        assert columns <= actual.get(table_name, set())
    assert await migration_session.scalar(
        text(
            "SELECT has_table_privilege('polyglot_runtime',"
            "'exercises.exercise_instances','DELETE')"
        )
    ) is False


async def test_submitted_raw_answer_cannot_be_rewritten(
    migration_session: AsyncSession,
) -> None:
    await seed_attempt(migration_session)
    await migration_session.execute(
        text(
            "UPDATE exercises.exercise_attempts SET status='submitted',"
            "answer_kind='self_grade',raw_answer='\"good\"'::jsonb,input_method='keyboard',"
            "input_locale='it-IT',submitted_at=:now,idempotency_key='submit-1',"
            "request_fingerprint=:fingerprint,version=2,updated_at=:now "
            "WHERE attempt_id=:attempt"
        ),
        {"attempt": ATTEMPT_ID, "now": NOW, "fingerprint": "a" * 64},
    )
    with pytest.raises(DBAPIError, match="submitted exercise answer is immutable"):
        await migration_session.execute(
            text(
                "UPDATE exercises.exercise_attempts SET raw_answer='\"easy\"'::jsonb "
                "WHERE attempt_id=:attempt"
            ),
            {"attempt": ATTEMPT_ID},
        )


async def test_new_correction_closes_previous_revision_without_rewriting_it(
    migration_session: AsyncSession,
) -> None:
    await seed_attempt(migration_session)
    await migration_session.execute(
        text(
            "UPDATE exercises.exercise_attempts SET status='submitted',"
            "answer_kind='self_grade',raw_answer='\"good\"'::jsonb,input_method='keyboard',"
            "input_locale='it-IT',submitted_at=:now,idempotency_key='submit-1',"
            "request_fingerprint=:fingerprint,version=2,updated_at=:now "
            "WHERE attempt_id=:attempt"
        ),
        {"attempt": ATTEMPT_ID, "now": NOW, "fingerprint": "b" * 64},
    )
    first = uid(30)
    second = uid(31)
    values = {
        "attempt": ATTEMPT_ID,
        "profile": PROFILE_ID,
        "provenance": uid(32),
        "now": NOW,
    }
    await migration_session.execute(
        text(
            "INSERT INTO exercises.exercise_corrections "
            "(correction_id,attempt_id,profile_id,revision_no,verdict,confidence,"
            "target_coverage,strategy,alternatives,explanation,error_codes,criterion_scores,"
            "provenance_id,requires_review,is_current,result_payload,created_at) VALUES "
            "(:correction,:attempt,:profile,1,'correct',1,1,'self_assessment','[]','valid',"
            "'[]','{}',:provenance,false,true,'{}',:now)"
        ),
        {**values, "correction": first},
    )
    await migration_session.execute(
        text(
            "UPDATE exercises.exercise_corrections SET is_current=false "
            "WHERE correction_id=:correction"
        ),
        {"correction": first},
    )
    await migration_session.execute(
        text(
            "INSERT INTO exercises.exercise_corrections "
            "(correction_id,attempt_id,profile_id,revision_no,verdict,confidence,"
            "target_coverage,strategy,alternatives,explanation,error_codes,criterion_scores,"
            "provenance_id,requires_review,supersedes_correction_id,is_current,result_payload,"
            "created_at) VALUES "
            "(:correction,:attempt,:profile,2,'partially_correct',1,0.5,'manual_review','[]',"
            "'reviewed','[]','{}',:provenance,false,:supersedes,true,'{}',:now)"
        ),
        {**values, "correction": second, "supersedes": first},
    )
    with pytest.raises(DBAPIError, match="immutable except current closure"):
        await migration_session.execute(
            text(
                "UPDATE exercises.exercise_corrections SET explanation='rewritten' "
                "WHERE correction_id=:correction"
            ),
            {"correction": first},
        )
