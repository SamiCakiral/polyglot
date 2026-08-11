# W19L - Local release readiness

- Status: `PARTIAL`
- Evidence date: `2026-08-11`
- Revision: the commit containing this report
- Environment: macOS arm64, Python `3.13.11`, Node `22.18.0`, PostgreSQL `17.10`
- Scope: local release only; W19C cloud delivery is deferred

## Machine verification

| Gate | Result | Evidence |
|---|---|---|
| Contracts | `PASS` | OpenAPI is current; 22 authoring tool fixtures, 6 policy cases and documentation links validate |
| Compose | `PASS` | Configuration renders only with the separate migration, runtime and retention secrets |
| Migrations | `PASS` | Empty PostgreSQL database upgraded from `0001_platform` to the single `0019_assessment_audio` head; Alembic reports no drift |
| Backend quality | `PASS` | Ruff clean; mypy clean on 158 source files |
| Backend matrix | `PASS` | 1,040 passed, 2 skipped, 1 dependency deprecation warning, with network disabled and three non-privileged database logins |
| Frontend quality | `PASS` | ESLint and strict TypeScript clean; 42 unit tests passed |
| Frontend build | `PASS` | Production build generated 164 modules; main bundle 459.70 kB, 134.19 kB gzip |
| Responsive/accessibility automation | `PASS` | Playwright: 24 passed, 30 intentionally inapplicable combinations skipped across 320, 768, compact, 1,440, reflow and 200% zoom projects |
| Restore rehearsal | `PASS` | `restore-report.json` verifies isolated restore, logical checksums and tombstone non-resurrection on synthetic FX-OPS data |
| Secret scan | `PASS` | Repository and history scan is required again after staging and before push |

## Product-path evidence

The local acceptance run covered registration, a French-to-Italian profile,
diagnostic, foundations, module enrollment, vocabulary, a complete seven-block
daily sprint, local Italian TTS, reading assessment, Word Bank and free
practice. Oral self-assessment remains non-evaluable without human review and
cannot create mastery credit.

The authoring path used the exact configured LM Studio model, produced a
structured draft through the controlled tool facade, registered immutable
provenance, then completed validation, approval by a distinct reviewer,
publication and retirement. The model never received publication or mastery
capability.

## Open acceptance gates

| Gate | Status | Reason |
|---|---|---|
| G4 human visual review | `pending_human` | Automated responsive and axe checks pass, but the final real-browser desktop/mobile review is not signed |
| P-LING | `pending_human` | The Italian linguistic fixture has no assigned human reviewer |
| P-PED | `pending_human` | The learning progression has no signed human pedagogical review |
| G7 / W19C | `deferred` | Cloud infrastructure, canary and production rollback proof are outside W19L |

No `v2.0.0` tag may be created while these human gates remain open. A local
release candidate may be packaged only as `PARTIAL`, without implying cloud,
linguistic, pedagogical or visual acceptance.
