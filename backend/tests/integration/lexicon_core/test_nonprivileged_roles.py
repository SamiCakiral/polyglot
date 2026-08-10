from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from polyglot.bootstrap.database import retention_database_url_from_environment


async def _role_state(session, expected_login: str, forbidden_role: str) -> None:
    row = (
        await session.execute(
            text(
                "SELECT current_user,session_user,rolsuper,rolbypassrls,"
                "pg_has_role(session_user,:forbidden,'MEMBER') AS forbidden_member "
                "FROM pg_roles WHERE rolname=session_user"
            ),
            {"forbidden": forbidden_role},
        )
    ).one()
    assert row.current_user == expected_login
    assert row.session_user == expected_login
    assert row.rolsuper is False
    assert row.rolbypassrls is False
    assert row.forbidden_member is False


async def test_migration_matrix_uses_locked_role(migration_session) -> None:
    await _role_state(
        migration_session,
        "polyglot_migration_login",
        "polyglot_runtime",
    )
    assert await migration_session.scalar(
        text("SELECT has_schema_privilege('polyglot_migration','lexicon','CREATE')")
    ) is True


async def test_runtime_matrix_uses_locked_role(runtime_session) -> None:
    await _role_state(
        runtime_session,
        "polyglot_runtime_login",
        "polyglot_migration",
    )


async def test_retention_role_is_locked_and_separate() -> None:
    engine = create_async_engine(retention_database_url_from_environment())
    try:
        async with engine.connect() as connection:
            await _role_state(
                connection,
                "polyglot_retention_login",
                "polyglot_runtime",
            )
    finally:
        await engine.dispose()
