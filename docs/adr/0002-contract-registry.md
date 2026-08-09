# ADR 0002: Make contracts the W00 shared interface

## Status

Accepted.

## Decision

Canonical enums, public commands, public queries, errors, event metadata, and
author tools live under `contracts/`. W00 validates JSON-syntax YAML with the
Python standard library only. Generated OpenAPI is deferred to W01.

## Consequences

Consumers use the registry as the initial machine-readable interface. Renaming
or competing names require an explicit W00 contract change and a normative
documentation update.

## Sources

`docs/v2/25-registre-enums-commandes-api.md`,
`docs/v2/27-plan-implementation-detaille.md`, and
`docs/v2/30-contrats-outils-auteur.md`.
