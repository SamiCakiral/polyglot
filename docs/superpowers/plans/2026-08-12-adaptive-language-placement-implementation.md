# Adaptive Language Placement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not dispatch subagents. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed six-question onboarding diagnostic with a deterministic, multilingual, sequential placement engine that uses bounded skill estimates, optional LM Studio rubric scoring, real listening media, and P0-P3 calibration.

**Architecture:** Add a focused `polyglot.modules.placement` bounded context. PostgreSQL owns published item banks, immutable runs, responses, interpretations, observations, contradictions, estimate revisions, decisions, and calibration cycles. A pure policy selects one frozen item at a time; specialized scorers interpret responses; the existing LM Studio provider is reused behind a strict evaluator adapter. The existing onboarding state consumes the final placement decision but does not calculate it.

**Tech Stack:** Python 3.13.11, FastAPI 0.141.1, SQLAlchemy 2.0.51, PostgreSQL 17, Alembic 1.19.1, Pydantic 2.13.4, httpx 0.28.1, React 19.2.8, TypeScript 6.0.3, TanStack Query 5.101.4, Vitest 4.1.10, Playwright 1.62.0, Docker Compose, LM Studio `qwen/qwen3.6-35b-a3b`.

## Global Constraints

- PostgreSQL remains the sole source of truth.
- Public APIs remain under `/api/v1`; OpenAPI and the generated TypeScript client must stay synchronized.
- Every effectful command requires `Idempotency-Key`, expected version, CSRF/origin checks, and owner authorization.
- Responses, instances, interpretations, observations, decisions, and snapshots are append-only; invalidation or replacement is explicit.
- Normal placement duration is 8-12 minutes, maximum 20 minutes, with an evidence-based early exit for confirmed absolute beginners.
- Skill levels use the internal 0-8 scale and are never presented as official CEFR, ACTFL, or native certification.
- Declared experience changes the prior only; it never creates pedagogical evidence.
- LM Studio endpoint is `POST http://localhost:1234/api/v1/chat`, model is exactly `qwen/qwen3.6-35b-a3b`, `store=false`, no retry, no fallback, and no silent model substitution.
- Only `output[type="message"]` is consumed from LM Studio; reasoning is ignored.
- The placement evaluator and conversational teacher are separate roles.
- TTS can measure listening; speaking remains `not_observed` without a qualified STT/live/human path.
- Provider unavailability is visible and never becomes learner failure.
- Italian is the complete placement pack; Japanese proves script-sensitive multilingual behavior.
- No V1/V2 data migration is required; local development volumes may be reset.
- Implementation runs inline in this task; no subagents.

---

## File and Boundary Map

### New backend module

- `backend/src/polyglot/modules/placement/domain.py`: immutable run, item, response, estimate, contradiction, and decision types.
- `backend/src/polyglot/modules/placement/policy.py`: pure candidate filtering, priority calculation, estimate updates, and stop rules.
- `backend/src/polyglot/modules/placement/scoring.py`: deterministic and structured scorers plus observation validation.
- `backend/src/polyglot/modules/placement/evaluator.py`: strict LM Studio evaluator contract and parser.
- `backend/src/polyglot/modules/placement/persistence.py`: SQLAlchemy table metadata, owner-scoped repository, and application service.
- `backend/src/polyglot/modules/placement/catalogue.py`: published bank reader and pack validation.
- `backend/src/polyglot/modules/placement/calibration.py`: P0-P3 calibration policy and sprint probe requests.
- `backend/src/polyglot/interfaces/http/routes/placement.py`: placement API schemas and routes only.

### Existing backend integration points

- `backend/src/polyglot/interfaces/http/app.py`: construct placement dependencies and mount the router.
- `backend/src/polyglot/modules/language_profiles/onboarding.py`: consume a placement decision and retain user choice semantics.
- `backend/src/polyglot/modules/language_profiles/onboarding_persistence.py`: read the latest placement snapshot instead of accepting arbitrary placement writes.
- `backend/src/polyglot/modules/sprints/persistence.py`: request at most two calibration probes and record calibration advancement after completed daily runs.
- `backend/src/polyglot/modules/teacher/persistence.py`: include a bounded placement summary in teacher context.
- `backend/src/polyglot/bootstrap/pilot.py`: publish Italian and Japanese placement banks.
- `backend/src/polyglot/modules/media/ports.py`: expose deterministic placement listening capabilities through the existing TTS abstraction.

### Database and contracts

- `backend/migrations/versions/0025_adaptive_placement.py`: new `placement` schema, RLS policies, constraints, indexes, events, and grants.
- `contracts/registry/commands.yaml`: placement commands.
- `contracts/registry/queries.yaml`: placement reads.
- `contracts/events/event-catalogue.yaml`: placement and calibration events.
- `contracts/tests/fixtures/canonical-sets.json`: canonical command/query mappings.
- `contracts/openapi/v1.json`: generated API contract.

### Frontend

- `frontend/src/features/profile/placement-page.tsx`: sequential placement workflow and result routing.
- `frontend/src/features/profile/placement-reader.tsx`: typed item readers for placement primitives.
- `frontend/src/features/profile/placement-result.tsx`: per-skill result, confidence, unknowns, and choice controls.
- `frontend/src/features/profile/placement-state.ts`: resume key and run-state helpers.
- `frontend/src/features/profile/profile-page.tsx`: profile/goals shell only; remove the fixed manifest UI after cutover.
- `frontend/src/generated/*`: regenerated API client and models.
- `frontend/tests/e2e/placement/placement.spec.ts`: Italian, Japanese, provider failure, resume, and P0-P3 journeys.

---

### Task 1: Placement Domain and Versioned Policy

**Files:**
- Create: `backend/src/polyglot/modules/placement/__init__.py`
- Create: `backend/src/polyglot/modules/placement/domain.py`
- Create: `backend/src/polyglot/modules/placement/policy.py`
- Create: `backend/tests/unit/placement/test_domain.py`
- Create: `backend/tests/unit/placement/test_policy.py`
- Create: `backend/tests/property/placement/test_policy_properties.py`

**Interfaces:**
- Consumes: `EntryPath` from `polyglot.modules.language_profiles.onboarding` and UUIDv7 identifiers.
- Produces: `SkillDimension`, `ObservationStatus`, `PlacementStatus`, `ScoringKind`, `SkillEstimate`, `PlacementCandidate`, `PlacementObservation`, `PlacementState`, `PlacementPolicyV1`, `SelectionDecision`, and `StopDecision`.

- [ ] **Step 1: Write failing domain validation tests**

```python
def test_unobserved_skill_has_no_invented_level() -> None:
    estimate = SkillEstimate.unobserved("listening")
    assert estimate.status is ObservationStatus.NOT_OBSERVED
    assert estimate.probable_level is None
    assert estimate.confidence == 0

def test_observed_bounds_must_be_ordered() -> None:
    with pytest.raises(DomainError):
        SkillEstimate.observed("reading", lower=5, probable=3, upper=4, confidence=0.8)
```

- [ ] **Step 2: Run the tests and confirm missing-module failure**

Run: `cd backend && .venv/bin/pytest tests/unit/placement/test_domain.py -q`

Expected: collection fails because `polyglot.modules.placement` does not exist.

- [ ] **Step 3: Implement immutable domain types**

Implement these exact constructors and fields:

```python
class SkillDimension(StrEnum):
    SCRIPT = "script"
    READING = "reading"
    LISTENING = "listening"
    WRITING = "writing"
    SPEAKING = "speaking"
    VOCABULARY = "vocabulary"
    GRAMMAR_FUNCTIONS = "grammar_functions"
    INTERACTION_REPAIR = "interaction_repair"
    PRAGMATICS_REGISTER = "pragmatics_register"

@dataclass(frozen=True, slots=True)
class SkillEstimate:
    skill_ref: str
    status: ObservationStatus
    lower_bound: int | None
    probable_level: int | None
    upper_bound: int | None
    confidence: float
    independent_evidence_count: int
    confirmed_success_level: int | None
    confirmed_failure_level: int | None
    unresolved_contradiction_ids: tuple[UUID, ...]
```

Validate levels in `[0, 8]`, ordered bounds, confidence in `[0, 1]`, and no levels for `NOT_OBSERVED`.

- [ ] **Step 4: Write failing policy examples**

Cover:

```python
def test_beginner_prior_starts_at_level_one(): ...
def test_advanced_prior_starts_at_level_six(): ...
def test_strong_success_raises_lower_bound_only(): ...
def test_open_response_cannot_close_bound_without_corroboration(): ...
def test_twenty_minutes_forces_partial_completion(): ...
def test_confirmed_beginner_can_stop_before_eight_minutes(): ...
def test_same_seed_and_history_select_same_candidate(): ...
```

- [ ] **Step 5: Implement `PlacementPolicyV1`**

Expose pure methods:

```python
class PlacementPolicyV1:
    minimum_seconds = 480
    target_seconds = 720
    maximum_seconds = 1200

    def initial_state(self, entry_path: EntryPath, skill_refs: tuple[str, ...]) -> PlacementState: ...
    def update(self, state: PlacementState, observation: PlacementObservation) -> PlacementState: ...
    def select(self, state: PlacementState, candidates: tuple[PlacementCandidate, ...], *, seconds_remaining: int, seed: str) -> SelectionDecision: ...
    def should_stop(self, state: PlacementState, *, elapsed_seconds: int) -> StopDecision: ...
```

Use explicit integer/rational weights and deterministic tie-breaking by candidate UUID. Do not add IRT dependencies.

- [ ] **Step 6: Add property tests**

Prove that bounds never leave `[0, 8]`, lower never exceeds upper, elapsed time never selects an oversized item, used variants are never selected, and identical input produces identical output.

- [ ] **Step 7: Run focused quality checks**

Run:

```bash
cd backend
.venv/bin/ruff check src/polyglot/modules/placement tests/unit/placement tests/property/placement
.venv/bin/mypy src/polyglot/modules/placement
.venv/bin/pytest tests/unit/placement tests/property/placement -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/src/polyglot/modules/placement backend/tests/unit/placement backend/tests/property/placement
git commit -m "feat(placement): add bounded adaptive policy"
```

---

### Task 2: PostgreSQL Placement Baseline

**Files:**
- Create: `backend/migrations/versions/0025_adaptive_placement.py`
- Create: `backend/tests/integration/placement/test_migration_0025.py`
- Modify: `backend/migrations/env.py`
- Modify: `backend/tests/integration/platform/test_installed_artifact.py`

**Interfaces:**
- Consumes: domain enums and existing `identity.accounts`, `language_profiles.learner_language_profiles`, `catalogue.language_pack_revisions`, and media identifiers.
- Produces: all SQL tables required by `SqlPlacementService` and one migration head `0025_adaptive_placement`.

- [ ] **Step 1: Write migration shape tests**

Assert presence of schema `placement` and tables:

```text
policy_revisions
item_blueprints
item_blueprint_revisions
variant_revisions
rubric_revisions
runs
item_instances
responses
scoring_interpretations
observations
skill_estimate_revisions
contradictions
decisions
calibration_cycles
```

Also assert RLS is enabled, runtime cannot bypass ownership, one active run exists per profile, and response/instance rows reject updates and deletes through runtime grants.

- [ ] **Step 2: Run the migration test and confirm failure**

Run: `cd backend && .venv/bin/pytest tests/integration/placement/test_migration_0025.py -q`

Expected: FAIL because revision `0025_adaptive_placement` is absent.

- [ ] **Step 3: Implement migration `0025_adaptive_placement`**

Use UUIDv7 primary keys, JSONB only for closed payloads, foreign keys for published revisions, checks for levels `[0,8]`, ordered bounds, confidence `[0,1]`, positive durations, and allowed statuses. Add unique constraints for `(run_id, ordinal)`, `(run_id, idempotency_key)`, and one current item per active run.

Add owner RLS via `runs.profile_id -> learner_language_profiles.account_id = app.user_id`. Child-table policies must resolve ownership through `runs`.

- [ ] **Step 4: Register migration-owned schema exclusions correctly**

Update `backend/migrations/env.py` so Alembic compares ORM-owned tables while preserving SQL-owned RLS policies, triggers, and immutable-row guards.

- [ ] **Step 5: Validate complete migration lifecycle**

Run on a disposable database:

```bash
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/alembic -c backend/alembic.ini downgrade 0024_parallel_practice
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/alembic -c backend/alembic.ini check
backend/.venv/bin/alembic -c backend/alembic.ini heads
```

Expected: one head, no drift.

- [ ] **Step 6: Verify wheel packaging**

Update the installed-artifact test to require `polyglot/migrations/versions/0025_adaptive_placement.py`, then run it against the disposable PostgreSQL database.

- [ ] **Step 7: Commit**

```bash
git add backend/migrations backend/tests/integration/placement backend/tests/integration/platform/test_installed_artifact.py
git commit -m "feat(placement): persist adaptive runs and evidence"
```

---

### Task 3: Published Placement Catalogue and Pack Validation

**Files:**
- Create: `backend/src/polyglot/modules/placement/catalogue.py`
- Create: `backend/tests/unit/placement/test_catalogue.py`
- Create: `backend/tests/integration/placement/test_catalogue_repository.py`
- Modify: `backend/src/polyglot/bootstrap/pilot.py`
- Create: `scripts/generate_placement_fixtures.py`
- Create: `fixtures/canonical/FX-PLACEMENT-IT/manifest.json`
- Create: `fixtures/canonical/FX-PLACEMENT-IT/catalogue.json`
- Create: `fixtures/canonical/FX-PLACEMENT-JA/manifest.json`
- Create: `fixtures/canonical/FX-PLACEMENT-JA/catalogue.json`

**Interfaces:**
- Consumes: `PlacementCandidate`, core primitive IDs, language pack provenance, Italian grammar functions, Japanese script definitions, and existing TTS fixtures.
- Produces: `PlacementCatalogueReader.read_pack(pack_revision_id) -> PublishedPlacementPack` and `validate_pack(pack) -> ValidationReport`.

- [ ] **Step 1: Write pack validation tests**

Reject packs with missing primary skill, difficulty outside 0-8, fewer than two primitives for a measurable core dimension, missing rubric, duplicate variant checksum, unresolvable prerequisite, or listening item without media requirements.

- [ ] **Step 2: Implement closed catalogue dataclasses and reader**

Define:

```python
@dataclass(frozen=True, slots=True)
class PublishedPlacementVariant: ...

@dataclass(frozen=True, slots=True)
class PublishedPlacementBlueprint:
    blueprint_revision_id: UUID
    primitive_revision_id: UUID
    primary_skill_ref: str
    secondary_skill_refs: tuple[str, ...]
    editorial_difficulty: int
    expected_duration_seconds: int
    checker_kind: ScoringKind
    variant_pool_id: UUID
    variants: tuple[PublishedPlacementVariant, ...]

class PlacementCatalogueReader(Protocol):
    async def read_pack(self, pack_revision_id: UUID) -> PublishedPlacementPack | None: ...
```

- [ ] **Step 3: Generate the Italian fixture bank**

Include deterministic coverage from levels 0-8 for script/phonology access, reading, listening, vocabulary, grammar functions, writing, repair, and register. Provide at least three variants for decision-critical cells and ceiling tasks at levels 7-8. Reuse certified grammar references rather than embedding Italian constants in the engine.

- [ ] **Step 4: Generate the Japanese proof bank**

Include script-free sound/meaning tasks, hiragana access, segmentation, listening, basic writing, grammar functions, and at least one high-level placeholder-free ceiling branch using published Japanese content. Ensure failed script access filters kanji-dependent items rather than blocking training.

- [ ] **Step 5: Publish fixture revisions in `bootstrap/pilot.py`**

Insertion must be idempotent by revision ID and provenance. Extend bootstrap count assertions so Italian and Japanese placement rows are independently counted.

- [ ] **Step 6: Test cross-language isolation**

Seed both packs, publish a newer Italian blueprint for a primitive also used by Japanese, and assert Japanese catalogue reads never return Italian provenance.

- [ ] **Step 7: Run tests and fixture regeneration checks**

```bash
cd backend
.venv/bin/pytest tests/unit/placement/test_catalogue.py tests/integration/placement/test_catalogue_repository.py -q
cd ..
python3 scripts/generate_placement_fixtures.py --check
```

- [ ] **Step 8: Commit**

```bash
git add backend/src/polyglot/modules/placement/catalogue.py backend/src/polyglot/bootstrap/pilot.py backend/tests fixtures/canonical/FX-PLACEMENT-* scripts/generate_placement_fixtures.py
git commit -m "feat(placement): publish Italian and Japanese item banks"
```

---

### Task 4: Candidate Selection, Contradictions, and Stop Decisions

**Files:**
- Modify: `backend/src/polyglot/modules/placement/policy.py`
- Create: `backend/tests/unit/placement/test_selection_scenarios.py`
- Create: `backend/tests/property/placement/test_selection_properties.py`

**Interfaces:**
- Consumes: published candidates and `PlacementState`.
- Produces: selection reason codes `required_coverage`, `information_gain`, `contradiction_resolution`, `ceiling_probe`, and `modality_balance`; contradiction open/resolve operations; stop reasons `sufficient_precision`, `confirmed_foundations`, `time_limit`, and `bank_exhausted`.

- [ ] **Step 1: Add golden persona tests**

Implement deterministic scenarios for absolute beginner, false beginner, balanced intermediate, advanced ceiling search, native declaration, strong reading/weak listening, Japanese oral familiarity without script, and French/Spanish contrastive interference in Italian.

- [ ] **Step 2: Implement candidate filtering**

Filter used variants, unmet prerequisites, inaccessible scripts, missing media, unavailable scorer, excluded themes, accessibility conflicts, and candidates exceeding remaining time.

- [ ] **Step 3: Implement priority scoring with persisted reason data**

Return:

```python
@dataclass(frozen=True, slots=True)
class SelectionDecision:
    candidate_id: UUID
    primary_reason: str
    reason_values: tuple[tuple[str, int], ...]
```

Use scaled integers rather than floating-point tie decisions.

- [ ] **Step 4: Implement contradiction lifecycle**

Open contradictions only for materially incompatible observations. A resolution item must use another variant and preferably another primitive. Unresolved contradictions lower confidence and block a precision stop, but not the 20-minute stop.

- [ ] **Step 5: Implement stop rules exactly**

Require two independent opportunities for each indispensable measurable dimension, bounded uncertainty, required prerequisites tested, no blocking contradiction, and a ceiling probe when it can change content selection. Early beginner exit requires convergent failures on two primitives plus one functional recognition or production attempt.

- [ ] **Step 6: Run focused tests and commit**

```bash
cd backend
.venv/bin/pytest tests/unit/placement/test_selection_scenarios.py tests/property/placement/test_selection_properties.py -q
git add src/polyglot/modules/placement/policy.py tests/unit/placement tests/property/placement
git commit -m "feat(placement): select adaptive probes deterministically"
```

---

### Task 5: Deterministic and Structured Scoring

**Files:**
- Create: `backend/src/polyglot/modules/placement/scoring.py`
- Create: `backend/tests/unit/placement/test_scoring.py`
- Create: `backend/tests/property/placement/test_scoring_properties.py`

**Interfaces:**
- Consumes: frozen item instance, answer payload, rubric revision, reveal/help/media-use facts.
- Produces: `ScoringInterpretationDraft` and validated `PlacementObservation` values.

- [ ] **Step 1: Write scorer contract tests**

Cover single choice, multi-choice, ordering, pairing, normalized alternatives, exact reconstruction, cloze tokens, conjugation cells, translation alternatives, and a deliberately non-evaluable speaking item.

- [ ] **Step 2: Implement scorer registry**

Expose:

```python
class PlacementScorer(Protocol):
    def score(self, instance: FrozenPlacementItem, answer: PlacementAnswer) -> ScoringInterpretationDraft: ...

def scorer_for(kind: ScoringKind) -> PlacementScorer: ...
```

Do not reuse `_normalized_foundation_answer`; move shared Unicode normalization to a focused helper under `placement/scoring.py` with script-aware behavior that does not strip Japanese characters.

- [ ] **Step 3: Implement observation validation**

Reject skill refs not declared by the item, criterion scores outside the rubric, success claims after answer reveal, independent-evidence claims from the same variant pool, and high confidence on partially evaluable output.

- [ ] **Step 4: Add property tests**

Prove normalization idempotence, choice order invariance where allowed, invalid answer shapes fail closed, and no scorer can emit a skill outside the item contract.

- [ ] **Step 5: Run checks and commit**

```bash
cd backend
.venv/bin/ruff check src/polyglot/modules/placement/scoring.py tests/unit/placement tests/property/placement
.venv/bin/mypy src/polyglot/modules/placement/scoring.py
.venv/bin/pytest tests/unit/placement/test_scoring.py tests/property/placement/test_scoring_properties.py -q
git add src/polyglot/modules/placement/scoring.py tests/unit/placement tests/property/placement
git commit -m "feat(placement): score closed placement tasks"
```

---

### Task 6: Strict LM Studio Placement Evaluator

**Files:**
- Create: `backend/src/polyglot/modules/placement/evaluator.py`
- Create: `backend/tests/unit/placement/test_evaluator.py`
- Create: `backend/tests/integration/placement/test_lm_studio_evaluator.py`
- Modify: `backend/src/polyglot/modules/generation/providers.py` only if a generic message-extraction defect is demonstrated by a failing provider test.

**Interfaces:**
- Consumes: existing `ChatProvider`, `ChatRequest`, frozen task, rubric, allowed skill refs, and learner response.
- Produces: `PlacementJudgementDraft`; never `PlacementDecision` or direct mastery.

- [ ] **Step 1: Write strict parser tests**

Test exact keys, statuses, criterion ranges, allowed skill refs, error spans, fatal codes, confidence, rationale length, extra keys, markdown fences, missing message, reasoning-only output, wrong returned model, timeout, and network failure.

- [ ] **Step 2: Implement closed evaluator schema**

```python
@dataclass(frozen=True, slots=True)
class PlacementJudgementDraft:
    status: JudgementStatus
    criterion_scores: tuple[tuple[str, int], ...]
    demonstrated_skill_refs: tuple[str, ...]
    error_observations: tuple[ErrorObservation, ...]
    fatal_error_codes: tuple[str, ...]
    confidence: float
    short_rationale: str

class PlacementEvaluator:
    async def evaluate(self, task: EvaluationTask) -> PlacementJudgementDraft: ...
```

The evaluator prompt must omit prior level, probable level, and global placement result.

- [ ] **Step 3: Reuse `LmStudioChatProvider` without retry**

Send exactly one request with model `qwen/qwen3.6-35b-a3b`, temperature 0, reasoning off, and store false. Convert provider/schema failures to an interpretation status, not learner failure.

- [ ] **Step 4: Add real opt-in LM Studio smoke test**

Gate with `POLYGLOT_TEST_LM_STUDIO=1`. Assert returned model identity, message extraction, valid structured judgement, and absence of automatic second request by using an instrumented client in non-live tests.

- [ ] **Step 5: Run tests and commit**

```bash
cd backend
.venv/bin/pytest tests/unit/placement/test_evaluator.py tests/integration/placement/test_lm_studio_evaluator.py -q
git add src/polyglot/modules/placement/evaluator.py tests/unit/placement tests/integration/placement
git commit -m "feat(placement): evaluate open responses with LM Studio"
```

---

### Task 7: Owner-Scoped Placement Application Service

**Files:**
- Create: `backend/src/polyglot/modules/placement/persistence.py`
- Create: `backend/tests/integration/placement/conftest.py`
- Create: `backend/tests/integration/placement/test_service.py`
- Create: `backend/tests/integration/placement/test_permissions.py`
- Create: `backend/tests/integration/placement/test_reconstruction.py`

**Interfaces:**
- Consumes: policy, catalogue, scorers, evaluator, clock, ID generator, media service capability lookup, and request actor.
- Produces: `SqlPlacementService.start`, `get_run`, `get_current_item`, `submit_response`, `interrupt`, `resume`, `complete`, `get_profile`, and `list_history`.

- [ ] **Step 1: Write public-flow integration tests**

Test start freezes first item, GET is side-effect free, submit atomically stores response/interpretation/observations/estimate and next item, idempotent replay returns the same version, stale `If-Match` conflicts, interrupt/resume preserves current item, completion writes P0, and another account receives 404/forbidden without data leakage.

- [ ] **Step 2: Define service commands and views**

```python
@dataclass(frozen=True, slots=True)
class StartPlacementRun:
    run_id: UUID
    pack_revision_id: UUID
    policy_revision_id: UUID
    entry_path: EntryPath
    seed: str

@dataclass(frozen=True, slots=True)
class SubmitPlacementResponse:
    response_id: UUID
    item_instance_id: UUID
    answer: dict[str, JsonValue]
    elapsed_seconds: int
    media_events: tuple[MediaUseEvent, ...]
```

Views must expose current item and progress description without answer keys or checker values.

- [ ] **Step 3: Implement transactional start and selection**

Lock the profile, reject a second active run, persist prior estimates separately from evidence, select with policy, freeze all referenced revisions, emit `placement_run_started` and `placement_item_selected`, then commit.

- [ ] **Step 4: Implement transactional submission**

Lock the run and current item. Reserve idempotency receipt. Persist raw response. Score through the declared route. Persist interpretation and validated observations. Update estimates and contradictions. Either persist a stop decision or select/freeze the next item in the same transaction.

- [ ] **Step 5: Implement completion and reconstruction**

Completion requires a persisted stop decision. Write immutable `PlacementDecision` and estimate revision set P0, update onboarding through a dedicated internal method, and emit completion events. Reconstruction must replay observations and produce the same estimate fingerprint and decision reason.

- [ ] **Step 6: Run PostgreSQL tests and commit**

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest tests/integration/placement -q
git add src/polyglot/modules/placement/persistence.py tests/integration/placement
git commit -m "feat(placement): orchestrate immutable adaptive runs"
```

---

### Task 8: Listening Media and TTS Evidence

**Files:**
- Modify: `backend/src/polyglot/modules/placement/persistence.py`
- Modify: `backend/src/polyglot/modules/media/ports.py`
- Modify: `backend/src/polyglot/modules/media/persistence.py`
- Create: `backend/tests/integration/placement/test_listening.py`
- Modify: `scripts/generate_tts_fixtures.py`
- Modify: `fixtures/tts/local-v2/manifest.json`

**Interfaces:**
- Consumes: `TtsPort`, target language/voice capabilities, frozen placement variant, and media storage.
- Produces: signed/listenable media reference in `PlacementItemView` and immutable playback-count evidence.

- [ ] **Step 1: Write listening behavior tests**

Assert Italian uses `Alice`, Japanese uses `Kyoko`, source text/checksum/voice/speed are pinned, transcription is absent before submission, playback counts persist, unavailable TTS selects a published equivalent media item when present, and otherwise marks listening temporarily unavailable without lowering estimates.

- [ ] **Step 2: Add placement-specific synthesis request**

Use the existing generic TTS port. Do not introduce Italian constants into placement. Resolve voice through the active Language Pack and return a durable media ID plus signed content URL.

- [ ] **Step 3: Add fixture audio for placement variants**

Regenerate deterministic local fixtures and update manifest checksums. `--check` must detect missing or changed audio.

- [ ] **Step 4: Run media and placement tests**

```bash
cd backend
.venv/bin/pytest tests/unit/media tests/integration/media tests/integration/placement/test_listening.py -q
cd ..
python3 scripts/generate_tts_fixtures.py --check
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/polyglot/modules/media backend/src/polyglot/modules/placement backend/tests fixtures/tts scripts/generate_tts_fixtures.py
git commit -m "feat(placement): measure listening with pinned audio"
```

---

### Task 9: Placement HTTP API, Events, and Generated Client

**Files:**
- Create: `backend/src/polyglot/interfaces/http/routes/placement.py`
- Modify: `backend/src/polyglot/interfaces/http/app.py`
- Create: `backend/tests/contract/placement/test_commands.py`
- Create: `backend/tests/contract/placement/test_openapi.py`
- Modify: `contracts/registry/commands.yaml`
- Modify: `contracts/registry/queries.yaml`
- Modify: `contracts/events/event-catalogue.yaml`
- Modify: `contracts/tests/fixtures/canonical-sets.json`
- Modify: `contracts/openapi/v1.json`
- Regenerate: `frontend/src/generated/`

**Interfaces:**
- Consumes: `SqlPlacementService` methods from Task 7.
- Produces: the exact `/api/v1` resources specified in the design, ETags, typed problem responses, and generated React Query hooks.

- [ ] **Step 1: Write contract tests for all routes**

Cover:

```text
GET  /language-packs/{pack_revision_id}/placement-policy
POST /language-profiles/{profile_id}/placement-runs
GET  /placement-runs/{run_id}
GET  /placement-runs/{run_id}/current-item
POST /placement-runs/{run_id}/responses
POST /placement-runs/{run_id}:complete
POST /placement-runs/{run_id}:interrupt
POST /placement-runs/{run_id}:resume
GET  /language-profiles/{profile_id}/placement-profile
GET  /language-profiles/{profile_id}/placement-history
POST /language-profiles/{profile_id}/placement:choose
```

- [ ] **Step 2: Implement closed Pydantic schemas and router**

Do not expose checker values, model answers, hidden difficulty calculations, or LLM rationale before completion. Return `current_item=None` only for a completed/interrupted state where that is explicit.

- [ ] **Step 3: Wire runtime dependencies**

Construct one `LmStudioChatProvider`, pass it to both teacher and placement evaluator as separate service adapters, inject media service and catalogue reader, then mount `placement_router`.

- [ ] **Step 4: Register commands, queries, and events**

Update canonical mappings and event catalogue. Validate command idempotency and errors such as `active_run_exists`, `version_conflict`, `provider_unavailable`, `content_unavailable`, and `run_expired`.

- [ ] **Step 5: Export OpenAPI and regenerate frontend client**

```bash
backend/.venv/bin/python -m polyglot.interfaces.http.export_openapi
cd frontend && pnpm generate:api && pnpm typecheck
```

- [ ] **Step 6: Validate contracts and commit**

```bash
python3 scripts/validate_contract_registry.py contracts/registry contracts/tests --validate-tool-fixtures
cd backend && .venv/bin/pytest tests/contract/placement tests/contract/platform/test_openapi.py -q
git add backend contracts frontend/src/generated
git commit -m "feat(placement): expose adaptive placement API"
```

---

### Task 10: Sequential Placement Frontend

**Files:**
- Create: `frontend/src/features/profile/placement-page.tsx`
- Create: `frontend/src/features/profile/placement-reader.tsx`
- Create: `frontend/src/features/profile/placement-state.ts`
- Create: `frontend/src/features/profile/placement-page.test.tsx`
- Create: `frontend/src/features/profile/placement-reader.test.tsx`
- Modify: `frontend/src/features/profile/profile-page.tsx`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/app/styles.css`

**Interfaces:**
- Consumes: generated placement hooks and current-item response.
- Produces: `/language-profile/placement/:runId`, one task per screen, autosaved resume state, and accessible specialized readers.

- [ ] **Step 1: Write failing UI tests**

Test one visible item only, submit-before-next behavior, no answer key exposure, resume existing run, interrupt, radio/ordering/text/cloze/listening readers, unavailable provider message, and keyboard operation.

- [ ] **Step 2: Implement placement state helper**

```typescript
export function placementRunKey(profileId: string): string;
export function rememberPlacementRun(profileId: string, runId: string): void;
export function forgetPlacementRun(profileId: string): void;
```

Use profile-scoped storage and treat the server as authoritative.

- [ ] **Step 3: Implement specialized reader dispatch**

Map primitive/response kind to existing exercise reader patterns where compatible. Keep stable dimensions, labels, focus movement, audio controls, and submit state. Never render all bank items.

- [ ] **Step 4: Implement sequential page**

Start or resume a run, render current frozen instance, submit one answer, refresh run, and navigate to result when a stop decision is ready. Display qualitative progress and elapsed guidance, not a fixed question count.

- [ ] **Step 5: Remove fixed manifest presentation from onboarding**

`profile-page.tsx` retains language/profile/goals/entry path. Replace the six-fieldset branch with start/resume placement navigation. Do not keep the fixed manifest as fallback.

- [ ] **Step 6: Run frontend checks and commit**

```bash
cd frontend
pnpm lint
pnpm test -- --run src/features/profile/placement-page.test.tsx src/features/profile/placement-reader.test.tsx src/features/profile/profile-onboarding.test.tsx
pnpm typecheck
git add src
git commit -m "feat(placement): add sequential onboarding experience"
```

---

### Task 11: Per-Skill Result and Learner Choice

**Files:**
- Create: `frontend/src/features/profile/placement-result.tsx`
- Create: `frontend/src/features/profile/placement-result.test.tsx`
- Modify: `frontend/src/features/profile/placement-page.tsx`
- Modify: `backend/src/polyglot/modules/language_profiles/onboarding.py`
- Modify: `backend/src/polyglot/modules/language_profiles/onboarding_persistence.py`
- Create: `backend/tests/integration/placement/test_onboarding_projection.py`

**Interfaces:**
- Consumes: immutable `PlacementDecisionView` and existing `PlacementChoice` semantics.
- Produces: descriptive skill cards, confidence/unknowns, recommended foundations/module inputs, and choice events that change content selection without rewriting evidence.

- [ ] **Step 1: Write result projection tests**

Assert unobserved listening is rendered as `Non observé`, weak writing cannot be hidden by strong reading, `start_easier` changes resolved content level only, `challenge` raises proposed difficulty only, and no choice mutates P0 estimates.

- [ ] **Step 2: Replace arbitrary placement write path**

Remove or make internal-only `PATCH /onboarding/placement`. Onboarding must consume the placement decision created by `SqlPlacementService.complete`; clients cannot submit detected bands or evidence counts.

- [ ] **Step 3: Implement result UI**

Show observed dimensions, confidence language, unresolved contradictions, temporarily unavailable modalities, recommended start, targeted foundations, and four user choices. Do not display a dominant average score.

- [ ] **Step 4: Test accessibility and responsive layout**

Verify headings, status text, button names, no color-only confidence, 320 px reflow, and zoom 200%.

- [ ] **Step 5: Run tests and commit**

```bash
cd backend && .venv/bin/pytest tests/integration/placement/test_onboarding_projection.py tests/unit/language_profiles/test_onboarding.py -q
cd ../frontend && pnpm test -- --run src/features/profile/placement-result.test.tsx
git add backend frontend
git commit -m "feat(placement): explain placement and learner choices"
```

---

### Task 12: P0-P3 Sprint Calibration

**Files:**
- Create: `backend/src/polyglot/modules/placement/calibration.py`
- Create: `backend/tests/unit/placement/test_calibration.py`
- Create: `backend/tests/integration/placement/test_sprint_calibration.py`
- Modify: `backend/src/polyglot/modules/sprints/persistence.py`
- Modify: `backend/src/polyglot/modules/sprints/domain.py`
- Modify: `frontend/src/features/today/today-page.tsx`
- Modify: `frontend/src/features/progress/progress-page.tsx`

**Interfaces:**
- Consumes: completed P0 decision, unresolved contradictions, sprint theme/content candidates, and completed exercise observations.
- Produces: at most two `CalibrationProbeRequest` values per daily sprint, P1/P2/P3 estimate snapshots, and an explained adjustment record.

- [ ] **Step 1: Write calibration policy tests**

```python
def test_sprint_one_confirms_general_difficulty(): ...
def test_sprint_two_targets_highest_priority_contradiction(): ...
def test_sprint_three_confirms_curriculum_prerequisite(): ...
def test_free_practice_does_not_advance_p0_p3_cycle(): ...
def test_daily_sprint_contains_at_most_two_calibration_probes(): ...
def test_major_adjustment_requires_explanation_codes(): ...
```

- [ ] **Step 2: Implement `CalibrationPolicyV1`**

```python
class CalibrationPolicyV1:
    def requests_for(self, cycle: PlacementCalibrationCycle, session_context: CalibrationSessionContext) -> tuple[CalibrationProbeRequest, ...]: ...
    def advance(self, cycle: PlacementCalibrationCycle, observations: tuple[PlacementObservation, ...]) -> CalibrationAdvance: ...
```

- [ ] **Step 3: Integrate probes into daily composition**

Insert probes after mandatory due reviews and within the selected budget. Match theme/vocabulary where possible. Do not consume or reorder curriculum days beyond the normal daily completion rules.

- [ ] **Step 4: Advance only after completed daily runs**

On completion, validate eligible observations, append the next snapshot, decrement remaining calibration sessions, and finish at P3. Interrupted/abandoned/free runs do not advance the cycle.

- [ ] **Step 5: Surface calibration status**

Today shows a concise `Profil en cours d'affinage` state. Progress shows P0-P3 history and explanations for material changes, with no silent downgrade language.

- [ ] **Step 6: Run tests and commit**

```bash
cd backend
.venv/bin/pytest tests/unit/placement/test_calibration.py tests/integration/placement/test_sprint_calibration.py tests/integration/sprints -q
cd ../frontend
pnpm test -- --run src/features/today src/features/progress
git add backend frontend
git commit -m "feat(placement): calibrate profile across first sprints"
```

---

### Task 13: Teacher Context Without Evaluator Authority

**Files:**
- Modify: `backend/src/polyglot/modules/teacher/persistence.py`
- Modify: `backend/src/polyglot/modules/teacher/orchestration.py`
- Create: `backend/tests/integration/teacher/test_placement_context.py`
- Modify: `frontend/src/features/teacher/teacher-drawer.tsx`

**Interfaces:**
- Consumes: latest P0-P3 placement profile summary.
- Produces: minimal teacher context with observed levels, uncertainty, errors, known-language bridges, priorities, and explicit unknowns.

- [ ] **Step 1: Write teacher boundary tests**

Assert prompt context includes `reading level 5`, `listening uncertain`, and `speaking not observed`; excludes raw responses by default; and teacher actions cannot create placement observations, estimate revisions, decisions, or calibration advancement.

- [ ] **Step 2: Implement bounded summary query**

Add a repository query returning only latest estimates, confidence bands, error codes, relevant account-language bridges, and calibration status. Keep evaluator rationale and learner raw text out of the default teacher prompt.

- [ ] **Step 3: Strengthen teacher action allowlist**

Add explicit negative tests for `assign_level`, `record_placement_evidence`, and `complete_calibration`. Keep existing reversible actions unchanged.

- [ ] **Step 4: Display provisional context status**

The drawer may state that the profile is still being calibrated. It must not claim that the professor determined the level.

- [ ] **Step 5: Run tests and commit**

```bash
cd backend
.venv/bin/pytest tests/integration/teacher/test_placement_context.py tests/unit/teacher -q
cd ../frontend
pnpm test -- --run src/features/teacher/teacher-drawer.test.tsx
git add backend frontend
git commit -m "feat(teacher): consume bounded placement context"
```

---

### Task 14: Retire Fixed Diagnostic and Preserve Historical Readability

**Files:**
- Modify: `backend/src/polyglot/interfaces/http/routes/catalogue.py`
- Modify: `backend/src/polyglot/interfaces/http/routes/language_profiles.py`
- Modify: `backend/src/polyglot/modules/language_profiles/application.py`
- Modify: `backend/src/polyglot/modules/lexicon/exchange/persistence.py`
- Create: `backend/tests/integration/placement/test_data_rights.py`
- Modify: `frontend/src/features/profile/profile-page.tsx`
- Modify: `contracts/registry/commands.yaml`
- Modify: `contracts/registry/queries.yaml`
- Modify: `contracts/openapi/v1.json`
- Modify: `frontend/src/generated/`
- Modify: existing diagnostic tests to become historical-read tests or remove obsolete behavior assertions.

**Interfaces:**
- Consumes: complete replacement API from Tasks 7-11.
- Produces: no fixed six-question creation path; old completed diagnostic rows remain readable for audit/export until the next clean local reset.

- [ ] **Step 1: Add a negative contract test**

Assert OpenAPI no longer exposes `/language-packs/{pack_revision_id}/placement-manifest` and frontend contains no copy `Six tâches` or loop rendering all placement items.

- [ ] **Step 2: Remove fixed creation and completion routes**

Remove new-run access through legacy diagnostic commands. If historical GET remains during the same release, mark it read-only and absent from current onboarding navigation.

- [ ] **Step 3: Remove obsolete calculation paths**

Delete `skill_profile_from_diagnostic` usage for new placements and the block-ordinal-as-difficulty mapping. Preserve only code required to deserialize historical rows until the clean baseline decision removes them.

- [ ] **Step 4: Integrate export and deletion rights**

Extend `SqlExchangeService._build_export_payload` so a profile export includes
placement runs, frozen item metadata, learner responses, interpretations,
observations, estimate revisions, contradictions, decisions, and calibration
history. Do not export private model reasoning because it is never persisted.

Verify profile deletion blocks new placement runs immediately and that the
existing purge/cascade path removes private placement rows while leaving shared
published item banks intact. Add assertions for both export content and purge
scope in `test_data_rights.py`.

- [ ] **Step 5: Re-export contracts and regenerate client**

Run OpenAPI export, registry validation, generated-client build, and a repository search proving no fixed copy or route remains.

- [ ] **Step 6: Commit**

```bash
git add backend frontend contracts
git commit -m "refactor(onboarding): retire fixed diagnostic flow"
```

---

### Task 15: Full Validation, Graphical Audit, and Delivery

**Files:**
- Create: `frontend/tests/e2e/placement/placement.spec.ts`
- Create: `docs/evidence/placement/README.md`
- Add screenshots under: `docs/evidence/placement/browser/`
- Modify: `README.md` only if onboarding/run instructions changed.

**Interfaces:**
- Consumes: complete adaptive placement feature.
- Produces: empty-database proof, real LM Studio proof, responsive screenshots, clean Git state, commit, push, and healthy Docker runtime at `http://127.0.0.1:9001`.

- [ ] **Step 1: Add complete Playwright journeys**

Journey A: fresh account, French and Spanish known, Italian already started, adaptive reading/listening/writing/grammar, LM Studio production score, result choice, first daily sprint.

Journey B: fresh French-to-Japanese beginner, script-inaccessible branch, script-free task, foundation recommendation, first card, and profile switch.

Journey C: advanced profile reaches ceiling probe without native certification.

Journey D: LM Studio unavailable, open response preserved/non-evaluable, deterministic continuation, honest partial result.

Journey E: interruption/reload/resume with no duplicate response.

Journey F: P0 plus three completed daily sprints produces P3 and an explained adjustment.

- [ ] **Step 2: Run backend static and unit/property suites**

```bash
cd backend
.venv/bin/ruff check src tests migrations
.venv/bin/mypy src
.venv/bin/pytest tests/unit tests/property -q
```

- [ ] **Step 3: Reset PostgreSQL and run integration/contracts**

```bash
set -a; source .local/runtime.env; set +a
docker compose down --volumes --remove-orphans
docker compose up -d --wait postgres
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
cd backend
PYTHONPATH=. .venv/bin/pytest tests/integration tests/contract -q
```

- [ ] **Step 4: Run real LM Studio validation**

```bash
cd backend
POLYGLOT_TEST_LM_STUDIO=1 .venv/bin/pytest tests/integration/placement/test_lm_studio_evaluator.py -q
```

Record model identity, one-request behavior, structured result validity, and message-only extraction. Do not record private reasoning.

- [ ] **Step 5: Run frontend quality and E2E**

```bash
cd frontend
pnpm lint
pnpm test -- --run
pnpm build
pnpm test:e2e
```

- [ ] **Step 6: Perform manual graphical audit**

Using the in-app browser, inspect onboarding, each reader type, listening state, result, teacher provisional context, and calibration status at 320x800, 768x900, and 1440x900. Check horizontal overflow, focus order, text overlap, media controls, console errors, keyboard-only operation, axe, and zoom 200%.

- [ ] **Step 7: Validate repository and package boundaries**

```bash
python3 scripts/validate_contract_registry.py contracts/registry contracts/tests --validate-tool-fixtures --check-doc-links --check-artifacts
git diff --check
git status --short
```

Run the installed-wheel migration round-trip test. If macOS offloads a tracked document and blocks link validation, hydrate that tracked file first and rerun; do not waive the final gate.

- [ ] **Step 8: Rebuild clean deliverable and leave it running**

```bash
set -a; source .local/runtime.env; set +a
docker compose down --volumes --remove-orphans
docker compose up -d --build --wait
curl -fsS http://127.0.0.1:9001/api/v1/health/live
curl -fsS http://127.0.0.1:9001/api/v1/health/ready
```

Expected: PostgreSQL, backend, and frontend healthy; readiness reports database and object storage ready.

- [ ] **Step 9: Final review, commit, and push**

Review staged files for secrets, private prompts, databases, conflict markers, generated reports, and unrelated changes. Then:

```bash
git add backend frontend contracts fixtures scripts docs README.md
git commit -m "feat(placement): deliver adaptive multilingual onboarding"
git push origin codex/v2-rebuild
```

Do not commit `frontend/test-results`, Playwright HTML reports, `.local`, secrets, or databases.

---

## Execution Order and Review Gates

| Wave | Tasks | Review gate |
|---|---|---|
| A | 1-2 | Pure policy and PostgreSQL invariants approved |
| B | 3-5 | Italian/Japanese banks, selection, and closed scoring approved |
| C | 6-8 | LM evaluator, application service, and listening proof approved |
| D | 9-11 | Public API, sequential UX, and result semantics approved |
| E | 12-14 | P0-P3, teacher boundary, and fixed-flow retirement approved |
| F | 15 | Empty-database, live-provider, visual, and delivery gates complete |

At each gate, inspect the diff, run the listed focused tests, and push only if the increment is independently usable. Never combine a failing migration, an unstable contract, and frontend changes in one recovery commit.
