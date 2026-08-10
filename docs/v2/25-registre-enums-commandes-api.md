# Polyglot V2 - Registre canonique des enums, commandes et routes

## 1. Autorité

Ce document ferme le contrat conceptuel de `C04` et `C05`. Sous réserve des
décisions explicitement approuvées du document 06, il est normatif pour les noms
techniques et correspondances API. Le document 09 est seul propriétaire des
transitions et de leurs préconditions ; le document 16 décrit le transport et le
frontend. En cas
d'écart de nom ou de route entre contrats de même rang, le présent registre
prévaut jusqu'à génération de l'OpenAPI exécutable.

Tous les enums et codes techniques sont ASCII `lower_snake_case`. Les labels
français sont des traductions UI, jamais des valeurs persistées. Les priorités
de tâche s'écrivent `PRI-P0`; les gates de release `GATE-G0`; les bandes
d'évaluation `ASSESS-B0..B4`.

## 2. Enums centraux

| Type | Valeurs canoniques |
|---|---|
| `language_profile_status` | `onboarding`, `foundations`, `active`, `paused`, `archived`, `deleting`, `deleted` |
| `content_revision_status` | `draft`, `validating`, `validated`, `approved`, `published`, `retired`, `superseded`, `rejected`, `abandoned` |
| `module_enrollment_status` | `planned`, `active`, `paused`, `completed`, `abandoned`, `cancelled` |
| `session_plan_status` | `draft`, `preparing`, `ready`, `failed`, `expired`, `cancelled` |
| `sprint_run_status` | `not_started`, `in_progress`, `interrupted`, `completed`, `stopped`, `cancelled` |
| `exercise_block_status` | `pending`, `available`, `in_progress`, `completed`, `skipped`, `abandoned`, `unavailable` |
| `attempt_status` | `draft`, `submitted`, `correcting`, `corrected`, `not_evaluable` |
| `attempt_terminal_reason` | `none`, `correction_unavailable`, `correction_ambiguous`, `answer_invalid`, `user_cancelled` |
| `correction_case_status` | `closed`, `contested`, `review_pending`, `resolved` |
| `correction_verdict` | `correct`, `partially_correct`, `incorrect`, `ambiguous`, `invalid_answer`, `not_evaluable` |
| `learning_need_status` | `open`, `planned`, `resolved`, `superseded` |
| `assessment_run_status` | `prepared`, `in_progress`, `paused`, `submitted`, `expired`, `scoring`, `review_required`, `completed`, `cancelled` |
| `job_status` | `requested`, `queued`, `running`, `retry_wait`, `cancel_requested`, `succeeded`, `failed`, `cancelled` |
| `mastery_status` | `non_observed`, `discovered`, `in_progress`, `reliable`, `mastered`, `review_due`, `not_evaluable` |
| `memory_prompt_status` | `active`, `suspended`, `superseded`, `archived`, `deleted` |
| `memory_state` | `new`, `learning`, `review`, `relearning` |
| `memory_rating` | `again`, `hard`, `good`, `easy` |
| `media_status` | `reserved`, `uploading`, `uploaded`, `verifying`, `quarantined`, `processing`, `ready`, `rejected`, `failed`, `deleting`, `deleted` |

### 2.1 Enums de domaine complémentaires

Ces valeurs ont la même autorité que les enums centraux. Un pack peut étendre
ses propres taxonomies linguistiques, mais aucun module applicatif ne crée une
valeur persistée hors de ce registre sans RFC de contrat.

| Type | Valeurs canoniques |
|---|---|
| `account_status` | `active`, `locked`, `pending_deletion`, `deleted` |
| `account_role` | `learner`, `author`, `reviewer`, `support`, `admin`, `worker` |
| `identity_provider_type` | `local_password`, `oidc` |
| `consent_status` | `granted`, `withdrawn` |
| `privacy_class` | `public`, `internal`, `personal`, `sensitive`, `secret` |
| `guided_run_status` | `prepared`, `in_progress`, `interrupted`, `completed`, `expired`, `cancelled` |
| `modality` | `reading`, `listening`, `writing`, `speaking` |
| `operation` | `recognize`, `recall`, `discriminate`, `transform`, `produce`, `interact`, `repair`, `transfer` |
| `prerequisite_edge_type` | `required`, `recommended`, `contrast`, `transfer` |
| `mention_analysis_status` | `pending`, `ambiguous`, `resolved`, `disputed` |
| `list_type` | `manual`, `editorial`, `dynamic` |
| `list_status` | `active`, `archived` |
| `session_purpose` | `daily`, `free`, `foundation`, `assessment_prep` |
| `module_arc_type` | `discovery`, `guided_use`, `integration`, `transfer`, `consolidation` |
| `session_block_family` | `recall_warmup`, `lexical_acquisition`, `version_input`, `grammar_toolbox`, `transformation_gym`, `listening`, `shadowing`, `guided_output`, `free_writing`, `delayed_recode`, `reflection_close` |
| `session_lexical_role` | `new`, `due`, `debt`, `target`, `support`, `distractor`, `rescue` |
| `exercise_language_certification_status` | `certified`, `suspended`, `withdrawn` |
| `primitive_maturity` | `core`, `extended`, `future` |
| `answer_kind` | `acknowledgement`, `single_choice`, `graded_choice`, `selection`, `pairing`, `grouping`, `ordered_items`, `cells`, `spans`, `tokens`, `text`, `short_text`, `audio_ref`, `self_grade`, `self_assessment`, `no_answer` |
| `hint_level` | `h0`, `h1`, `h2`, `h3`, `h4` |
| `correction_strategy` | `exact_normalized`, `accepted_set`, `morphological`, `structural_constraints`, `bounded_translation`, `rubric`, `self_assessment`, `human_review`, `llm_review` |
| `validation_report_status` | `pending`, `running`, `passed`, `failed`, `human_required`, `cancelled` |
| `assessment_section_status` | `pending`, `in_progress`, `completed`, `skipped`, `expired` |
| `assessment_result_status` | `valid`, `indicative`, `not_evaluable` |
| `assessment_band` | `assess_b0`, `assess_b1`, `assess_b2`, `assess_b3`, `assess_b4` |
| `tts_availability` | `available`, `temporarily_unavailable`, `retired`, `unsupported` |
| `job_attempt_status` | `running`, `succeeded`, `retryable_failed`, `failed`, `cancelled` |
| `tool_invocation_status` | `requested`, `running`, `succeeded`, `failed`, `cancelled` |
| `import_status` | `uploaded`, `quarantined`, `parsing`, `invalid`, `preview_ready`, `awaiting_decision`, `committing`, `committed`, `failed`, `cancelled`, `reverted` |
| `import_line_status` | `pending`, `accepted`, `rejected`, `conflict`, `committed`, `reverted` |
| `import_strategy` | `fail_on_conflict`, `reuse_exact`, `create_distinct`, `interactive` |
| `import_conflict_class` | `exact_identity`, `same_sense`, `same_form_other_sense`, `same_prompt`, `content_revision_conflict`, `private_public_collision`, `ambiguous` |
| `export_status` | `requested`, `queued`, `running`, `ready`, `failed`, `expired`, `cancelled` |
| `command_receipt_status` | `started`, `succeeded`, `rejected`, `failed` |
| `deletion_request_status` | `requested`, `confirmed`, `blocked`, `purging`, `completed`, `cancelled`, `failed` |
| `delivery_status` | `specified`, `planned`, `implemented`, `verified`, `accepted`, `released` |
| `learning_phase` | `diagnostic`, `foundations`, `module_learning`, `paused`, `archived` |
| `diagnostic_classification` | `beginner`, `false_beginner`, `intermediate`, `undetermined` |
| `foundation_block_status` | `locked`, `available`, `in_progress`, `passed`, `waived` |
| `foundation_run_block_status` | `pending`, `available`, `in_progress`, `completed`, `failed`, `waived` |
| `lexical_unit_type` | `word`, `multiword_expression`, `proper_name`, `lexicalized_construction` |
| `lexical_visibility` | `shared`, `private` |
| `delayed_task_type` | `delayed_recode`, `delayed_recall`, `transfer_check` |
| `delayed_task_due_rule` | `next_active_session`, `after_24h`, `after_7d` |
| `delayed_task_status` | `scheduled`, `due`, `fulfilled`, `expired`, `cancelled` |
| `observation_target_type` | `skill`, `lexical_sense`, `lexical_form`, `grammar_structure`, `grammar_pattern`, `pronunciation_target` |
| `observation_role` | `primary`, `secondary`, `support`, `distractor` |
| `observation_result` | `success`, `partial_success`, `failure`, `inconclusive` |
| `evidence_source_type` | `assessment`, `daily_sprint`, `foundations`, `free_practice`, `diagnostic`, `declaration`, `exposure` |
| `lexical_learning_preference` | `normal`, `prioritize`, `ignore` |
| `free_practice_challenge` | `gentler`, `matched`, `stretch` |

Mapping UX initial : `non_observed -> Non observé`, `discovered -> Découvert`,
`in_progress -> En cours`, `reliable -> Fiable`, `mastered -> Maîtrisé`,
`review_due -> À revoir`, `not_evaluable -> Non évaluable`. Les vues Word Bank
`rencontré`, `reconnu` et `utilisable` sont des filtres dérivés, pas des états de
maîtrise supplémentaires.

## 3. Règles communes des commandes

- Toutes les commandes sont authentifiées sauf inscription et création de
  session.
- Toute création/soumission/import/job exige `Idempotency-Key`.
- Toute mutation d'une ressource existante exige `If-Match` sauf ajout
  append-only dédupliqué.
- Les routes d'action utilisent un nom stable après `:` ; elles ne simulent pas
  une modification CRUD ambiguë.
- `idem` dans les tables vaut `required`, `supported` ou `n/a`.
- Erreurs communes : `validation_failed`, `unauthenticated`, `forbidden`,
  `not_found`, `version_conflict`, `idempotency_conflict`,
  `invalid_transition`, `rate_limited`, `dependency_unavailable` et
  `internal_error`.

## 4. Identité, profil et diagnostic

| Commande | Route | Permission/précondition | Événement principal | Erreurs spécifiques | idem |
|---|---|---|---|---|---|
| `RegisterAccount` | `POST /api/v1/accounts` | public, identité unique | `account_registered` | `identity_conflict` | required |
| `AuthenticateSession` | `POST /api/v1/session` | identité valide | `session_authenticated` | `invalid_credentials`, `account_locked` | required |
| `RevokeSession` | `DELETE /api/v1/session` | session courante | `session_revoked` | - | supported |
| `ChangePassword` | `PUT /api/v1/account/password` | identité locale, réauth récente | `password_changed`, `sessions_revoked` | `identity_provider_mismatch` | required |
| `UpdateUserPreferences` | `PATCH /api/v1/account/preferences` | propriétaire, version | `user_preferences_updated` | - | supported |
| `UpdateConsent` | `PUT /api/v1/consents/{purpose}` | propriétaire, finalité connue, version | `consent_updated` | `consent_purpose_unknown` | required |
| `CreateLanguageProfile` | `POST /api/v1/language-profiles` | paire/variété publiée | `language_profile_created` | `profile_already_exists` | required |
| `UpdateLearningGoals` | `PATCH /api/v1/language-profiles/{profile_id}/goals` | propriétaire, non supprimé | `learning_goals_updated` | - | supported |
| `StartDiagnostic` | `POST /api/v1/language-profiles/{profile_id}/diagnostics` | statut `onboarding` | `diagnostic_started` | `diagnostic_unavailable` | required |
| `SubmitDiagnosticResponse` | `POST /api/v1/diagnostics/{run_id}/responses` | run ouvert, item courant | `diagnostic_response_recorded` | `response_conflict` | required |
| `CompleteDiagnostic` | `POST /api/v1/diagnostics/{run_id}:complete` | règle d'arrêt atteinte | `diagnostic_completed`, `placement_decided` | `insufficient_coverage` | required |
| `StartFoundationRun` | `POST /api/v1/language-profiles/{profile_id}/foundation-runs` | statut `foundations` | `foundation_run_started` | `foundation_pack_missing` | required |
| `CompleteFoundationGate` | `POST /api/v1/foundation-runs/{run_id}:complete` | contrôles et délai présents | `foundation_gate_completed` | `gate_not_ready` | required |
| `PauseLanguageProfile` | `POST /api/v1/language-profiles/{profile_id}:pause` | `active` | `language_profile_paused` | - | required |
| `ArchiveLanguageProfile` | `POST /api/v1/language-profiles/{profile_id}:archive` | pas de suppression en cours | `language_profile_archived` | - | required |
| `RestoreLanguageProfile` | `POST /api/v1/language-profiles/{profile_id}:restore` | archived, pack encore compatible | `language_profile_restored` | `pack_incompatible` | required |
| `DeleteLanguageProfile` | `DELETE /api/v1/language-profiles/{profile_id}` | propriétaire, réauth récente | `language_profile_deletion_requested` | `active_export_or_job` | required |

## 5. Lexique, listes, mémoire et échange

| Commande | Route | Permission/précondition | Événement principal | Erreurs spécifiques | idem |
|---|---|---|---|---|---|
| `RecordLexicalEncounter` | `POST /api/v1/language-profiles/{profile_id}/encounters` | propriétaire/source autorisée | `lexical_encounter_recorded` | `source_revision_missing` | required |
| `ResolveMention` | `POST /api/v1/lexical-mentions/{mention_id}:resolve` | propriétaire, candidat valide | `mention_resolved` | `sense_ambiguous` | required |
| `AddPrivateLexicalUnit` | `POST /api/v1/language-profiles/{profile_id}/private-lexicon` | propriétaire | `private_lexical_unit_added` | `duplicate_candidate` | required |
| `AssertLexicalRelation` | `POST /api/v1/lexical-senses/{sense_id}/personal-relations` | propriétaire | `lexical_relation_asserted` | `relation_invalid` | required |
| `RetractLexicalRelation` | `POST /api/v1/personal-lexical-relations/{relation_id}:retract` | propriétaire, relation active | `lexical_relation_retracted` | - | required |
| `MergeLexicalUnits` | `POST /api/v1/language-profiles/{profile_id}/private-lexicon:merge` | propriétaire, unités privées compatibles | `lexical_units_merged` | `merge_ambiguous` | required |
| `SplitLexicalSense` | `POST /api/v1/lexical-senses/{sense_id}:split-private` | propriétaire, sens privé | `lexical_sense_split` | `canonical_sense_immutable` | required |
| `DeletePrivateContext` | `DELETE /api/v1/lexical-encounters/{encounter_id}/private-context` | propriétaire, réauth récente | `private_context_deleted` | - | required |
| `CaptureLexicalGap` | `POST /api/v1/attempts/{attempt_id}/lexical-gaps` | propriétaire, tentative ouverte/corrigée | `lexical_gap_captured` | `support_language_not_allowed` | required |
| `DeclareLexicalFamiliarity` | `PUT /api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/declaration` | propriétaire | `lexical_familiarity_declared` | - | required |
| `SetLexicalLearningPreference` | `PUT /api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/preference` | propriétaire | `lexical_learning_preference_set` | - | required |
| `UpsertLexicalAnnotation` | `PUT /api/v1/language-profiles/{profile_id}/lexical-senses/{sense_id}/annotation` | propriétaire, version si existante | `lexical_annotation_upserted` | - | required |
| `DeleteLexicalAnnotation` | `DELETE /api/v1/lexical-annotations/{annotation_id}` | propriétaire, version | `lexical_annotation_deleted` | - | required |
| `CreateVocabularyList` | `POST /api/v1/language-profiles/{profile_id}/vocabulary-lists` | propriétaire | `vocabulary_list_created` | - | required |
| `ReviseVocabularyList` | `PATCH /api/v1/vocabulary-lists/{list_id}` | propriétaire, version | `vocabulary_list_revised` | `snapshot_immutable` | supported |
| `ChangeListMembers` | `POST /api/v1/vocabulary-lists/{list_id}/members:batch` | propriétaire, version | `vocabulary_list_revised` | `member_conflict` | required |
| `FreezeVocabularyList` | `POST /api/v1/vocabulary-lists/{list_id}:snapshot` | propriétaire | `vocabulary_list_snapshot_created` | - | required |
| `CloneVocabularyList` | `POST /api/v1/vocabulary-lists/{list_id}:clone` | liste visible, propriétaire destination | `vocabulary_list_cloned` | `list_not_shareable` | required |
| `MergeVocabularyLists` | `POST /api/v1/vocabulary-lists:merge` | propriétaire des listes, stratégie explicite | `vocabulary_lists_merged` | `list_merge_conflict` | required |
| `PublishVocabularyListSnapshot` | `POST /api/v1/vocabulary-lists/{list_id}/snapshots/{snapshot_id}:publish` | propriétaire/auteur, snapshot figé, droits/licence | `vocabulary_list_snapshot_published` | `license_missing`, `private_context_present` | required |
| `RetireSharedVocabularyList` | `POST /api/v1/shared-vocabulary-lists/{publication_id}:retire` | propriétaire éditorial/reviewer | `shared_vocabulary_list_retired` | `publication_not_active` | required |
| `CreateMemoryPrompt` | `POST /api/v1/language-profiles/{profile_id}/memory-prompts` | cible/protocole compatibles | `memory_prompt_created` | `prompt_conflict` | required |
| `SubmitMemoryReview` | `POST /api/v1/memory-prompts/{prompt_id}/reviews` | prompt actif, note autorisée | `memory_review_recorded` | `rating_not_allowed` | required |
| `SuspendMemoryPrompt` | `POST /api/v1/memory-prompts/{prompt_id}:suspend` | propriétaire, actif | `memory_prompt_suspended` | - | required |
| `ResumeMemoryPrompt` | `POST /api/v1/memory-prompts/{prompt_id}:resume` | propriétaire, suspendu | `memory_prompt_resumed` | - | required |
| `ResetMemoryPrompt` | `POST /api/v1/memory-prompts/{prompt_id}:reset` | propriétaire, raison | `memory_schedule_reset` | - | required |
| `MergeMemoryPrompts` | `POST /api/v1/memory-prompts:merge` | prompts compatibles ou arbitrage | `memory_prompts_merged` | `incompatible_protocols` | required |
| `ArchiveMemoryPrompt` | `POST /api/v1/memory-prompts/{prompt_id}:archive` | propriétaire, non terminal | `memory_prompt_archived` | - | required |
| `RestoreMemoryPrompt` | `POST /api/v1/memory-prompts/{prompt_id}:restore` | propriétaire, archivé | `memory_prompt_restored` | `target_revision_unavailable` | required |
| `DeleteMemoryPrompt` | `DELETE /api/v1/memory-prompts/{prompt_id}` | propriétaire, réauth récente | `memory_prompt_deleted` | - | required |
| `CreateImport` | `POST /api/v1/language-profiles/{profile_id}/imports` | upload vérifié | `import_created` | `unsupported_import_format` | required |
| `ResolveImportConflict` | `POST /api/v1/imports/{import_id}/conflicts/{conflict_id}:resolve` | propriétaire/reviewer, action autorisée | `import_conflict_resolved` | `conflict_action_invalid`, `preview_stale` | required |
| `CommitImport` | `POST /api/v1/imports/{import_id}:commit` | preview courant, stratégie choisie | `import_committed` | `preview_stale`, `unresolved_conflict` | required |
| `RevertImport` | `POST /api/v1/imports/{import_id}:revert` | inverse encore applicable | `import_reverted` | `resource_reused` | required |
| `RequestExport` | `POST /api/v1/language-profiles/{profile_id}/exports` | propriétaire, réauth récente | `export_requested` | - | required |

## 6. Contenu, curriculum et génération

| Commande | Route | Permission/précondition | Événement principal | Erreurs spécifiques | idem |
|---|---|---|---|---|---|
| `CreateContentDraft` | `POST /api/v1/authoring/drafts` | `author`, portée pack | `content_draft_created` | - | required |
| `ReviseContentDraft` | `PATCH /api/v1/authoring/drafts/{draft_id}` | auteur assigné, version | `content_draft_revised` | - | supported |
| `ValidateContentRevision` | `POST /api/v1/authoring/drafts/{draft_id}:validate` | draft | `content_validated` ou `content_validation_failed` | `validator_unavailable` | required |
| `ApproveContentRevision` | `POST /api/v1/authoring/drafts/{draft_id}:approve` | reviewer distinct, validated | `content_approved` ou `content_rejected` | `self_approval_forbidden` | required |
| `PublishContentRevision` | `POST /api/v1/authoring/drafts/{draft_id}:publish` | approved, réauth récente | `content_published` | `reference_not_publishable` | required |
| `RetireContentRevision` | `POST /api/v1/content/{content_id}/revisions/{revision_id}:retire` | reviewer/admin | `content_retired` | `historical_rights_conflict` | required |
| `CreateLearningModule` | `POST /api/v1/authoring/modules` | author, pack | `learning_module_created` | - | required |
| `PublishLearningModule` | `POST /api/v1/authoring/modules/{module_id}:publish` | manifeste approuvé | `learning_module_published` | `module_validation_failed` | required |
| `EnrollInModule` | `POST /api/v1/language-profiles/{profile_id}/module-enrollments` | prérequis ou dispense | `module_enrollment_created` | `prerequisite_missing` | required |
| `PauseModuleEnrollment` | `POST /api/v1/module-enrollments/{id}:pause` | actif | `module_enrollment_paused` | - | required |
| `CompleteModuleEnrollment` | `POST /api/v1/module-enrollments/{id}:complete` | critères de sortie satisfaits | `module_enrollment_completed` | `completion_criteria_missing` | required |
| `RequestGenerationJob` | `POST /api/v1/generation-jobs` | author/reviewer, outil autorisé | `generation_job_requested` | `budget_exceeded`, `provider_unavailable` | required |
| `CancelGenerationJob` | `POST /api/v1/generation-jobs/{job_id}:cancel` | créateur/opérateur, annulable | `generation_job_cancel_requested` | `job_not_cancellable` | required |
| `InvokeAuthoringTool` | `POST /api/v1/tools/{tool_name}:invoke` | author/reviewer/service, schéma et quota valides | `authoring_tool_invoked` | `tool_not_allowed`, `tool_schema_invalid` | required |

## 7. Planification, sprint et exercices

| Commande | Route | Permission/précondition | Événement principal | Erreurs spécifiques | idem |
|---|---|---|---|---|---|
| `ComposeDailySession` | `POST /api/v1/language-profiles/{profile_id}/daily-plans` | profil actif, budget valide | `session_plan_composed` | `no_valid_composition` | required |
| `ComposeFreePractice` | `POST /api/v1/language-profiles/{profile_id}/free-practice-plans` | cible/prérequis valides | `free_practice_plan_composed` | `prerequisite_missing` | required |
| `PrepareSessionPlan` | `POST /api/v1/session-plans/{plan_id}:prepare` | plan draft | `session_plan_ready` ou `session_plan_failed` | `content_unavailable` | required |
| `CancelSessionPlan` | `POST /api/v1/session-plans/{plan_id}:cancel` | draft/preparing/ready | `session_plan_cancelled` | `run_already_started` | required |
| `StartSprintRun` | `POST /api/v1/session-plans/{plan_id}/runs` | plan ready/non expiré | `sprint_run_started` | `active_run_exists` | required |
| `InterruptSprintRun` | `POST /api/v1/sprint-runs/{run_id}:interrupt` | in_progress, raison | `sprint_run_interrupted` | - | required |
| `ResumeSprintRun` | `POST /api/v1/sprint-runs/{run_id}:resume` | interrupted/non expiré | `sprint_run_resumed` | `run_expired` | required |
| `StopSprintRun` | `POST /api/v1/sprint-runs/{run_id}:stop` | in_progress/interrupted | `sprint_run_stopped` | - | required |
| `CompleteSprintRun` | `POST /api/v1/sprint-runs/{run_id}:complete` | noyau conforme | `sprint_run_completed` | `required_block_incomplete` | required |
| `OpenExerciseAttempt` | `POST /api/v1/exercise-instances/{instance_id}/attempts` | bloc in_progress, instance assignée | `exercise_attempt_opened` | `attempt_already_open` | required |
| `SaveAttemptDraft` | `PATCH /api/v1/attempts/{attempt_id}/draft` | attempt draft, version | `attempt_draft_saved` | `draft_stale` | supported |
| `UseExerciseHint` | `POST /api/v1/attempts/{attempt_id}/hints` | attempt draft, aide suivante | `exercise_hint_used` | `hint_not_available` | required |
| `SubmitExerciseAttempt` | `POST /api/v1/attempts/{attempt_id}:submit` | draft, réponse valide | `exercise_attempt_submitted` | `answer_shape_invalid` | required |
| `ContestCorrection` | `POST /api/v1/attempts/{attempt_id}/correction-case` | corrected, propriétaire | `correction_contested` | `case_already_open` | required |
| `ReviewCorrection` | `POST /api/v1/attempts/{attempt_id}:mark-correction-read` | corrected/not_evaluable, propriétaire | `correction_reviewed` | - | required |
| `ReviewCorrectionCase` | `POST /api/v1/correction-cases/{case_id}:resolve` | reviewer/humain autorisé | `correction_case_resolved` | `review_conflict` | required |
| `SkipExerciseBlock` | `POST /api/v1/sprint-runs/{run_id}/blocks/{block_id}:skip` | available/in_progress | `exercise_block_skipped` | `block_required` | required |
| `AbandonExerciseBlock` | `POST /api/v1/sprint-runs/{run_id}/blocks/{block_id}:abandon` | in_progress | `exercise_block_abandoned` | - | required |

## 8. Évaluations, médias et jobs

| Commande | Route | Permission/précondition | Événement principal | Erreurs spécifiques | idem |
|---|---|---|---|---|---|
| `PrepareAssessment` | `POST /api/v1/language-profiles/{profile_id}/assessments` | protocole disponible | `assessment_prepared` | `assessment_unavailable` | required |
| `StartAssessment` | `POST /api/v1/assessments/{run_id}:start` | prepared, matériel prêt | `assessment_started` | `media_not_ready` | required |
| `SaveAssessmentResponse` | `PATCH /api/v1/assessments/{run_id}/responses/{item_id}` | run ouvert, version | `assessment_response_saved` | `response_stale` | supported |
| `PauseAssessment` | `POST /api/v1/assessments/{run_id}:pause` | protocole autorise pause | `assessment_paused` | `pause_not_allowed` | required |
| `ResumeAssessment` | `POST /api/v1/assessments/{run_id}:resume` | paused, fenêtre valide | `assessment_resumed` | `assessment_expired` | required |
| `SubmitAssessment` | `POST /api/v1/assessments/{run_id}:submit` | in_progress/paused | `assessment_submitted` | - | required |
| `ReviewAssessmentResult` | `POST /api/v1/assessments/{run_id}:resolve-review` | reviewer qualifié, grille courante | `assessment_review_resolved` | `review_conflict`, `rubric_stale` | required |
| `ReserveMediaUpload` | `POST /api/v1/media/uploads` | propriétaire/auteur, quota | `media_upload_reserved` | `media_quota_exceeded` | required |
| `CompleteMediaUpload` | `POST /api/v1/media/uploads/{upload_id}:complete` | objet présent/empreinte | `media_uploaded` | `media_integrity_failed` | required |
| `DeleteMedia` | `DELETE /api/v1/media/{media_id}` | propriétaire ou droits éditoriaux | `media_deletion_requested` | `media_still_required` | required |
| `CancelJob` | `POST /api/v1/jobs/{job_id}:cancel` | propriétaire/opérateur | `job_cancel_requested` | `job_not_cancellable` | required |

## 9. Lectures canoniques

`GET` : `/session`, `/language-profiles`, `/language-profiles/{id}`,
`/diagnostics/{id}`, `/foundation-runs/{id}`, `/catalogue/targets`,
`/language-packs`, `/lexicon/search`, `/lexical-senses/{id}`,
`/language-profiles/{id}/word-bank`, `/language-profiles/{id}/lexical-annotations`,
`/vocabulary-lists`, `/vocabulary-lists/{id}`, `/shared-vocabulary-lists`,
`/shared-vocabulary-lists/{id}`, `/memory-prompts/due`,
`/imports/{id}`, `/exports/{id}`, `/module-enrollments/{id}`,
`/session-plans/{id}`, `/sprint-runs/{id}`, `/exercise-instances/{id}`,
`/attempts/{id}`, `/correction-cases/{id}`,
`/language-profiles/{id}/progress`,
`/language-profiles/{id}/recommendations`,
`/assessments/{id}`, `/authoring/drafts`, `/authoring/drafts/{draft_id}`,
`/authoring/catalogue`,
`/authoring/modules`, `/authoring/content/{id}/history`,
`/authoring/previews/{id}`, `/validation-reports/{id}`,
`/jobs/{id}`, `/jobs/{id}/events`, `/media/{id}` et
`/media/tts/capabilities`.

Toutes les collections sont paginées par curseur. Chaque lecture personnelle
exige la portée du profil. Les vues d'explication retournent IDs de faits,
versions de politique et raisons autorisées, jamais le contexte privé d'un autre
utilisateur.

## 10. Commandes internes sans route publique

Elles utilisent la même enveloppe, les mêmes règles d'idempotence et les mêmes
événements que les commandes HTTP, mais sont émises par un handler autorisé ou
un worker. Elles ne sont jamais invocables directement par le navigateur.

| Commande interne | Émetteur | Effet/événement | Précondition principale |
|---|---|---|---|
| `AnalyzeSource` | worker lexique | `source_analysis_completed` | source vérifiée et schéma supporté |
| `CorrectExerciseAttempt` | handler/worker correction | `exercise_attempt_corrected` ou `attempt_not_evaluable` | tentative submitted/correcting |
| `OpenLearningNeed` | projecteur progression | `learning_need_opened` ou `learning_need_cause_added` | cause qualifiée et dédupliquée |
| `ResolveLearningNeed` | projecteur progression | `learning_need_resolved` | preuve conforme à la politique |
| `StartGenerationAttempt` | worker génération | `generation_attempt_started` | lease actif, budget réservé |
| `SubmitGeneratedDraft` | worker génération | `generated_draft_submitted` | sortie bornée et provenance complète |
| `FailGenerationAttempt` | worker génération | `generation_attempt_failed` | erreur classée, retry explicitement décidé |
| `ScoreAssessment` | worker évaluation | `assessment_scored` ou `assessment_review_required` | run submitted/expired |
| `ImportLexicalSource` | handler d'import | `lexical_source_imported` | import committed et artefact vérifié |
| `VerifyMediaUpload` | worker média | `media_upload_verified` ou `media_rejected` | objet présent, taille et empreinte attendues |
| `QuarantineMedia` | worker média/sécurité | `media_quarantined` | scan requis ou signal de risque |
| `ProcessMedia` | worker média | `media_processing_started` | upload vérifié, format autorisé |
| `MarkMediaReady` | worker média | `media_ready` | variantes et checksums complets |
| `MarkMediaFailed` | worker média | `media_failed` | erreur classée, aucun retry implicite |
| `PurgeMedia` | worker suppression | `media_deleted` | demande autorisée et références libérées |

## 11. Compatibilité et preuve

L'implémentation produit `contracts/openapi/v1.json`, un client TypeScript et
des JSON Schema d'événements/outils. Avant cela, ce document vaut spécification,
pas preuve `GATE-G1`. La gate exige pour chaque ligne : exemple positif, erreurs,
test d'autorisation, test d'idempotence/précondition et événement validé.
