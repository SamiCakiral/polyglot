# W15 phase A fix round 2 report

## Status

PASS for the requested FX-MEDIA blockers. The canonical manifest, reproducibility
metadata and the hostile-archive and expired-rights fixture oracles are now
validated and executable offline.

## Findings closed

- `FX-MEDIA/manifest.json` contains only the W00 fields and validates as a
  positive, accepted canonical fixture.
- `fixture-metadata.json` pins schema version 1, synthetic seed `5015`, the
  fixture clock, the SHA-256 fingerprint of `media.json`, seven explicit
  oracles and an empty network dependency list.
- `hostile_archive` declares `quarantined/hostile_archive` and is executed
  through `reserved -> uploading -> uploaded -> verifying -> quarantined`.
- `rights_expired` declares `quarantined/rights_expired` and is executed through
  the same public transitions at the fixture clock.
- The contract test consumes the published fixture payload and clock; it does
  not replace either case with an equivalent hard-coded domain scenario.

## TDD evidence

- RED commit `9b2fbc7`: `4 failed, 2 passed`. Failures independently exposed
  the invalid manifest, incomplete metadata, missing hostile-archive outcome
  and missing expired-rights outcome.
- GREEN contract test: `6 passed`.
- Complete W15 target: `31 passed in 67.66s` across unit, property and contract
  media tests.

## Validation evidence

- Canonical W00 schema validation, payload fingerprint verification and empty
  network dependencies: PASS (`FX-MEDIA: W00 manifest valid; payload fingerprint
  valid; offline`).
- Ruff on W15 source and tests: `All checks passed!`.
- Mypy on the four W15 media source files with an isolated cache:
  `Success: no issues found in 4 source files`.
- `git diff --check` on the W15 test and fixture bundle: PASS.

## Scope retained

- No migration, route, OpenAPI, composition root, provider integration or
  network fallback was added.
- No media production source was changed; the existing generic ports and state
  machine remain intact.
- Concurrent platform, exercises and test-package changes were preserved and
  excluded from the W15 commits.

## Limits

- The rereview's minor UTC and timestamp-constructor invariant remains outside
  this fix round, as requested.
- Backend-wide collection was not rerun; round 2 validation is limited to the
  canonical validator and the complete W15 target.
- No push was performed.
