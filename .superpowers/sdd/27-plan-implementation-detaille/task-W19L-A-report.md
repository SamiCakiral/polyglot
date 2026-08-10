# W19L-A report: local backup and restore rehearsal

## Status

`PASS` for the local synthetic rehearsal implementation and its disposable
PostgreSQL execution. This is explicitly not W19C, PITR, cloud, canary, or
release proof.

## Delivered scope

- `scripts/restore-rehearsal.sh` accepts explicit or environment-provided DSNs,
  object paths, `FX-OPS`, and a JSON report path. It uses strict Bash, refuses
  equal sources/targets, creates temporary artifacts with cleanup, performs no
  retry, redacts DSNs, and never writes to the source after the dump.
- `fixtures/canonical/FX-OPS/` is synthetic only: active account, pending
  outbox, logical tombstone, no-resurrection oracle, and fictitious private
  object with SHA-256 oracle.
- The runbook and JSON schema example document preparation, validation,
  failure handling, cleanup, and the W19L/W19C boundary.

## Evidence

- RED: `uv run pytest tests/performance/test_restore_rehearsal.py -q` initially
  failed because both the script and the FX-OPS object fixture were absent.
- GREEN, deterministic checks: `uv run pytest tests/performance/test_restore_rehearsal.py -q`
  returned `3 passed, 1 skipped`; the opt-in real test is skipped unless
  `W19_REAL_TEST=1` is set.
- Real disposable rehearsal: `W19_REAL_TEST=1 uv run pytest
  tests/performance/test_restore_rehearsal.py -q` returned `5 passed in 5.31s`.
  It started independent source/target PostgreSQL 17 containers, migrated and
  seeded only the source, used `pg_dump` format custom and `pg_restore`, and
  checked migration head, account, outbox, tombstone, no resurrection, and
  copied-object checksum.
- Final static checks passed: `bash -n`, Ruff format/check, FX-OPS payload
  checksums, and `git diff --check`.
- Gitleaks v8.30.0 scanned the W19L-A write set through read-only mounts and
  returned `no leaks found`. A whole-repository scan found unrelated existing
  findings and cache-read errors, so it is not used as this sub-lot's result.

## Limits

- `shellcheck` is not installed on this workstation, so no ShellCheck result is
  claimed.
- Host `pg_dump`, `pg_restore`, and `psql` are absent. The real test used the
  PostgreSQL 17 tools inside disposable containers through test-local wrappers;
  the production script reports `PARTIAL` when the required local tools are
  absent.
- No Compose file, business backend, migration, frontend, CI, cloud resource,
  secret, user datum, or deployment workflow was modified.
