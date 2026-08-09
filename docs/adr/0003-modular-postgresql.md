# ADR 0003: Use a modular monolith with PostgreSQL authority

## Status

Accepted.

## Decision

The future application is a modular monolith with explicit domain boundaries.
PostgreSQL is the source of truth. W00 adds neither runtime code nor database
code.

## Consequences

SQLite is not a V2 persistence option. Microservices, mandatory distributed
cache, and event sourcing for every aggregate remain out of the MVP.

## Sources

`docs/v2/06-glossaire-decisions.md` DEC-T01 and DEC-T02.
