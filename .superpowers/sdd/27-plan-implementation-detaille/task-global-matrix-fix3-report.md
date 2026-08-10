# Global matrix scanner fix round 3

## Verdict

**PASS.** Sensitive assignments now take absolute priority over both narrow
documentary classifications. The repository worktree and complete Git history
remain clean, while adversarial assignments are detected. No history rewrite,
path allowlist, commit allowlist or broad documentation exemption was added.

## Reproduction

The two adversarial cases from `task-global-matrix-final-review.md` were added
without storing a secret-shaped literal in the tracked test source:

1. a proof sentence containing the synthetic report fragment, assigned to a
   sensitive API-key variable;
2. the split quoted report expression, assigned to the same sensitive variable.

At RED commit `1242630`, the targeted test failed because the first value was
classified as documentation and returned no finding. The same root cause
applied to the second value.

## Fix

GREEN commit `89bc03a` adds a line-scoped sensitive-assignment classifier. It
recognizes case-insensitive shell, Python-style and YAML-style assignments for
names ending in:

- `API_KEY`, `ACCESS_KEY`, `SECRET_KEY` or `PRIVATE_KEY`;
- `TOKEN`, `SECRET`, `PASSWORD` or `CREDENTIAL(S)`.

For each secret-shaped match, the scanner first checks whether its exact span
is inside the value side of one of these assignments. If so, it emits the
finding immediately. Documentary classifiers are considered only when no
sensitive assignment contains the match.

The adversarial matrix covers the two review cases plus a lowercase YAML
`provider_token:` assignment. Controls prove that:

- the two documentary references alone remain ignored;
- direct and underscore-prefixed real values remain detected;
- a report-shaped value directly assigned to a sensitive name remains detected;
- all AWS, GitHub, Google, OpenAI and private-key historical families remain
  detected by the existing suite.

## Autonomous proof

Environment: `/tmp/polyglot-global-matrix-fix3`, locked dependencies, no use of
the worktree `backend/.venv`.

```text
targeted adversarial test                         1 passed in 0.06s
unit and contract security suite                  10 passed in 2.06s
repository and complete history scan              clean
Ruff targeted files                               passed
mypy security scanner                             passed
```

## Containment

- Only `security_checks.py` and its targeted unit test changed in RED/GREEN.
- W06 application, routes, migrations, fixtures and tests were left untouched.
- No PostgreSQL or other service was started.
- No push.
