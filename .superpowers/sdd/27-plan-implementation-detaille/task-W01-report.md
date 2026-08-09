# W01 Report

## Status

DONE_WITH_CONCERNS - round-four operational database identity fix implemented
and locally verified. Hosted CI is prepared but has not been run or claimed green.

## Review-fix commits

- `02e384b` test(platform): capture lifecycle retention red
- `2be5ac8` feat(platform): separate job claims and retention
- `89b1887` test(platform): capture replay fencing red
- `4cfa222` fix(platform): stabilize replay and fence outbox
- `181cc9c` test(platform): capture error event boundary red
- `5b40d16` fix(platform): enforce public event boundaries
- `b09e751` test(platform): capture migration artifact red
- `8a3a4b5` build(platform): ship and verify migration runtime
- `254f88d` test(contracts): restore cache bypass red
- `33f1b3e` fix(contracts): constrain local cache exemptions
- `4109a23` test(platform): capture ops security red
- `aa61dde` ci(platform): add ops and security gates
- `3aeed07` test(platform): capture canonical number red
- `3aee0a3` fix(platform): canonicalize JSON across runtimes
- `3f4041c` test(ci): capture uv audit export red
- `4a9bd2e` fix(ci): audit exported uv lock
- `59f93b5` docs(w01): record review fix evidence
- `5e3afaa` test(platform): capture scoped purge requirements
- `33ff638` fix(platform): authorize scoped private-event purge
- `43489be` test(platform): capture database-time lease fencing
- `25e6c13` fix(platform): fence terminal writes with database time
- `a8651a9` test(platform): capture closed receipt replay contract
- `3bfc585` fix(platform): bound command replay descriptors
- `23ffa84` test(ci): capture digest-scoped CVE disposition
- `6a11e4b` fix(ci): pin postgres and encode CVE disposition
- `ec582a2` docs(w01): preserve round-two review evidence
- `d58bf29` test(ci): capture Trivy expiry timestamp format
- `ed6ca4c` fix(ci): use Trivy-compatible VEX expiry
- `e3401d9` test(platform): capture authorized subject purge red
- `2e838ae` fix(platform): authorize deletion-request purge
- `46fa704` test(ci): capture immutable Trivy pins red
- `a92c118` fix(ci): pin safe Trivy action and binary
- `d6fbc54` test(platform): capture reservation boundary red
- `6fe85e3` fix(platform): close command reservation state
- `d89477c` docs(w01): preserve round-three review evidence
- `bdee1e6` test(platform): require workload database logins
- `5c7ccc2` fix(platform): isolate database workload identities

## RED evidence

- Job lifecycle and retention: 3 failed before `SqlJobStore`, mutable claims and
  controlled purge existed.
- Idempotency, inbox and outbox fencing: 9 failed before stable command results,
  complete command identity checks, divergent inbox detection and lease tokens.
- RFC 9457 and event boundary: 15 failed before `message_key`, closed HTTP
  handling, generic 500 handling, mandatory readiness and W00 event validation.
- Migration/artifact gates failed on missing hexadecimal constraints, absent
  packaged migrations/contracts, absent installed-wheel runner and absent CI
  downgrade gate.
- W00 cache adversarial test failed for both
  `contracts/tests/__pycache__/private.pyc` and `docs/.venv/secret.txt` before
  exact cache-root validation.
- Ops/security: 4 failed before the pinned image, FX-OPS, repository/history
  scanner and CI security jobs.
- RFC 8785 numeric equivalence: 1 failed because `1` and `1.0` produced different
  fingerprints.
- Dependency gate first failed because `pip-audit --locked` does not consume
  `uv.lock`; the final gate audits uv's fully pinned, hashed export.
- Round-two private-event RED: 5 contract cases failed because `DomainEvent`
  lacked account/profile subject scope; the integration contract also required
  the absent exact-subject purge function and schema columns.
- Round-two lease RED: 4 adversarial tests failed because backdated semantic
  timestamps let expired job success/failure and outbox ack/fail consume leases.
- Round-two receipt RED: 5 malformed/open descriptors persisted and the migration
  test failed on the absent replay-shape constraint (6 failures total).
- Round-two CI/VEX RED: 3 tests failed on the moving CI service tag and absent
  VEX/ignore artifacts. The actual Trivy gate then exposed its required RFC 3339
  expiry format; the added format test failed once before the ignore was fixed.
- Round-three purge authorization RED: 7 tests failed because the retention role,
  deletion-request validation/transition, tombstone uniqueness and role ACLs did
  not exist.
- Round-three Trivy RED: the current workflow failed the immutable-reference
  contract because both scanner steps used affected mutable `0.33.1` tags. Four
  adversarial mutations prove rejection of mutable, pre-0.35, `latest` and
  missing binary references.
- Round-three reservation RED: 9 tests failed because terminal/malformed
  reservations passed the domain/store boundaries and SQL accepted null/open
  terminal shapes.
- Round-four identity RED: Compose still rendered `POSTGRES_USER=polyglot`, CI
  had no provisioning step, all three integration URLs authenticated as the
  same `polyglot` account, and the retention environment reader did not exist.
  The focused contract run failed `2` of `11`; the real-login run failed all
  `3` identity/configuration cases. Purge tests were changed before production
  code to require independent runtime and retention connections without
  `SET ROLE`.

## GREEN evidence

- W00 validator: 22 tool fixtures, 6 policy simulations, documentation links,
  artifact boundary and registry valid.
- W00 unittest discovery: 23 passed, including both cache bypass cases.
- `uv lock --check`: 39 packages resolved with no lock drift.
- Ruff: all checks passed. Strict Mypy: 27 source files clean.
- Unit/property: 16 passed, including nested JSON and RFC 8785 vectors.
- Compose recreated the digest-pinned PostgreSQL service and reported healthy.
- Alembic: downgrade to base, upgrade to `0001_platform (head)`, one head,
  current at head, and `No new upgrade operations detected`.
- Integration/contract: 83 passed in 4.77s. This includes job claim/renewal/
  takeover/success/failure/retry, immutable attempts, controlled purge,
  stable idempotency replay, inbox divergence, outbox fencing, migration
  completeness, RFC 9457, event boundary, FX-OPS, Compose and OpenAPI checks.
- Deterministic OpenAPI check: passed.
- Repository plus full Git history secret scan: clean.
- `pip-audit` over uv's hashed production dependency export: no known
  vulnerabilities.
- `git diff --check`: passed before report update.
- Round-two focused GREEN: scoped purge/event/migration `18 passed`; job/outbox
  fencing `14 passed`; receipt/migration `15 passed`; digest/VEX/Compose `7
  passed`; VEX expiry `2 passed`. Ruff and strict Mypy remained clean.
- Final W00: 22 tool fixtures, 6 policy cases, documentation links, artifact
  boundary and registry valid; unittest discovery `23 passed`.
- Final W01: `uv lock --check` resolved 39 packages without drift; Ruff clean;
  strict Mypy clean across 27 source files; unit/property `16 passed`; Compose
  PostgreSQL healthy at the reviewed digest.
- Final migration/artifact: downgrade to base, upgrade to `0001_platform (head)`,
  exactly one head, current at head, no upgrade operations detected, installed
  wheel migration `1 passed`.
- Final security: repository/history secret scan clean; `pip-audit` found no
  known vulnerabilities; Trivy 0.69.3 filesystem scan found 0 Critical findings;
  the pinned PostgreSQL image scan found 0 unsuppressed Critical findings and
  reported the reviewed `gosu` finding suppressed by the scoped exception.
- Round-three focused GREEN: purge/migration `10 passed`; Trivy CI contract `7
  passed`; reservation boundary `20 passed`; combined focused suite `37 passed`.
- Official action verification: `git ls-remote` against
  `https://github.com/aquasecurity/trivy-action.git` resolved
  `refs/tags/v0.36.0^{}` to full commit
  `ed142fd0673e97e23eac54620cfb913e5ce36c25`. Both workflow steps use that SHA,
  annotate `v0.36.0`, and pin Aqua-advisory-safe Trivy binary `v0.69.3`.
- Round-four focused GREEN: an empty Compose volume bootstrapped three
  non-superuser login identities, the bootstrap script reran successfully,
  migration-login-only downgrade/re-upgrade succeeded, and the identity,
  retention, runtime-health, Compose/CI and installed-artifact selection passed
  `26` tests. Ruff remained clean and strict Mypy remained clean across `27`
  source files.
- Round-four final W00/W01: registry validation passed; W00 unittest discovery
  passed `23`; `uv lock --check` resolved `39` packages; unit/property passed
  `16`; the digest-pinned Compose database was healthy; Alembic reported one
  `0001_platform (head)`, current at head and no upgrade operations; the
  installed wheel migration passed `1`; integration/contract passed `88`; and
  deterministic OpenAPI validation passed.
- Round-four final security: repository/full-history secret scan was clean;
  `pip-audit 2.9.0` found no known vulnerabilities in the frozen hashed export;
  Trivy `0.69.3` reported `0` Critical repository findings and `0` unsuppressed
  Critical findings for the pinned PostgreSQL digest. The reviewed `gosu`
  exception remained the only suppressed image finding.

## Architecture disposition

- `jobs` remains mutable aggregate state; `job_claims` owns renewable/fenced
  lease state; `job_attempts` stores terminal append-only facts only.
- Domain events and security audit remain append-only for ordinary writes.
  Expired rows can only be removed through the transaction-authorized,
  `SECURITY DEFINER` purge function, which writes a new audit entry.
- Account/profile deletion uses a separate transaction authorization scoped to
  the exact subject and private privacy classes. The security-definer function
  locks a matching confirmed/purging deletion request, transitions it atomically
  to completed, removes matching outbox/event rows, leaves other subjects
  untouched, upserts the deletion tombstone and appends an audit linked to the
  deletion request.
- PostgreSQL group roles are explicit and distinct: `polyglot_migration` owns
  the purge functions but has execute revoked, `polyglot_runtime` is denied,
  and only `polyglot_retention` can execute them. Bootstrap provisions separate
  `polyglot_migration_login`, `polyglot_runtime_login` and
  `polyglot_retention_login` identities, each inheriting exactly one group.
  Alembic, application and retention connections authenticate independently;
  focused tests prove session identity, non-superuser attributes, single-group
  membership, runtime denial and retention success without `SET ROLE`.
- Cluster-global identities are owned by the bootstrap layer, not Alembic.
  Downgrade removes the application schema while preserving the identities, so
  the dedicated migration login can recreate the schema without `CREATEROLE`;
  deleting the Compose volume performs complete local identity cleanup.
- Job terminal writes and outbox terminal acknowledgements fence lease ownership
  against PostgreSQL `clock_timestamp()` in the same SQL statement while keeping
  caller timestamps as semantic fact timestamps.
- Command receipts accept only bounded success or problem descriptors. Their
  canonical payload limit is 512 bytes and the database enforces the closed
  status/result shape.
- New reservations are domain/store constrained to `started` with null result
  fields. Stored terminal receipts are hydrated internally and can only be
  reached through `complete()`; SQL checks fail closed on null payloads,
  non-integer versions, unknown error codes and message-key mismatches.
- Object storage remains the explicit local filesystem placeholder. A real
  object-store adapter remains deferred to W15.
- OpenAPI validation is deliberately a W01 route-membership guard for the two
  health routes, not a claim of complete W00 API compatibility.

## Round-two CVE disposition

- `CVE-2025-68121` is recorded as `not_affected` for only
  `postgres:17-alpine@sha256:742f40ea20b9ff2ff31db5458d127452988a2164df9e17441e191f3b72252193`
  and `usr/local/bin/gosu`: the affected `crypto/tls` path is not imported or
  executed by `gosu`'s credential-switch/exec surface.
- Owner: `platform-security`. Recheck: `2026-09-15`. Expiry:
  `2026-09-30T23:59:59Z`. The exception must be removed when an official rebuilt
  digest is adopted, and the tests/gate fail after the review window expires.

## Concerns

- GitHub-hosted CI has not been run or claimed green. The parent must push and
  verify the prepared workflow.
- The digest-scoped CVE exception requires recheck by `2026-09-15` and expires
  on `2026-09-30`; replacing the PostgreSQL digest requires updating Compose,
  CI, Trivy, VEX and the parity tests together.
