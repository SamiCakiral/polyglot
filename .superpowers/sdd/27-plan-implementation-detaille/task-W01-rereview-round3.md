# W01 Re-review - Fix round 3

## Verdict

**REQUEST CHANGES.** The immutable Trivy action/binary pins and the
reserve-only-started command receipt contract are resolved. The deletion
function itself now locks and validates a confirmed request, scopes deletion,
transitions the request, creates/updates a tombstone, and audits atomically.
However, the distinct-role security boundary is not used by the actual runtime:
Compose, CI, migrations, and application sessions still connect as the same
`polyglot` PostgreSQL superuser. That account bypasses all function ACLs, so the
round-2 destructive-purge Critical remains open operationally.

Hosted CI has not run. Reported tests remain unverified; no test suite was rerun
for this review.

## Scope and method

- Reviewed the brief, round-2 open findings, updated report, and only the
  `5db85e2..fefc9bf` implementation diff for new behavior.
- Confirmed the checkout is exactly `fefc9bf`.
- Adjudicated the three requested blockers and inspected their changed tests for
  bypasses and false evidence.
- Used `git ls-remote` only to verify the Trivy release tag-to-commit mapping; no
  local or broad suite was executed.
- `git diff --check 5db85e2..fefc9bf` is clean. This requested report is the only
  file written by the review.

## Critical finding

1. **The real runtime still connects as superuser, bypassing the new purge-role
   ACLs.** The migration creates three `NOLOGIN` group roles and grants purge
   execution only to `polyglot_retention`
   (`backend/migrations/versions/0001_platform.py:18-30,624-647`). The function
   body is now appropriately request-authorized: it locks the deletion request,
   accepts only confirmed/purging state, verifies the exact subject, performs
   deletion, writes the tombstone, marks completion, and appends a fixed audit
   record in one transaction
   (`backend/migrations/versions/0001_platform.py:524-622`).

   Those ACLs do not constrain the deployed connection. Compose still sets
   `POSTGRES_USER=polyglot` (`compose.yaml:4-9`), and the CI migration/test URLs
   still authenticate as `polyglot` (`.github/workflows/ci.yml:89-106`). The
   Docker Official PostgreSQL image creates the `POSTGRES_USER` account with
   superuser power
   ([official image documentation](https://github.com/docker-library/docs/blob/master/postgres/README.md)).
   The application and Alembic both consume the same generic
   `POLYGLOT_DATABASE_URL` (`backend/src/polyglot/bootstrap/database.py:13-22`;
   `backend/migrations/env.py:21-35`); there is no runtime, migration, or
   retention login-role provisioning or separate connection configuration.
   PostgreSQL superusers bypass object privilege checks
   ([PostgreSQL role documentation](https://www.postgresql.org/docs/17/role-attributes.html)),
   so normal application code can still instantiate `SqlRetentionStore` and
   execute either purge function despite the revokes.

   The tests conceal this by starting with the `polyglot` superuser and manually
   issuing `SET LOCAL ROLE polyglot_runtime` for the denial case or
   `SET LOCAL ROLE polyglot_retention` for purge execution
   (`backend/tests/integration/platform/test_migration.py:257-303`;
   `backend/tests/integration/platform/test_retention.py:115-124,184-195,271-283`).
   They prove the group-role ACL definitions, not that the actual application
   connection is least privileged.

   Provision distinct login identities outside the superuser runtime path,
   grant each only its intended group role, and configure separate migration,
   application, and retention-worker URLs. Compose and CI must run the app/tests
   under the runtime login and invoke purge through a retention login; Alembic
   alone may use the migration identity. Add independent-connection tests proving
   runtime denial and retention success without `SET ROLE` from a superuser.

## Requested blocker disposition

| Blocker | Verdict | Evidence |
|---|---|---|
| Authorized deletion-request purge, distinct roles, tombstone | **Partial; Critical open** | Request locking/state/subject validation, exact private-event deletion, request completion, tombstone upsert, fixed audit, and rollback behavior are implemented atomically (`0001_platform.py:524-622`). Group ACLs are defined, but the actual runtime remains the `polyglot` superuser and bypasses them. |
| Safe immutable Trivy action and binary pin | **Resolved** | Both scanner steps use full action commit `ed142fd0673e97e23eac54620cfb913e5ce36c25` annotated as `v0.36.0` and explicitly pin Trivy `v0.69.3` (`.github/workflows/ci.yml:67-85`). Live `git ls-remote` verification mapped `refs/tags/v0.36.0^{}` to that commit. `v0.69.3` is listed as safe by Aqua's incident advisory ([GHSA-69fq-xp46-6x23](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23)). Contract tests reject mutable, affected, latest, and missing-version variants (`backend/tests/contract/platform/test_ci.py:12-48,81-111`). |
| Reserve-only-started closed receipt state | **Resolved** | `CommandReceipt.__post_init__` and `reserve()` both require `started` with null result fields; terminal hydration is internal (`records.py:61-86`; `repositories.py:83-126`). The SQL constraint now fails closed with explicit non-null/object checks, integer-version syntax, closed error codes, matching message keys, and outer `IS TRUE` (`0001_platform.py:34-81,83-130`). Tests cover constructor, forged-object store bypass, SQL null/open/error/version shapes, and normal terminal replay (`test_command_receipts.py:249-367`). |

## Test validity and new breakage

- Deletion-request tests validly cover absent, unconfirmed, and mismatched
  requests, exact-subject preservation, atomic completion, tombstone contents,
  and audit linkage. Their role test is insufficient because every connection
  begins as superuser and privilege separation is simulated with `SET ROLE`.
- The Trivy contract is static but appropriately verifies exact immutable action
  and binary pins. The action commit mapping was independently confirmed during
  this review. Hosted execution remains an external evidence gap, not a source
  defect in this fix.
- Receipt tests cover the prior constructor/store/SQL bypasses and preserve
  terminal replay by using an internal stored-row hydrator. No new
  Critical/Important receipt defect was found.
- Creating cluster-global roles in the Alembic migration requires a
  role-administration-capable migration identity and leaves those roles after
  `downgrade()` drops only the schema (`0001_platform.py:18-30,659-660`). This
  should be addressed by the required login-role provisioning design rather than
  relying on the application migration to bootstrap production identities.
- No other new Critical or Important breakage was found in the supplied fix
  diff. All report test and scanner claims remain unverified.

## Acceptance status

W01 does not pass at `fefc9bf`. The SQL deletion workflow, Trivy gate source, and
receipt state machine are acceptable, but W01 still needs real least-privilege
database connection wiring and proof before the destructive purge boundary can
be accepted. After that change, run the full matrix and hosted CI. The existing
digest-scoped `CVE-2025-68121` exception remains non-blocking and time-bounded.
