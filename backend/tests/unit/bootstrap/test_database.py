from sqlalchemy import make_url


def test_explicit_database_urls_remain_closed_by_workload_for_ci() -> None:
    from polyglot.bootstrap import database

    environment = {
        "POLYGLOT_MIGRATION_DATABASE_URL": (
            "postgresql+asyncpg://migration@migration-db/migration"
        ),
        "POLYGLOT_DATABASE_URL": "postgresql+asyncpg://runtime@runtime-db/runtime",
        "POLYGLOT_RETENTION_DATABASE_URL": (
            "postgresql+asyncpg://retention@retention-db/retention"
        ),
    }

    assert hasattr(database, "workload_database_url_from_environment")
    build_url = database.workload_database_url_from_environment

    expected_components = {
        "migration": ("migration", "migration-db", "migration"),
        "runtime": ("runtime", "runtime-db", "runtime"),
        "retention": ("retention", "retention-db", "retention"),
    }
    for workload, expected in expected_components.items():
        parsed = make_url(build_url(workload, environment))
        assert (parsed.username, parsed.host, parsed.database) == expected
