# W01 Re-review - Fix round 1

## Verdict

**REQUEST CHANGES.** Fix round 1 resolves most of the original W01 findings,
including the impossible mutable/append-only job-attempt design, idempotency
identity and stable replay, inbox checksum divergence, RFC 9457 handling,
migration/package gates, W00 cache-boundary regression, canonical JSON coverage,
and readiness behavior. However, one prior Critical retention finding remains
only partially fixed, and lease fencing still relies on caller-controlled event
timestamps rather than database time. Two privacy/schema regressions were also
introduced by the fix.

The Trivy `CVE-2025-68121` result does **not** block W01 on vulnerability
applicability: the vulnerable Go `crypto/tls` session-resumption path is not used
by the `gosu` executable embedded in the PostgreSQL image. It should be recorded
as a reviewed, digest-scoped external-image VEX exception and monitored for an
official image rebuild. The missing encoded exception still means the prepared
hosted workflow is expected to be red, so acceptance evidence remains incomplete.

## Scope and method

- Reviewed the supplied brief, prior review, updated report, and only the
  `e376a46..59f93b5` fix diff for implementation changes.
- Confirmed the checkout is at `59f93b5` and inspected the relevant clauses of
  docs 09, 17, 25, and 26 where needed.
- Reported local test and scanner results are treated as unverified claims. No
  test suite was rerun: the remaining failures follow directly from the SQL
  predicates and schema constraints, so no focused execution was needed.
- `git diff --check e376a46..59f93b5` is clean. The review file is the only
  artifact written by this read-only review.

## Critical findings

1. **The controlled purge still cannot execute account/profile deletion.** The
   new trigger exception authorizes deletion only when `OLD.expires_at <= cutoff`
   (`backend/migrations/versions/0001_platform.py:292-305`), and the only purge
   API deletes every expired event/audit row globally by time
   (`backend/migrations/versions/0001_platform.py:320-367`;
   `backend/src/polyglot/platform/persistence/repositories.py:387-423`). It has no
   subject type, subject ID/fingerprint, or scope predicate. A confirmed account
   or profile deletion therefore cannot purge that subject's non-expired private
   events within 30 days; advancing the cutoff would also delete other subjects'
   rows. This remains contrary to account/profile active purge and scoped
   deletion requirements (`docs/v2/17-securite-confidentialite-jobs-medias.md:97-117`;
   `docs/v2/26-dictionnaire-donnees.md:738-776`). The new retention test proves
   only global expiry of one already-expired row and even assigns a synthetic
   profile to an account event (`backend/tests/integration/platform/test_retention.py:15-81`).
   Add a narrowly authorized, audited subject-scoped purge path and prove that a
   target subject's private rows are removed without deleting another subject's
   rows. Ordinary writes must remain append-only.

## Important findings

1. **Job and outbox lease expiry is checked against a caller-supplied semantic
   timestamp, not current database time.** Job completion consumes a claim when
   `lease_expires_at > finished_at`
   (`backend/src/polyglot/platform/persistence/repositories.py:276-357`), and
   outbox acknowledgement uses the same pattern with `published_at` or
   `failed_at` (`backend/src/polyglot/platform/persistence/repositories.py:496-550`).
   A delayed or stale worker can submit an old timestamp after real lease expiry
   and still consume/acknowledge the claim if no replacement has yet overwritten
   the token. The new tests pass simulated current timestamps and therefore do
   not cover this bypass (`backend/tests/integration/platform/test_job_lifecycle.py:46-102`;
   `backend/tests/integration/platform/test_event_delivery.py:157-198`). Keep the
   semantic completion timestamp for the fact, but fence ownership with database
   time such as `lease_expires_at > clock_timestamp()` (or a separately injected,
   trusted current time) in the same statement. Add an adversarial late-call/
   backdated-timestamp test for both jobs and outbox.

2. **Stable command replay adds an unrestricted private-data sink outside the
   documented receipt contract.** `result_payload jsonb` was added to the
   migration and dataclass (`backend/migrations/versions/0001_platform.py:20-39`;
   `backend/src/polyglot/platform/persistence/records.py:53-67`), and `complete()`
   accepts and persists any JSON object without a byte bound, allowed schema, or
   secret/private-field validation
   (`backend/src/polyglot/platform/persistence/repositories.py:75-116`). Document
   26 defines `CommandReceipt` with `result_ref` but no result body
   (`docs/v2/26-dictionnaire-donnees.md:654-660`), while docs 17 requires strict
   size/type/shape validation and forbids secrets in business storage
   (`docs/v2/17-securite-confidentialite-jobs-medias.md:83-95,136-145`). The tests
   call one example "bounded" but no bound is enforced
   (`backend/tests/integration/platform/test_command_receipts.py:132-168`). Store
   a closed, bounded replay descriptor/problem shape, or validate size and
   forbidden fields at the receipt boundary. Do not permit arbitrary response,
   prompt, token, signed URL, or uploaded content to be copied into receipts.

3. **All personal/sensitive events are incorrectly forced to reference a
   profile.** Both the database constraint and `DomainEvent` validation require
   `profile_id` whenever privacy is personal or sensitive
   (`backend/migrations/versions/0001_platform.py:42-72`;
   `backend/src/polyglot/platform/persistence/records.py:97-136`). The canonical
   envelope and data dictionary make `profile_id` optional, "profil si
   pertinent" (`docs/v2/26-dictionnaire-donnees.md:660-663`); account-scoped
   personal events can legitimately exist before a language profile. The
   retention test masks the mismatch by giving `account_registered` a fabricated
   profile ID (`backend/tests/integration/platform/test_retention.py:26-45`).
   Require a retention scope appropriate to the aggregate, for example account
   or profile subject identity plus expiry, rather than requiring every private
   event to have a profile.

## Minor findings

1. **CI integration tests do not use the image that Compose pins and Trivy
   scans.** Compose and the image scan use digest
   `sha256:742f40...2193`, while the PostgreSQL service uses the moving
   `postgres:17-alpine` tag (`compose.yaml:1-16`; `.github/workflows/ci.yml:75-99`).
   This weakens reproducibility and can test a different image from the reviewed
   runtime. Pin the CI service to the same digest and update all three references
   together.

## Prior finding disposition

| Prior finding | Disposition | Evidence |
|---|---|---|
| Critical 1 - mutable lease fields in append-only attempts | **Resolved** | Mutable ownership moved to `job_claims`; `job_attempts` now stores terminal immutable facts (`0001_platform.py:159-188,312-314`). Lifecycle tests cover renewal, takeover, terminal facts, and retry. |
| Critical 2 - append-only blocks retention/deletion | **Partial; Critical remains open** | The audited expiry path resolves ordinary time-based expiration, but has no account/profile scope and cannot satisfy deletion requests. See Critical 1 above. |
| Important 1 - idempotency target/precondition and completion replay | **Resolved** | Replay compares fingerprint, aggregate type/ID, and expected version; completion is terminal and stable (`repositories.py:37-116`; `test_command_receipts.py:11-168`). Privacy of the newly added arbitrary replay body is a separate new finding. |
| Important 2 - stale outbox acknowledgement | **Partial; Important remains open** | Lease tokens and affected-row results fix same-worker token reuse, but expiry trusts `published_at`/`failed_at`. See Important 1 above. |
| Important 3 - incomplete RFC 9457/405/500 handling | **Resolved** | `message_key`, closed status mapping, generic failures, and correlation headers are implemented and covered by focused contract tests. |
| Important 4 - W00 event/UUIDv7/private boundary | **Partial** | Event catalogue/version, UUIDv7, UTC, size, secret class, and forbidden-key checks are now enforced. The profile-only private scope is over-restrictive and deletion remains incomplete; see Critical 1 and Important 3. |
| Important 5 - migration completeness/downgrade gate | **Resolved** | Schema assertions, trigger/function checks, Alembic round trip, and CI migration checks were added. |
| Important 6 - wheel misses migrations | **Resolved** | Wheel force-includes Alembic resources and W00 event contracts, and an isolated installed-artifact migration runner is gated (`backend/pyproject.toml:22-29`). |
| Important 7 - W00 cache bypass/write-set regression | **Resolved** | Adversarial cases were restored and cache exemptions constrained. The W00 correction is isolated in coherent RED/GREEN commits `254f88d` and `33f1b3e`. |
| Important 8 - security/FX-OPS/hosted gates | **Partial; external evidence open** | FX-OPS, secret/history scan, dependency audit, pinned Compose image, Trivy steps, packaging, and migration gates exist. Hosted CI has not run (`task-W01-report.md:5-6,91`), and the Trivy exception is not encoded. |
| Minor 1 - inbox divergent checksum ignored | **Resolved** | Duplicate receipts compare the checksum and raise a closed conflict on divergence. |
| Minor 2 - SHA fields only length checked | **Resolved** | Lowercase hexadecimal checks now cover command, inbox, job, provenance, audit, and tombstone fingerprints. |
| Minor 3 - canonical JSON proof too narrow | **Resolved** | RFC 8785 is used and tests cover nested values, numeric equivalence, and independent vectors. |
| Minor 4 - OpenAPI claim too broad | **Resolved by accurate scope** | The report now explicitly describes a health-route membership guard rather than full W00 compatibility (`task-W01-report.md:79-80`). That scope is sufficient for W01's two routes. |
| Minor 5 - empty readiness reports ready | **Resolved** | Production app creation requires mandatory probes; empty probes are permitted only through explicit test mode. |

## Trivy CVE adjudication

`CVE-2025-68121` is a real Go standard-library flaw in TLS session resumption
when certificate pools are changed through `Config.Clone` or
`GetConfigForClient`; fixed Go versions are 1.24.13 and 1.25.7
([NVD](https://nvd.nist.gov/vuln/detail/CVE-2025-68121),
[Go vulnerability record](https://pkg.go.dev/vuln/GO-2026-4337)). The scanner
finds an affected Go toolchain version embedded in `gosu`, but `gosu`'s program
surface is user/group lookup followed by credential switching and `exec`; its
main program does not import or invoke `crypto/tls`
([gosu source](https://github.com/tianon/gosu/blob/master/main.go)). The official
PostgreSQL entrypoint invokes it only to change from root to the `postgres` user
before restarting the entrypoint
([official entrypoint](https://github.com/docker-library/postgres/blob/master/docker-entrypoint.sh)).
The `gosu` maintainers also explicitly classify Go CVEs in unreachable standard-
library interfaces as scanner false positives and recommend reachability-aware
`govulncheck` evidence
([gosu security policy](https://github.com/tianon/gosu/blob/master/SECURITY.md)).

Therefore:

- **W01 vulnerability acceptance:** non-blocking external-image exception.
- **Required record:** reviewed VEX/ignore entry scoped to
  `CVE-2025-68121`, the exact PostgreSQL image digest, and the unreachable
  `gosu` TLS path; include an owner and expiry/recheck condition.
- **Update action:** move to an official rebuilt digest when available, then
  remove the exception.
- **CI consequence today:** `.github/workflows/ci.yml:75-82` uses
  `exit-code: 1` without a committed VEX/ignore input, and the report says the
  gate is expected to surface the finding (`task-W01-report.md:84-88`). Hosted
  CI cannot be claimed green until the exception or rebuilt image is present.
  This evidence gap is not itself the reason for the `REQUEST CHANGES` verdict.

## Acceptance status

W01 should not be accepted or used as the permanent migration base until the
Critical subject-scoped deletion path and the Important lease-timestamp,
receipt-payload, and private-event-scope findings are fixed. Afterward, run the
full matrix and hosted CI, record the digest-scoped CVE disposition, and attach
the hosted run as acceptance evidence. The current report's local green claims
remain unverified by this re-review.
