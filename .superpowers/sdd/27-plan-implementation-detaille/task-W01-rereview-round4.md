# W01 Re-review - Fix round 4

## Verdict

**REQUEST CHANGES.** The round-three Critical is resolved at the PostgreSQL
authorization boundary: the patch provisions three distinct non-superuser
logins, routes Alembic, runtime, and retention through separate environment
URLs, uses those identities in Compose and CI, and proves permissions through
independent connections without `SET ROLE`. Empty-volume initialization and
schema downgrade/re-upgrade are structurally coherent.

One new **Important** operational defect remains. Compose interpolates raw
passwords directly into SQLAlchemy URLs. Passwords containing ordinary URI
reserved characters such as `@`, `:`, or `/` produce a different username,
host, or database when parsed, so the advertised workload URLs can fail or
connect to the wrong endpoint. The committed contract tests use only
hyphenated passwords and therefore do not detect this.

Hosted CI and the report's broad test claims remain unverified. No broad suite
was rerun for this review.

## Scope and method

- Read the W01 brief, round-three report, updated implementation report, and
  only the supplied `fefc9bf..aeefaf3` fix diff.
- Confirmed the checkout is exactly `aeefaf3d01abb3b2883613ffd4337aff5f5c8c3b`.
- Inspected only operational identity provisioning, workload URL selection,
  Compose/CI use, independent connection proofs, empty-volume behavior, and
  cleanup/downgrade behavior.
- `git diff --check fefc9bf..aeefaf3` is clean.
- Did not run any broad suite. A focused read-only Compose-render and
  SQLAlchemy-URL parse check was run solely to adjudicate password handling.
  This requested report is the only file written by the review.

## Important finding

1. **Compose workload URLs break for passwords containing URI-reserved
   characters.** `compose.yaml:35-37` inserts each raw
   `POLYGLOT_*_DB_PASSWORD` between `user:` and `@host` in a URL. There is no
   encoding, validation, or documented URL-safe password restriction. A
   focused render with migration password `mig:r@tion/secret` produced:

   ```text
   postgresql+asyncpg://polyglot_migration_login:mig:r@tion/secret@127.0.0.1:55432/polyglot
   ```

   SQLAlchemy parsed that value as password `mig:r`, host `tion`, no port, and
   database `secret@127.0.0.1:55432/polyglot`. The runtime and retention URLs
   fail equivalently. The bootstrap itself safely receives the original secret
   as an environment value (`compose.yaml:8-10`; `bootstrap-identities.sh:4-12`),
   so the database role password and the client URL can disagree.

   The Compose contract fixes all three passwords to hyphen-only literals and
   asserts the directly interpolated URLs
   (`backend/tests/contract/platform/test_compose.py:9-16,89-102`). It therefore
   validates only the happy-path serialization and misses the malformed-URL
   case.

   Do not build database URLs by raw interpolation. Accept complete workload
   URLs as separately supplied secrets, construct them with SQLAlchemy's URL
   API from component variables, or percent-encode and adversarially test every
   password component. Include at least `:`, `@`, `/`, `%`, and `#` cases.

## Round-three Critical disposition

| Requirement | Verdict | Evidence |
|---|---|---|
| Distinct login provisioning | **Resolved** | `ops/postgres/bootstrap-identities.sh:24-73` creates three `NOLOGIN` groups and three separate `LOGIN` roles, forces all privileged role attributes off, sets independent passwords, and grants exactly the intended group memberships. Cross-workload memberships are revoked at lines 75-87. |
| Database and schema privilege separation | **Resolved** | Bootstrap revokes public/direct database rights and grants migration, runtime, and retention capabilities separately (`bootstrap-identities.sh:89-112`). Migration grants schema/table access and purge execution only as intended (`backend/migrations/versions/0001_platform.py:610-647`). |
| App, Alembic, and retention URL selection | **Partial; Important open** | Runtime and retention have distinct readers (`backend/src/polyglot/bootstrap/database.py:13-18`), and Alembic uses only `POLYGLOT_MIGRATION_DATABASE_URL` (`backend/migrations/env.py:21-35`). Identity selection is correct, but Compose-generated URLs are invalid for unescaped reserved characters. |
| Compose usage | **Partial; Important open** | Empty-volume init mounts the bootstrap script, health checks through the runtime login, and exposes three distinct URL keys (`compose.yaml:4-37`). The raw URL interpolation defect prevents these values from being generally operational. |
| CI usage | **Resolved** | CI initializes a fresh PostgreSQL service under a bootstrap identity, provisions before migration, and supplies three distinct workload URLs (`.github/workflows/ci.yml:87-130`). Its fixed URL-safe test passwords avoid the Compose defect but do not weaken CI's identity separation. |
| Independent connection proof without `SET ROLE` | **Resolved** | Fixtures open separate engines from the three URLs (`backend/tests/integration/platform/conftest.py:9-51`). Tests assert session identity, non-superuser attributes, exact direct membership, and privilege matrices (`test_migration.py:312-393`). Runtime denial and retention success no longer use `SET ROLE` (`test_migration.py:263-309`; `test_retention.py:64-290`). |
| Empty-volume reproducibility | **Resolved in source; reported execution unverified** | Compose installs the executable bootstrap script in `/docker-entrypoint-initdb.d` (`compose.yaml:23-25`), while CI explicitly runs the same script against its fresh service before Alembic. The script is idempotent for the declared roles and rotates their passwords on rerun. |
| Downgrade and cleanup | **Resolved in source; reported execution unverified** | Alembic now begins directly with schema creation and downgrade drops only that application schema (`0001_platform.py:18`; `0001_platform.py:646-647`). This permits re-upgrade with the migration login while retaining workload identities. In Compose, removing the named PostgreSQL volume removes the cluster and its roles; no external role state is created by the Compose init path. |

## New breakage and acceptance

No new Critical defect was found in the fix diff. The prior superuser-bypass
Critical is closed. W01 does not yet pass at `aeefaf3` because the new Compose
workload URL contract is not safe for unrestricted secret values. After URL
construction is made encoding-safe and covered by an adversarial contract test,
the operational least-privilege blocker can be accepted, subject to hosted CI.
