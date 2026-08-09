# W00 Report

## Status

COMPLETE

## Commits

- `7c6e390` `feat(contracts): add W00 registry validation`
- `2ef24b9` `chore(v2)!: remove V1 runtime baseline`

## Files changed

- Removed tracked V1 Flask runtime, SQLite-oriented configuration, V1 tests, and
  V1 environment/dependency files.
- Replaced root README and `.gitignore`; added `CONTRIBUTING.md`.
- Added ADRs `docs/adr/0001-v2-baseline.md` through
  `docs/adr/0008-post-v2-tutor-and-stt.md`.
- Added the W00 registry, event envelope and catalogue, eleven author-tool
  input/output schemas, fixture manifest schema, positive/negative fixtures,
  and `scripts/validate_contract_registry.py`.
- Updated `docs/v2/27-plan-implementation-detaille.md` with the approved
  W19L/W19C split.

## RED evidence

`python3 contracts/tests/test_validate_contract_registry.py` initially ran four
negative contract cases and failed all four because
`scripts/validate_contract_registry.py` did not exist. The failures covered
unknown enum values, duplicate routes, events missing `schema_version`, and
tools missing limits.

## GREEN evidence

- `python3 contracts/tests/test_validate_contract_registry.py`: 4 tests passed.
- `python3 scripts/validate_contract_registry.py contracts/registry contracts/tests`:
  `contract registry valid`.
- Registry coverage: 95 public commands, 37 public query routes, 37 public
  query names, 80 errors, and 11 author tools.
- `git diff --check`: passed.

## Remaining concerns

- The standard-library validator intentionally accepts JSON syntax only; JSON
  is valid YAML, but general YAML syntax needs a future parser if required.
- OpenAPI generation and application/runtime validation are deferred to W01.
- W19C cloud delivery, the always-on tutor, and provider-backed STT remain
  deferred by approved decision.

## Fix Round 1

### Status

Review findings addressed; post-commit clean-status verification remains part
of the final completion check.

### RED evidence

- `contracts/tests/test_w00_contract_delivery.py` first failed five cases:
  unknown command/tool errors and an incomplete canonical tool set were
  accepted; fixture execution and repeatable scans were absent.
- The subsequent common-limits test failed because the validator accepted a
  manifest with `common_limits` removed.

### GREEN evidence

- The error registry now contains 116 canonical errors from documents 25 and
  30. Command and tool error references are rejected unless registered.
- Canonical snapshots protect the exact public command, query, error, and tool
  sets.
- All 22 tool schemas are concrete, closed JSON schemas. Catalogue filters
  remain optional; `pack_revision_id` is required and `limit` is bounded at
  200.
- `python3 contracts/tests/test_validate_contract_registry.py`: 4 passed.
- `python3 contracts/tests/test_w00_contract_delivery.py`: 6 passed.
- The registry command executed 22 tool fixtures and completed both the
  documentation-link and V1/private-artifact scans.

### Remaining concerns

- The W00 schema evaluator intentionally implements only the JSON Schema
  keywords used by these shipped contracts; W01 may adopt a fuller validator
  with its runtime dependency set.

## Fix Round 2

### RED evidence

- Canonical HTTP method/route/idempotency changes and an untracked V1 `app/`
  runtime were initially accepted by the validator.

### GREEN evidence

- `python3 contracts/tests/test_validate_contract_registry.py`: 4 passed
  against copied shipped contracts.
- `python3 contracts/tests/test_w00_contract_delivery.py`: 9 passed.
- The registry command validated 22 tool fixtures, six explicit meta-cases,
  docs links, and artifact boundaries. `exercise.submit_draft` accepts only
  `draft`; its `published` fixture is rejected.

## Fix Round 3

### Status

COMPLETE for the requested contract-policy simulation and artifact boundary.

### Prior hang diagnosis

- The hang was not reproducible at `4bf9849`: the original four registry tests
  completed in 0.191 s, and the ten delivery tests completed in 0.561 s with
  one ordinary artifact-policy failure caused by the newly present W01 brief.
- The concrete harness defect was that validator children and both Git scans
  had no timeout, so any stalled child could leave the suite waiting forever.
  Test children and Git scans now have 10 s bounds; all final commands also ran
  inside 30 s or 40 s outer bounds. Timeout policy itself is simulated from
  logical elapsed time and never sleeps.

### RED evidence

- After adding invocation contexts and executable assertions, the 17-test
  delivery suite failed as expected: static meta-case checking could not emit
  closed transcripts, ignored repaired contexts, and did not consult manifest
  roles or timeout limits.
- Exact artifact assertions exposed the previous false-positive test path:
  failures now have to name the injected file under `contracts/`, `scripts/`,
  or `docs/`, and ignored bytecode is rejected as an arbitrary artifact.

### GREEN evidence

- `contracts/tests/test_validate_contract_registry.py`: 4 passed in 0.212 s.
- `contracts/tests/test_w00_contract_delivery.py`: 17 passed in 1.307 s.
- The dependency-free simulator executed exactly six cases and emitted the
  closed errors `idempotency_conflict`, `tool_not_allowed`,
  `version_conflict`, `size_limit_exceeded`, `timeout`, and
  `tool_not_allowed`. Every transcript recorded `effects=[]` and
  `forbidden_effects=[]`.
- Counterfactual tests repair each triggering context and require the case to
  stop rejecting. Separate mutations prove that manifest roles, timeout limits,
  and each tool's common-plus-specific error allowlist are consulted.
- The full validator reported 22 tool fixtures, 6 policy cases,
  `documentation links valid`, `artifact boundary valid`, and
  `contract registry valid`.
- Standalone documentation-link and artifact checks passed. `git diff --check`
  passed. A pre-existing ignored validator bytecode cache was removed so the
  strict artifact baseline is genuinely clean.

### Remaining concerns

- This is deliberately a pre-handler contract-policy simulator, not production
  tool execution. Runtime handler/effect integration remains deferred.
- The existing canonical error snapshot still omits the document-30 common
  codes `scope_forbidden` and `reference_not_found`. They are outside this
  round's write scope and are not emitted by its six required cases.
