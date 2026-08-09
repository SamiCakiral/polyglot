# W01 Re-review - Fix round 5

## Verdict

**PASS.** The sole round-four Important finding is fully resolved. Compose no
longer constructs database URLs by interpolating raw passwords. It exposes
structured connection components, and the shared SQLAlchemy `URL.create`
builder safely renders migration, runtime, and retention URLs while preserving
their distinct identities. The adversarial contract covers `:`, `@`, `/`, `%`,
and `#` for all three passwords and verifies the parsed connection components.

No load-bearing Critical or Important finding remains in the scoped
`aeefaf3..2f0f6b3` fix. Hosted CI and the updated report's broad test claims
remain unverified, but that is external evidence/polish rather than a source
blocker for this breaker round. No broad suite was rerun.

## Scope and method

- Read the round-four open finding, updated W01 report, and only the supplied
  `aeefaf3..2f0f6b3` fix diff.
- Confirmed the checkout is exactly `2f0f6b35b6aac230c2e038d5e88289380b727ff4`.
- Inspected only reserved-character-safe configuration, workload URL routing,
  preservation of identity separation, and changed tests for false evidence or
  new Critical/Important breakage.
- `git diff --check aeefaf3..2f0f6b3` is clean.
- Did not rerun tests. This requested report is the only file written by the
  review.

## Finding disposition

| Requirement | Verdict | Evidence |
|---|---|---|
| Remove raw password interpolation | **Resolved** | `compose.yaml:34-44` replaces `x-polyglot-database-urls` with structured driver, host, port, database, username, and password values. Passwords are no longer embedded in URI authority strings by Compose. |
| Reserved-character-safe URL construction | **Resolved** | `workload_database_url_from_environment()` builds component-based URLs with SQLAlchemy `URL.create` and renders them explicitly (`backend/src/polyglot/bootstrap/database.py:23-41`). This encodes URI-reserved password characters without changing the underlying password. |
| Distinct migration/runtime/retention selection | **Resolved** | The explicit-URL map remains closed by workload (`database.py:16-20`), component variable names are workload-prefixed (`database.py:32-39`), and the three public readers select only migration, runtime, or retention respectively (`database.py:44-53`). |
| Alembic separation | **Resolved** | Alembic now calls only `migration_database_url_from_environment()` (`backend/migrations/env.py:10,20-21`), so both complete-URL CI configuration and structured local configuration retain the dedicated migration identity. |
| Runtime and retention separation | **Resolved** | Application and integration paths consume the workload-specific runtime and retention readers (`database.py:48-53`; `backend/tests/integration/platform/conftest.py:7-26`). The fix does not alter the login provisioning or PostgreSQL grants accepted in round four. |
| CI compatibility | **Resolved** | Explicit complete URLs remain supported and mapped independently for CI. The unit test supplies different migration, runtime, and retention hosts/databases and verifies that no workload selects another workload's URL (`backend/tests/unit/bootstrap/test_database.py:4-27`). |
| Adversarial test validity | **Resolved** | The Compose contract renders passwords containing all five previously identified reserved characters, passes the rendered component mapping through the production builder, reparses each URL, and checks username, exact password, host, port, and database for all workloads (`backend/tests/contract/platform/test_compose.py:11-15,104-124`). This would fail under the round-four raw interpolation behavior. |

## New breakage

No new Critical or Important breakage was found. The component configuration
retains the same fixed login names established by the least-privilege fix, and
the explicit URL path remains intentionally available for CI. Validation and
error-message refinements for malformed operator-supplied configuration would
be non-blocking polish; they do not reopen password round-tripping or identity
separation.

## Acceptance

W01 passes the requested final scoped source review at `2f0f6b3`. The only
remaining follow-up is to observe the prepared workflow in hosted CI; it is not
a load-bearing code finding in this round.
