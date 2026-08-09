# ADR 0001: Keep a clean V2 baseline

## Status

Accepted.

## Decision

V2 is a greenfield repository baseline. V1 is preserved by the
`v1.0.0-legacy` tag and remains an archive and visual reference only. No V1
runtime, SQLite data, generated content, decks, scripts, tests, or virtual
environment is carried into this branch.

## Consequences

Migration of V1 user data is excluded. Historical screenshots and `docs/v2`
remain versioned as the approved design baseline.

## Sources

`docs/v2/06-glossaire-decisions.md` DEC-001 and DEC-012.
