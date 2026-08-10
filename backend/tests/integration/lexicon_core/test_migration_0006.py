from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


EXPECTED_TABLES = {
    "private_lexical_units",
    "private_lexical_senses",
    "lexical_encounters",
    "lexical_mentions",
    "mention_candidates",
    "mention_resolutions",
    "personal_lexical_relations",
    "lexical_relation_retractions",
    "lexical_declarations",
    "lexical_preferences",
    "lexical_annotations",
    "lexical_annotation_revisions",
    "lexicon_command_receipts",
}


async def test_migration_creates_only_w06_lexicon_tables(
    migration_session: AsyncSession,
) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'lexicon'"
                )
            )
        ).scalars()
    )

    assert EXPECTED_TABLES <= tables
    assert not any(
        token in name
        for name in tables
        for token in ("mastery", "debt", "card", "memory_prompt", "vocabulary_list")
    )


async def test_encounters_and_source_facts_are_append_only(
    migration_session: AsyncSession,
) -> None:
    triggers = set(
        (
            await migration_session.execute(
                text(
                    "SELECT event_object_table || ':' || event_manipulation "
                    "FROM information_schema.triggers WHERE trigger_schema = 'lexicon'"
                )
            )
        ).scalars()
    )

    assert "lexical_encounters:DELETE" in triggers
    assert "lexical_encounters:UPDATE" in triggers
    assert "lexical_mentions:DELETE" in triggers
    assert "lexical_mentions:UPDATE" in triggers
    assert "mention_resolutions:DELETE" in triggers
    assert "mention_resolutions:UPDATE" in triggers


async def test_every_personal_table_has_forced_rls_and_owner_policy(
    migration_session: AsyncSession,
) -> None:
    protected = EXPECTED_TABLES - {"private_lexical_senses", "mention_candidates"}
    rows = (
        await migration_session.execute(
            text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, count(p.polname) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "LEFT JOIN pg_policy p ON p.polrelid = c.oid "
                "WHERE n.nspname = 'lexicon' AND c.relkind = 'r' "
                "GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity"
            )
        )
    ).all()
    by_name = {name: (rls, forced, policies) for name, rls, forced, policies in rows}

    for table in protected:
        assert by_name[table][0] is True
        assert by_name[table][1] is True
        assert by_name[table][2] >= 1


async def test_migration_exposes_required_indexes_and_no_shared_catalogue_mutator(
    migration_session: AsyncSession,
) -> None:
    indexes = set(
        (
            await migration_session.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = 'lexicon'"
                )
            )
        ).scalars()
    )
    functions = set(
        (
            await migration_session.execute(
                text(
                    "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                    "WHERE n.nspname = 'lexicon'"
                )
            )
        ).scalars()
    )

    assert {
        "ix_lexicon_encounters_profile_time",
        "ix_lexicon_mentions_unresolved",
        "ix_lexicon_private_unit_search",
        "ix_lexicon_annotations_profile_sense",
    } <= indexes
    assert not any("catalogue" in function and "mutat" in function for function in functions)
