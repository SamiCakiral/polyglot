# Global matrix - independent audit and fix

## Verdict

**PASS for the two requested signals.** Both failures were reproduced from a
fresh PostgreSQL 17 database and a complete Python environment under `/tmp`.
The fixes are limited to test isolation for `content` and to a demonstrated
false positive in the repository secret scanner. No history was rewritten and
no current or historical credential was allowlisted.

## 1. Catalogue/content order contamination

### Reproduction

On a fresh database migrated from `base` to `0005_content`, the exact order
`tests/integration/catalogue` then `tests/integration/content` failed after
`40 passed`:

```text
duplicate key value violates unique constraint "language_packs_pack_code_key"
Key (pack_code)=(it-IT__fr-FR) already exists.
```

The catalogue suite left pack `019fe900-5000-7000-8002-000000000001`. The
content fixture then tried to create the same `pack_code` with pack
`019fe003-0000-7000-8010-000000000001`. Its autouse cleanup truncated content
and platform tables but not the catalogue tables that the fixture itself
reseeds.

### TDD and fix

- RED commit `6c0860c` adds a regression proving that the content suite starts
  without residual catalogue packs: `1 failed`, observed value `1`.
- GREEN extends only `tests/integration/content/conftest.py`: it truncates the
  existing catalogue tables with `CASCADE` before each content test, then each
  content fixture reseeds its own deterministic references.
- The GREEN files were committed in `145058d` while the concurrent W06 task
  committed its own staged work. They remain independently identifiable in
  that commit; no W06 file was modified by this audit.

Fresh `/tmp` proof after the fix:

```text
tests/integration/catalogue tests/integration/content   78 passed in 7.03s
```

No application or business behavior changed.

## 2. Git-history secret scan

### Reproduction and classification

The scan from the Documents worktree exceeded its 30-second history timeout
because of local filesystem I/O. The same repository cloned under `/tmp`
completed in 0.42 seconds and reported:

```text
history:openai_api_key
tracked:.superpowers/sdd/27-plan-implementation-detaille/task-W05-report.md:openai_api_key
```

Targeted Git pickaxe inspection found no AWS, GitHub, Google or private-key
match. The only `sk-` family matches were:

| Commit | Path | Classification |
| --- | --- | --- |
| `15b0dd3` | `.superpowers/sdd/27-plan-implementation-detaille/task-W05-report.md` | false positive |
| `da1f203` | `.superpowers/sdd/27-plan-implementation-detaille/task-W05-report.md` | false positive |

The matched text was the `sk-` substring inside the documented filename
`task-W05-rejection-report.md`. It was not a token, credential, prompt secret
or user datum. No true secret was found.

### TDD and fix

- RED commit `6c0860c` proves that the exact filename is incorrectly detected
  while a synthetic standalone key remains detectable: `1 failed`.
- GREEN requires a token boundary before `sk-`. It does not allowlist a file,
  commit, value or secret family, and the positive synthetic-key oracle still
  passes.
- The GREEN scanner change is also contained in `145058d` for the concurrent
  staging reason recorded above.

Autonomous `/tmp` proof after the fix:

```text
targeted boundary regression                         1 passed
platform security contract                           2 passed
scanner CLI                                          repository and history secret scan clean
Ruff on all four changed files                       All checks passed
git diff --check                                     passed
```

## Process containment

- No Git history rewrite, secret masking or broad allowlist.
- No changes under `language_profiles`, `exercises_core` or their fixtures.
- No push.
- Blocked Documents-path processes `76334` and `77091` were terminated alone.
- All final matrix evidence used the isolated `/tmp/polyglot-global-matrix-src`
  environment and PostgreSQL on port `55441`.
