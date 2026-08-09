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
