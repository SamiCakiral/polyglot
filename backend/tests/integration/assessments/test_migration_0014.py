from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

EXPECTED_TABLES = {
    "assessment_definitions",
    "assessment_definition_revisions",
    "assessment_forms",
    "assessment_section_definitions",
    "assessment_items",
    "assessment_runs",
    "assessment_section_runs",
    "assessment_responses",
    "assessment_results",
    "assessment_evidence",
    "assessment_reviews",
    "form_exposures",
}
IMMUTABLE_TABLES = {
    "assessment_definition_revisions",
    "assessment_forms",
    "assessment_section_definitions",
    "assessment_items",
    "assessment_results",
    "assessment_evidence",
    "assessment_reviews",
    "form_exposures",
}


async def test_migration_creates_complete_assessment_storage(
    migration_session: AsyncSession,
) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='assessments'"
                )
            )
        ).scalars()
    )
    assert tables == EXPECTED_TABLES


async def test_assessment_facts_and_published_forms_are_immutable(
    migration_session: AsyncSession,
) -> None:
    triggers = set(
        (
            await migration_session.execute(
                text(
                    "SELECT event_object_table || ':' || event_manipulation "
                    "FROM information_schema.triggers WHERE trigger_schema='assessments'"
                )
            )
        ).scalars()
    )
    for table in IMMUTABLE_TABLES:
        assert f"{table}:UPDATE" in triggers
        assert f"{table}:DELETE" in triggers


async def test_all_assessment_tables_force_rls(migration_session: AsyncSession) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,count(p.polname) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "LEFT JOIN pg_policy p ON p.polrelid=c.oid "
                "WHERE n.nspname='assessments' AND c.relkind='r' "
                "GROUP BY c.relname,c.relrowsecurity,c.relforcerowsecurity"
            )
        )
    ).all()
    assert {row[0] for row in rows} == EXPECTED_TABLES
    assert all(row[1] is True and row[2] is True and row[3] >= 1 for row in rows)


async def test_four_protocols_are_seeded_with_fingerprinted_forms(
    migration_session: AsyncSession,
) -> None:
    rows = (
        await migration_session.execute(
            text(
                "SELECT d.modality,r.protocol_code,f.checksum "
                "FROM assessments.assessment_definitions d "
                "JOIN assessments.assessment_definition_revisions r "
                "ON r.assessment_definition_id=d.assessment_definition_id "
                "JOIN assessments.assessment_forms f "
                "ON f.assessment_revision_id=r.assessment_revision_id "
                "ORDER BY d.modality"
            )
        )
    ).all()
    assert [row[0] for row in rows] == ["listening", "reading", "speaking", "writing"]
    assert all(row[1].endswith("_V0") and len(row[2]) == 64 for row in rows)
