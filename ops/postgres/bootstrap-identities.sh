#!/usr/bin/env bash
set -euo pipefail

: "${POLYGLOT_MIGRATION_DB_PASSWORD:?POLYGLOT_MIGRATION_DB_PASSWORD must be set}"
: "${POLYGLOT_RUNTIME_DB_PASSWORD:?POLYGLOT_RUNTIME_DB_PASSWORD must be set}"
: "${POLYGLOT_RETENTION_DB_PASSWORD:?POLYGLOT_RETENTION_DB_PASSWORD must be set}"

psql_arguments=(
  --set=ON_ERROR_STOP=1
  --set=migration_password="$POLYGLOT_MIGRATION_DB_PASSWORD"
  --set=runtime_password="$POLYGLOT_RUNTIME_DB_PASSWORD"
  --set=retention_password="$POLYGLOT_RETENTION_DB_PASSWORD"
)

if [[ -n "${POLYGLOT_BOOTSTRAP_DATABASE_URL:-}" ]]; then
  psql_connection=("$POLYGLOT_BOOTSTRAP_DATABASE_URL")
else
  : "${POSTGRES_USER:?POSTGRES_USER must be set by the PostgreSQL image}"
  : "${POSTGRES_DB:?POSTGRES_DB must be set by the PostgreSQL image}"
  psql_connection=(--username "$POSTGRES_USER" --dbname "$POSTGRES_DB")
fi

psql "${psql_connection[@]}" "${psql_arguments[@]}" <<'SQL'
SELECT 'CREATE ROLE polyglot_migration NOLOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'polyglot_migration')
\gexec
SELECT 'CREATE ROLE polyglot_runtime NOLOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'polyglot_runtime')
\gexec
SELECT 'CREATE ROLE polyglot_retention NOLOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'polyglot_retention')
\gexec

ALTER ROLE polyglot_migration
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;
ALTER ROLE polyglot_runtime
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;
ALTER ROLE polyglot_retention
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;

SELECT 'CREATE ROLE polyglot_migration_login LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'polyglot_migration_login')
\gexec
SELECT 'CREATE ROLE polyglot_runtime_login LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'polyglot_runtime_login')
\gexec
SELECT 'CREATE ROLE polyglot_retention_login LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'polyglot_retention_login')
\gexec

ALTER ROLE polyglot_migration_login
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;
ALTER ROLE polyglot_runtime_login
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;
ALTER ROLE polyglot_retention_login
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;

SELECT format(
    'ALTER ROLE polyglot_migration_login PASSWORD %L',
    :'migration_password'
) \gexec
SELECT format(
    'ALTER ROLE polyglot_runtime_login PASSWORD %L',
    :'runtime_password'
) \gexec
SELECT format(
    'ALTER ROLE polyglot_retention_login PASSWORD %L',
    :'retention_password'
) \gexec

GRANT polyglot_migration TO polyglot_migration_login WITH INHERIT TRUE, SET TRUE;
GRANT polyglot_runtime TO polyglot_runtime_login WITH INHERIT TRUE, SET TRUE;
GRANT polyglot_retention TO polyglot_retention_login WITH INHERIT TRUE, SET TRUE;

SELECT format('REVOKE %I FROM %I', parent.rolname, member.rolname)
FROM pg_auth_members AS membership
JOIN pg_roles AS parent ON parent.oid = membership.roleid
JOIN pg_roles AS member ON member.oid = membership.member
WHERE (parent.rolname, member.rolname) IN (
    ('polyglot_runtime', 'polyglot_migration_login'),
    ('polyglot_retention', 'polyglot_migration_login'),
    ('polyglot_migration', 'polyglot_runtime_login'),
    ('polyglot_retention', 'polyglot_runtime_login'),
    ('polyglot_migration', 'polyglot_retention_login'),
    ('polyglot_runtime', 'polyglot_retention_login')
)
\gexec

SELECT format(
    'REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC',
    current_database()
) \gexec
SELECT format(
    'REVOKE ALL ON DATABASE %I FROM polyglot_migration_login, '
    'polyglot_runtime_login, polyglot_retention_login',
    current_database()
) \gexec
SELECT format(
    'GRANT CONNECT, CREATE, TEMPORARY ON DATABASE %I TO polyglot_migration',
    current_database()
) \gexec
SELECT format(
    'GRANT CONNECT, TEMPORARY ON DATABASE %I TO polyglot_runtime',
    current_database()
) \gexec
SELECT format(
    'GRANT CONNECT ON DATABASE %I TO polyglot_retention',
    current_database()
) \gexec

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO polyglot_migration;
SQL
