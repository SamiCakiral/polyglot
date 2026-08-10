# W02 Implementation Report - Identity, Sessions and Consent

Date: 2026-08-10

Branch: `codex/v2-rebuild`

Accepted base: `2350974`

Delivery state: implementation and local proof complete; no push performed and no
human product/security approval is asserted by this report.

## Scope Delivered

- Pure identity domain with the six canonical roles: `learner`, `author`,
  `reviewer`, `support`, `admin` and `worker`.
- Account lifecycle, strict local/OIDC identity shapes, NFKC/casefold identifier
  normalization, Argon2id password hashing and a deterministic fake OIDC port.
- Opaque server sessions with 12-hour learner idle timeout, 30-minute authoring
  idle timeout, seven-day absolute timeout, rotation after 24 hours and on role
  change, plus individual and global revocation.
- Session-derived opaque cookie and CSRF material. Only SHA-256 fingerprints are
  persisted. Provider credentials, plaintext passwords, recovery secrets and raw
  session/CSRF tokens are not persisted.
- Owner authorization expressed with actor, action, resource and scope, enforced
  authoritatively in the application and backed by PostgreSQL owner RLS.
- Versioned preferences and append-only consent decisions for the four seeded
  consent purposes.
- W01 command receipts, full identity-bound idempotency, immutable domain events,
  outbox facts, append-only security audit entries and RFC 9457 errors reused
  without changing the W00 registries.

## HTTP Contracts

The generated OpenAPI now exposes the W00 mappings:

- `POST /api/v1/accounts` - `RegisterAccount`
- `POST /api/v1/session` - `AuthenticateSession`
- `GET /api/v1/session` - current session, preferences and consent state
- `DELETE /api/v1/session` - `RevokeSession`
- `PUT /api/v1/account/password` - `ChangePassword`
- `PATCH /api/v1/account/preferences` - `UpdateUserPreferences`
- `PUT /api/v1/consents/{purpose}` - `UpdateConsent`

Mutations require an exact same-origin `Origin` and a CSRF token bound to the
resolved session. Authentication sets `__Host-polyglot_session` with `Secure`,
`HttpOnly`, `SameSite=Lax`, `Path=/` and no `Domain`. Closed request models reject
mixed local/OIDC credential shapes and resource owner identifiers supplied by a
client.

## Persistence

Migration `0002_identity` creates:

- `identity.accounts`
- `identity.login_identities`
- `identity.account_roles`
- `identity.auth_sessions`
- `identity.user_preferences`
- `identity.consent_purposes`
- `identity.consent_grants`

UUIDv7 checks, provider-shape checks, Argon2id checks, active identity/role
uniqueness, session deadlines and relevant indexes are database-enforced.
Consent facts are append-only. Personal tables enable RLS using the transaction-local
`app.user_id`; RLS is intentionally not forced, and the non-owner runtime identity is
subject to the policies. Narrow `SECURITY DEFINER` lookup functions are
granted only to the runtime identity and public execution is revoked. The
migration, runtime and retention PostgreSQL logins remain separate.

## Canonical Fixtures

- `FX-USERS`: six synthetic accounts, all six roles, one Argon2id local identity
  and crossed owner allow/deny oracles.
- `FX-AUTH`: expired session, mismatched CSRF fingerprints, fake OIDC assertion
  and stale-role session rotation oracle.
- Both closed W00 manifests contain only `id`, `kind` and `expected_status` and
  validate against `contracts/fixtures/manifest.schema.json`. Separate fixture
  metadata contains the schema version, deterministic integer seed, fixed aware
  clock, SHA-256 payload fingerprint and named oracles.
- Fixture contract tests reject plaintext credential, provider-token, recovery,
  session-token and CSRF-token fields.

## TDD Evidence

The implementation was committed as coherent RED/GREEN increments:

1. `9a096c8` `test(w02): add failing identity domain cases`
   - RED: identity domain/password modules and their policies were absent.
2. `8f5ce8f` `feat(w02): add identity domain policies`
   - GREEN: pure roles, identities, Argon2id, sessions, preferences, consent and
     owner policy.
3. `5c96a6e` `test(w02): add failing identity persistence cases`
   - RED: `0002_identity`, repositories, constraints and RLS were absent.
4. `f74c087` `feat(w02): persist identity with owner RLS`
   - GREEN: migration, repository, transaction-local actor and PostgreSQL proof.
5. `f181a7a` `test(w02): add failing command and session contracts`
   - RED: W00 commands/routes, secure cookie/CSRF and application workflows were
     absent.
6. `9266ba6` `feat(w02): expose identity commands and secure sessions`
   - GREEN: command service, HTTP routes, runtime wiring and generated OpenAPI.
7. `0f01203` `test(w02): add failing canonical fixture cases`
   - RED: three fixture tests failed because `FX-USERS` and `FX-AUTH` did not
     exist.
8. `5e4c334` `test(w02): add canonical identity fixtures`
   - GREEN: all three fixture contracts passed.
9. `f6998f2` `test(w02): reject mixed OIDC credentials`
   - RED: valid fake OIDC and no-persistence checks passed, but mixed OIDC/local
     credential bodies were accepted instead of returning validation errors.
10. `289f9cb` `fix(w02): close OIDC credential boundary`
    - GREEN: exact provider shapes enforced and installed-wheel proof extended to
      `0002_identity`.
11. `2fe8b29` `test(w02): capture session rotation review failures`
    - RED: original absolute expiry, mutation continuation, one-successor concurrency
      and rotation fact tests failed.
12. `decee04` `fix(w02): preserve linear session rotation chains`
    - GREEN: original authentication boundary, serialized successor creation and
      transactional session events/audits passed.
13. `d59b135` `test(w02): capture identity hardening failures`
    - RED: timing equalization, throttle, secret redaction, anonymous idempotency,
      terminal replay, CAS, kill-switch and global-revoke cases failed.
14. `1b4273f` `fix(w02): harden identity mutation semantics`
    - GREEN: all identity hardening and concurrency cases passed.
15. `3d66874` `test(w02): capture contract rollback failures`
    - RED: real W00 fixture schema, OpenAPI security/details and destructive downgrade
      guard tests failed.
16. `f518f20` `fix(w02): publish closed identity contracts`
    - GREEN: closed manifests, typed OpenAPI, stronger compatibility validation and
      explicit disposable downgrade passed.
17. `fe38691` `test(w02): reject timing padding as credential`
    - RED: an incomplete internal command could authenticate if its account password
      equaled the fixed timing-padding value.
18. `9a860a9` `fix(w02): close timing padding credential path`
    - GREEN: original credential shape is required for success while every local miss
      still performs one valid Argon2id verification.

## Adversarial Coverage

Automated tests cover duplicate and concurrent registration, idempotent replay,
conflicting replay, invalid credentials without account disclosure, locked and
deleted accounts, session fixation, individual/global revocation, expired idle
and absolute deadlines, 24-hour and role-change rotation, stale versions, IDOR,
cross-origin and missing-origin mutations, session-bound CSRF, consent replay and
conflict, strict OIDC/local unions and absence of persisted provider credentials.

## Final Verification

Local environment: macOS ARM64, CPython 3.13.11, uv locked environment and real
PostgreSQL 17 container with independent migration/runtime/retention logins.

- W00 registry validator: `contract registry valid`.
- W00 unittest discovery: 23 tests, `OK`.
- Locked environment: `uv sync --locked`, 48 packages resolved and 47 audited.
- Ruff: `All checks passed` for `src` and `tests`.
- Strict Mypy: `Success: no issues found in 35 source files`.
- Final committed-HEAD combined unit/property/integration/contract rerun, excluding
  the separately executed wheel test: `175 passed in 12.71s`.
- Exact focused W02 identity target matrix before the final combined rerun: `67 passed
  in 7.28s`; the terminal timing-padding regression and dummy-hash test then passed
  together (`2 passed in 0.49s`).
- Empty migration: base -> `0001_platform` -> `0002_identity` passed.
- Full guarded rollback/re-upgrade: `0002_identity` -> base -> head passed.
- Prior-revision migration: `0002_identity` -> `0001_platform` -> head passed.
- Destructive downgrade without
  `POLYGLOT_ALLOW_DESTRUCTIVE_IDENTITY_DOWNGRADE=true` failed closed with the explicit
  disposable-environment/permanent-data-loss error and left `0002_identity` current.
- Alembic: exactly one head, current at `0002_identity`, `No new upgrade operations
  detected`.
- Installed wheel: contains both migrations and its own guarded round trip passed (`1
  passed in 0.75s` on the final committed-HEAD rerun).
- Deterministic OpenAPI check: passed.
- Repository plus full Git history secret scan: clean.
- `pip-audit 2.9.0` over the frozen hashed production export: `No known
  vulnerabilities found`.
- Pinned Trivy 0.69.3 final-code filesystem scan: zero Critical vulnerabilities,
  misconfigurations or secrets.
- Pinned Trivy 0.69.3 PostgreSQL digest scan: zero unsuppressed Critical findings. The
  existing digest-scoped `gosu` CVE-2025-68121 exception remains the only suppression.
- `git diff --check`: passed before this report update.

All review-round database suites were executed serially. No final-head deadlock,
unexpected exception or failed assertion was observed.

## Write-Set Notes

The domain, migration, tests and fixtures remain inside the W02 write set. The
following adjacent W01-owned files were changed only where integration required
it:

- `backend/pyproject.toml` and `backend/uv.lock` pin Argon2 support and the test-only
  Draft 2020-12 `jsonschema` validator.
- `backend/migrations/env.py` registers W02 metadata for drift detection.
- `backend/src/polyglot/interfaces/http/app.py` wires the identity service with
  fail-closed runtime session/origin settings.
- W01 runtime-health and installed-artifact tests supply the new required test
  settings and assert `0002_identity` packaging.
- `contracts/openapi/v1.json` is the deterministic generated artifact.

No W00 canonical registry, command, query, enum, error or event contract was
rewritten.

## Rollback

Set `POLYGLOT_REGISTRATION_ENABLED=false` and/or `POLYGLOT_OIDC_ENABLED=false` at the
application configuration boundary, invoke the explicit account-wide session revoke
procedure when required, and revert the W02 application code while leaving
`0002_identity` in place. This production rollback preserves account, consent and
preference history. Downgrade is limited to disposable environments, requires
`POLYGLOT_ALLOW_DESTRUCTIVE_IDENTITY_DOWNGRADE=true`, and permanently deletes the
identity schema. Guarded migration round trips prove only that disposable test path.
Append-only platform event/audit facts remain immutable until retention applies.

## Concerns and Acceptance Boundary

- The brief names `docs/v2/25-matrice-tracabilite.md`, but that path does not
  exist at the accepted base. The available canonical document used here is
  `docs/v2/25-registre-enums-commandes-api.md`; traceability requirements are
  also represented in the existing docs set.
- No deployed preview environment was supplied, so cookie/header behavior was
  exercised dynamically through the ASGI application and real PostgreSQL, not
  through a remote preview URL.
- The inherited digest-scoped Trivy exception for CVE-2025-68121 still requires
  the W01 recheck/expiry process; W02 introduced no new suppression.
- Product and security approver sign-off remains a separate gate and is not
  inferred from green automated evidence.

## W02 Review Fix Round 1 - Exact Final Evidence

Final implementation head before this report commit: `9a860a9`.

- Review findings 1-3: original `authenticated_at` and seven-day absolute deadline
  survive every rotation; mutation-triggered successors are returned via secure cookie
  and CSRF response state; PostgreSQL advisory transaction locking plus revoke CAS
  creates one successor and writes creation/revocation event, outbox and audit facts in
  the same transaction.
- Review findings 4-8: fixed valid dummy Argon2id verification, bounded source and
  normalized-identifier throttling, secret-safe representations/logging, stable
  anonymous registration receipts, exact terminal replay, mandatory password
  `If-Match`, account/credential CAS and serialized consent versions are covered by
  focused real-PostgreSQL adversarial tests.
- Review findings 9-10: OpenAPI exposes the cookie security scheme, Origin, CSRF and
  If-Match headers, discriminated local/OIDC union and RFC 9457 responses; compatibility
  validation rejects missing W02 operations/security/details. FX-USERS and FX-AUTH are
  validated by `Draft202012Validator` against the real W00 manifest schema and use only
  registered errors.
- Review finding 11: runtime registration/OIDC switches and explicit global session
  revoke are exercised; application rollback retains `0002_identity`; destructive
  downgrade is opt-in and labelled permanent data loss.
- W00 evidence: registry validator `contract registry valid`; canonical unittest
  discovery 23 tests, `OK`.
- Final code matrix: `175 passed in 12.71s`; installed artifact and packaged migration
  round trip `1 passed in 0.75s`.
- Migration evidence: empty base-to-head, full guarded base rollback/re-upgrade and
  `0001_platform` downgrade/re-upgrade passed; exactly one head; current
  `0002_identity (head)`; `No new upgrade operations detected`.
- Quality/contracts: Ruff `All checks passed`; strict Mypy `Success: no issues found in
  35 source files`; deterministic OpenAPI check passed; `git diff --check` passed before
  this report edit.
- Security: repository plus Git-history secret scan clean; `pip-audit 2.9.0` reported
  `No known vulnerabilities found`; pinned Trivy `0.69.3` final-code filesystem scan
  found zero Critical vulnerabilities/misconfigurations/secrets; the pinned PostgreSQL
  digest scan found zero unsuppressed Critical vulnerabilities.
