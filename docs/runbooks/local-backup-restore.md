# Local backup and restore rehearsal (W19L-A)

## Scope

This runbook rehearses a PostgreSQL custom-format backup and local filesystem
object copy using the synthetic `FX-OPS` fixture. It is local W19L evidence
only. It does not establish W19C cloud readiness, PITR, canary readiness, or a
release decision.

## Preparation

1. Install PostgreSQL client tools compatible with the source server:
   `pg_dump`, `pg_restore`, and `psql`.
   SHA-256 is selected portably from `sha256sum`, `shasum`, `openssl`, or the
   configured Python runtime.
2. Ensure the database operator can read `pg_control_system()` on both
   connections, either as a superuser in a disposable setup or through the
   PostgreSQL monitoring privileges approved for that setup. The script uses
   the cluster system identifier and database OID only for the isolation gate.
3. Create two disposable PostgreSQL databases. The source is seeded before the
   rehearsal; the target must be empty. Never point either option at a shared,
   staging, or production database.
4. Create two separate local directories. Copy
   `fixtures/canonical/FX-OPS/objects/` into the source directory and create an
   empty target directory.
5. On the disposable source only, migrate to the fixture head and load
   `fixtures/canonical/FX-OPS/seed.sql`. The seed keeps one active account and
   one pending outbox record. It also creates a second active account, records
   its completed deletion, removes it, and writes the corresponding tombstone.
6. Pass connection strings through the shell environment or command arguments.
   Do not place credentials in a shell history, report path, or committed file.

## Execution

Run from the repository root. The sample DSNs contain no password and are only
valid for a trusted disposable local setup.

```bash
./scripts/restore-rehearsal.sh \
  --fixture FX-OPS \
  --source-dsn 'postgresql://operator@127.0.0.1:55441/polyglot_source' \
  --target-dsn 'postgresql://operator@127.0.0.1:55442/polyglot_target' \
  --source-objects /tmp/fx-ops-source-objects \
  --target-objects /tmp/fx-ops-target-objects \
  --report /tmp/w19-restore-report.json
```

The script first validates DSN syntax without echoing malformed values. It then
connects to both databases and refuses equal cluster-system-identifier/database-
OID pairs, including `localhost`, `127.0.0.1`, DNS aliases, and tunnels resolving
to the same database. This gate runs before `pg_dump`. It also refuses equal
object directories and a nonempty object target, creates temporary backup
artifacts, and removes them on exit. It reads the source only, writes the
custom-format archive with `pg_dump`, copies files in manifest order, and
restores only to the target with `pg_restore`.

## Validation

Read the JSON report rather than terminal output. A valid `PASS` report records:

- the current Git revision and UTC timestamp;
- expurgated source and target identifiers, never credentials;
- PostgreSQL client versions and the selected SHA-256 provider;
- SHA-256 fingerprints for the archive and object manifest;
- equal logical database SHA-256 fingerprints generated from canonical FX-OPS
  rows on the source before dump and the target after restore;
- the expected migration head;
- source and target checks for the active account, pending outbox, completed
  deletion history, logical tombstone, deleted-account absence, and object
  checksum, followed by an explicit `tombstone_non_resurrection` check.

`docs/evidence/W19/restore-report.example.json` is schema documentation only;
it is synthetic and is not execution evidence.

## Failure handling

`FAIL` means a required safety or integrity check failed. `PARTIAL` means local
preconditions such as PostgreSQL client tooling are unavailable. Neither result
is a pass. The script performs no retry. Preserve the report, discard the
disposable target database and object directory, correct the local setup, and
re-run only with new disposable targets.

A malformed DSN is represented as `redacted` in the report. Its raw value is
never copied into an error, stdout, stderr, or a traceback. Missing or failing
SHA-256 providers also terminate through a structured `FAIL`/`PARTIAL` report.

Do not try to repair the target and re-run over it. Do not write to the source
after the dump, and do not infer recovery-point, cloud, canary, or release
coverage from this rehearsal.

## Cleanup

After capturing the report, remove both disposable databases and both temporary
object directories. The script deletes its own temporary dump and manifests via
an exit trap; it never deletes the source or target directories supplied by the
operator.

## W19L/W19C boundary

W19L-A proves only a reproducible local rehearsal with synthetic data. W19C
remains responsible for managed cloud backup and recovery, IAM and secrets,
hosted observability, approval, rollback evidence, and canary promotion.
