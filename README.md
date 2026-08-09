# Polyglot V2

Polyglot V2 is a greenfield rebuild of the language-learning product. The V1
implementation is preserved by the `v1.0.0-legacy` Git tag and is not part of
this branch.

## Current baseline

W00 provides the repository baseline and machine-readable contracts. There is
no application runtime, database, web server, package manager, or deployment
configuration in this increment.

The normative architecture is in [docs/v2](docs/v2/README.md). The contract
registry is validated with only the Python standard library:

```bash
python3 scripts/validate_contract_registry.py contracts/registry contracts/tests
python3 contracts/tests/test_validate_contract_registry.py
```

Generated OpenAPI, application dependencies, PostgreSQL migrations, and the
runtime bootstrap begin in W01.

## Repository layout

```text
contracts/   Machine-readable enums, API surface, events, tools, and fixtures
docs/v2/     Approved V2 architecture and historical V1 screenshots
docs/adr/    Implementation decisions recorded for the rebuild
scripts/     Dependency-free validation utilities
```

## Scope boundaries

- PostgreSQL is the future source of truth; W00 contains no database code.
- A generated artifact may create a draft only. It cannot publish content or
  award mastery.
- The always-on tutor and provider-backed STT are post-V2 capabilities.
- W19 is split into local release readiness (W19L) and deferred cloud delivery
  (W19C).
