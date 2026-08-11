# W19L - Real-browser acceptance audit

- Status: `technical_pass`, with independent human review pending
- Date: `2026-08-11`
- Runtime: current `codex/v2-rebuild` checkout, real FastAPI service, clean
  PostgreSQL acceptance database, local object storage and local Italian TTS
- Browser: in-app Chromium at 320, 768 and 1,440 CSS pixels
- API mocks: disabled
- Test identities: fresh disposable accounts; credentials are not retained in
  this repository

## Learner journey

| Area | Real-browser result |
|---|---|
| Account | Registration, login, recent-authentication renewal and logout passed |
| Language profile | French to Italian profile creation and profile recovery after login passed |
| Placement | Beginner foundation gate and intermediate diagnostic path both passed |
| Curriculum | Module discovery, enrollment and learner-facing presentation passed |
| Daily plan | 30-minute composition selected the required learning blocks coherently |
| Vocabulary | Due review, daily cards, reveal and ratings updated the personal Word Bank |
| Sprint | Recall, comprehension, shadowing, guided production and reflection completed |
| Grammar/Gym | Controlled structure practice ran without exposing internal primitive identifiers |
| Audio | Italian TTS produced playable local audio for shadowing and listening |
| J+1 | Inversion remained locked until its source production was available and frozen |
| Free practice | A free session could be composed and paused without advancing the curriculum |
| Progress | Reading and writing evidence updated separately; oral axes received no false mastery credit |
| Reading assessment | Completed with an independent scored result |
| Listening assessment | All 16 audio segments played and the assessment produced a scored result |
| Writing assessment | Submission completed and remained pending review without an invented score |
| Speaking assessment | Self-assessment completed as `not_evaluable`, with zero confidence and no mastery credit |
| Export | Recent authentication was requested, renewed, and followed by successful export creation |
| Session closure | Logout revoked the session, cleared client state and returned to the login page |

## Defects found and closed

1. Sprint completion used the version captured before exercise progress and
   could return `Version conflict`. Completion and pause now refetch the run and
   submit the current version.
2. The settings export sent an unsupported scope. It now uses the four backend
   boolean scopes: learning history, memory prompts, vocabulary lists and Word
   Bank.
3. Recent-authentication renewal kept stale query and CSRF state. Reauthentication
   now performs a full internal return after clearing cached server state, while
   ordinary onboarding keeps SPA navigation.
4. The curriculum exposed technical module and novelty labels. Learner-facing
   module presentation now derives stable titles and plain-language planning
   copy.

Each behavior has a focused frontend regression test in addition to the real
browser proof.

## Visual review

The current checkout was reviewed at desktop, tablet and narrow mobile sizes.
No blocking overlap, truncation, inaccessible navigation or incoherent hierarchy
was observed. The compact layout preserves all five primary destinations and
uses the menu for account actions. The progress view keeps the four modalities
separate and labels unavailable evidence honestly.

- `browser/progress-desktop-1440-final.png`
- `browser/learn-desktop-1440-final.png`
- `browser/progress-tablet-768-final.png`
- `browser/learn-mobile-320-final.png`

These captures are engineering evidence, not a substitute for the independent
human `G4`, `P-LING` or `P-PED` signatures.
