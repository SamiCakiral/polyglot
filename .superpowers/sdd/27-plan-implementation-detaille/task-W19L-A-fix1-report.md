# W19L-A fix round 1 report

## Status

`PASS` for the six P1/P2 findings in `task-W19L-A-review.md`, limited to the
local synthetic W19L-A rehearsal. This is not W19C, PITR, cloud, canary, or
release proof.

## Review closure

| Finding | Correction | Evidence |
| --- | --- | --- |
| P1 source/target aliases | The script queries `pg_control_system().system_identifier` and the current database OID on both connections, then rejects equality before `pg_dump`. Textual normalization remains an early guard only. | The alias regression test returns the same server facts for `localhost` and `127.0.0.1`, observes rejection, and proves `pg_dump` was not called. The disposable PostgreSQL test executes the same identity query against two real PostgreSQL 17 clusters. |
| P1 malformed DSN leakage | DSN parsing and redaction catch all parser/port failures, suppress parser stderr, emit `redacted`, and still write the closed JSON failure report. | The malformed-port sentinel is absent from stdout, stderr, and JSON; no traceback is present and `target` is `redacted`. |
| P1 portable SHA-256 | Provider selection is `sha256sum`, `shasum`, `openssl`, then Python. Provider absence is `PARTIAL`; execution or digest-shape failure is routed through structured `FAIL`. | The Linux test runs the complete script in `python:3.13.11-slim-bookworm`, asserts `shasum` is absent, selects `sha256sum`, and produces a `PASS` JSON report. |
| P2 logical database checksum | Canonical FX-OPS rows from migration, accounts, events, outbox, deletion history, and tombstones are serialized and SHA-256 hashed on source before dump and target after restore. Both hashes are reported and must match. | The real restore report contains equal non-empty `source_database_logical_sha256` and `target_database_logical_sha256` values plus `database_logical_checksum=PASS`. |
| P2 tombstone non-resurrection | FX-OPS creates a second active account, records a completed deletion request, deletes the account, and writes its tombstone. The same history/tombstone/absence oracles run on source before dump and target after restore. | Explicit source and target checks cover completed deletion history, tombstone presence, deleted active-account absence, and final `tombstone_non_resurrection=PASS`. |
| P2 report location | The original report is tracked under the SDD task directory and no root copy remains. | `.superpowers/sdd/27-plan-implementation-detaille/task-W19L-A-report.md` exists; root `task-W19L-A-report.md` is removed. |

## TDD evidence

- Alias RED: `test_rejects_host_aliases_for_same_server_database_before_dump`
  failed because the dump marker existed. GREEN: the alias and malformed-DSN
  focused run returned `2 passed`.
- Malformed DSN RED: the JSON `target` was empty and the parser path exposed a
  traceback/value. GREEN: the report uses `redacted`, with no sentinel or
  traceback in any output.
- Linux SHA RED: `/repo/scripts/restore-rehearsal.sh` exited on
  `shasum: command not found` without creating the report. GREEN: the focused
  Linux test returned `1 passed` and reported `sha256sum`.
- Logical DB checksum RED: the real test failed with missing
  `source_database_logical_sha256`. GREEN: the focused PostgreSQL restore
  returned `1 passed` with equal source/target hashes.
- Tombstone RED: the real report lacked
  `source_completed_deletion_history_present`. GREEN: the focused PostgreSQL
  restore returned `1 passed` with all source/target deletion checks.

## Final verification

- `W19_REAL_TEST=1 uv run pytest tests/performance/test_restore_rehearsal.py -q`:
  `8 passed`, including disposable PostgreSQL source/target and Linux SHA
  portability containers.
- Ruff format/check: PASS.
- `bash -n` and ShellCheck v0.10.0 in a read-only container: PASS.
- JSON parsing and committed FX-OPS payload checksums: PASS.
- Gitleaks v8.30.0 targeted to the W19L-A write set: no leaks found.
- `git diff --check`: PASS.

## Limits

- The logical database fingerprint intentionally covers the complete synthetic
  FX-OPS dataset, not physical PostgreSQL pages or unrelated application data.
- The isolation gate requires permission to execute `pg_control_system()` on
  both disposable connections. Failure is explicit and blocks the dump.
- No Compose file, business backend, migration, frontend, workflow, cloud
  resource, secret, or real user datum is included in this round.
