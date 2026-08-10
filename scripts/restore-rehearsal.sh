#!/usr/bin/env bash
# Rehearse a local PostgreSQL/object-store restore using synthetic FX-OPS data only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
FIXTURE="${W19_FIXTURE:-}"
SOURCE_DSN="${W19_SOURCE_DSN:-}"
TARGET_DSN="${W19_TARGET_DSN:-}"
SOURCE_OBJECTS="${W19_SOURCE_OBJECTS:-}"
TARGET_OBJECTS="${W19_TARGET_OBJECTS:-}"
REPORT="${W19_REPORT:-${TMPDIR:-/tmp}/w19-restore-rehearsal-report.json}"
EXPECTED_MIGRATION_HEAD="${W19_EXPECTED_MIGRATION_HEAD:-}"
PG_DUMP_BIN="${PG_DUMP_BIN:-pg_dump}"
PG_RESTORE_BIN="${PG_RESTORE_BIN:-pg_restore}"
PSQL_BIN="${PSQL_BIN:-psql}"
STATUS="FAIL"
ERROR_MESSAGE=""
WORK_DIR=""
CHECKS_FILE="$(mktemp "${TMPDIR:-/tmp}/w19-checks.XXXXXX")"

cleanup() {
    rm -f "$CHECKS_FILE"
    if [[ -n "$WORK_DIR" && -d "$WORK_DIR" ]]; then
        rm -rf "$WORK_DIR"
    fi
}
trap cleanup EXIT

usage() {
    cat <<'EOF'
Usage: scripts/restore-rehearsal.sh --fixture FX-OPS --source-dsn DSN --target-dsn DSN \
  --source-objects PATH --target-objects PATH --report PATH [options]

Creates a custom-format PostgreSQL backup and deterministic local object copy,
then restores only into a separate, empty target database and object directory.

Required options (or W19_* environment variables):
  --fixture FX-OPS              Synthetic fixture code; only FX-OPS is accepted
  --source-dsn DSN              PostgreSQL source DSN
  --target-dsn DSN              PostgreSQL isolated target DSN
  --source-objects PATH         Existing synthetic source object directory
  --target-objects PATH         Existing, empty isolated target directory
  --report PATH                 JSON report destination

Optional:
  --expected-migration-head ID  Override fixture migration head
  --pg-dump-bin PATH            pg_dump executable (default: pg_dump)
  --pg-restore-bin PATH         pg_restore executable (default: pg_restore)
  --psql-bin PATH               psql executable (default: psql)
  --help                        Show this help
EOF
}

add_check() {
    printf '%s\t%s\t%s\n' "$1" "$2" "$3" >>"$CHECKS_FILE"
}

redacted_dsn() {
    "$PYTHON_BIN" - "$1" <<'PY'
from sys import argv
from urllib.parse import urlsplit, urlunsplit

value = argv[1]
parts = urlsplit(value)
if not parts.scheme or not parts.hostname:
    print("redacted")
else:
    netloc = parts.hostname
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    print(urlunsplit((parts.scheme, netloc, parts.path, "", "")))
PY
}

database_identity() {
    "$PYTHON_BIN" - "$1" <<'PY'
from sys import argv, exit
from urllib.parse import unquote, urlsplit

parts = urlsplit(argv[1])
scheme = {"postgres": "postgresql"}.get(parts.scheme, parts.scheme)
if scheme != "postgresql" or not parts.hostname or not parts.path.strip("/"):
    exit(1)
port = parts.port if parts.port is not None else 5432
print(f"{parts.hostname.lower()}:{port}/{unquote(parts.path.lstrip('/'))}")
PY
}

write_report() {
    local revision utc
    revision="$(git -C "$ROOT_DIR" rev-parse HEAD 2>/dev/null || printf 'unknown')"
    utc="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    mkdir -p "$(dirname "$REPORT")"
    W19_REPORT_STATUS="$STATUS" \
        W19_REPORT_REVISION="$revision" \
        W19_REPORT_UTC="$utc" \
        W19_REPORT_FIXTURE="$FIXTURE" \
        W19_REPORT_SOURCE="$(redacted_dsn "$SOURCE_DSN")" \
        W19_REPORT_TARGET="$(redacted_dsn "$TARGET_DSN")" \
        W19_REPORT_EXPECTED_HEAD="$EXPECTED_MIGRATION_HEAD" \
        W19_REPORT_ERROR="$ERROR_MESSAGE" \
        W19_REPORT_PG_DUMP_VERSION="${PG_DUMP_VERSION:-unavailable}" \
        W19_REPORT_PG_RESTORE_VERSION="${PG_RESTORE_VERSION:-unavailable}" \
        W19_REPORT_PSQL_VERSION="${PSQL_VERSION:-unavailable}" \
        W19_REPORT_ARCHIVE_SHA256="${ARCHIVE_SHA256:-}" \
        W19_REPORT_OBJECT_MANIFEST_SHA256="${OBJECT_MANIFEST_SHA256:-}" \
        W19_REPORT_CHECKS_FILE="$CHECKS_FILE" \
        "$PYTHON_BIN" - "$REPORT" <<'PY'
import json
import os
from pathlib import Path

checks = []
for line in Path(os.environ["W19_REPORT_CHECKS_FILE"]).read_text(encoding="utf-8").splitlines():
    name, status, detail = line.split("\t", 2)
    checks.append({"name": name, "status": status, "detail": detail})
payload = {
    "schema_version": 1,
    "workstream": "W19L-A",
    "fixture": os.environ["W19_REPORT_FIXTURE"],
    "revision": os.environ["W19_REPORT_REVISION"],
    "utc": os.environ["W19_REPORT_UTC"],
    "status": os.environ["W19_REPORT_STATUS"],
    "source": os.environ["W19_REPORT_SOURCE"],
    "target": os.environ["W19_REPORT_TARGET"],
    "expected_migration_head": os.environ["W19_REPORT_EXPECTED_HEAD"],
    "tool_versions": {
        "pg_dump": os.environ["W19_REPORT_PG_DUMP_VERSION"],
        "pg_restore": os.environ["W19_REPORT_PG_RESTORE_VERSION"],
        "psql": os.environ["W19_REPORT_PSQL_VERSION"],
    },
    "fingerprints": {
        "postgresql_archive_sha256": os.environ["W19_REPORT_ARCHIVE_SHA256"],
        "object_manifest_sha256": os.environ["W19_REPORT_OBJECT_MANIFEST_SHA256"],
    },
    "checks": checks,
    "errors": [os.environ["W19_REPORT_ERROR"]] if os.environ["W19_REPORT_ERROR"] else [],
    "limitations": ["Local W19L evidence only; it is not W19C cloud, PITR, canary, or release proof."],
}
Path(__import__("sys").argv[1]).write_text(
    json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
)
PY
}

fail() {
    local status="$1"
    local check_name="$2"
    local detail="$3"
    STATUS="$status"
    ERROR_MESSAGE="$detail"
    add_check "$check_name" "FAIL" "$detail"
    write_report
    printf 'Restore rehearsal failed; report written to %s\n' "$REPORT" >&2
    exit 1
}

require_value() {
    local name="$1"
    local value="$2"
    [[ -n "$value" ]] || fail "FAIL" "argument_${name}" "required value is missing"
}

canonical_directory() {
    (cd "$1" && pwd -P)
}

sha256_file() {
    shasum -a 256 "$1" | awk '{print $1}'
}

validate_object_manifest() {
    local directory="$1" phase="$2" manifest_records actual relative expected expected_count actual_count
    manifest_records="$WORK_DIR/object-records.tsv"
    "$PYTHON_BIN" - "$FIXTURE_DIR/oracles.json" >"$manifest_records" <<'PY'
import base64
import json
import sys

for item in json.load(open(sys.argv[1], encoding="utf-8"))["objects"]:
    print(f"{item['path']}\t{item['sha256']}")
PY
    expected_count="$(wc -l <"$manifest_records" | tr -d ' ')"
    actual_count="$(find "$directory" -type f -print | wc -l | tr -d ' ')"
    [[ "$actual_count" == "$expected_count" ]] || fail "FAIL" "${phase}_object_manifest" "object count differs from FX-OPS manifest"
    while IFS=$'\t' read -r relative expected; do
        [[ -f "$directory/$relative" ]] || fail "FAIL" "${phase}_object_manifest" "required fixture object is missing"
        actual="$(sha256_file "$directory/$relative")"
        [[ "$actual" == "$expected" ]] || fail "FAIL" "${phase}_object_manifest" "fixture object checksum differs"
    done <"$manifest_records"
    add_check "${phase}_object_manifest" "PASS" "all fixture object checksums match"
}

copy_objects_deterministically() {
    local records relative expected
    records="$WORK_DIR/object-records.tsv"
    while IFS=$'\t' read -r relative expected; do
        mkdir -p "$(dirname "$TARGET_OBJECTS/$relative")"
        cp "$SOURCE_OBJECTS/$relative" "$TARGET_OBJECTS/$relative"
    done <"$records"
    OBJECT_MANIFEST_SHA256="$(sha256_file "$records")"
    validate_object_manifest "$TARGET_OBJECTS" "target"
    add_check "deterministic_object_copy" "PASS" "sorted FX-OPS manifest copied"
}

run_psql_scalar() {
    local dsn="$1" query="$2"
    "$PSQL_BIN" --no-psqlrc --quiet --tuples-only --no-align --set ON_ERROR_STOP=1 --dbname "$dsn" --command "$query" 2>"$WORK_DIR/tool.stderr" | tr -d '[:space:]'
}

parse_options() {
    while (($#)); do
        case "$1" in
            --fixture) FIXTURE="${2:-}"; shift 2 ;;
            --source-dsn) SOURCE_DSN="${2:-}"; shift 2 ;;
            --target-dsn) TARGET_DSN="${2:-}"; shift 2 ;;
            --source-objects) SOURCE_OBJECTS="${2:-}"; shift 2 ;;
            --target-objects) TARGET_OBJECTS="${2:-}"; shift 2 ;;
            --report) REPORT="${2:-}"; shift 2 ;;
            --expected-migration-head) EXPECTED_MIGRATION_HEAD="${2:-}"; shift 2 ;;
            --pg-dump-bin) PG_DUMP_BIN="${2:-}"; shift 2 ;;
            --pg-restore-bin) PG_RESTORE_BIN="${2:-}"; shift 2 ;;
            --psql-bin) PSQL_BIN="${2:-}"; shift 2 ;;
            --help) usage; exit 0 ;;
            *) fail "FAIL" "argument_parsing" "unsupported option" ;;
        esac
    done
}

main() {
    parse_options "$@"
    require_value fixture "$FIXTURE"
    require_value source_dsn "$SOURCE_DSN"
    require_value target_dsn "$TARGET_DSN"
    require_value source_objects "$SOURCE_OBJECTS"
    require_value target_objects "$TARGET_OBJECTS"
    require_value report "$REPORT"
    [[ "$FIXTURE" == "FX-OPS" ]] || fail "FAIL" "fixture" "only FX-OPS is supported"
    FIXTURE_DIR="$ROOT_DIR/fixtures/canonical/$FIXTURE"
    [[ -f "$FIXTURE_DIR/manifest.json" && -f "$FIXTURE_DIR/oracles.json" ]] || fail "FAIL" "fixture" "FX-OPS manifest or oracles are missing"
    if [[ -z "$EXPECTED_MIGRATION_HEAD" ]]; then
        EXPECTED_MIGRATION_HEAD="$("$PYTHON_BIN" - "$FIXTURE_DIR/manifest.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["expected_migration_head"])
PY
)" || fail "FAIL" "fixture" "cannot read expected migration head"
    fi
    [[ -d "$SOURCE_OBJECTS" && -d "$TARGET_OBJECTS" ]] || fail "FAIL" "object_directories" "source and target object directories must exist"
    SOURCE_OBJECTS="$(canonical_directory "$SOURCE_OBJECTS")"
    TARGET_OBJECTS="$(canonical_directory "$TARGET_OBJECTS")"
    SOURCE_DATABASE_IDENTITY="$(database_identity "$SOURCE_DSN")" || fail "FAIL" "source_target_distinct" "source DSN is not a PostgreSQL database identifier"
    TARGET_DATABASE_IDENTITY="$(database_identity "$TARGET_DSN")" || fail "FAIL" "source_target_distinct" "target DSN is not a PostgreSQL database identifier"
    [[ "$SOURCE_DATABASE_IDENTITY" != "$TARGET_DATABASE_IDENTITY" ]] || fail "FAIL" "source_target_distinct" "source and target DSNs identify the same database"
    [[ "$SOURCE_OBJECTS" != "$TARGET_OBJECTS" ]] || fail "FAIL" "source_target_distinct" "source and target object directories must differ"
    add_check "source_target_distinct" "PASS" "source and target are distinct"
    [[ -z "$(find "$TARGET_OBJECTS" -mindepth 1 -print -quit)" ]] || fail "FAIL" "target_object_directory" "target object directory must be empty"
    WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/w19-restore.XXXXXX")"
    for tool in "$PG_DUMP_BIN" "$PG_RESTORE_BIN" "$PSQL_BIN" "$PYTHON_BIN"; do
        command -v "$tool" >/dev/null 2>&1 || fail "PARTIAL" "tool_preflight" "required local PostgreSQL or Python tool is unavailable"
    done
    PG_DUMP_VERSION="$("$PG_DUMP_BIN" --version 2>"$WORK_DIR/tool.stderr")" || fail "PARTIAL" "tool_preflight" "pg_dump version check failed"
    PG_RESTORE_VERSION="$("$PG_RESTORE_BIN" --version 2>"$WORK_DIR/tool.stderr")" || fail "PARTIAL" "tool_preflight" "pg_restore version check failed"
    PSQL_VERSION="$("$PSQL_BIN" --version 2>"$WORK_DIR/tool.stderr")" || fail "PARTIAL" "tool_preflight" "psql version check failed"
    add_check "tool_preflight" "PASS" "PostgreSQL client tools are available"
    [[ "$(run_psql_scalar "$SOURCE_DSN" 'SELECT 1')" == "1" ]] || fail "FAIL" "source_reachable" "source PostgreSQL is unavailable"
    add_check "source_reachable" "PASS" "source PostgreSQL responded"
    validate_object_manifest "$SOURCE_OBJECTS" "source"
    ARCHIVE_PATH="$WORK_DIR/source.dump"
    "$PG_DUMP_BIN" --format=custom --no-owner --no-privileges --file="$ARCHIVE_PATH" "$SOURCE_DSN" 2>"$WORK_DIR/tool.stderr" || fail "FAIL" "pg_dump" "pg_dump custom-format backup failed"
    [[ -s "$ARCHIVE_PATH" ]] || fail "FAIL" "pg_dump" "pg_dump archive is empty"
    ARCHIVE_SHA256="$(sha256_file "$ARCHIVE_PATH")"
    add_check "pg_dump" "PASS" "custom-format archive created and checksummed"
    [[ "$(run_psql_scalar "$TARGET_DSN" "SELECT count(*) FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema')")" == "0" ]] || fail "FAIL" "target_database_isolation" "target PostgreSQL database is not empty"
    add_check "target_database_isolation" "PASS" "target PostgreSQL database is empty"
    copy_objects_deterministically
    "$PG_RESTORE_BIN" --clean --if-exists --no-owner --no-privileges --dbname "$TARGET_DSN" "$ARCHIVE_PATH" 2>"$WORK_DIR/tool.stderr" || fail "FAIL" "pg_restore" "pg_restore failed on the isolated target"
    add_check "pg_restore" "PASS" "custom-format archive restored to isolated target"
    [[ "$(run_psql_scalar "$TARGET_DSN" 'SELECT version_num FROM alembic_version')" == "$EXPECTED_MIGRATION_HEAD" ]] || fail "FAIL" "migration_head" "restored migration head does not match FX-OPS"
    add_check "migration_head" "PASS" "restored migration head matches FX-OPS"
    while IFS=$'\t' read -r oracle_name oracle_expected oracle_query; do
        actual="$(run_psql_scalar "$TARGET_DSN" "$oracle_query")" || fail "FAIL" "$oracle_name" "fixture oracle query failed"
        [[ "$actual" == "$oracle_expected" ]] || fail "FAIL" "$oracle_name" "fixture oracle did not match expected result"
        add_check "$oracle_name" "PASS" "fixture oracle matched"
    done < <("$PYTHON_BIN" - "$FIXTURE_DIR/oracles.json" <<'PY'
import base64
import json
import sys

for oracle in json.load(open(sys.argv[1], encoding="utf-8"))["database"]:
    print(f"{oracle['name']}\t{oracle['expected']}\t{oracle['query']}")
PY
)
    STATUS="PASS"
    ERROR_MESSAGE=""
    write_report
    printf 'Restore rehearsal passed; report written to %s\n' "$REPORT"
}

main "$@"
