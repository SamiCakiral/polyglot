# ADR 0005: Require scoped identity and privacy by default

## Status

Accepted.

## Decision

V2 uses account roles with author and reviewer separation, server sessions, and
default-deny authorization. Personal data remains scoped to its owner and is
not exposed through tool results without an explicit authorized scope.

## Consequences

The author-tool contracts encode role and scope constraints. JWT persistence in
browser storage and cross-profile data access are excluded.

## Sources

`docs/v2/06-glossaire-decisions.md` DEC-T03 and
`docs/v2/17-securite-confidentialite-jobs-medias.md`.
