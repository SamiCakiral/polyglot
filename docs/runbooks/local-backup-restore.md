# Local backup and restore rehearsal (W19L-A)

## Scope

This runbook rehearses a PostgreSQL custom-format backup and local filesystem
object copy using the synthetic `FX-OPS` fixture. It is local W19L evidence
only. It does not establish W19C cloud readiness, PITR, canary readiness, or a
release decision.

## Preparation

1. Install PostgreSQL client tools compatible with the source server:
   `pg_dump`, `pg_restore`, and `psql`.
2. Create two disposable PostgreSQL databases. The source is seeded before the
   rehearsal; the target must be empty. Never point either option at a shared,
   staging, or production database.
3. Create two separate local directories. Copy
   `fixtures/canonical/FX-OPS/objects/` into the source directory and create an
   empty target directory.
4. On the disposable source only, migrate to the fixture head and load
   `fixtures/canonical/FX-OPS/seed.sql`. The seed has one active account, one
   pending outbox record, one logical tombstone, and no account for the
   tombstoned subject.
5. Pass connection strings through the shell environment or command arguments.
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

The script refuses equal source/target DSNs or object directories, refuses a
nonempty object target, creates temporary backup artifacts, and removes them
on exit. It reads the source only, writes the custom-format archive with
`pg_dump`, copies files in manifest order, and restores only to the target with
`pg_restore`.

## Validation

Read the JSON report rather than terminal output. A valid `PASS` report records:

- the current Git revision and UTC timestamp;
- expurgated source and target identifiers, never credentials;
- PostgreSQL client tool versions;
- SHA-256 fingerprints for the archive and object manifest;
- the expected migration head;
- the active account, pending outbox, logical tombstone, no-resurrection, and
  object checksum oracles.

`docs/evidence/W19/restore-report.example.json` is schema documentation only;
it is synthetic and is not execution evidence.

## Failure handling

`FAIL` means a required safety or integrity check failed. `PARTIAL` means local
preconditions such as PostgreSQL client tooling are unavailable. Neither result
is a pass. The script performs no retry. Preserve the report, discard the
disposable target database and object directory, correct the local setup, and
re-run only with new disposable targets.

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
