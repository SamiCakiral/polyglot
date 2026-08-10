# W02 Scoped Re-review - Fix Round 1

**Verdict: REQUEST CHANGES**

Reviewed base `a0f9b39` to head `c124d8a` from the supplied fix package only. No
Git command was run. The updated implementation report is treated as unverified.
No test was run because the two remaining blockers are directly established by
the patch and do not require runtime or database proof.

## Original finding verdicts

1. **Critical - CLOSED.** Rotation now preserves `authenticated_at` and the
   original `absolute_expires_at`, bounds idle expiry by that deadline, and
   refuses rotation at expiry. Evidence:
   `backend/src/polyglot/modules/identity/domain.py:356`,
   `backend/src/polyglot/modules/identity/domain.py:360`.
2. **Important - CLOSED.** Preference and consent mutations return a session
   continuation and apply the replacement cookie and CSRF response header when
   rotation occurred. Evidence:
   `backend/src/polyglot/interfaces/http/routes/identity.py:218`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:453`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:487`.
3. **Important - CLOSED.** Rotation is serialized by a transaction-scoped
   advisory lock, conditionally revokes one predecessor, reuses its successor
   for a waiting request, and emits the rotation event/audit facts in the same
   transaction. Evidence:
   `backend/src/polyglot/modules/identity/persistence.py:691`,
   `backend/src/polyglot/modules/identity/application.py:797`,
   `backend/src/polyglot/modules/identity/application.py:940`.
4. **Important - CLOSED.** Local authentication performs one Argon2id verify
   using a valid dummy hash on misses and applies bounded source plus identifier
   throttling with `rate_limited`. Evidence:
   `backend/src/polyglot/modules/identity/application.py:54`,
   `backend/src/polyglot/modules/identity/application.py:60`,
   `backend/src/polyglot/modules/identity/application.py:594`.
5. **Important - CLOSED.** Passwords, OIDC codes, session tokens and CSRF tokens
   are excluded from command/result representations. Evidence:
   `backend/src/polyglot/modules/identity/application.py:121`,
   `backend/src/polyglot/modules/identity/application.py:139`,
   `backend/src/polyglot/modules/identity/application.py:147`.
6. **Important - CLOSED.** Registration receipts use a stable anonymous actor
   and aggregate before account allocation, so a key cannot create a second
   account under a different identifier. Evidence:
   `backend/src/polyglot/modules/identity/application.py:53`,
   `backend/src/polyglot/modules/identity/application.py:487`.
7. **Important - CLOSED.** Password change and logout load the terminal session
   identity and consult the receipt before requiring the session to remain
   active, while a fresh command on the revoked session is still rejected.
   Evidence: `backend/src/polyglot/modules/identity/application.py:981`,
   `backend/src/polyglot/modules/identity/application.py:1249`.
8. **Important - CLOSED.** Password changes require the client version and use
   account and password compare-and-swap writes; consent streams are serialized
   and version races map to `version_conflict`. Evidence:
   `backend/src/polyglot/interfaces/http/routes/identity.py:400`,
   `backend/src/polyglot/modules/identity/persistence.py:762`,
   `backend/src/polyglot/modules/identity/persistence.py:854`.
9. **Important - OPEN.** The OpenAPI security/header contract remains
   inaccurate. See finding 1 below.
10. **Important - CLOSED.** Both fixture manifests now use the W00 closed shape,
    are validated with the canonical schema, and `FX-AUTH` uses the registered
    `unauthenticated` error. Evidence:
    `backend/tests/contract/identity/test_fixtures.py:45`,
    `fixtures/canonical/FX-AUTH/auth.json:9`,
    `fixtures/canonical/FX-AUTH/manifest.json:2`,
    `fixtures/canonical/FX-USERS/manifest.json:2`.
11. **Important - OPEN.** The migration guard is bypassed by the packaged
    round-trip entry point. See finding 2 below.

## Open findings

1. **Important - Finding 9: mandatory runtime headers are still optional in OpenAPI.**
   `Origin`, `X-CSRF-Token`, and `If-Match` are all declared as nullable and every
   route parameter defaults to `None`, so the generated contract marks them
   `required: false`. Runtime then rejects an omitted Origin/CSRF header and an
   omitted `If-Match`. The compatibility check compares parameter names only and
   therefore accepts this mismatch. Generated clients may validly omit headers
   that every successful call requires. Make the applicable typed headers
   non-nullable/required and make compatibility assert `required: true`, not just
   presence. Evidence:
   `backend/src/polyglot/interfaces/http/routes/identity.py:27`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:28`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:29`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:166`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:188`,
   `backend/src/polyglot/interfaces/http/export_openapi.py:59`,
   `backend/src/polyglot/interfaces/http/export_openapi.py:122`.

2. **Important - Finding 11: packaged round-trip silently opts into permanent data loss.**
   The migration itself now fails closed unless
   `POLYGLOT_ALLOW_DESTRUCTIVE_IDENTITY_DOWNGRADE=true`, but `round_trip()` sets
   that variable to `true` internally before downgrading to base. The packaged
   CLI dispatches directly to this helper, so an operator can invoke
   `round-trip` without the promised explicit disposable-environment opt-in and
   still drop the identity schema. Remove the internal override and require the
   caller to supply the flag; CI already supplies it explicitly. Evidence:
   `backend/src/polyglot/bootstrap/migrations.py:24`,
   `backend/src/polyglot/bootstrap/migrations.py:28`,
   `backend/src/polyglot/bootstrap/migrations.py:30`,
   `backend/src/polyglot/bootstrap/migrations.py:44`,
   `.github/workflows/ci.yml:50`.

## Scoped regression check

No additional W02 Critical or Important regression was found in the supplied fix
diff. Out-of-scope observations were not used to extend this review loop.
