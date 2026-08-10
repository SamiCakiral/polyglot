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
Consent facts are append-only. Personal tables enable and force RLS using the
transaction-local `app.user_id`. Narrow `SECURITY DEFINER` lookup functions are
granted only to the runtime identity and public execution is revoked. The
migration, runtime and retention PostgreSQL logins remain separate.

## Canonical Fixtures

- `FX-USERS`: six synthetic accounts, all six roles, one Argon2id local identity
  and crossed owner allow/deny oracles.
- `FX-AUTH`: expired session, mismatched CSRF fingerprints, fake OIDC assertion
  and stale-role session rotation oracle.
- Both manifests include schema version, deterministic integer seed, fixed aware
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
- W00 unittest discovery: `23 passed`.
- Locked environment: `uv sync --locked`, 43 packages resolved and 42 audited.
- Ruff: all checks passed for `src` and `tests`.
- Strict Mypy: no issues in 35 source files.
- Final committed-HEAD unit/property rerun: `39 passed in 5.98s`.
- Exact W02 target matrix: `47 passed`.
- Empty migration: base -> `0001_platform` -> `0002_identity` passed.
- Full rollback/re-upgrade: `0002_identity` -> base -> head passed.
- Prior-revision migration: `0002_identity` -> `0001_platform` -> head passed.
- Alembic: exactly one head, current at `0002_identity`, no metadata drift.
- Installed wheel: contains both migrations and its own round trip passed (`1
  passed in 0.75s` on the final committed-HEAD rerun).
- Integration/contract matrix excluding the separately executed wheel test: `117
  passed in 8.88s` on the final clean serial rerun.
- Deterministic OpenAPI check: passed.
- Repository plus full Git history secret scan: clean.
- `pip-audit 2.9.0` over the frozen hashed production export: no known
  vulnerabilities.
- Trivy 0.69.3 filesystem scan: zero Critical findings.
- Trivy 0.69.3 pinned PostgreSQL image scan: zero unsuppressed Critical findings.
  The existing digest-scoped `gosu` CVE-2025-68121 exception is the only
  suppressed finding.
- `git diff --check`: passed before this report update.

One attempted final rerun overlapped a still-finishing all-suite invocation and
produced six PostgreSQL deadlocks between test cleanup `TRUNCATE` locks and test
writes. No assertion or product behavior failed. Process inspection confirmed no
remaining test process, and the same integration/contract command then passed
all 117 tests serially in 8.88s. The green serial result above is the acceptance
evidence.

## Write-Set Notes

The domain, migration, tests and fixtures remain inside the W02 write set. The
following adjacent W01-owned files were changed only where integration required
it:

- `backend/pyproject.toml` and `backend/uv.lock` pin Argon2 support.
- `backend/migrations/env.py` registers W02 metadata for drift detection.
- `backend/src/polyglot/interfaces/http/app.py` wires the identity service with
  fail-closed runtime session/origin settings.
- W01 runtime-health and installed-artifact tests supply the new required test
  settings and assert `0002_identity` packaging.
- `contracts/openapi/v1.json` is the deterministic generated artifact.

No W00 canonical registry, command, query, enum, error or event contract was
rewritten.

## Rollback

Disable registration/OIDC at the application configuration boundary, globally
revoke sessions when required, revert the W02 application commits and downgrade
`0002_identity` to `0001_platform`. The migration round trips prove this path.
Append-only platform event/audit facts remain immutable until their existing
retention policy applies.

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
