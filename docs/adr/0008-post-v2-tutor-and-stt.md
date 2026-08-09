# ADR 0008: Defer the always-on tutor and provider-backed STT

## Status

Accepted.

## Decision

The always-on contextual tutor and provider-backed STT are post-V2. V2 supports
deterministic local fixtures and the simulated oral protocol without requiring
a live tutor, STT, TTS, LLM, or provider fallback.

## Consequences

No mastery is inferred from simulated oral practice or unavailable media. A
future STT adapter must preserve attempt, correction, and observation contracts.

## Sources

`docs/v2/05-matrice-conservation-v1-v2.md` DEC-009,
`docs/v2/12-contrats-exercices.md`, and
`docs/v2/17-securite-confidentialite-jobs-medias.md`.
