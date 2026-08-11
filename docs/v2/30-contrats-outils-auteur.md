# Polyglot V2 - Contrats de la façade d'outils auteur

## 1. Portée et autorité

Ce document est propriétaire des entrées, sorties, effets, limites et erreurs de
la façade décrite au document 15. Les noms de commandes et erreurs communes
restent ceux du document 25 ; les entités restent celles du document 26. Ces
outils sont utilisables par le runner déterministe, un humain outillé ou, plus
tard, un LLM. Aucun outil n'accède directement à la base ni ne publie un contenu.

## 2. Enveloppe commune

Toute invocation contient :

| Champ | Type | Règle |
|---|---|---|
| `tool_name` | code fermé | un des onze outils de la section 4 |
| `tool_version` | semver | version publiée et compatible |
| `invocation_id` | UUIDv7 | identité de l'appel |
| `actor_id` | UUIDv7 | humain, runner ou service authentifié |
| `actor_role` | `account_role` | doit être autorisé par le contrat |
| `scope` | objet typé | pack, profil, job et mandat explicites |
| `idempotency_key` | texte | obligatoire pour tout outil à effet |
| `expected_version` | entier nullable | obligatoire si une ressource mutable est visée |
| `input` | objet JSON | validé avant le handler |
| `trace` | objet | `correlation_id`, `causation_id`, révisions de politiques |

Toute sortie contient `invocation_id`, `tool_version`, `status`, `output` ou
`error`, `output_schema_version`, `provenance_id`, `started_at`, `finished_at` et
`output_fingerprint`. Un succès ne renvoie que les champs autorisés au rôle. Une
erreur utilise `{code, field_path?, retryable, details_codes[]}` sans trace,
secret, prompt privé complet ni donnée d'un autre profil.

## 3. Règles transversales

- Taille d'entrée par défaut : 256 KiB ; sortie : 1 MiB ; texte libre unitaire :
  20 000 caractères. Un contrat plus strict prévaut.
- Timeout handler : 10 s en lecture, 30 s en validation, 60 s pour soumettre un
  brouillon complexe. Le runner utilise les mêmes limites logiques.
- Une même clé et le même fingerprint retournent la même sortie ; une même clé
  avec un autre corps retourne `idempotency_conflict`.
- Les outils de lecture sont `side_effect=none`. Les outils de soumission créent
  uniquement un brouillon, rapport, signalement ou correction révisable.
- Aucun outil ne peut approuver, publier, retirer, attribuer une maîtrise ou
  modifier un calendrier FSRS.
- Les IDs proposés par l'appelant ne sont acceptés que dans les namespaces de
  brouillon réservés ; les IDs canoniques sont attribués par le backend.
- Toutes les références sont vérifiées dans la révision épinglée. Une référence
  absente donne `reference_not_found`, une révision périmée `version_conflict`.
- Les champs inconnus sont rejetés. Les listes ont un ordre déterministe et une
  pagination par curseur si elles dépassent la limite.
- Les onze schémas ont une fixture positive et au moins une fixture négative ;
  le runner compare sortie, événement, absence d'effet interdit et empreinte.

Erreurs fermées communes : `tool_schema_invalid`, `tool_not_allowed`,
`scope_forbidden`, `reference_not_found`, `version_conflict`,
`idempotency_conflict`, `size_limit_exceeded`, `timeout`, `dependency_unavailable`
et `internal_error`. `retryable=false` par défaut ; aucun retry n'est automatique.

## 4. Registre des outils

### 4.1 `profile.read_authorized`

- **Rôle** : `learner` propriétaire, ou `author` avec mandat actif.
- **Entrée** : `profile_id`, `purpose` parmi `session_authoring`,
  `correction_review`, `recommendation_explanation`, et `field_groups[]` parmi
  `goals`, `constraints`, `mastery_summary`, `due_summary`, `module_position`.
- **Sortie MVP** : `profile_id`, groupes autorisés, indicateur de
  pseudonymisation et date de coupure. Jamais réponse brute, contexte lexical
  privé, email, identité ou audio.
- **Effet/idempotence/limite** : aucun ; cache privé 60 s ; 100 facettes agrégées.
- **Erreurs** : `mandate_missing`, `field_group_forbidden`, `profile_deleted`.
- **Positif** : `{"profile_id":"P1","purpose":"session_authoring","field_groups":["goals","mastery_summary"]}`.
- **Rejet** : demander `raw_attempts` retourne `tool_schema_invalid`.

### 4.2 `catalogue.list_targets`

- **Rôle** : toute lecture catalogue authentifiée.
- **Entrée** : `pack_revision_id`, filtres optionnels `target_types[]`,
  `modality`, `operation`, `prerequisite_of`, `status=published`, `cursor`,
  `limit<=200`.
- **Sortie MVP** : références de cibles, curseur nullable et indicateur de
  stabilité pour la révision demandée.
- **Effet/idempotence** : aucun ; résultat stable pour révision et curseur.
- **Erreurs** : `pack_not_published`, `cursor_invalid`, `filter_invalid`.
- **Positif** : liste les structures italiennes publiées de production écrite.
- **Rejet** : `limit=1000` retourne `size_limit_exceeded`.

### 4.3 `lexicon.read_session_scope`

- **Rôle** : propriétaire ou auteur mandaté pour le plan.
- **Entrée** : `profile_id`, `planning_snapshot_id`, `roles[]`,
  `target_refs[]`, `list_snapshot_ids[]`, `max_senses<=200`.
- **Sortie MVP** : références de sens autorisées et identifiant du snapshot
  retenu. Les notes privées ne sont jamais retournées à un auteur.
- **Effet/idempotence** : aucun ; snapshot obligatoire et immuable.
- **Erreurs** : `snapshot_stale`, `sense_out_of_scope`, `private_context_forbidden`.
- **Positif** : renvoie 8 sens `new` et 12 sens `support` du snapshot.
- **Rejet** : un sens hors snapshot retourne `sense_out_of_scope`.

### 4.4 `exercise.get_blueprint`

- **Rôle** : `author`, `reviewer` ou runner de certification.
- **Entrée** : `primitive_id`, `primitive_contract_version`,
  `language_pack_revision_id`, `mode`, capacités d'accessibilité demandées.
- **Sortie MVP** : primitive, version du contrat, stratégies de correction et
  preuve explicite que le blueprint ne peut pas publier.
- **Effet/idempotence** : aucun ; 1 blueprint par appel.
- **Erreurs** : `primitive_unknown`, `language_not_certified`, `mode_unsupported`.
- **Positif** : récupère le blueprint `controlled_transformation` italien.
- **Rejet** : une stratégie libre hors registre retourne `mode_unsupported`.

### 4.5 `exercise.submit_draft`

- **Rôle** : `author` sur le pack ; `side_effect=create_draft`.
- **Entrée** : `reserved_draft_id?`, `pack_revision_id`, `primitive_id`,
  `blueprint_version`, `stimulus`, `response_contract`, `target_bindings`,
  `accepted_answers_or_rubric`, `hints`, `difficulty_profile`, `provenance_inputs`.
- **Sortie** : `draft_id`, type, révision 1, findings de schéma immédiats et
  checksum. Statut toujours `draft`, avec capacités de publication et de
  maîtrise explicitement à `false`.
- **Idempotence/limites** : clé obligatoire ; 100 cibles, 100 réponses acceptées,
  20 aides maximum ; timeout 60 s.
- **Erreurs** : `blueprint_mismatch`, `target_not_published`,
  `correction_path_missing`, `answer_leak_detected`.
- **Positif** : crée un cloze déterministe avec réponses accentuées publiées.
- **Rejet** : un bloc obligatoire sans correcteur local donne
  `correction_path_missing`.

### 4.6 `content.validate_draft`

- **Rôle** : `author` ou `reviewer` ; `side_effect=create_validation_report`.
- **Entrée** : `draft_revision_id`, `validator_profile_id`,
  `validator_revision_ids[]`, `requested_checks[]`, `seed`.
- **Sortie MVP** : identifiant de rapport immuable, findings, décision
  `passed|failed|human_required` et indicateur de troncature.
- **Idempotence/limites** : une clé par tuple de révisions ; 10 000 findings
  maximum puis `report_truncated=true` ; timeout 30 s logique.
- **Erreurs** : `validator_unavailable`, `draft_not_found`,
  `validator_pack_incompatible`.
- **Positif** : le runner retrouve exactement les findings d'une fixture V1.
- **Rejet** : une révision de validateur incompatible donne
  `validator_pack_incompatible` sans rapport partiel déclaré réussi.

### 4.7 `curriculum.submit_module_draft`

- **Rôle** : `author` ; `side_effect=create_module_draft`.
- **Entrée** : pack, identité du module, public, objectifs, prérequis, politique
  de sortie, `day_draft_refs[]`, longueur min/max, contexte et provenance.
- **Sortie MVP** : identifiant de brouillon module, révision, findings et
  checksum, sans capacité de publication ni d'attribution de maîtrise.
- **Idempotence/limites** : 31 jours et 500 cibles maximum ; clé obligatoire.
- **Erreurs** : `prerequisite_cycle`, `day_revision_invalid`,
  `module_exit_unmeasurable`, `load_budget_exceeded`.
- **Positif** : soumet le module pilote italien de trois jours.
- **Rejet** : une sortie sans protocole de preuve donne
  `module_exit_unmeasurable`.

### 4.8 `curriculum.submit_day_draft`

- **Rôle** : `author` ; `side_effect=create_day_draft`.
- **Entrée** : `module_draft_id`, ordinal, arc, contexte, objectifs, nouveautés,
  rappels, besoins J+1, listes, compositions 10..60 minutes et provenance.
- **Sortie MVP** : identifiant de brouillon journée, révision, findings et
  checksum, sans capacité de publication ni d'attribution de maîtrise.
- **Idempotence/limites** : 60 blocs candidats, 200 sens, 20 cibles nouvelles ;
  clé et version du module obligatoires.
- **Erreurs** : `budget_infeasible`, `novelty_limit_exceeded`,
  `delayed_source_invalid`, `required_block_not_correctable`.
- **Positif** : J2 contient rappel J1, boîte grammaticale, Gym et production.
- **Rejet** : un J+1 issu d'une correction ambiguë donne
  `delayed_source_invalid`.

### 4.9 `correction.submit_structured_draft`

- **Rôle** : `reviewer` ou service correcteur mandaté ;
  `side_effect=create_correction_revision_draft`.
- **Entrée** : `attempt_id`, `attempt_version`, `strategy`, `verdict`,
  `criterion_scores`, `error_codes`, `proposed_answer`, `alternatives`,
  `explanation_codes`, `confidence`, `target_observations[]`, provenance.
- **Sortie MVP** : identifiant de correction brouillon, révision, findings et
  checksum. Elle ne devient jamais courante avant la commande métier de revue
  et ne peut ni publier ni attribuer de maîtrise.
- **Idempotence/limites** : 50 erreurs, 20 alternatives, 100 observations ;
  réponse brute accessible uniquement dans la portée de la tentative.
- **Erreurs** : `attempt_not_submitted`, `rubric_mismatch`,
  `observation_target_not_discriminant`, `confidence_inconsistent`.
- **Positif** : propose une traduction bornée partiellement correcte à 0.92.
- **Rejet** : créditer un mot fourni comme aide donne
  `observation_target_not_discriminant`.

### 4.10 `quality.report_ambiguity`

- **Rôle** : propriétaire, `author` ou `reviewer` ;
  `side_effect=create_quality_report`.
- **Entrée** : `resource_ref`, `resource_revision_id`, `ambiguity_type`,
  `location`, `description`, `candidate_interpretations[]`, contexte privé
  facultatif explicitement consenti.
- **Sortie MVP** : identifiant de signalement, fingerprint de déduplication,
  visibilité et statut `open`.
- **Idempotence/limites** : 10 interprétations, description 4 000 caractères ;
  les doublons relient le reporter sans dupliquer le dossier.
- **Erreurs** : `resource_revision_missing`, `private_context_not_consented`,
  `report_scope_forbidden`.
- **Positif** : signale deux réponses italiennes naturelles acceptables.
- **Rejet** : joindre une production privée sans consentement donne
  `private_context_not_consented`.

### 4.11 `progress.explain_recommendation`

- **Rôle** : propriétaire ou support mandaté en lecture ; aucun effet.
- **Entrée** : `profile_id`, `recommendation_id`, `as_of_projection_version`,
  `detail_level` parmi `summary`, `evidence`, `policy`.
- **Sortie MVP** : identifiant de recommandation, codes de raison, faits
  autorisés et alternatives. Aucun raisonnement privé de modèle n'est exposé.
- **Idempotence/limites** : 100 références de preuve, contextes privés masqués.
- **Erreurs** : `projection_version_unavailable`, `recommendation_expired`,
  `evidence_scope_forbidden`.
- **Positif** : explique qu'une structure est à revoir après perte de fraîcheur.
- **Rejet** : demander la preuve d'un autre profil donne `scope_forbidden`.

## 5. Runner et critères d'acceptation

Le runner exécute au minimum : un succès et chaque erreur spécifique, répétition
idempotente, conflit de fingerprint, rôle interdit, référence périmée, taille
maximale, timeout simulé et vérification d'absence d'effet interdit pour chaque
outil. Il fige horloge, UUID, graine, catalogue et ordre des résultats.

Une sortie conforme au schéma mais pédagogiquement invalide doit être rejetée
par le validateur de domaine, pas acceptée parce que le JSON est valide. La gate
`G6` exige les onze outils, leurs schémas générés, les fixtures, un transcript
JSONL reproductible et la preuve qu'aucun outil ne peut publier ou attribuer une
maîtrise.
