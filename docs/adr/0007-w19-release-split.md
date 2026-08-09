# ADR 0007: Split W19 into local release readiness and cloud delivery

## Status

Accepted.

## Decision

W19 is split into W19L and W19C. W19L covers reproducible local release
readiness and offline evidence. W19C covers the deferred cloud-delivery scope:
managed infrastructure, cloud IAM and secrets, hosted observability, backup
and restoration evidence, and canary promotion.

## Consequences

W19L does not claim cloud readiness. W19C remains blocked until its cloud
environment, approval, and rollback evidence exist.

## Sources

`docs/v2/18-exploitation-environnements-livraison.md` and
`docs/v2/27-plan-implementation-detaille.md`.
