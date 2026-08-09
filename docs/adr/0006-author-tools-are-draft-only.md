# ADR 0006: Keep author tools bounded and draft-only

## Status

Accepted.

## Decision

All eleven author tools have closed input and output schemas, explicit limits,
roles, errors, and side effects. A tool may create only a draft, report, or
revision candidate. It cannot approve, publish, retire, award mastery, or
modify an FSRS schedule.

## Consequences

Model output stays reviewable. Tool failures are explicit and no retry is
automatic without a later policy and budget.

## Sources

`docs/v2/30-contrats-outils-auteur.md`.
