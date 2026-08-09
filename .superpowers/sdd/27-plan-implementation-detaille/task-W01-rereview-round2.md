# W01 Re-review - Fix round 2

## Verdict

**REQUEST CHANGES.** Round 2 correctly fixes database-time terminal lease
fencing, account-scoped private events, PostgreSQL digest parity, and the
digest/path/expiry metadata for `CVE-2025-68121`. The subject purge now filters
the exact target atomically, but it still self-authorizes instead of requiring a
confirmed deletion request or a dedicated database role. The command replay
fix can also be bypassed through `reserve()`. Finally, the required hosted Trivy
gate invokes a version tag covered by Aqua's Critical 2026 supply-chain
advisory; that gate is not acceptable or reliably runnable.

The PostgreSQL-image CVE remains a valid **non-blocking external-image
exception** once the scanner action itself is replaced with a known-safe,
immutable reference. Hosted CI has not run, and the report's test/security
claims remain unverified by this review.

## Scope and method

- Primary inputs: the W01 brief, round-1 re-review, updated report, and supplied
  `59f93b5..5db85e2` fix diff.
- The checkout was confirmed at `5db85e2`. Implementation inspection was
  limited to the supplied fix diff and directly affected current lines.
- Every round-1 Critical/Important finding, the CI digest Minor, and the CVE
  exception/gate are adjudicated below.
- No test suite was rerun. The open defects are directly established by the
  changed control flow, SQL privileges/constraints, tests, and workflow
  references. `git diff --check 59f93b5..5db85e2` is clean.
- The requested review report is the only file written by this read-only pass.

## Critical findings

1. **The subject purge is scoped but not narrowly authorized.**
   `purge_subject_private_events()` creates its own transaction authorization
   from caller-provided `subject_type` and `subject_id`, deletes matching rows,
   and writes caller-provided audit metadata
   (`backend/migrations/versions/0001_platform.py:449-504`). It does not require,
   lock, or validate a `deletion_requests` row in `confirmed`/`purging` state; it
   does not link the audit to a deletion request or write the required
   tombstone. Any caller able to execute the function can therefore purge any
   account/profile's private event history and choose its own actor/reason.

   `REVOKE ... FROM PUBLIC` is not a role boundary for the function owner. The
   supplied runtime and migration configuration both use the same environment
   database URL, while Compose creates only the `polyglot` owner account
   (`compose.yaml:3-9`; `backend/src/polyglot/bootstrap/database.py:13-22`;
   `backend/migrations/env.py:21-35`). No dedicated retention role or `GRANT`
   exists. Consequently the function is either callable by the broad owner used
   by the application, or unusable by a future restricted runtime role. The
   migration test checks only that pseudo-role `public` lacks `EXECUTE`; it never
   proves denial for the runtime role or authorization for a retention worker
   (`backend/tests/integration/platform/test_migration.py:217-251`). The scoped
   deletion test invokes the store directly without creating a deletion request
   (`backend/tests/integration/platform/test_retention.py:115-175`).

   Preserve the exact-subject and privacy-class predicates, but require a locked
   confirmed deletion request whose subject matches, update its state and create
   the tombstone atomically, and expose execution only to a dedicated retention
   role distinct from the migration owner and normal application role. Add
   negative tests for an absent/unconfirmed/mismatched request and for the normal
   runtime role.

2. **The security gate uses a Trivy action tag covered by a known Critical
   supply-chain compromise.** Both scanner steps invoke
   `aquasecurity/trivy-action@0.33.1`
   (`.github/workflows/ci.yml:67-83`). Aqua's official advisory states that all
   pre-`0.35.0` unprefixed action tags were affected during the March 2026
   compromise, that the original tags were deleted, and that known-safe action
   references start at `0.35.0`; it also recommends full immutable SHA pinning
   ([GHSA-69fq-xp46-6x23](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23)).
   The current reference may fail action resolution now and must not be restored
   or executed from the affected tag. This line predates the round-2 edits, but
   it is part of the explicitly required CVE gate and prevents that gate from
   being accepted. Replace both uses with the full commit SHA of a current
   known-safe release, explicitly pin a known-safe Trivy binary version, and add
   a contract check that rejects mutable/affected action references.

## Important findings

1. **The closed command replay contract is bypassable through `reserve()`.** The
   new `_validate_receipt_replay()` correctly validates terminal results, but it
   is called only by `complete()`
   (`backend/src/polyglot/platform/persistence/repositories.py:33-80,125-151`).
   `CommandReceipt` has no constructor validation, and `reserve()` inserts every
   field from the supplied dataclass without requiring `status == "started"`
   (`backend/src/polyglot/platform/persistence/records.py:54-68`;
   `backend/src/polyglot/platform/persistence/repositories.py:83-98`). A caller
   can reserve a fabricated terminal receipt and bypass the closed `ErrorCode`
   and message-key checks entirely.

   The database constraint does not close the bypass. For rejected/failed rows
   it accepts any two strings named `code` and `message_key`; for succeeded rows
   it accepts any JSON number as `version`; and SQL `NULL` can make a `CHECK`
   expression evaluate unknown and pass because terminal branches do not
   explicitly require `result_payload IS NOT NULL`
   (`backend/migrations/versions/0001_platform.py:38-60`). Thus a terminal
   reservation can persist arbitrary string content up to 512 bytes and can
   create a replay for a command that never ran. The new adversarial tests cover
   only `complete()` and never call `reserve()` with terminal or malformed state
   (`backend/tests/integration/platform/test_command_receipts.py:171-246`).

   Require reservation records to be exactly `started` with null result fields,
   preferably in both the dataclass/store and database operation. Keep terminal
   transitions exclusively in `complete()`, add explicit non-null and semantic
   checks to the database constraint where feasible, and test terminal/malformed
   reservation attempts.

## Round-1 disposition

| Round-1 open item | Verdict | Evidence |
|---|---|---|
| Critical - subject-scoped account/profile purge | **Partial; Critical remains open** | Exact subject and privacy-class filtering plus atomic outbox/event deletion are implemented (`0001_platform.py:340-364,449-504`) and another subject remains untouched in the test. Confirmation, role authorization, tombstone, and trustworthy request linkage are absent. |
| Important - terminal lease fencing trusts semantic timestamps | **Resolved** | Job claim consumption and both outbox terminal actions compare expiry to PostgreSQL `clock_timestamp()` in the same write (`repositories.py:331-411,583-637`). Backdated success/failure/publish/fail tests cover the original bypass. |
| Important - unrestricted command replay payload | **Partial; Important remains open** | `complete()` now permits only a 512-byte success descriptor or closed problem descriptor. `reserve()` bypasses that validator and the SQL constraint is weaker; see Important 1. |
| Important - all private events require a profile | **Resolved** | Private events require an expiring account/profile subject scope, while `profile_id` remains optional (`records.py:77-143`; `0001_platform.py:66-110`). The account-without-profile contract test is valid. |
| Minor - CI PostgreSQL service uses moving tag | **Resolved** | Compose, the Trivy image scan, and the CI service use the same digest (`compose.yaml:3`; `.github/workflows/ci.yml:75-89`), with a parity contract test. |
| Required CVE exception/gate | **Exception resolved; gate Critical** | OpenVEX and Trivy ignore entries are digest-, CVE-, and component-path scoped, owned, time-bounded, and wired only to the pinned image scan (`security/vex/postgres-17-alpine-CVE-2025-68121.json:1-33`; `.trivyignore.yaml:1-10`; `.github/workflows/ci.yml:75-83`). The scanner action reference itself is affected/unacceptable; see Critical 2. |

## CVE exception adjudication

The repository now contains the required decision record:

- exact product digest and `usr/local/bin/gosu` component path;
- `not_affected` / `vulnerable_code_not_in_execute_path` disposition;
- owner, reachability rationale, recheck date, expiry, and removal condition;
- a matching Trivy ignore used only by the exact pinned image scan;
- tests that fail after the recheck/expiry window and detect digest drift.

Those controls correctly implement the round-1 ruling that
`CVE-2025-68121` is a non-blocking external-image exception. The exception does
not justify the affected Trivy action reference. Local Trivy 0.69.1 claims in
`task-W01-report.md:101-104` do not establish that the GitHub workflow can safely
resolve and execute its action, and the report confirms hosted CI has not run
(`task-W01-report.md:137-143`).

## Test validity and new breakage

- Lease tests target the original backdated-timestamp defect and correspond to
  the database-time predicates; no new lease regression was found.
- Event-scope tests prove an account event without `profile_id` and reject
  incomplete/unknown private subject scope; no new envelope breakage was found.
- Retention tests prove row-level target isolation and audit insertion, but call
  the privileged path directly and therefore do not prove authorization.
- Replay tests exercise only `complete()` and miss the terminal `reserve()`
  path, which is the new bypass introduced by the fix's split validation.
- VEX tests validate internal file consistency and dates, but do not validate
  the safety or resolvability of the referenced GitHub Action.
- No other Critical, Important, or relevant Minor regression was found in the
  supplied fix diff. All reported test and scanner results remain unverified.

## Acceptance status

W01 is not acceptable at `5db85e2`. Close the destructive-purge authorization
and command-reservation bypass, replace the affected Trivy action with a
known-safe immutable reference, then run the full matrix and hosted CI. The
PostgreSQL `CVE-2025-68121` exception itself does not require replacement of the
current database image before W01 acceptance, provided its expiry/recheck gate
remains operational.
