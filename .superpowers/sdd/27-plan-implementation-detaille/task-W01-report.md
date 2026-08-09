# W01 Report

## Status

DONE_WITH_CONCERNS - review fixes implemented and locally verified. Hosted CI is
prepared but has not been run or claimed green.

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
- Integration/contract: 50 passed in 3.73s. This includes job claim/renewal/
  takeover/success/failure/retry, immutable attempts, controlled purge,
  stable idempotency replay, inbox divergence, outbox fencing, migration
  completeness, installed-wheel migration round trip, RFC 9457, event boundary,
  FX-OPS, Compose and OpenAPI checks.
- Deterministic OpenAPI check: passed.
- Repository plus full Git history secret scan: clean.
- `pip-audit` over uv's hashed production dependency export: no known
  vulnerabilities.
- `git diff --check`: passed before report update.

## Architecture disposition

- `jobs` remains mutable aggregate state; `job_claims` owns renewable/fenced
  lease state; `job_attempts` stores terminal append-only facts only.
- Domain events and security audit remain append-only for ordinary writes.
  Expired rows can only be removed through the transaction-authorized,
  `SECURITY DEFINER` purge function, which writes a new audit entry.
- Object storage remains the explicit local filesystem placeholder. A real
  object-store adapter remains deferred to W15.
- OpenAPI validation is deliberately a W01 route-membership guard for the two
  health routes, not a claim of complete W00 API compatibility.

## Concerns

- Local Trivy found one fixed Critical in the official pinned PostgreSQL image:
  `CVE-2025-68121` in the Go standard library embedded in `gosu` 1.24.6. The
  current official `postgres:17-alpine` digest is unchanged. The prepared hosted
  Trivy gate is expected to surface this until the official image is rebuilt or
  a reviewed VEX exception is approved.
- Docker Scout could not run without Docker Hub authentication; Trivy provided
  the local image evidence instead.
- GitHub-hosted CI has not been run. The parent must push and verify it.
