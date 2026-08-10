# W02 Scoped Re-review - Fix Round 2

**Verdict: PASS**

Reviewed base `c124d8a` to head `cee8a43` from the supplied fix package only. No
Git command was run. The updated implementation report is treated as unverified.
No test was run because both closure decisions are directly established by the
patch and no concrete runtime doubt remains.

## Finding verdicts

1. **Required runtime headers in OpenAPI/compatibility - CLOSED.** `Origin`,
   `X-CSRF-Token`, and `If-Match` are now non-nullable header types and are
   required arguments on every applicable route. The generated contract marks
   them required strings, while supported `Idempotency-Key` headers remain
   optional. Registry compatibility now indexes parameters and rejects a
   mandatory header unless `required` is exactly `true`. Evidence:
   `backend/src/polyglot/interfaces/http/routes/identity.py:27`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:28`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:29`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:275`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:362`,
   `backend/src/polyglot/interfaces/http/routes/identity.py:395`,
   `backend/src/polyglot/interfaces/http/export_openapi.py:53`,
   `backend/src/polyglot/interfaces/http/export_openapi.py:68`,
   `backend/src/polyglot/interfaces/http/export_openapi.py:135`.

2. **Explicit destructive round-trip opt-in - CLOSED.** `round_trip()` no longer
   imports, sets, restores, or otherwise overrides
   `POLYGLOT_ALLOW_DESTRUCTIVE_IDENTITY_DOWNGRADE`; it calls the guarded
   downgrade with the caller's environment unchanged. The installed-artifact
   regression explicitly removes the flag and expects failure before setting it
   to `true` for the successful disposable round trip. Evidence:
   `backend/src/polyglot/bootstrap/migrations.py:23`,
   `backend/src/polyglot/bootstrap/migrations.py:25`,
   `backend/tests/integration/platform/test_installed_artifact.py:49`,
   `backend/tests/integration/platform/test_installed_artifact.py:67`.

## Scoped regression check

No new W02 Critical or Important breakage was introduced by the supplied fix
diff. No out-of-scope observation was used to extend the review loop.
