# Global matrix - scanner reproducibility fix round 2

## Verdict

**PASS.** The repository scanner is reproducibly clean on a fresh checkout,
including the complete shared Git history. Real secret-shaped values remain
detected, including values after an underscore and values whose payload happens
to resemble a report name. No history was rewritten and no path, commit, token
or secret variable name was allowlisted.

## Reproduced failure

The review finding was reproduced from a clean `/tmp` clone at RED commit
`8dd886f`:

```text
targeted contextual regression    1 failed
scanner CLI                       history:openai_api_key
                                  tracked:backend/tests/contract/platform/test_security.py:openai_api_key
```

The tracked finding came from the literal source fragment previously used to
construct `task-W05-rejection-report.md`. At runtime its preceding `ta` blocked
the key pattern, but the raw source scanner saw a quoted fragment starting at
`sk-`. The same committed source line remained present in Git patches.

## TDD

- RED `8dd886f` adds a source-context regression without embedding a detectable
  key-shaped literal in the test file.
- The test separately constructs a real sensitive variable name and real key
  value at runtime, and requires that assignment to remain detected.
- GREEN `c012c87` implements the precise classification and clarifies the old
  contract fixture data.

## Fix

The scanner now distinguishes only the historical source syntax that splits a
task report filename across two quoted strings: `"ta" + "sk-W...-report.md"`.
The candidate capture must cover exactly the same span as the secret match.
This is contextual classification, not a general filename, test-directory or
history allowlist.

The token boundary was also corrected from `(?<![A-Za-z0-9_-])` to
`(?<![A-Za-z0-9-])`. The former incorrectly suppressed real keys after an
underscore, as demonstrated by the pre-existing all-family oracle. The new
rule still rejects `sk-` embedded in ordinary words such as `task`, while
detecting:

- standalone and quoted key values;
- values assigned to a sensitive variable name;
- values following an underscore;
- a real value shaped like `sk-W05-rejection-report` outside the exact split
  source context;
- AWS, GitHub, Google, OpenAI and private-key families in historical content.

The current contract test now assembles its documentary path from safe segments
and no longer stores the detectable fragment in a tracked source file.

## Clean-checkout proof

Checkout: `/tmp/polyglot-global-matrix-fix2-green`, HEAD `c012c87`, clean Git
status, locked Python environment installed under `/tmp`.

```text
python -m polyglot.platform.security_checks --repository-root ..
repository and history secret scan clean

pytest tests/unit/platform/test_security_checks.py \
       tests/contract/platform/test_security.py -q
10 passed in 1.68s

ruff check targeted files
All checks passed!

mypy src/polyglot/platform/security_checks.py
Success: no issues found in 1 source file
```

## Containment

- No Git history rewrite.
- No broad allowlist and no suppression based on test path or commit.
- No W06 or W09 source, migration, fixture or test modified by this round.
- No PostgreSQL process started.
- No push.
