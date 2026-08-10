# W15 phase A fix round 1 report

## Status

PASS for the W15 fix round. Backend-wide default collection remains PARTIAL
because three pre-existing duplicate test module names are outside the W15
write set.

## Findings closed

- `request_deletion()` now accepts only `quarantined`, `ready`, `rejected` and
  `failed`. It rejects `reserved`, `uploading`, `uploaded`, `verifying`,
  `processing`, `deleting` and `deleted`.
- Pre-upload cancellation is explicit: `cancel_reservation(at)` performs only
  `reserved -> rejected`. Cleanup then follows `rejected -> deleting ->
  deleted`; no upload, verification, quarantine or processing state is
  simulated.
- Every `MediaStatus` is covered as an allowed or forbidden source for deletion.
- The W15 contract fixture test was renamed non-destructively from
  `test_fixtures.py` to `test_media_fixtures.py`, removing the W15 collection
  collision.

## TDD evidence

- RED commit `34d1ad3`: `6 failed, 12 passed`. The five in-flight deletion
  jumps did not raise, and the explicit reservation cancellation command was
  absent.
- GREEN machine tests: `18 passed`.
- GREEN complete W15 tests: `27 passed`.
- Ruff on W15 source and tests: `All checks passed!`.
- Mypy on four W15 source files with an isolated cache: `Success: no issues
  found in 4 source files`.

## Collection evidence

- Targeted media and existing contract fixture collection imports
  `tests/contract/media/test_media_fixtures.py` successfully. It collected 65
  tests and stopped only on the pre-existing content/catalogue
  `test_fixtures.py` collision.
- Full backend default collection reached `396 tests collected, 3 errors` in
  222.42 seconds before manual interruption of only the W15-owned pytest
  process. The remaining collisions are pre-existing:
  `contract/content/test_fixtures.py`,
  `integration/language_profiles/test_repository.py` and
  `unit/identity/test_domain.py`.
- No remaining collection error references W15 or `test_media_fixtures.py`.

## Scope retained

- No migration, route, OpenAPI, shared composition, network provider or public
  object storage change belongs to this fix round.
- Concurrent `language_profiles` worktree changes were preserved and excluded
  from both W15 commits.
