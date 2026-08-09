# Contributing to Polyglot V2

## Scope

Work only from the V2 contracts and normative documents in `docs/v2`. Do not
restore or copy V1 runtime code, SQLite data, generated decks, scripts, or tests
from `v1.0.0-legacy`.

## Contract changes

The registries under `contracts/` are shared public interfaces. A contract
change requires a focused W00 update with positive and negative fixtures,
dependency-free validation, and an update to its normative source document.
Do not introduce alternate names for canonical enums, commands, queries,
errors, events, or tools.

Run these checks before proposing a contract change:

```bash
python3 scripts/validate_contract_registry.py contracts/registry contracts/tests
python3 contracts/tests/test_validate_contract_registry.py
git diff --check
```

## Safety boundaries

- Use ASCII in source and configuration unless human-facing language requires
  another character set.
- Never commit secrets, personal data, local databases, virtual environments, or
  generated user content.
- Generated artifacts remain drafts. Publishing content, changing FSRS, and
  awarding mastery require later domain commands and human authorization.
- Do not add an implicit provider retry or fallback.

## Commit discipline

Keep commits coherent and reviewable. Preserve the docs/V2 link graph and do
not mark a delivery accepted or released without the evidence required by the
relevant gate.
