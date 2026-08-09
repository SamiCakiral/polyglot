# ADR 0004: Preserve command and event integrity

## Status

Accepted.

## Decision

Commands carry idempotency and concurrency semantics. Their typed events use a
versioned envelope. Future persistence writes state, events, and outbox records
atomically; no dual write is allowed.

## Consequences

The registry rejects duplicate mutation routes and events without a schema
version. Later implementations must preserve replay behavior and the event
envelope.

## Sources

`docs/v2/06-glossaire-decisions.md` DEC-T05 and
`docs/v2/09-etats-commandes-evenements.md`.
