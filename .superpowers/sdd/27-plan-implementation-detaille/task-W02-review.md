# W02 Review - Identity, Sessions and Consent

**Verdict: REQUEST CHANGES**

Reviewed base `2350974` to head `a0f9b39` from the supplied review package. The
package was read once; no Git command was run. The implementation report is treated
as unverified. No test was run because the blocking doubts are statically resolved
and this review may not mutate the database or services.

## Ordered findings

1. **Critical - Rotation defeats the seven-day absolute session limit.**
   `AuthSession.issue()` always sets `authenticated_at = now` and
   `absolute_expires_at = now + 7 days`; `_resolve_session()` uses it for every role
   or 24-hour rotation. A continuously used session can therefore rotate forever,
   and each rotation also makes it appear freshly authenticated. Preserve the
   original authentication instant and absolute deadline across the rotation chain,
   and reject rotation once that deadline is reached. Add a regression that rotates
   daily and is rejected at the original seven-day boundary.
   Evidence: `backend/src/polyglot/modules/identity/domain.py:318`,
   `backend/src/polyglot/modules/identity/domain.py:323`,
   `backend/src/polyglot/modules/identity/application.py:702`,
   `backend/src/polyglot/modules/identity/application.py:705`.

2. **Important - Rotation on a mutation revokes the browser cookie without delivering the replacement.**
   `_resolve_session()` returns a new token after revoking the old session, but the
   preference and consent commands discard both returned secrets and their HTTP
   handlers never refresh the cookie. The first mutation after a role/24-hour
   boundary can succeed and then leave the client authenticated only with a revoked
   token. Propagate rotation metadata through every authenticated command and set the
   replacement cookie/CSRF state atomically in the response.
   Evidence: `backend/src/polyglot/modules/identity/application.py:719`,
   `backend/src/polyglot/modules/identity/application.py:725`,
   `backend/src/polyglot/modules/identity/application.py:785`,
   `backend/src/polyglot/modules/identity/application.py:868`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:358`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:389`.

3. **Important - Session rotation is racy and bypasses event/audit consistency.**
   Session lookup does not lock the row, and the result of the conditional revoke is
   ignored before inserting a replacement. Two requests using the same old token can
   both mint valid successors. Rotation also writes neither the mandatory session
   creation/revocation audit records nor outbox events. Lock/CAS the old session,
   create at most one successor, reload that successor for losing requests, and emit
   the rotation facts in the same transaction.
   Evidence: `backend/src/polyglot/modules/identity/persistence.py:637`,
   `backend/src/polyglot/modules/identity/persistence.py:768`,
   `backend/src/polyglot/modules/identity/application.py:719`,
   `backend/src/polyglot/modules/identity/application.py:724`,
   `docs/v2/17-securite-confidentialite-jobs-medias.md:126`.

4. **Important - Local authentication exposes a practical account timing oracle and has no login throttle.**
   Unknown identifiers return before Argon2, while known identifiers with a wrong
   valid-length password execute the expensive Argon2id verification. Equal HTTP
   status/body tests do not cover this observable difference. The identity route and
   service also contain no distinct login rate limit despite document 17. Always run
   one verification against a fixed valid dummy Argon2id hash on misses/invalid
   identifiers, and add bounded per-origin/IP plus identifier throttling with the
   canonical `rate_limited` error.
   Evidence: `backend/src/polyglot/modules/identity/application.py:495`,
   `backend/src/polyglot/modules/identity/application.py:498`,
   `backend/src/polyglot/modules/identity/application.py:502`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:245`,
   `docs/v2/17-securite-confidentialite-jobs-medias.md:141`.

5. **Important - Secret-bearing command objects expose passwords and OIDC codes through `repr`.**
   The routes correctly accept `SecretStr`, but immediately unwrap the values into
   normal strings stored in dataclasses whose generated representation includes all
   fields. Logging/tracing a command or exception context can disclose current/new
   passwords and authorization codes, contrary to the no-secret-in-logs boundary.
   Use a redacted secret value type and/or `field(repr=False)` for every credential;
   add a regression over command representations and structured logs.
   Evidence: `backend/src/polyglot/modules/identity/application.py:60`,
   `backend/src/polyglot/modules/identity/application.py:70`,
   `backend/src/polyglot/modules/identity/application.py:88`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:230`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:258`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:340`.

6. **Important - Public registration idempotency is scoped by the account produced by the request.**
   A replay with the same `Idempotency-Key` but a different unused identifier gets a
   new candidate `actor_id`, so it does not collide with the first receipt and creates
   a second account/event. The current conflicting-replay test changes only the
   password while retaining the first identifier, so it misses this case. Reserve
   public registration keys in a stable anonymous command scope before choosing an
   account, then compare the full fingerprint.
   Evidence: `backend/src/polyglot/modules/identity/application.py:385`,
   `backend/src/polyglot/modules/identity/application.py:405`,
   `backend/src/polyglot/modules/identity/application.py:410`,
   `backend/migrations/versions/0001_platform.py:119`,
   `backend/tests/integration/identity/test_application.py:94`.

7. **Important - Completed password-change and logout commands cannot actually be replayed.**
   Both paths validate an active session before looking up the command receipt. Their
   first success revokes that session; password change also replaces the password
   before receipt lookup on a retry. An exact retry after a lost response therefore
   returns `unauthenticated`/`invalid_credentials` instead of the stored terminal
   result, violating `required`/`supported` idempotency. Permit only an exact replay
   of an already-terminal receipt to be resolved from the revoked session identity;
   never allow that path to execute a new effect.
   Evidence: `backend/src/polyglot/modules/identity/application.py:958`,
   `backend/src/polyglot/modules/identity/application.py:969`,
   `backend/src/polyglot/modules/identity/application.py:981`,
   `backend/src/polyglot/modules/identity/application.py:1006`,
   `backend/src/polyglot/modules/identity/application.py:1063`,
   `backend/src/polyglot/modules/identity/application.py:1072`.

8. **Important - Optimistic concurrency is incomplete for password and consent updates.**
   `ChangePassword` accepts no `If-Match`; it records a server-read version but does
   not use it in either password or account updates, so two requests verified against
   the same old password can both succeed and the last hash wins. Consent performs a
   separate `max(version)` read and insert without a lock, so concurrent writers can
   surface an unhandled uniqueness error as `internal_error` instead of
   `version_conflict`. Require the canonical client version for password changes and
   condition every write on it; serialize consent `(account,purpose)` or make the
   expected-version insert atomic and map the race to `version_conflict`.
   Evidence: `backend/src/polyglot/interfaces/http/routes/identity.py:332`,
   `backend/src/polyglot/modules/identity/application.py:988`,
   `backend/src/polyglot/modules/identity/persistence.py:593`,
   `backend/src/polyglot/modules/identity/persistence.py:725`,
   `backend/src/polyglot/modules/identity/persistence.py:740`,
   `docs/v2/25-registre-enums-commandes-api.md:112`.

9. **Important - The generated OpenAPI omits the security and error contract enforced at runtime.**
   `Origin`, `X-CSRF-Token`, `If-Match`, and the session cookie are read manually, so
   none appears in OpenAPI; no cookie security scheme exists, and identity operations
   advertise only success/422 rather than their RFC 9457 401/403/409/423 responses.
   The credential schema also cannot express the runtime-exclusive local/OIDC shapes.
   Model these as typed dependencies/headers and a discriminated request union, add
   shared problem responses/security schemes, and make registry compatibility verify
   required operations and contract details rather than only rejecting unknown paths.
   Evidence: `backend/src/polyglot/interfaces/http/routes/identity.py:31`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:125`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:130`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:147`,
   `contracts/openapi/v1.json:589`, `contracts/openapi/v1.json:640`,
   `contracts/openapi/v1.json:854`,
   `backend/src/polyglot/interfaces/http/export_openapi.py:41`.

10. **Important - `FX-USERS`/`FX-AUTH` are not valid W00 fixture manifests and contain a noncanonical error.**
    The closed W00 schema requires `id`, `kind`, and `expected_status`, while both
    manifests use undeclared fields such as `fixture_code`, `clock`, `payloads`, and
    `oracles`; the tests self-check those fields instead of validating the canonical
    schema. `FX-AUTH` also expects `session_expired`, which is absent from W00 and from
    the implementation (`unauthenticated` is returned). Resolve the manifest shape
    through W00/RFC ownership, validate it with the actual schema, and use only a
    registered error code.
    Evidence: `contracts/fixtures/manifest.schema.json:5`,
    `contracts/fixtures/manifest.schema.json:6`,
    `fixtures/canonical/FX-USERS/manifest.json:2`,
    `fixtures/canonical/FX-AUTH/manifest.json:2`,
    `fixtures/canonical/FX-AUTH/auth.json:9`,
    `backend/tests/contract/identity/test_fixtures.py:33`,
    `docs/v2/27-plan-implementation-detaille.md:189`.

11. **Important - The documented rollback is destructive and its claimed kill switches do not exist.**
    The report tells operators to disable registration/OIDC and downgrade, but runtime
    wiring has no registration/OIDC feature flag and always mounts registration; the
    downgrade drops the entire identity schema, including append-only consent and
    account history. Implement the specified switches and a global-revoke procedure,
    and document application rollback with `0002_identity` left in place. Restrict the
    destructive downgrade to disposable environments with an explicit data-loss
    warning.
    Evidence: `.superpowers/sdd/27-plan-implementation-detaille/task-W02-report.md:173`,
    `.superpowers/sdd/27-plan-implementation-detaille/task-W02-report.md:175`,
    `backend/src/polyglot/interfaces/http/app.py:66`,
    `backend/src/polyglot/interfaces/http/app.py:113`,
    `backend/migrations/versions/0002_identity.py:453`,
    `docs/v2/27-plan-implementation-detaille.md:78`.

## Non-blocking corrections and residual proof

- The report says personal tables **force** RLS, but the migration only enables it.
  Runtime is a non-owner and is still subject to the policies, so this is a report/test
  accuracy correction rather than a separate blocker. Evidence:
  `.superpowers/sdd/27-plan-implementation-detaille/task-W02-report.md:64`,
  `backend/migrations/versions/0002_identity.py:377`,
  `backend/tests/integration/identity/test_migration_0002.py:129`.
- The missing deployed-preview cookie/header scan and security/product approval are
  already disclosed by the implementation report and remain external acceptance
  gates, not additional code-review findings.
