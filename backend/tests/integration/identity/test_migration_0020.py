from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_0020_adds_owned_language_repertoire_and_onboarding_state(
    migration_session: AsyncSession,
) -> None:
    tables = set(
        (
            await migration_session.execute(
                text(
                    "SELECT table_schema || '.' || table_name "
                    "FROM information_schema.tables "
                    "WHERE (table_schema, table_name) IN "
                    "(('identity', 'account_languages'), "
                    "('language_profiles', 'onboarding_states'))"
                )
            )
        ).scalars()
    )
    rls = set(
        (
            await migration_session.execute(
                text(
                    "SELECT namespace.nspname || '.' || relation.relname "
                    "FROM pg_class AS relation "
                    "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
                    "WHERE relation.relrowsecurity AND (namespace.nspname, relation.relname) IN "
                    "(('identity', 'account_languages'), "
                    "('language_profiles', 'onboarding_states'))"
                )
            )
        ).scalars()
    )

    assert tables == {
        "identity.account_languages",
        "language_profiles.onboarding_states",
    }
    assert rls == tables
