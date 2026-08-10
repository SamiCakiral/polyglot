# Polyglot V2 - Dictionnaire de données normatif

## 1. Autorité et portée

Ce document fixe le vocabulaire de données persistant de Polyglot V2. Il
consolide les agrégats, entités, faits, projections et contrats définis dans les
documents 06 à 25. Il est normatif pour :

- les noms des entités et champs structurants ;
- les identifiants, versions, dates et durées ;
- la propriété, la nullabilité, les cardinalités et contraintes d'unicité ;
- la distinction entre faits, révisions immuables, état d'agrégat et
  projections ;
- les politiques de suppression, anonymisation, archivage et rétention ;
- l'utilisation des enums canoniques du document 25.

Il ne constitue ni un schéma SQL, ni une migration, ni un contrat OpenAPI. Les
types physiques, index couvrants et noms de tables pourront être spécialisés
sans modifier les invariants ci-dessous. Toute divergence de sens exige une
décision documentaire préalable.

Ordre d'autorité appliqué : décisions du document 06, registre des enums et
commandes du document 25, contrats de domaine des documents 07 à 24, puis le
présent dictionnaire pour les détails de persistance restés implicites.

## 2. Notation et conventions transversales

### 2.1 Lecture des tableaux

| Colonne | Signification |
|---|---|
| `Requis` = `oui` | Valeur présente à la création ou avant la première transition qui l'exige. |
| `Requis` = `conditionnel` | Valeur obligatoire lorsque la condition indiquée est vraie. |
| `Requis` = `non` | Information facultative qui ne porte aucun invariant central. |
| `Nullable` = `non` | La colonne persistée ne contient jamais `NULL`. |
| `Nullable` = `oui` | `NULL` signifie exclusivement « pas encore produit », « inconnu » ou « sans objet » selon la règle. |

Une collection connue mais vide est `[]`, jamais `NULL`. Un booléen est
toujours binaire ; un état inconnu utilise un enum ou une absence explicitement
autorisée, jamais un troisième booléen implicite.

### 2.2 Types logiques

| Type logique | Règle normative |
|---|---|
| `uuid7` | UUIDv7 généré par l'application, opaque dans les API. |
| `stable_code` | Code humain stable ASCII `lower_snake_case` ou code éditorial documenté ; jamais clé primaire. |
| `text` | Unicode conservé sans perte ; normalisation dérivée séparée de la valeur brute. |
| `locale_tag` | Tag BCP 47 canonique, par exemple `fr-FR` ou `it-IT`. |
| `iana_timezone` | Identifiant IANA, jamais un simple offset. |
| `instant` | Instant UTC, stocké avec fuseau et rendu RFC 3339 UTC. |
| `local_date` | Date issue d'un fuseau et d'une règle de bascule explicitement épinglés. |
| `duration_ms` | Entier positif ou nul ; temps actif et temps mural restent séparés. |
| `decimal_score` | Décimal borné, jamais flottant binaire lorsqu'une égalité métier est attendue. |
| `money_minor` | Entier en unité monétaire mineure avec `currency_code`. |
| `json_versioned` | Payload validé par schéma, avec `schema_version`; interdit pour propriétaire, état, relation ou invariant central. |
| `sha256` | Empreinte hexadécimale SHA-256 d'octets ou d'un payload canonique. |

Les scores et confiances utilisent par défaut `[0,1]`. Les valeurs
d'observation utilisent `[-1,1]`. Les poids sont non négatifs. Les durées,
compteurs et ordinaux sont des entiers non négatifs, sauf mention contraire.

### 2.3 Identités et références

1. Toute identité d'agrégat ou d'entité persistante est un `uuid7` suffixé
   `_id`.
2. Un lemme, une adresse, un nom, une forme normalisée ou un code de pack n'est
   jamais un identifiant technique.
3. Une référence historique pointe vers une révision précise par
   `*_revision_id`, pas seulement vers l'identité stable.
4. Une référence courante éditoriale peut pointer vers `*_id`, mais toute
   exécution la résout et l'épingle avant démarrage.
5. Une référence polymorphe utilise un couple fermé `target_type` +
   `target_id`. Elle n'est autorisée que pour les cibles explicitement listées
   dans ce document.
6. Les IDs externes restent dans `external_ref` avec fournisseur, namespace et
   provenance ; ils ne remplacent jamais l'ID Polyglot.
7. Le mot « référence » n'implique pas une clé étrangère SQL. Une référence vers
   un agrégat d'un autre module est validée par son port owner et stockée comme
   UUID opaque. Une FK n'est créée que si la table cible existe déjà et si le
   module propriétaire de la relation la déclare dans sa migration ; les liens
   causaux polymorphes ne deviennent jamais des FK.

### 2.4 Versions

| Champ | Usage |
|---|---|
| `version` | Entier de concurrence optimiste d'un agrégat mutable, initialisé à `1` et incrémenté à chaque mutation confirmée. |
| `revision_id` | Identité UUIDv7 d'une révision immuable. |
| `revision_no` | Ordinal strictement croissant au sein d'une identité stable. |
| `schema_version` | Version entière du contrat de payload ou d'événement. |
| `policy_revision_id` | Révision immuable de la politique ayant produit une décision ou projection. |
| `engine_version` | Version exacte d'un moteur externe ou interne reproductible. |

Une révision publiée n'est jamais modifiée. Une correction, une
désambiguïsation ou une politique plus récente crée une nouvelle révision ou un
fait de remplacement. Les projections portent leur propre `projection_version`
et les versions des politiques appliquées.

### 2.5 Temps et journée pédagogique

- Tous les `*_at` sont des `instant` UTC.
- `created_at` et `updated_at` décrivent la persistance ; `occurred_at` décrit le
  fait métier ; `recorded_at` décrit son entrée dans Polyglot.
- Le temps actif est persisté en `duration_ms`; une pause ne l'augmente pas.
- `pedagogical_day` est une `local_date` calculée depuis `timezone_snapshot` et
  `day_cutover_local_time`. Ces deux valeurs sont figées sur le plan ou le run.
- Un changement ultérieur de fuseau ne modifie aucun fait historique.
- Une échéance `after_24h` conserve un `not_before_at` et ne peut être avancée.
- Les expirations sont serveur : `expires_at = NULL` signifie « sans expiration
  définie », pas « expiration inconnue ».

### 2.6 Propriété, portée et confidentialité

| Type de donnée | Champ propriétaire | Politique |
|---|---|---|
| Compte | `account_id` | Accès par session et rôle. |
| Donnée d'apprentissage | `profile_id` | Isolation stricte et RLS par profil. |
| Donnée éditoriale | `editorial_owner_id` et portée de pack | Auteur/reviewer assigné ; publication séparée. |
| Donnée système | aucun propriétaire utilisateur | Accès par rôle de service borné et audit. |
| Donnée partagée publiée | révision et licence | Lecture selon canal ; aucune donnée personnelle incorporée. |

Chaque enregistrement porte une `privacy_class` parmi `public`, `internal`,
`personal`, `sensitive` ou `secret` lorsque sa classe n'est pas imposée par son
type. `secret` n'est jamais stocké dans les tables métier.

## 3. Registre des agrégats et propriétaires

| Domaine owner | Racine d'agrégat | Entités possédées principales | Propriétaire métier |
|---|---|---|---|
| `identity` | `Account` | `LoginIdentity`, `AccountRole`, `AuthSession` | compte |
| `identity` | `UserPreferences` | `ConsentGrant` | compte |
| `language_profiles` | `LearnerLanguageProfile` | `SupportLanguageAuthorization`, `DeclaredLanguageExperience` | compte/profil |
| `language_profiles` | `DiagnosticRun` | `DiagnosticResponse` | profil |
| `language_profiles` | `FoundationRun` | `FoundationGateResult` | profil |
| `catalogue` | `LanguagePack` | `LanguagePackRevision`, certifications | owner éditorial |
| `catalogue` | `LexicalUnit` | révisions, sens, formes, cadres et attestations | catalogue ou profil privé |
| `catalogue` | `Skill` | `SkillRevision`, `SkillPrerequisiteEdge` | owner éditorial |
| `catalogue` | `GrammarStructure` | révisions et `GrammarPattern` | owner éditorial |
| `lexicon` | `LexicalEncounter` | mentions et résolutions | profil |
| `lexicon` | `ProductionArtifact` | références média et analyses | profil |
| `lexicon` | `VocabularyList` | révisions, membres, snapshots, associations | profil ou owner éditorial |
| `lexicon.memory` | `MemoryPrompt` | `MemoryReview`, `MemoryScheduleReset` | profil |
| `content` | `ContentItem` | `ContentRevision`, rapports de validation | owner éditorial |
| `curriculum` | `LearningModule` | révisions et `ModuleDay` | owner éditorial |
| `curriculum` | `ModuleEnrollment` | journées adaptatives et avancement | profil |
| `sprints` | `SessionPlan` | snapshot, blocs et sélections figées | profil |
| `sprints` | `SprintRun` | `ExerciseBlockRun` | profil |
| `exercises` | `ExerciseDefinition` | révisions, contrats et politiques référencées | owner éditorial |
| `exercises` | `ExerciseInstance` | bindings et stimuli épinglés | catalogue ou plan |
| `exercises` | `Attempt` | réponse, aides, événements média, corrections | profil |
| `exercises` | `CorrectionCase` | décisions de revue | profil/reviewer |
| `progress` | `LearningObservation` | liens de remplacement et `LearningEvidence` | profil |
| `progress` | `MasteryProjection` | `PersonalSenseFacet`, `LearningNeed`, causes et recommandations | profil |
| `assessments` | `AssessmentDefinition` | révisions, formes, sections et items | owner éditorial |
| `assessments` | `AssessmentRun` | réponses, minuteur, résultat et preuves | profil |
| `media` | `MediaAsset` | révisions, variantes, segments et upload | compte ou owner éditorial |
| `platform.jobs` | `Job` | `JobAttempt`, événements de progression | acteur demandeur |
| `generation` | `GenerationJob` | `GenerationAttempt` | auteur/reviewer |
| `lexicon.exchange` | `ImportRun` | aperçu, lignes, conflits et manifeste | profil/auteur |
| `lexicon.exchange` | `ExportRun` | manifeste et artefact chiffré | profil/compte |
| `platform` | `DeletionRequest` | étapes et `DeletionTombstone` | sujet supprimé |
| `platform` | `ProvenanceRecord` | sources, transformations et empreintes | système/owner éditorial |

Une transaction ne modifie qu'un agrégat propriétaire, plus ses événements et
son outbox. Une relation vers un autre domaine est validée par son interface et
persistée comme référence, jamais par mutation directe de l'agrégat distant.

### 3.1 Résolution des noms conceptuels des documents 06 à 25

| Nom rencontré | Représentation canonique V2 | Nature |
|---|---|---|
| `PresentedOccurrence` | `LexicalEncounter` avec `action=presented` ou `heard` et positions de source | fait append-only |
| `AttentionEvent` | `LexicalAttentionEvent` rattaché à une rencontre | fait append-only |
| `ReviewEvent` | `MemoryReview` | fait append-only |
| `ScheduleState` | `MemoryScheduleState` | projection |
| `LearnerFacet` | `PersonalSenseFacet` pour un sens, `MasteryProjection` pour une compétence | projection |
| `Observation` | `LearningObservation` | fait append-only |
| `Answer` | valeur union fermée possédée par `Attempt` ou `AssessmentResponse` | valeur immuable après soumission |
| `AnswerContract`, `SkillTargetSpec`, `DifficultyProfile` | valeurs structurées de `ExerciseDefinitionRevision` | révision immuable |
| `HintDefinition` | contenu typé épinglé par la politique d'aide | révision de contenu |
| `AcceptedAnswerSet`, `Rubric`, `Transcript` | `ContentRevision` avec un `content_type` fermé | révision de contenu |
| `ReviewEvent` FSRS importé | archive de provenance jusqu'à validation, puis `MemoryReview` si compatible | archive ou fait |
| `PresentedOccurrence` agrégée | une `LexicalEncounter` avec compteur uniquement pour occurrences incidentes autorisées | fait borné par politique |
| `OralAsset` | entité publiée liant média, transcript, segments et voix | révision éditoriale |
| `Provenance` | `ProvenanceRecord` référencé, jamais texte libre dupliqué | fait de lignée |

Les alias de cette table ne créent aucune seconde source de vérité. Le nom de la
colonne « représentation canonique » est celui utilisé par les schémas futurs.

## 4. Identity et préférences

### 4.1 `Account`, identité et session

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `Account` | `account_id` | `uuid7` | oui | non | Racine et propriétaire. |
| `Account` | `status` | `account_status` | oui | non | Enum du document 25. |
| `Account` | `security_version`, `session_version`, `version` | entier | oui | non | Incrémentés selon leur portée. |
| `Account` | `created_at`, `security_last_activity_at` | `instant` | oui | non | Activité de sécurité, pas activité pédagogique. |
| `Account` | `deleted_at` | `instant` | conditionnel | oui | Requis lorsque `status=deleted`. |
| `LoginIdentity` | `identity_id`, `account_id` | `uuid7` | oui | non | Appartient à un compte. |
| `LoginIdentity` | `provider_type` | `identity_provider_type` | oui | non | Enum canonique du document 25. |
| `LoginIdentity` | `normalized_identifier` | `text` | conditionnel | oui | Requis pour une identité locale. |
| `LoginIdentity` | `password_hash` | `text` sensible | conditionnel | oui | Argon2id local uniquement. |
| `LoginIdentity` | `issuer`, `subject` | `text` | conditionnel | oui | Requis ensemble pour OIDC. |
| `LoginIdentity` | `created_at`, `last_authenticated_at` | `instant` | oui/non | non/oui | Dernière authentification inconnue avant usage. |
| `AccountRole` | `account_id`, `role` | `uuid7`, `account_role` | oui | non | Attribution active versionnée et auditée. |
| `AccountRole` | `granted_at`, `granted_by_actor_id` | `instant`, `uuid7` | oui | non | Aucun rôle implicite hors création contrôlée. |
| `AuthSession` | `session_id`, `account_id` | `uuid7` | oui | non | Jeton opaque hors table métier ; empreinte seulement. |
| `AuthSession` | `session_fingerprint`, `csrf_secret_hash` | `sha256` | oui | non | Données sensibles non réversibles. |
| `AuthSession` | `created_at`, `last_seen_at`, `idle_expires_at`, `absolute_expires_at` | `instant` | oui | non | Expirations serveur. |
| `AuthSession` | `revoked_at`, `revoke_reason` | `instant`, `stable_code` | conditionnel | oui | Présents ensemble après révocation ; raisons dans un registre versionné. |

### 4.2 `UserPreferences` et consentements

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `UserPreferences` | `account_id` | `uuid7` | oui | non | Un-à-un avec `Account`. |
| `UserPreferences` | `interface_locale` | `locale_tag` | oui | non | Langue d'interface. |
| `UserPreferences` | `timezone` | `iana_timezone` | oui | non | Valeur courante, non rétroactive. |
| `UserPreferences` | `day_cutover_local_time` | heure locale | oui | non | Défaut `04:00`. |
| `UserPreferences` | `preferred_sprint_minutes` | entier | oui | non | `10..60`, pas de 5. |
| `UserPreferences` | `accessibility_preferences`, `media_preferences` | `json_versioned` | oui | non | Schémas fermés ; aucun invariant pédagogique. |
| `UserPreferences` | `preferred_voice_id`, `voice_catalog_revision_id` | `uuid7` | non | oui | Présents ensemble ; voix retirée conservée comme préférence. |
| `UserPreferences` | `version`, `created_at`, `updated_at` | entier/`instant` | oui | non | Concurrence optimiste. |
| `ConsentGrant` | `consent_id`, `account_id`, `purpose_code` | `uuid7`, `stable_code` | oui | non | Une finalité précise. |
| `ConsentGrant` | `status`, `policy_revision_id` | `consent_status`, `uuid7` | oui | non | Accord ou retrait versionné. |
| `ConsentGrant` | `decided_at`, `withdrawn_at` | `instant` | oui/conditionnel | non/oui | Retrait append-only ou nouvelle décision. |

## 5. Profil linguistique, diagnostic et fondations

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `LearnerLanguageProfile` | `profile_id`, `account_id`, `target_variety_id` | `uuid7` | oui | non | Un profil par variété cible non supprimée. |
| `LearnerLanguageProfile` | `native_variety_id` | `uuid7` | oui | non | Langue principale d'explication. |
| `LearnerLanguageProfile` | `status` | `language_profile_status` | oui | non | Enum du document 25. |
| `LearnerLanguageProfile` | `current_phase` | `learning_phase` | oui | non | Enum canonique du document 25. |
| `LearnerLanguageProfile` | `active_module_enrollment` | dérivé | non | n/a | Non persisté : W11 résout l'unique enrôlement actif par query. |
| `LearnerLanguageProfile` | `correction_preference`, `availability_pattern` | `json_versioned` | oui | non | Contexte, jamais preuve. |
| `LearnerLanguageProfile` | `goals`, `interests`, `excluded_themes` | liste de codes/références | oui | non | Listes vides autorisées. |
| `LearnerLanguageProfile` | `version`, `created_at`, `updated_at`, `archived_at`, `deleted_at` | entier/`instant` | oui/conditionnel | mixte | Dates terminales cohérentes avec le statut. |
| `SupportLanguageAuthorization` | `authorization_id`, `profile_id`, `variety_id` | `uuid7` | oui | non | Consentement explicite par langue d'appui. |
| `SupportLanguageAuthorization` | `authorized_at`, `revoked_at` | `instant` | oui/conditionnel | non/oui | Une autorisation révoquée n'est plus utilisable. |
| `DeclaredLanguageExperience` | `experience_id`, `profile_id`, `variety_id` | `uuid7` | oui | non | Déclaration sans poids de preuve. |
| `DeclaredLanguageExperience` | `declared_level`, `years_experience`, `notes` | texte/décimal | non | oui | Données de contexte. |
| `DeclaredLanguageExperience` | `declared_at`, `superseded_at` | `instant` | oui/conditionnel | non/oui | Historique conservé. |
| `DiagnosticRun` | `diagnostic_run_id`, `profile_id`, `policy_revision_id` | `uuid7` | oui | non | Snapshot de diagnostic. |
| `DiagnosticRun` | `status` | `guided_run_status` | oui | non | Enum du document 25. |
| `DiagnosticRun` | `started_at`, `expires_at`, `completed_at` | `instant` | conditionnel | oui | Fenêtre de reprise de 24 h par politique. |
| `DiagnosticRun` | `classification`, `confidence`, `stop_reason` | `diagnostic_classification`/score/code | conditionnel | oui | Requis à la complétion. |
| `DiagnosticResponse` | `response_id`, `diagnostic_run_id`, `item_revision_id` | `uuid7` | oui | non | Réponse figée et idempotente. |
| `DiagnosticResponse` | `answer`, `submitted_at`, `correction_id` | union/`instant`/`uuid7` | oui/oui/conditionnel | non/non/oui | Correction absente si non évaluable. |
| `FoundationRun` | `foundation_run_id`, `profile_id`, `pack_revision_id` | `uuid7` | oui | non | Exécute une gate publiée. |
| `FoundationRun` | `status`, `started_at`, `completed_at` | `guided_run_status`/`instant` | oui/oui/conditionnel | non/non/oui | Même sémantique de run guidé, sans CECR. |
| `FoundationGateResult` | `gate_result_id`, `foundation_run_id`, `gate_revision_id` | `uuid7` | oui | non | Résultat immuable. |
| `FoundationGateResult` | `passed`, `coverage`, `confidence`, `decided_at` | booléen/scores/`instant` | oui | non | `passed` exige toutes les conditions bloquantes. |
| `FoundationGateResult` | `waiver_reason`, `waiver_evidence_ids` | code/liste UUID | conditionnel | oui/non | Requis pour une dispense ; aucune maîtrise rétroactive. |
| `FoundationDefinitionRevision` | `foundation_revision_id`, `pack_revision_id`, `revision_no`, `status` | références/entier/`content_revision_status` | oui | non | Révision générique publiée par le pack. |
| `FoundationBlockRevision` | `block_revision_id`, `foundation_revision_id`, `ordinal`, `block_code`, `component_type` | références/entier/codes | oui | non | Script, perception, production, interaction ou réparation. |
| `FoundationBlockRevision` | `prerequisite_refs`, `exercise_definition_revision_ids`, `media_alternative_refs`, `waiver_policy_revision_id` | listes/références | oui | non | Toutes les dépendances sont publiées. |
| `FoundationGateRevision` | `gate_revision_id`, `foundation_revision_id`, `blocking_target_refs`, `coverage_threshold`, `confidence_threshold`, `delay_rules` | références/listes/décimaux/structure | oui | non | Décision de sortie versionnée et explicable. |

## 6. Catalogue de langue, compétences et politiques

### 6.1 Packs et variétés

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `LanguageVariety` | `variety_id`, `language_tag`, `region_code` | `uuid7`, `locale_tag`, code | oui/oui/non | non/non/oui | Région optionnelle. |
| `LanguageVariety` | `script_codes`, `text_direction`, `segmentation_policy_revision_id` | liste/enum/`uuid7` | oui | non | Capacités linguistiques versionnées. |
| `LanguageVariety` | `media_capabilities`, `normalization_policy_revision_id` | `json_versioned`, `uuid7` | oui | non | Déclarations du pack, pas du fournisseur. |
| `LanguagePack` | `pack_id`, `pack_code` | `uuid7`, `stable_code` | oui | non | Identité stable distincte de la paire affichée. |
| `LanguagePackRevision` | `pack_revision_id`, `pack_id`, `revision_no` | `uuid7`, entier | oui | non | Révision immuable. |
| `LanguagePackRevision` | `target_variety_id`, `support_variety_ids` | `uuid7`, liste UUID | oui | non | Au moins une langue d'appui certifiée. |
| `LanguagePackRevision` | `status` | `content_revision_status` | oui | non | Cycle éditorial du document 25. |
| `LanguagePackRevision` | `engine_compatibility`, `capability_manifest`, `checksum_manifest` | intervalles/`json_versioned`/`sha256` | oui | non | Manifeste atomique. |
| `LanguagePackRevision` | `license_refs`, `provenance_id`, `published_at` | références/`uuid7`/`instant` | oui/oui/conditionnel | non/non/oui | Date requise si publiée. |

### 6.2 Compétences, structures, moules et prérequis

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `Skill` | `skill_id`, `skill_code` | `uuid7`, `stable_code` | oui | non | Identité stable. |
| `SkillRevision` | `skill_revision_id`, `skill_id`, `revision_no` | `uuid7`, entier | oui | non | Révision immuable. |
| `SkillRevision` | `skill_type`, `modality`, `operation`, `target_ref` | enums/référence | oui | non | Facette mesurable. |
| `SkillRevision` | `scope`, `evidence_protocol_ids`, `load_profile` | typé/listes | oui | non | Protocoles autorisés et difficulté multidimensionnelle. |
| `SkillRevision` | `status`, `provenance_id` | `content_revision_status`, `uuid7` | oui | non | Publication contrôlée. |
| `GrammarStructure` | `structure_id`, `structure_code`, `function_skill_id` | `uuid7`, code, `uuid7` | oui | non | Fonction communicative reliée. |
| `GrammarStructureRevision` | `structure_revision_id`, `structure_id`, `revision_no` | `uuid7`, entier | oui | non | Contraintes, contrastes et erreurs versionnés. |
| `GrammarStructureRevision` | `constraints`, `contrasts`, `typical_errors`, `variants` | structures typées | oui | non | Listes vides autorisées uniquement après validation. |
| `GrammarPattern` | `pattern_id`, `structure_revision_id`, `pattern_code` | `uuid7`, code | oui | non | Moule productif. |
| `GrammarPattern` | `template`, `slots`, `instantiation_rules`, `examples`, `counterexamples` | structures typées | oui | non | Graphie cible Unicode conservée. |
| `SkillPrerequisiteEdge` | `edge_id`, `from_skill_revision_id`, `to_skill_revision_id` | `uuid7` | oui | non | Direction prérequis vers cible. |
| `SkillPrerequisiteEdge` | `edge_type`, `provenance_id` | `prerequisite_edge_type`, `uuid7` | oui | non | Enum canonique du document 25. |
| `PolicyRevision` | `policy_revision_id`, `policy_code`, `revision_no` | `uuid7`, code, entier | oui | non | Paramètres calculables versionnés. |
| `PolicyRevision` | `schema_version`, `payload`, `status`, `effective_from` | entier/`json_versioned`/enum/`instant` | oui | non | Une projection épingle cette révision. |
| `ProvenanceRecord` | `provenance_id`, `source_type`, `source_ref`, `created_by_actor_id` | références/enums | oui/oui/non | non/non/oui | Auteur humain, import, fixture, outil ou fournisseur. |
| `ProvenanceRecord` | `tool_revision_id`, `model_code`, `prompt_revision_id`, `transformation_chain`, `input_fingerprint`, `created_at` | références/codes/structure/empreinte/instant | conditionnel | mixte | Aucun contexte privé complet. |

Le sous-graphe des arêtes `required` est acyclique. Une arête ne propage aucune
maîtrise et ne peut référencer une révision retirée pour une nouvelle
publication.

## 7. Catalogue lexical partagé

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `LexiconSource` | `source_id`, `source_type`, `title`, `license_ref` | `uuid7`, enum, texte/réf. | oui | non | Origine et droits. |
| `LexiconSourceRevision` | `source_revision_id`, `source_id`, `revision_no`, `checksum` | `uuid7`, entier, `sha256` | oui | non | Source exacte épinglable. |
| `LexicalUnit` | `lexical_unit_id`, `variety_id`, `unit_type` | `uuid7`, `lexical_unit_type` | oui | non | Enum canonique du document 25. |
| `LexicalUnit` | `visibility`, `owner_profile_id` | `lexical_visibility`, `uuid7` | oui/conditionnel | non/oui | Owner requis si `private`. |
| `LexicalUnitRevision` | `unit_revision_id`, `lexical_unit_id`, `revision_no` | `uuid7`, entier | oui | non | Lemme éditorial et descriptions. |
| `LexicalUnitRevision` | `lemma`, `part_of_speech`, `register`, `status` | texte/enums + `content_revision_status` | oui/oui/non/oui | non/non/oui/non | Le lemme n'est pas l'identité. |
| `LexicalSense` | `sense_id`, `lexical_unit_id`, `sense_code` | `uuid7`, code | oui | non | Grain pédagogique stable. |
| `LexicalSenseRevision` | `sense_revision_id`, `sense_id`, `revision_no` | `uuid7`, entier | oui | non | Révision immuable du sens. |
| `LexicalSenseRevision` | `definition`, `domains`, `register`, `status`, `source_revision_ids` | texte/listes/enums | oui | non | Définition dans sa langue éditoriale. |
| `LemmaRepresentation` | `lemma_representation_id`, `unit_revision_id`, `script_code`, `value` | `uuid7`, codes, texte | oui | non | Plusieurs scripts possibles. |
| `FormAnalysis` | `form_analysis_id`, `unit_revision_id`, `surface` | `uuid7`, texte | oui | non | Une surface peut avoir plusieurs analyses. |
| `FormAnalysis` | `morphological_features`, `pronunciation_refs`, `normalization_key` | typé/listes/texte | oui | non | Clé de recherche non identitaire. |
| `UsageFrame` | `usage_frame_id`, `sense_revision_id`, `frame_type` | `uuid7`, enum | oui | non | Valence, collocation, registre ou pragmatique. |
| `UsageFrame` | `constraints`, `slot_specs`, `examples` | structures typées | oui | non | Cadre versionné avec la révision du sens. |
| `Attestation` | `attestation_id`, `sense_revision_id`, `source_revision_id` | `uuid7` | oui | non | Exemple sourcé. |
| `Attestation` | `text`, `context`, `rights_ref`, `position_spec` | texte/structure/réf. | oui | non | Position exacte et droits. |
| `SemanticEdge` | `edge_id`, `source_sense_revision_id`, `target_sense_revision_id` | `uuid7` | oui | non | Sens vers sens. |
| `LexicalEdge` | `edge_id`, `source_unit_revision_id`, `target_unit_revision_id` | `uuid7` | oui | non | Unité vers unité. |
| `TranslationAssertion` | `assertion_id`, `source_sense_revision_id`, `target_sense_revision_id` | `uuid7` | oui | non | Directionnelle et qualifiée. |
| `RelationAssertion` | `relation_type`, `direction`, `scope`, `confidence`, `source_revision_id` | enums/score/`uuid7` | oui | non | Colonnes communes aux arêtes. |
| `ExpressionComponent` | `expression_unit_revision_id`, `component_unit_revision_id`, `position` | `uuid7`, entier | oui | non | Expression et composants distincts. |
| `FormRealization` | `form_analysis_id`, `unit_revision_id`, `sense_revision_id` | `uuid7` | oui/oui/non | non/non/oui | Sens nullable si la forme ne le désambiguïse pas. |
| `UsageFrameMember` | `usage_frame_id`, `sense_revision_id`, `role_code`, `position` | références/code/entier | oui | non | Jointure typée, pas arête universelle. |
| `TargetLexiconSet` | `lexicon_set_id`, `set_code`, `variety_id` | `uuid7`, code | oui | non | Référentiel borné. |
| `TargetLexiconSetRevision` | `lexicon_set_revision_id`, `lexicon_set_id`, `revision_no`, `denominator` | `uuid7`, entier | oui | non | Membres, licence et provenance figés. |

Il n'existe aucune unicité sur `(variety_id, lemma)` ou sur une traduction.
Homonymes, polysémie, formes syncrétiques et variantes restent distincts.

## 8. Mémoire lexicale personnelle, listes et FSRS

### 8.1 Rencontres, productions et résolution

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `LexicalEncounter` | `encounter_id`, `profile_id`, `occurred_at`, `recorded_at` | `uuid7`, `instant` | oui | non | Fait append-only. |
| `LexicalEncounter` | `surface`, `modality`, `role`, `action`, `intentionality` | texte/enums | oui | non | La présentation n'est pas une preuve. |
| `LexicalEncounter` | `source_revision_id`, `position_spec`, `context_ref` | `uuid7`, structure/réf. | conditionnel | oui | Source/position requises hors ajout manuel. |
| `LexicalEncounter` | `session_plan_id`, `sprint_run_id`, `attempt_id`, `media_revision_id`, `list_snapshot_id` | `uuid7` | non | oui | Liens causaux facultatifs. |
| `LexicalEncounter` | `idempotency_key`, `request_fingerprint`, `retention_policy_revision_id` | texte/`sha256`/`uuid7` | oui | non | Deux occurrences réelles ont deux clés. |
| `LexicalMention` | `mention_id`, `encounter_id`, `candidate_analysis_ids` | `uuid7`, liste UUID | oui | non | Candidats ordonnés avec confiance. |
| `LexicalMention` | `analysis_status` | `mention_analysis_status` | oui | non | Enum canonique du document 25. |
| `MentionResolution` | `resolution_id`, `mention_id`, `sense_revision_id` | `uuid7` | oui/conditionnel | non/oui | Sens absent uniquement pour une contestation non résolue. |
| `MentionResolution` | `decision`, `confidence`, `actor_id`, `decided_at`, `supersedes_resolution_id` | enum/score/UUID/`instant` | oui | mixte | Append-only ; résolution courante dérivée. |
| `LexicalAttentionEvent` | `attention_event_id`, `encounter_id`, `profile_id`, `action`, `occurred_at` | références/enum/instant | oui | non | Recherche, révélation, sélection, répétition ou consultation. |
| `LexicalAttentionEvent` | `source_attempt_id`, `hint_use_id`, `details`, `idempotency_key` | références/structure/texte | non/non/non/oui | oui/oui/oui/non | Ne devient jamais une preuve seul. |
| `ProductionArtifact` | `artifact_id`, `profile_id`, `expected_variety_id` | `uuid7` | oui | non | Réponse brute immuable après soumission. |
| `ProductionArtifact` | `raw_text`, `media_revision_id` | texte/`uuid7` | conditionnel | oui | Au moins l'un des deux est présent. |
| `ProductionArtifact` | `consent_id`, `retention_policy_revision_id`, `created_at`, `submitted_at` | références/`instant` | conditionnel | mixte | Consentement requis pour média conservé. |

### 8.2 Preuves lexicales, facettes et dettes

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `LearningEvidence` | `evidence_id`, `profile_id`, `observation_id` | `uuid7` | oui | non | Conclusion atomique dérivée d'une observation éligible. |
| `LearningEvidence` | `target_type`, `target_id`, `facet_key` | enum/référence | oui | non | Cible lexicale ou compétence précise. |
| `LearningEvidence` | `evidence_score`, `evidence_mass`, `source_weight`, `independence_weight` | `decimal_score` | oui | non | Valeurs épinglées par politique. |
| `LearningEvidence` | `opportunity_id`, `delay_band`, `context_family_id`, `eligible` | `uuid7`, enum/réf., booléen | oui | non | Rejeu identique non contributif. |
| `LearningEvidence` | `policy_revision_id`, `created_at`, `invalidated_at`, `replacement_evidence_id` | références/`instant` | oui/oui/conditionnel | mixte | Invalidation logique, jamais suppression. |
| `PersonalSenseFacet` | `profile_id`, `sense_id`, `modality`, `operation`, `direction` | références/enums | oui | non | Clé naturelle de projection. |
| `PersonalSenseFacet` | `mastery_status`, `score`, `confidence`, `freshness` | enum/scores | oui | non | Projection, jamais saisie manuellement. |
| `PersonalSenseFacet` | `evidence_count`, `contradiction_count`, `last_activity_at`, `next_verification_at` | compteurs/`instant` | oui/oui/non/non | non/non/oui/oui | Absence de preuve autorise dates nulles. |
| `PersonalSenseFacet` | `projection_version`, `policy_revision_id`, `last_event_id` | entier/UUID | oui | non | Reconstructible. |
| `LearningNeed` | `need_id`, `profile_id`, `target_type`, `target_id`, `facet_key` | références/enums | oui | non | Dette ciblée. |
| `LearningNeed` | `status` | `learning_need_status` | oui | non | Enum du document 25. |
| `LearningNeed` | `urgency`, `opened_at`, `planned_at`, `resolved_at`, `superseded_by_need_id` | score/instants/UUID | oui/conditionnel | mixte | Dates cohérentes avec le statut. |
| `LearningNeed` | `resolution_policy_revision_id`, `resolution_evidence_id`, `version` | références/entier | conditionnel | mixte | Preuve requise pour `resolved`. |
| `LearningNeedCause` | `cause_id`, `need_id`, `cause_type`, `source_fact_id`, `opened_at` | références/enum/`instant` | oui | non | Plusieurs causes dédupliquées. |

### 8.3 Listes et snapshots

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `VocabularyList` | `list_id`, `profile_id`, `editorial_owner_id`, `variety_id` | `uuid7` | oui/conditionnel | mixte | Exactement un owner personnel ou éditorial. |
| `VocabularyList` | `list_type`, `status`, `current_revision_id`, `version` | enums/UUID/entier | oui | non | Manuel, éditorial ou dynamique ; active/archived. |
| `VocabularyListRevision` | `list_revision_id`, `list_id`, `revision_no`, `name`, `purpose` | références/entier/texte | oui | non | Révision immuable. |
| `VocabularyListRevision` | `query_definition`, `ordered`, `color`, `tags`, `provenance_id` | typé/booléen/valeurs | conditionnel/non | mixte | Requête requise pour une liste dynamique. |
| `ListMembership` | `membership_id`, `list_revision_id`, `sense_id`, `position`, `role` | références/entier/enum | oui | non | Référence le sens, pas sa copie. |
| `ListSnapshot` | `snapshot_id`, `list_id`, `source_revision_id`, `created_at`, `checksum` | références/`instant`/`sha256` | oui | non | Immuable. |
| `ListSnapshotMember` | `snapshot_id`, `sense_revision_id`, `position`, `role` | références/entier/enum | oui | non | Exactement les membres historiques. |
| `ListAssociation` | `association_id`, `list_id`, `target_type`, `target_id`, `role`, `valid_from`, `valid_until` | références/enums/instants | oui | mixte | Cible module, journée, plan ou exercice. |
| `UserLexicalAnnotation` | `annotation_id`, `profile_id`, `sense_id`, `body`, `tags`, `version` | références/texte/liste/entier | oui | non | Privée et supprimable. |
| `PersonalLexicalPreference` | `profile_id`, `sense_id`, `learning_preference`, `declared_familiarity`, `version`, `updated_at` | références/`lexical_learning_preference`/booléen/entier/instant | oui/oui/non/oui/oui | mixte | Déclaration et préférence n'ont aucun poids de preuve. |
| `PersonalRelation` | `relation_id`, `profile_id`, `source_sense_id`, `target_sense_id`, `relation_type` | références/enum | oui | non | Ne modifie pas le catalogue partagé. |

### 8.4 Invites mémoire et calendrier

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `MemoryPrompt` | `prompt_id`, `profile_id`, `target_type`, `target_id`, `target_revision_id` | références | oui | non | Une cible et révision précises. |
| `MemoryPrompt` | `direction`, `modality`, `operation`, `protocol_revision_id` | enums/référence | oui | non | Deux directions = deux prompts. |
| `MemoryPrompt` | `scheduler_policy_revision_id`, `desired_retention`, `status`, `version` | référence/score/enum/entier | oui | non | Rétention `0.80..0.97`. |
| `MemoryPrompt` | `created_at`, `suspended_at`, `archived_at`, `deleted_at`, `superseded_by_prompt_id` | instants/UUID | oui/conditionnel | mixte | Cycle du document 24. |
| `MemoryScheduleState` | `prompt_id`, `scheduler_kind`, `scheduler_version`, `parameter_set_id` | références/codes | oui | non | Projection courante. |
| `MemoryScheduleState` | `state`, `difficulty`, `stability`, `desired_retention` | enum/décimaux | oui | non | `memory_state` du document 25. |
| `MemoryScheduleState` | `last_review_at`, `due_at`, `last_rating` | instants/enum | non | oui | Tous nuls pour un prompt neuf. |
| `MemoryScheduleState` | `reps`, `lapses`, `projection_version`, `last_review_id` | entiers/UUID | oui/oui/oui/non | non/non/non/oui | Reconstructible depuis les reviews. |
| `MemoryReview` | `review_id`, `prompt_id`, `opportunity_id`, `attempt_id` | références | oui/oui/non | non/non/oui | Fait append-only. |
| `MemoryReview` | `rating`, `reviewed_at`, `scheduled_for_at`, `active_duration_ms` | enum/instants/durée | oui | non | `memory_rating` du document 25. |
| `MemoryReview` | `answer_ref`, `correction_id`, `hint_summary`, `state_before`, `state_after` | références/structures | conditionnel | mixte | Correction requise si note vérifiée. |
| `MemoryReview` | `scheduler_version`, `parameter_set_id`, `idempotency_key`, `request_fingerprint` | codes/références/texte/`sha256` | oui | non | Rejeu déterministe. |
| `MemoryScheduleReset` | `reset_id`, `prompt_id`, `reason`, `reset_at`, `previous_state_ref` | références/code/`instant` | oui | non | Conserve l'historique et ouvre une nouvelle lignée. |

## 9. Contenu, validation et publication

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `ContentItem` | `content_id`, `content_type`, `variety_id`, `editorial_owner_id` | références/enums | oui | non | Identité stable et lignée. |
| `ContentItem` | `parent_content_id`, `lineage_root_id`, `created_at` | références/`instant` | non/oui/oui | oui/non/non | Parent facultatif ; racine obligatoire. |
| `ContentRevision` | `content_revision_id`, `content_id`, `revision_no`, `schema_version` | références/entiers | oui | non | Immuable. |
| `ContentRevision` | `status` | `content_revision_status` | oui | non | Enum du document 25. |
| `ContentRevision` | `payload`, `payload_checksum`, `provenance_id`, `rights_ref` | `json_versioned`, `sha256`, références | oui | non | Payload typé et droits connus. |
| `ContentRevision` | `pinned_revision_refs`, `created_by_actor_id`, `approved_by_actor_id` | listes/UUID | oui/oui/conditionnel | non/non/oui | Approbateur distinct requis pour approbation. |
| `ContentRevision` | `created_at`, `validated_at`, `approved_at`, `published_at`, `retired_at` | instants | oui/conditionnel | mixte | Cohérents avec le statut. |
| `ContentRevision` | `channel_code`, `compatibility_range`, `supersedes_revision_id` | code/intervalle/UUID | conditionnel | mixte | Canal requis à la publication. |
| `ValidationReport` | `report_id`, `subject_revision_id`, `validator_set_revision_id` | références | oui | non | Rapport immuable. |
| `ValidationReport` | `status`, `started_at`, `completed_at`, `summary_checksum` | `validation_report_status`/instants/`sha256` | oui | non | Rapport machine ou revue humaine requise. |
| `ValidationFinding` | `finding_id`, `report_id`, `validator_code`, `severity`, `path`, `message_code` | références/codes/enums/texte | oui | non | Aucun booléen global ne simule la revue humaine. |
| `ValidationFinding` | `redacted_value`, `resolved_by_revision_id` | texte/UUID | non | oui | Valeur privée ou hostile toujours expurgée. |

Une seule révision `published` active est autorisée par `(content_id,
channel_code, compatibility_range)` à un instant donné. Retrait et remplacement
bloquent les nouveaux usages sans casser les références historiques.

## 10. Curriculum, enrôlement et planification

### 10.1 Modules et journées

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `LearningModule` | `module_id`, `module_code`, `pack_id`, `editorial_owner_id` | références/code | oui | non | Identité stable. |
| `LearningModuleRevision` | `module_revision_id`, `module_id`, `revision_no`, `status` | références/entier/`content_revision_status` | oui | non | Révision publiée immuable. |
| `LearningModuleRevision` | `primary_intention`, `final_mission_revision_id`, `entry_profile_codes` | texte/référence/listes | oui | non | Contrat communicatif. |
| `LearningModuleRevision` | `nominal_days`, `max_days`, `min_minutes`, `max_minutes` | entiers | oui | non | `3 <= nominal_days <= max_days <= 30`. |
| `LearningModuleRevision` | `prerequisite_skill_revision_ids`, `target_skill_revision_ids`, `lexicon_set_revision_ids` | listes UUID | oui | non | Références épinglées avec rôles séparés. |
| `LearningModuleRevision` | `exit_policy_revision_id`, `recall_policy_revision_id`, `provenance_id` | références | oui | non | Critères versionnés. |
| `ModuleDay` | `module_day_id`, `module_revision_id`, `ordinal`, `arc_type` | références/entier/enum | oui | non | Ordinal pédagogique, pas date civile. |
| `ModuleDay` | `primary_targets`, `secondary_targets`, `context_revision_ids`, `candidate_primitive_ids` | listes typées | oui | non | Cibles et contenus. |
| `ModuleDay` | `new_lexicon_refs`, `support_lexicon_refs`, `due_target_refs`, `modality_targets` | listes typées | oui | non | Rôles explicites. |
| `ModuleDay` | `minimum_useful_minutes`, `novelty_budget`, `required_block_roles`, `fallback_revision_ids` | entiers/listes | oui | non | Planifiable hors réseau. |
| `ModuleEnrollment` | `enrollment_id`, `profile_id`, `module_revision_id` | références | oui | non | Version épinglée au début. |
| `ModuleEnrollment` | `status` | `module_enrollment_status` | oui | non | Enum du document 25. |
| `ModuleEnrollment` | `current_day_ordinal`, `started_on_pedagogical_day`, `completed_at` | entier/date/instant | conditionnel | mixte | Jour n'avance qu'après noyau terminé. |
| `ModuleEnrollment` | `waiver_refs`, `migration_map_revision_id`, `version` | listes/référence/entier | oui/non/oui | non/oui/non | Migration explicite seulement. |
| `AdaptiveDayInstance` | `adaptive_day_id`, `enrollment_id`, `insert_before_ordinal`, `reason_need_ids` | références/entier/liste | oui | non | Appartient à l'enrôlement, pas au module publié. |
| `AdaptiveDayInstance` | `day_payload_revision_id`, `status`, `created_at` | référence/enum/instant | oui | non | Compte dans `max_days`. |

### 10.2 Plans de session et tâches différées

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `SessionPlan` | `plan_id`, `profile_id`, `purpose`, `policy_revision_id` | références/enum | oui | non | `daily`, `free`, `foundation`, `assessment_prep`. |
| `SessionPlan` | `status` | `session_plan_status` | oui | non | Enum du document 25. |
| `SessionPlan` | `budget_minutes`, `seed`, `planner_version` | entier/code | oui | non | Budget `10..60`, pas de 5. |
| `SessionPlan` | `pedagogical_day`, `timezone_snapshot`, `day_cutover_local_time`, `cutoff_at` | date/fuseau/heure/instant | oui | non | Entrées figées. |
| `SessionPlan` | `module_enrollment_id`, `module_day_id`, `supersedes_plan_id` | références | conditionnel/non | oui | Module absent en pratique libre. |
| `SessionPlan` | `planning_snapshot_id`, `content_p50_ms`, `content_p80_ms`, `novelty_points` | référence/durées/décimal | oui | non | Respect du budget et marge. |
| `SessionPlan` | `created_at`, `ready_at`, `expires_at`, `failure_code`, `version` | instants/code/entier | oui/conditionnel | mixte | Plan `ready` immuable. |
| `PlanningSnapshot` | `snapshot_id`, `profile_id`, `captured_at`, `schema_version`, `checksum` | références/instant/entier/`sha256` | oui | non | Entrées du compositeur. |
| `PlanningSnapshot` | `mastery_projection_versions`, `memory_cutoff`, `need_ids`, `list_snapshot_ids`, `media_availability_refs` | structures/références | oui | non | Aucun fait postérieur au cutoff. |
| `PlanningSnapshot` | `free_practice_context_ref`, `free_practice_intent`, `free_practice_challenge` | référence/texte privé/`free_practice_challenge` | conditionnel | oui | Tous nuls hors pratique libre ; l'intention est une contrainte, pas une vérité. |
| `SessionPlanBlock` | `plan_block_id`, `plan_id`, `ordinal`, `block_family`, `required` | références/entier/enum/booléen | oui | non | Liste ordonnée. |
| `SessionPlanBlock` | `exercise_instances`, `reason_codes`, `target_refs`, `estimated_p50_ms`, `estimated_p80_ms` | dérivé/listes/durées | oui | non | Instances ordonnées par la liaison ; au moins une raison et une cible ou rôle de bilan. |
| `SessionPlanExerciseInstance` | `plan_id`, `plan_block_id`, `instance_id`, `ordinal` | références/entier | oui | non | Liaison W12 vers instances W09 ; unicité plan/instance et bloc/ordinal. |
| `SessionLexicalSelection` | `selection_id`, `plan_id`, `sense_revision_id`, `role`, `reason_code` | références/enums | oui | non | `new`, `due`, `debt`, `target`, `support`, `distractor`, `rescue`. |
| `DelayedTask` | `delayed_task_id`, `profile_id`, `task_type`, `source_revision_id` | références/`delayed_task_type` | oui | non | J+1 ou rappel différé. |
| `DelayedTask` | `due_rule`, `not_before_at`, `status`, `fulfilled_by_observation_id` | `delayed_task_due_rule`/instant/`delayed_task_status`/UUID | oui/oui/oui/conditionnel | non/non/non/oui | `next_active_session` distinct de `after_24h`. |
| `DelayedRecodeSpec` | `delayed_task_id`, `source_attempt_id`, `source_correction_id`, `source_target_text_revision_id`, `support_text_revision_id` | références | oui | non | Source J0 corrigée et immuable. |
| `DelayedRecodeSpec` | `accepted_answer_set_revision_id`, `rubric_revision_id`, `target_refs`, `direction`, `correction_policy_revision_id` | références/listes/enums | oui/conditionnel | mixte | Au moins un ensemble accepté ou une grille. |

## 11. Définitions, instances et exécution d'exercices

### 11.1 Définitions et instances

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `ExerciseDefinition` | `definition_id`, `definition_code` | `uuid7`, code | oui | non | Identité fonctionnelle. |
| `ExerciseDefinitionRevision` | `definition_revision_id`, `definition_id`, `revision_no`, `schema_version` | références/entiers | oui | non | Contrat immuable. |
| `ExerciseDefinitionRevision` | `primitive_id`, `status`, `language_pack_revision_ids`, `modes` | enum/`content_revision_status`/listes | oui | non | `status=published` et certification de langue active sont requis pour planifier. |
| `ExerciseLanguageCertification` | `definition_revision_id`, `language_pack_revision_id`, `status`, `validated_at`, `validator_revision_ids` | références/enum/instant/liste | oui | non | `exercise_language_certification_status`; distinct du cycle éditorial. |
| `ExerciseDefinitionRevision` | `response_contract`, `stimulus_contract`, `target_contract`, `difficulty_profile` | structures typées | oui | non | Aucun payload libre. |
| `ExerciseDefinitionRevision` | `prerequisite_skill_revision_ids`, `hint_policy_revision_id`, `correction_policy_revision_id`, `observation_policy_revision_id` | références | oui | non | Politiques certifiées. |
| `ExerciseDefinitionRevision` | `accessibility_contract`, `min_duration_ms`, `p50_duration_ms`, `p80_duration_ms`, `example_revision_ids` | structure/durées/listes | oui | non | Fixtures valides et invalides requises pour `core`. |
| `ExerciseInstance` | `instance_id`, `definition_revision_id`, `language_pack_revision_id`, `seed` | références/entier | oui | non | Contenu figé, sans état utilisateur. |
| `ExerciseInstance` | `standalone_profile_id` | référence opaque | non | oui | Présent uniquement pour une pratique autonome ; aucun FK vers un lot aval. |
| `ExerciseInstance` | `stimulus_revision_ids`, `target_bindings`, `lexical_bindings`, `grammar_bindings` | listes typées | oui | non | Rôles principal/secondaire/support/distracteur. |
| `ExerciseInstance` | `accepted_answer_set_revision_id`, `rubric_revision_id` | références | conditionnel | oui | Obligatoires si la stratégie les utilise. |
| `ExerciseInstance` | `available_from`, `expires_at`, `provenance_id` | instants/référence | non/non/oui | oui/oui/non | Expiration non rétroactive. |
| `GymPlan` | `gym_plan_id`, `profile_id`, `grammar_target_revision_id`, `policy_revision_id`, `seed` | références/entier | oui | non | Séquence versionnée. |
| `GymPlan` | `lexical_support_snapshot_id`, `invariants`, `exit_evidence_spec` | références/structures | oui | non | Support non crédité automatiquement. |
| `GymStep` | `gym_step_id`, `gym_plan_id`, `ordinal`, `gym_operation`, `instance_id` | références/entier/enum | oui | non | Opérations `GYM-01..15`. |
| `GymCycle` | `gym_cycle_id`, `profile_id`, `gym_plan_revision_id`, `grammar_target_revision_id` | références | oui | non | Cycle personnel épinglé sur le plan et la structure. |
| `GymCycle` | `stage`, `completed`, `started_at`, `completed_at`, `version` | enum/booléen/instants/entier | oui | conditionnel | Agrégat reprenable ; terminé uniquement en `G4`. |
| `GymCycleRequirement` | `requirement_id`, `requirement_kind`, `definition_revision_id` | texte/enum/référence | oui | non | Une production guidée et une à trois transformations pour `G1`. |
| `GymCycleRecord` | `stage`, `verdict`, `hint_level`, `context_id`, `scene_id`, `structure_cued` | enums/références/booléen | oui | non | Fait immuable utilisé pour reconstruire le cycle. |
| `GymCycleRecord` | `credit`, `is_evidence`, `g1_requirement_id`, `attempt_id` | nombre/booléen/références | oui | oui/conditionnel | `G0`, révélation et indisponibilité ne créent aucun crédit. |

### 11.2 Sprint, blocs et tentatives

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `SprintRun` | `run_id`, `plan_id`, `profile_id`, `pedagogical_day` | références/date | oui | non | Un run quotidien actif par profil/jour. |
| `SprintRun` | `status` | `sprint_run_status` | oui | non | Enum du document 25. |
| `SprintRun` | `current_block_id`, `started_at`, `interrupted_at`, `completed_at` | références/instants | conditionnel | oui | Cohérents avec le statut. |
| `SprintRun` | `active_duration_ms`, `stop_reason`, `interrupt_reason`, `version` | durée/codes/entier | oui/non/non/oui | non/oui/oui/non | Raisons distinctes. |
| `ExerciseBlockRun` | `block_run_id`, `run_id`, `plan_block_id`, `ordinal` | références/entier | oui | non | Une exécution par bloc du plan. |
| `ExerciseBlockRun` | `status` | `exercise_block_status` | oui | non | Enum du document 25. |
| `ExerciseBlockRun` | `opened_at`, `completed_at`, `terminal_reason`, `replacement_instance_id` | instants/code/UUID | conditionnel | oui | Saut, abandon et indisponibilité distincts. |
| `Attempt` | `attempt_id`, `instance_id`, `profile_id`, `attempt_no` | références/entier | oui | non | Ordinal croissant par profil/instance. |
| `Attempt` | `status` | `attempt_status` | oui | non | Enum du document 25. |
| `Attempt` | `started_at`, `active_duration_ms`, `submitted_at`, `corrected_at` | instants/durée | oui/oui/conditionnel | mixte | Temps actif séparé. |
| `Attempt` | `answer_kind`, `raw_answer`, `input_method`, `input_locale` | enum/union/enums | conditionnel | oui | Réponse absente avant soumission. |
| `Attempt` | `normalization_policy_revision_id`, `normalized_answer` | référence/union | conditionnel | oui | Valeur dérivée, brut intact. |
| `Attempt` | `terminal_reason`, `idempotency_key`, `request_fingerprint`, `version` | `attempt_terminal_reason`/texte/`sha256`/entier | oui/conditionnel/conditionnel/oui | non/oui/oui/non | `terminal_reason=none` sauf pour `not_evaluable`; clé requise à la soumission/fin. |
| `HintUse` | `hint_use_id`, `attempt_id`, `hint_definition_revision_id`, `level`, `used_at` | références/enum/instant | oui | non | Journal append-only H0-H4. |
| `HintUse` | `reason`, `answer_state_checksum`, `effect_policy_revision_id` | code/`sha256`/référence | oui | non | Effet par cible explicable. |
| `AttemptMediaEvent` | `media_event_id`, `attempt_id`, `media_revision_id`, `event_type`, `occurred_at` | références/enum/instant | oui | non | Lecture, pause, vitesse, transcript. |
| `AttemptMediaEvent` | `position_ms`, `playback_rate`, `segment_id` | durée/décimal/UUID | conditionnel | oui | Selon le type d'événement. |

### 11.3 Corrections, contestations et observations

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `Correction` | `correction_id`, `attempt_id`, `revision_no`, `strategy`, `verdict` | références/entier/enums | oui | non | Révision immuable. |
| `Correction` | `confidence`, `rubric_revision_id`, `proposed_answer`, `alternatives`, `explanation` | score/référence/union/listes/texte | oui/conditionnel/non | mixte | Confiance appartient au correcteur. |
| `Correction` | `error_codes`, `criterion_scores`, `provenance_id`, `created_at` | structures/références/instant | oui | non | Sortie structurée. |
| `Correction` | `requires_review`, `supersedes_correction_id`, `is_current` | booléens/UUID | oui/non/oui | non/oui/non | `is_current` est une commodité contrôlée par unicité. |
| `CorrectionCase` | `case_id`, `attempt_id`, `status`, `opened_by_account_id` | références/enum | oui | non | `correction_case_status` du document 25. |
| `CorrectionCase` | `reason_code`, `user_comment`, `opened_at`, `resolved_at`, `resolution_correction_id` | code/texte/instants/UUID | oui/non/oui/conditionnel | mixte | Commentaire privé facultatif. |
| `LearningObservation` | `observation_id`, `profile_id`, `attempt_id`, `correction_id` | références | oui | non | Fait pédagogique append-only. |
| `LearningObservation` | `target_type`, `target_id`, `facet_key`, `modality`, `operation`, `role` | `observation_target_type`/références/`modality`/`operation`/`observation_role` | oui | non | Ce qui était réellement testé. |
| `LearningObservation` | `result`, `observation_value`, `correction_confidence`, `target_coverage`, `help_level` | `observation_result`/décimaux/`hint_level` | oui | non | Valeur issue du document 12. |
| `LearningObservation` | `opportunity_id`, `context_family_id`, `source_type`, `policy_revision_id`, `created_at` | références/`evidence_source_type`/instant | oui | non | Versions responsables épinglées. |
| `LearningObservation` | `invalidated_at`, `replacement_observation_id`, `invalidation_reason` | instant/UUID/code | conditionnel | oui | Invalidation logique seulement. |

## 12. Progression et recommandations

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `MasteryProjection` | `profile_id`, `skill_id`, `facet_key` | références/code | oui | non | Une ligne par facette de compétence. |
| `MasteryProjection` | `status` | `mastery_status` | oui | non | Enum du document 25. |
| `MasteryProjection` | `mastery_base`, `mastery_current`, `confidence`, `freshness`, `effective_mass` | décimaux | oui | non | Sans preuve : `0.50/0.50/0/0/0`; ces valeurs ne sont ni affichées ni agrégées. |
| `MasteryProjection` | `success_count`, `failure_count`, `context_count`, `session_count`, `delay_band_count`, `transfer_count` | entiers | oui | non | Comptes dédupliqués. |
| `MasteryProjection` | `last_evidence_at`, `next_verification_at`, `policy_revision_id`, `projection_version`, `last_event_id` | instants/références/entier | conditionnel | mixte | Dates nulles en absence de preuve. |
| `Recommendation` | `recommendation_id`, `profile_id`, `target_type`, `target_id`, `facet_key` | références/enums | oui | non | Projection explicable. |
| `Recommendation` | `reason_code`, `reason_params`, `missing_evidence_spec`, `proposed_activity` | code/structures | oui | non | Aucun texte arbitraire comme source de décision. |
| `Recommendation` | `priority`, `urgency`, `estimated_duration_ms`, `policy_revision_id` | décimaux/durée/référence | oui | non | Score initial du document 10. |
| `Recommendation` | `created_at`, `expires_at`, `dismissed_at`, `dismiss_reason` | instants/code | oui/non/non/non | mixte | Refus sans sanction. |

Les vues quatre compétences sont des agrégations de lecture de
`MasteryProjection` et des résultats d'évaluation. Elles ne sont pas persistées
comme score global de langue.

## 13. Évaluations

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `AssessmentDefinition` | `assessment_definition_id`, `definition_code`, `modality` | références/code/enum | oui | non | Une modalité par définition. |
| `AssessmentDefinitionRevision` | `assessment_revision_id`, `assessment_definition_id`, `revision_no`, `status` | références/entier/`content_revision_status` | oui | non | Révision éditoriale immuable. |
| `AssessmentDefinitionRevision` | `protocol_revision_id`, `coverage_matrix`, `difficulty_profile`, `time_limit_ms` | références/structures/durée | oui | non | Protocole commun. |
| `AssessmentDefinitionRevision` | `pause_policy`, `security_rules`, `rubric_revision_id`, `parallel_form_rules` | structures/référence | oui | non | Aides et reprises bornées. |
| `AssessmentForm` | `form_id`, `assessment_revision_id`, `form_code`, `checksum` | références/code/`sha256` | oui | non | Forme parallèle figée. |
| `AssessmentSectionDefinition` | `section_definition_id`, `form_id`, `ordinal`, `section_type`, `weight` | références/entier/enum/décimal | oui | non | Sections ordonnées. |
| `AssessmentItem` | `item_id`, `section_definition_id`, `exercise_instance_id`, `weight`, `coverage_targets` | références/décimal/listes | oui | non | Instance certifiée sans fuite de réponse. |
| `AssessmentRun` | `assessment_run_id`, `profile_id`, `assessment_revision_id`, `form_id` | références | oui | non | Cibles et forme épinglées. |
| `AssessmentRun` | `status` | `assessment_run_status` | oui | non | Enum du document 25. |
| `AssessmentRun` | `started_at`, `deadline_at`, `paused_at`, `submitted_at`, `completed_at` | instants | conditionnel | oui | Temps restant calculé serveur. |
| `AssessmentRun` | `target_snapshot_id`, `integrity_incidents`, `version` | référence/liste/entier | oui | non | Snapshot et concurrence. |
| `AssessmentSectionRun` | `section_run_id`, `assessment_run_id`, `section_definition_id`, `status` | références/`assessment_section_status` | oui | non | État et reprise par section. |
| `AssessmentSectionRun` | `started_at`, `completed_at`, `remaining_time_ms_at_pause` | instants/durée | conditionnel | oui | Restauration exacte. |
| `AssessmentResponse` | `response_id`, `assessment_run_id`, `item_id`, `answer`, `version` | références/union/entier | oui | non | Autosauvegarde versionnée. |
| `AssessmentResponse` | `saved_at`, `submitted_at`, `correction_id` | instants/UUID | oui/conditionnel | non/oui | Réponse finale immuable. |
| `AssessmentResult` | `result_id`, `assessment_run_id`, `modality`, `result_status` | références/enums | oui | non | `valid`, `indicative`, `not_evaluable`. |
| `AssessmentResult` | `score`, `band`, `confidence`, `coverage`, `integrity_factor` | décimaux/enum | conditionnel | oui | Score/bande absents si non évaluable. |
| `AssessmentResult` | `limiting_criteria`, `policy_revision_id`, `created_at` | liste/référence/instant | oui | non | Projection de résultat immuable pour le run. |
| `AssessmentEvidence` | `assessment_evidence_id`, `result_id`, `item_id`, `observation_id`, `modality`, `facet_key` | références/enums | oui | non | Ne crédite que la modalité mesurée. |

La bande utilise `ASSESS-B0..B4`. Elle n'est ni un niveau CECR, ni une clé de
déblocage automatique.

## 14. Médias, TTS et oral

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `MediaAsset` | `media_id`, `owner_account_id`, `editorial_owner_id`, `media_type` | références/enum | oui/conditionnel | mixte | Exactement un owner privé ou éditorial. |
| `MediaAsset` | `status` | `media_status` | oui | non | Enum du document 25. |
| `MediaAsset` | `privacy_class`, `created_at`, `expires_at`, `deletion_requested_at`, `version` | enum/instants/entier | oui/oui/non/non/oui | mixte | Rétention visible. |
| `MediaRevision` | `media_revision_id`, `media_id`, `revision_no`, `storage_key` | références/entier/texte | oui | non | Clé opaque. |
| `MediaRevision` | `sha256`, `size_bytes`, `detected_mime`, `duration_ms`, `variety_id` | empreinte/entiers/référence | oui/oui/oui/non/non | non/non/non/oui/oui | Durée/langue selon type. |
| `MediaRevision` | `rights_ref`, `license_ref`, `consent_id`, `source_ref`, `processing_version` | références/codes | conditionnel | oui | Obligatoires selon publication et caractère privé. |
| `MediaVariant` | `variant_id`, `media_revision_id`, `variant_type`, `storage_key`, `sha256` | références/enums/texte | oui | non | TTS, transcodage, miniature ou alternative. |
| `MediaSegment` | `segment_id`, `media_revision_id`, `ordinal`, `start_ms`, `end_ms`, `transcript_text` | références/entiers/texte | oui/oui/oui/oui/non | non/non/non/non/oui | `end_ms > start_ms`. |
| `OralAsset` | `oral_asset_id`, `media_revision_id`, `transcript_revision_id`, `speaker_or_voice_ref` | références | oui | non | Support oral publié. |
| `OralAsset` | `reference_rate`, `register`, `segment_ids`, `provenance_id` | décimal/enum/listes/réf. | oui | non | Vitesses publiées versionnées. |
| `MediaUpload` | `upload_id`, `media_id`, `reserved_by_actor_id`, `expected_size`, `expected_sha256` | références/entier/empreinte | oui | non | URL signée non persistée comme secret métier. |
| `MediaUpload` | `reserved_at`, `expires_at`, `completed_at`, `detected_mime`, `scan_result` | instants/enum | oui/oui/conditionnel | mixte | Vérification avant disponibilité. |
| `TtsVoiceCatalogRevision` | `catalog_revision_id`, `provider_code`, `provider_version`, `published_at` | références/codes/instant | oui | non | Catalogue versionné. |
| `TtsVoiceCapability` | `voice_id`, `catalog_revision_id`, `language_tags`, `formats`, `limits`, `availability` | références/listes/structure/enum | oui | non | `available`, `temporarily_unavailable`, `retired`, `unsupported`. |

Un enregistrement oral privé est local par défaut. Son upload ou sa conservation
exige une commande et un consentement explicites. Une voix ou un média retiré
ne déclenche aucun remplacement silencieux.

## 15. Jobs, génération, outils, imports et exports

### 15.1 Jobs et génération

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `Job` | `job_id`, `job_type`, `requested_by_actor_id`, `profile_id` | références/enum | oui/oui/non | non/non/oui | Profil si travail personnel. |
| `Job` | `status` | `job_status` | oui | non | Enum du document 25. |
| `Job` | `idempotency_key`, `request_fingerprint`, `correlation_id`, `payload_schema_version` | texte/empreinte/UUID/entier | oui | non | PostgreSQL reste source de vérité. |
| `Job` | `requested_at`, `queued_at`, `started_at`, `finished_at`, `cancel_requested_at` | instants | oui/conditionnel | mixte | Cohérents avec le statut. |
| `Job` | `progress_completed`, `progress_total`, `result_ref`, `error_code`, `version` | entiers/réf./code | oui/oui/non/non/oui | mixte | Aucun contenu privé dans le progrès. |
| `JobAttempt` | `job_attempt_id`, `job_id`, `attempt_no`, `status` | références/entier/`job_attempt_status` | oui | non | Tentative technique. |
| `JobAttempt` | `lease_owner`, `lease_expires_at`, `started_at`, `finished_at`, `retry_not_before_at` | texte/instants | conditionnel | oui | Lease de cinq minutes renouvelable. |
| `JobAttempt` | `provider_code`, `operation_code`, `error_code`, `retryable` | codes/booléen | conditionnel | mixte | Retry seulement par politique. |
| `GenerationJob` | `generation_job_id`, `job_id`, `purpose`, `contract_revision_id`, `target_author_id` | références/codes | oui | non | Spécialisation de `Job`. |
| `GenerationJob` | `input_fingerprint`, `budget_policy_revision_id`, `lineage_parent_id` | empreinte/références | oui/non | non/oui | Aucune publication automatique. |
| `GenerationAttempt` | `generation_attempt_id`, `generation_job_id`, `job_attempt_id` | références | oui | non | Appel concret. |
| `GenerationAttempt` | `provider_code`, `model_code`, `prompt_revision_id`, `tool_revision_ids`, `parameters` | codes/références/structure | oui | non | Fournisseur explicite. |
| `GenerationAttempt` | `raw_output_ref`, `resulting_draft_revision_id`, `latency_ms`, `input_tokens`, `output_tokens`, `cost_minor`, `currency_code` | références/mesures | conditionnel | mixte | Sortie invalide conservée selon rétention. |
| `GenerationAttempt` | `outcome`, `error_code`, `started_at`, `finished_at` | enum/code/instants | oui/non/oui/conditionnel | mixte | Aucun fallback silencieux. |
| `ToolContractRevision` | `tool_revision_id`, `tool_name`, `schema_version`, `input_schema`, `output_schema` | références/code/entier/JSON Schema | oui | non | Contrat immuable. |
| `ToolContractRevision` | `allowed_roles`, `data_scope`, `timeout_ms`, `size_budget`, `idempotency_policy` | listes/structures | oui | non | Allowlist fermée. |
| `ToolInvocation` | `invocation_id`, `tool_revision_id`, `actor_id`, `job_id`, `input_fingerprint` | références/empreinte | oui/oui/non/oui | non/non/oui/non | Audit sans payload privé complet. |
| `ToolInvocation` | `status`, `output_ref`, `error_code`, `started_at`, `finished_at` | `tool_invocation_status`/réf./code/instants | oui/non/non/oui/conditionnel | mixte | Sortie validée avant usage. |

### 15.2 Imports, partage et exports

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `ImportRun` | `import_id`, `profile_id`, `editorial_owner_id`, `format_id`, `schema_version` | références/codes/entier | oui/conditionnel | mixte | Exactement une portée personnelle ou éditoriale. |
| `ImportRun` | `status`, `media_revision_id`, `source_checksum`, `encoding`, `created_at`, `expires_at` | `import_status`/références/empreinte/texte/instants | oui | non | Pipeline `uploaded` à `reverted`. |
| `ImportRun` | `strategy`, `catalogue_version_at_preview`, `preview_checksum`, `committed_at`, `reverted_at`, `version` | enum/réf./empreinte/instants/entier | conditionnel | mixte | Commit refuse un aperçu obsolète. |
| `ImportLine` | `import_line_id`, `import_id`, `line_no`, `source_path`, `status` | références/entier/texte/`import_line_status` | oui | non | Rapport par ligne. |
| `ImportLine` | `intermediate_payload`, `redacted_error_value`, `result_entity_refs` | `json_versioned`/texte/listes | conditionnel | oui | Aucun silence sur les erreurs. |
| `ImportConflict` | `conflict_id`, `import_line_id`, `conflict_class`, `candidate_refs`, `allowed_actions` | références/enum/listes | oui | non | Classes du document 22. |
| `ImportConflict` | `selected_action`, `decided_by_actor_id`, `decided_at` | enum/UUID/instant | conditionnel | oui | Requis avant commit si interactif. |
| `ImportManifest` | `manifest_id`, `import_id`, `created_refs`, `reused_refs`, `inverse_operations`, `checksum` | références/listes/structure/empreinte | oui | non | Permet compensation contrôlée. |
| `SharedListPublication` | `publication_id`, `list_snapshot_id`, `license_ref`, `provenance_id` | références | oui | non | Seul un snapshot choisi est partagé. |
| `SharedListPublication` | `status`, `published_at`, `retired_at` | `content_revision_status`/instants | oui/conditionnel | mixte | Aucune preuve, dette ou échéance privée. |
| `ExportRun` | `export_id`, `account_id`, `profile_id`, `job_id`, `scope` | références/structure | oui/oui/non/oui/oui | non/non/oui/non/non | Export compte ou langue. |
| `ExportRun` | `status`, `requested_at`, `completed_at`, `expires_at`, `manifest_checksum` | `export_status`/instants/empreinte | oui/conditionnel | mixte | Archive disponible 72 h. |
| `ExportArtifact` | `export_artifact_id`, `export_id`, `media_revision_id`, `encryption_scheme`, `schema_version` | références/code/entier | oui | non | URL signée non persistée. |

Formats initiaux : `polyglot.lexicon.bundle/v1`,
`polyglot.memory.prompts/v1`, `polyglot.generic.qa/v1`,
`polyglot.authoring.bundle/v1` et `polyglot.user.export/v1`.

## 16. Plateforme, événements, audit et suppression

| Entité | Champ | Type | Requis | Nullable | Règle |
|---|---|---|---:|---:|---|
| `CommandReceipt` | `command_id`, `command_type`, `actor_id`, `aggregate_type`, `aggregate_id` | références/codes | oui | non | Une commande acceptée. |
| `CommandReceipt` | `idempotency_key`, `request_fingerprint`, `expected_version`, `received_at`, `result_ref`, `status` | texte/empreinte/entier/instant/réf./`command_receipt_status` | oui/oui/non/oui/non/oui | mixte | Même clé + autre corps = conflit. |
| `DomainEvent` | `event_id`, `event_type`, `schema_version`, `aggregate_type`, `aggregate_id`, `aggregate_version` | références/codes/entiers | oui | non | Enveloppe du document 09. |
| `DomainEvent` | `actor_type`, `actor_id`, `profile_id`, `occurred_at`, `recorded_at` | enums/références/instants | oui/oui/non/oui/oui | non/non/oui/non/non | Profil si pertinent. |
| `DomainEvent` | `correlation_id`, `causation_id`, `command_id`, `privacy_class`, `policy_revision_ids`, `payload` | références/enum/liste/`json_versioned` | oui | non | Payload minimal. |
| `OutboxMessage` | `outbox_id`, `event_id`, `destination`, `created_at`, `published_at`, `attempt_count` | références/code/instants/entier | oui | mixte | Même transaction que l'événement. |
| `InboxReceipt` | `consumer_code`, `event_id`, `processed_at`, `result_checksum` | code/référence/instant/empreinte | oui | non | Déduplication `(consumer,event)`. |
| `ProjectionCheckpoint` | `projection_name`, `partition_key`, `last_event_id`, `last_recorded_at`, `projection_version` | codes/référence/instant/entier | oui | non | Reprise et reconstruction. |
| `SecurityAuditEntry` | `audit_id`, `actor_pseudonym`, `action_code`, `resource_type`, `resource_id`, `result` | références/codes | oui | non | Aucun contenu privé. |
| `SecurityAuditEntry` | `reason_code`, `occurred_at`, `request_id`, `correlation_id`, `session_fingerprint`, `truncated_ip` | codes/instant/références/empreintes | oui | non | Rétention 180 jours. |
| `DeletionRequest` | `deletion_request_id`, `subject_type`, `subject_id`, `requested_by_account_id`, `status` | références/`deletion_request_status` | oui | non | Compte, profil ou contexte privé. |
| `DeletionRequest` | `requested_at`, `confirmed_at`, `purge_due_at`, `completed_at`, `policy_revision_id` | instants/référence | oui/conditionnel | mixte | Purge active sous 30 jours. |
| `DeletionTombstone` | `tombstone_id`, `subject_type`, `subject_fingerprint`, `effective_at`, `policy_revision_id` | références/empreinte/instant | oui | non | Rejoué après restauration. |
| `DeletionTombstone` | `purged_scopes`, `last_applied_at`, `expires_at` | liste/instants | oui/oui/non | non/non/oui | Ne permet pas de reconstruire les données. |
| `FeatureFlag` | `flag_id`, `flag_code`, `owner`, `reason`, `expires_at` | références/codes/texte/instant | oui | non | Kill switch serveur, jamais permission. |
| `FeatureFlagValue` | `flag_id`, `environment`, `value`, `version`, `updated_at` | référence/enum/typé/entier/instant | oui | non | Valeur par environnement. |

Les registres de traçabilité d'ingénierie (`CapabilityId`, exigences `REQ-*`,
fixtures `FX-*`, preuves `P-*`, gates et releases) sont des artefacts versionnés
du dépôt ou du système de livraison. Ils ne font pas partie de la base métier.
S'ils sont persistés pour l'Atelier, ils conservent au minimum identifiant,
version, owner, contrats, fixture, preuves, approbateur et statut de livraison
du document 23.

## 17. Cardinalités et contraintes d'unicité

| Contrainte | Cardinalité ou unicité normative |
|---|---|
| Compte-préférences | `Account 1 -- 1 UserPreferences`. |
| Identité locale | `normalized_identifier` unique parmi les identités locales actives. |
| Identité OIDC | `(issuer, subject)` unique. |
| Rôle | `(account_id, role)` unique parmi les attributions actives. |
| Profil cible | Au plus un profil non supprimé par `(account_id, target_variety_id)` ; un profil archivé se restaure. |
| Langue d'appui | `(profile_id, variety_id)` unique parmi les autorisations non révoquées. |
| Révisions | `(stable_id, revision_no)` unique pour toute famille révisionnée. |
| Pack publié | Une révision active par `(pack_id, channel, compatibility_range)`. |
| Prérequis | Pas de doublon `(from_skill_revision_id, to_skill_revision_id, edge_type)` ; sous-graphe `required` acyclique. |
| Unité et sens lexicaux | `LexicalUnit 1 -- N LexicalSense`; aucune unicité par chaîne. |
| Forme | Une surface peut avoir N `FormAnalysis`; une analyse référence une révision d'unité. |
| Rencontre | `(profile_id, idempotency_key)` unique ; deux occurrences réelles ont des clés distinctes. |
| Résolution | Une résolution courante par `mention_id`; anciennes décisions conservées. |
| Facette lexicale | Unique par `(profile_id, sense_id, modality, operation, direction)`. |
| Dette | Au plus un besoin `open` ou `planned` par `(profile_id, target_type, target_id, facet_key)` ; causes multiples. |
| Liste | `VocabularyList 1 -- N VocabularyListRevision`; membre unique par `(list_revision_id, sense_id, role)`. |
| Snapshot de liste | Immuable ; membre unique par `(snapshot_id, sense_revision_id, role)`. |
| Prompt mémoire | Au plus un prompt non terminal par `(profile_id, target, direction, modality, protocol_revision_id)`. |
| Review mémoire | `(prompt_id, idempotency_key)` unique et `(prompt_id, opportunity_id)` dédupliqué lors d'une fusion. |
| Contenu publié | Une révision publiée active par identité, canal et compatibilité. |
| Module | `LearningModuleRevision 1 -- N ModuleDay`; `ordinal` unique et continu dans la révision. |
| Enrôlement | Un seul enrôlement `active` par profil ; plusieurs historiques terminés autorisés. |
| Plan quotidien | Au plus un `SessionPlan` non terminal par `(profile_id, pedagogical_day, purpose=daily)`. |
| Sprint quotidien | Au plus un `SprintRun` actif par `(profile_id, pedagogical_day)` ; les runs terminaux restent historiques. |
| Bloc | `(run_id, plan_block_id)` unique. |
| Tentative | `(profile_id, instance_id, attempt_no)` unique ; au plus une tentative `draft` ouverte par instance/profil. |
| Soumission | `(attempt_id, idempotency_key)` unique ; un payload divergent est rejeté. |
| Correction | `(attempt_id, revision_no)` unique ; une seule correction courante. |
| Observation | Une observation logique par `(attempt_id, target, facet_key, policy_revision_id)` ; remplacement explicite. |
| Projection de maîtrise | Unique par `(profile_id, skill_id, facet_key)`. |
| Évaluation | Un run référence une seule forme ; une réponse unique par `(assessment_run_id, item_id)`. |
| Média | `(media_id, revision_no)` unique ; `(sha256, size_bytes)` sert à détecter, jamais à imposer une identité métier. |
| Job | `(requested_by_actor_id, job_type, idempotency_key)` unique. |
| Import | `(scope_owner, idempotency_key)` unique ; `line_no` unique dans l'import. |
| Outbox/inbox | `event_id` unique ; `(consumer_code, event_id)` unique. |

## 18. Faits, état mutable, révisions et projections

| Classe | Objets | Mutation autorisée | Source de reconstruction |
|---|---|---|---|
| Faits append-only | rencontres, productions soumises, réponses finales, aides, événements média, reviews mémoire, observations, événements de domaine, audit | Ajout, invalidation ou remplacement logique seulement | eux-mêmes et leurs versions épinglées |
| Révisions immuables | packs, unités/sens, compétences, structures, contenus, définitions, modules, évaluations, politiques, listes figées | Nouvelle révision ; jamais modification en place après publication/usage | identité stable + chaîne de révisions |
| État d'agrégat mutable | compte, profil, enrôlement, plan avant `ready`, sprint, tentative avant soumission, dette, prompt, job | Commande autorisée, contrôle `version`, événement | état courant + événements nécessaires à l'audit |
| Projections persistées | `PersonalSenseFacet`, `MemoryScheduleState`, `MasteryProjection`, recommandations, vues Word Bank et progression | Recalcul uniquement ; aucune saisie utilisateur directe | faits + politiques + horloge + checkpoint |
| Projections éphémères | couverture d'un référentiel, file due, recommandations temporaires, résumé quatre compétences | Recalcul à la lecture ou cache invalidable | projections/faits autorisés et cutoff |
| Archives non actives | historique SM-2, sorties de génération privées expirables, source d'import, anciennes projections | Lecture/audit selon rétention ; jamais moteur courant | artefact archivé et manifeste |

Une projection doit exposer `policy_revision_id`, `projection_version`, instant
de calcul et IDs des faits ou un mécanisme paginé d'explication. La suppression
d'un contexte peut rendre une preuve non reconstructible ; elle est alors
invalidée explicitement plutôt que conservée comme résultat opaque.

## 19. Suppression, archivage et rétention

### 19.1 Politique par famille

| Famille | Action utilisateur | Rétention active | Fin de cycle |
|---|---|---|---|
| Compte/profil, preuves et réponses | suppression asynchrone auditée | tant que compte/profil existe | purge ou anonymisation sous 30 jours ; tombstone conservé selon politique |
| Profil linguistique | pause ou archive réversible | faits conservés | suppression bloque runs/jobs puis purge la portée privée |
| Brouillon de réponse non soumis | aucune conservation demandée | 24 h | expiration automatique |
| Réponse soumise et observation | aucune édition destructive | vie du profil | purge/anonymisation liée au profil ; remplacement logique avant purge |
| Audio brut d'entraînement | sauvegarde explicite facultative | 24 h par défaut | objet et dérivés purgés |
| Audio d'évaluation | consentement et protocole | 7 jours | purge audio ; transcription/projection seulement si nécessaire et consentie |
| Prompt/sortie de génération privée | aucun droit de publication implicite | 30 jours | contenu purgé ; empreinte, coût et statut non sensibles conservés |
| Contenu publié et provenance | retrait, jamais effacement immédiat | vie du contenu + 5 ans | suppression seulement si droits l'exigent et références traitées |
| Liste | archive réversible | vie du profil | snapshots utilisés restent interprétables jusqu'à purge du profil |
| Prompt mémoire | suspension/archive/reset | reviews conservées | suppression privée selon dépendances de preuve |
| Média éditorial | retrait ou suppression selon droits | tant que droits valides | indisponible, puis purge objet ; métadonnée minimale si historique requis |
| Fichier d'import et quarantaine | commit/cancel | durée courte fixée par politique | purge du fichier ; manifeste et rapport expurgé conservés |
| Export privé | téléchargement autorisé | 72 h après disponibilité | purge de l'archive chiffrée |
| Logs applicatifs | automatique | 30 jours | expiration |
| Audit sécurité privilégié | aucune suppression ordinaire | 180 jours | expiration contrôlée |
| Sauvegardes | automatique | 35 jours glissants | expiration ; tombstones rejoués à toute restauration |

### 19.2 Règles de suppression

1. L'archivage masque et désactive ; il ne supprime aucun fait.
2. Le retrait éditorial interdit les nouveaux usages ; les usages épinglés
   restent interprétables tant que les droits le permettent.
3. Une suppression privée ne supprime jamais un catalogue partagé.
4. Une liste ou carte utilisée par une session ne retire pas son snapshot
   historique.
5. Une suppression de compte ou profil ferme sessions, bloque jobs et nouvelles
   commandes, purge projections puis données privées, et écrit un tombstone.
6. Les sauvegardes ne sont pas réécrites ; une restauration applique les
   tombstones avant remise en service.
7. Les URLs signées, cookies, secrets et credentials ne sont jamais conservés
   comme données métier exportables.
8. Une opération destructive indique portée, dépendances, effet sur preuves,
   politique, acteur et corrélation dans l'audit.

## 20. Mapping des enums canoniques vers le document 25

Le tableau suivant est exhaustif pour les enums centraux du document 25. Les
valeurs persistées sont exactement celles du registre, en ASCII
`lower_snake_case`. Les labels UI n'en créent aucune nouvelle.

| Enum document 25 | Champs consommateurs | Source d'état |
|---|---|---|
| `language_profile_status` | `LearnerLanguageProfile.status` | commandes de profil et diagnostic/fondations |
| `content_revision_status` | `LanguagePackRevision.status`, `SkillRevision.status`, `ContentRevision.status`, révisions éditoriales compatibles | cycle validation/approbation/publication |
| `module_enrollment_status` | `ModuleEnrollment.status` | commandes d'enrôlement |
| `session_plan_status` | `SessionPlan.status` | composition et préparation |
| `sprint_run_status` | `SprintRun.status` | démarrage, interruption, reprise, arrêt, complétion |
| `exercise_block_status` | `ExerciseBlockRun.status` | disponibilité et actions de bloc |
| `attempt_status` | `Attempt.status` | ouverture, sauvegarde, soumission et correction |
| `attempt_terminal_reason` | `Attempt.terminal_reason` | raison terminale distincte de l'état et du verdict |
| `correction_case_status` | `CorrectionCase.status` | contestation et revue |
| `correction_verdict` | `Correction.verdict` | politique de correction |
| `learning_need_status` | `LearningNeed.status` | planification et preuve de résolution |
| `assessment_run_status` | `AssessmentRun.status` | minuteur, pause, soumission et scoring |
| `job_status` | `Job.status` et état externe de `GenerationJob` | dispatcher et worker persistants |
| `mastery_status` | `PersonalSenseFacet.mastery_status`, `MasteryProjection.status` | politique de maîtrise versionnée |
| `memory_prompt_status` | `MemoryPrompt.status` | commandes mémoire |
| `memory_state` | `MemoryScheduleState.state` | adaptateur FSRS |
| `memory_rating` | `MemoryReview.rating` et `Answer.self_grade` | protocole de rappel compatible |
| `media_status` | `MediaAsset.status` | pipeline upload, vérification, traitement et suppression |

Résolutions obligatoires des variantes présentes dans les documents antérieurs :

- `retired` n'est pas une valeur de `memory_prompt_status`; utiliser
  `archived`, ou `superseded` lorsqu'un prompt remplace un autre ;
- `contested` n'est pas un `correction_verdict`; c'est une vue dérivée de
  `CorrectionCase.status=contested` ;
- les états `draft_produced`, `validating`, `needs_revision`, `validated` et
  `closed` du récit de génération ne créent pas un second statut de job : le job
  utilise `job_status`, la sortie utilise `GenerationAttempt.outcome` et le
  brouillon utilise `content_revision_status` ;
- les libellés `rencontré`, `reconnu` et `utilisable` sont des filtres de
  projection Word Bank, pas des valeurs de `mastery_status` ;
- les accents des labels français n'apparaissent jamais dans les valeurs
  persistées.

### 20.1 Vocabulaires fermés complémentaires

Ces vocabulaires sont structurants et sont tous inscrits au registre canonique
du document 25, section 2.1. Le rappel ci-dessous indique leur owner métier ; il
ne constitue pas un second registre.

| Enum complémentaire | Valeurs initiales | Owner documentaire |
|---|---|---|
| `account_status` | `active`, `locked`, `pending_deletion`, `deleted` | 06, 08, 17 |
| `account_role` | `learner`, `author`, `reviewer`, `support`, `admin`, `worker` | 06, 17 |
| `identity_provider_type` | `local_password`, `oidc` | 06, 17 |
| `consent_status` | `granted`, `withdrawn` | 17, 25 |
| `privacy_class` | `public`, `internal`, `personal`, `sensitive`, `secret` | 17 |
| `guided_run_status` | `prepared`, `in_progress`, `interrupted`, `completed`, `expired`, `cancelled` | 10, 13 |
| `modality` | `reading`, `listening`, `writing`, `speaking` | 06, 10, 14 |
| `operation` | `recognize`, `recall`, `discriminate`, `transform`, `produce`, `interact`, `repair`, `transfer` | 06 |
| `prerequisite_edge_type` | `required`, `recommended`, `contrast`, `transfer` | 08 |
| `mention_analysis_status` | `pending`, `ambiguous`, `resolved`, `disputed` | 07 |
| `list_type` | `manual`, `editorial`, `dynamic` | 07 |
| `list_status` | `active`, `archived` | 07, 22 |
| `session_purpose` | `daily`, `free`, `foundation`, `assessment_prep` | 08 |
| `module_arc_type` | `discovery`, `guided_use`, `integration`, `transfer`, `consolidation` | 11 |
| `session_block_family` | `recall_warmup`, `lexical_acquisition`, `version_input`, `grammar_toolbox`, `transformation_gym`, `listening`, `shadowing`, `guided_output`, `free_writing`, `delayed_recode`, `reflection_close` | 11 |
| `session_lexical_role` | `new`, `due`, `debt`, `target`, `support`, `distractor`, `rescue` | 11 |
| `exercise_language_certification_status` | `certified`, `suspended`, `withdrawn` | 12 |
| `primitive_maturity` | `core`, `extended`, `future` | 12 |
| `answer_kind` | `acknowledgement`, `single_choice`, `graded_choice`, `selection`, `pairing`, `grouping`, `ordered_items`, `cells`, `spans`, `tokens`, `text`, `short_text`, `audio_ref`, `self_grade`, `self_assessment`, `no_answer` | 12 |
| `hint_level` | `h0`, `h1`, `h2`, `h3`, `h4` | 12 |
| `correction_strategy` | `exact_normalized`, `accepted_set`, `morphological`, `structural_constraints`, `bounded_translation`, `rubric`, `self_assessment`, `human_review`, `llm_review` | 12 |
| `validation_report_status` | `pending`, `running`, `passed`, `failed`, `human_required`, `cancelled` | 22 |
| `assessment_section_status` | `pending`, `in_progress`, `completed`, `skipped`, `expired` | 14 |
| `assessment_result_status` | `valid`, `indicative`, `not_evaluable` | 14 |
| `assessment_band` | `assess_b0`, `assess_b1`, `assess_b2`, `assess_b3`, `assess_b4` | 14, avec affichage `ASSESS-B0..B4` |
| `tts_availability` | `available`, `temporarily_unavailable`, `retired`, `unsupported` | 16 |
| `job_attempt_status` | `running`, `succeeded`, `retryable_failed`, `failed`, `cancelled` | 17 |
| `tool_invocation_status` | `requested`, `running`, `succeeded`, `failed`, `cancelled` | 22, 25 |
| `import_status` | `uploaded`, `quarantined`, `parsing`, `invalid`, `preview_ready`, `awaiting_decision`, `committing`, `committed`, `failed`, `cancelled`, `reverted` | 22 |
| `import_line_status` | `pending`, `accepted`, `rejected`, `conflict`, `committed`, `reverted` | 22 |
| `import_strategy` | `fail_on_conflict`, `reuse_exact`, `create_distinct`, `interactive` | 22 |
| `import_conflict_class` | `exact_identity`, `same_sense`, `same_form_other_sense`, `same_prompt`, `content_revision_conflict`, `private_public_collision`, `ambiguous` | 22 |
| `export_status` | `requested`, `queued`, `running`, `ready`, `failed`, `expired`, `cancelled` | 22 |
| `command_receipt_status` | `started`, `succeeded`, `rejected`, `failed` | 09, 25 |
| `deletion_request_status` | `requested`, `confirmed`, `blocked`, `purging`, `completed`, `cancelled`, `failed` | 17, 18 |
| `delivery_status` | `specified`, `planned`, `implemented`, `verified`, `accepted`, `released` | 23 |
| `learning_phase` | `diagnostic`, `foundations`, `module_learning`, `paused`, `archived` | 08, 10 |
| `diagnostic_classification` | `beginner`, `false_beginner`, `intermediate`, `undetermined` | 10 |
| `foundation_block_status` | `locked`, `available`, `in_progress`, `passed`, `waived` | 10, 13 |
| `foundation_run_block_status` | `pending`, `available`, `in_progress`, `completed`, `failed`, `waived` | 10, 13 |
| `lexical_unit_type` | `word`, `multiword_expression`, `proper_name`, `lexicalized_construction` | 07 |
| `lexical_visibility` | `shared`, `private` | 07 |
| `delayed_task_type` | `delayed_recode`, `delayed_recall`, `transfer_check` | 11 |
| `delayed_task_due_rule` | `next_active_session`, `after_24h`, `after_7d` | 11 |
| `delayed_task_status` | `scheduled`, `due`, `fulfilled`, `expired`, `cancelled` | 11 |
| `observation_target_type` | `skill`, `lexical_sense`, `lexical_form`, `grammar_structure`, `grammar_pattern`, `pronunciation_target` | 10, 12 |
| `observation_role` | `primary`, `secondary`, `support`, `distractor` | 12 |
| `observation_result` | `success`, `partial_success`, `failure`, `inconclusive` | 12 |
| `evidence_source_type` | `assessment`, `daily_sprint`, `foundations`, `free_practice`, `diagnostic`, `declaration`, `exposure` | 10 |
| `lexical_learning_preference` | `normal`, `prioritize`, `ignore` | 07 |
| `free_practice_challenge` | `gentler`, `matched`, `stretch` | 11 |

Les identifiants de primitives `EX-*`, transformations `GYM-*`, politiques
`*_V0`, fixtures `FX-*`, exigences `REQ-*`, preuves `P-*` et gates `G*` sont des
codes de registre versionnés, pas des enums extensibles par l'utilisateur.

## 21. Invariants de clôture du modèle de données

1. Toute table personnelle est rattachée directement ou transitivement à un
   `profile_id` ou `account_id` vérifiable par RLS.
2. Toute réponse finale, rencontre, review et observation est append-only.
3. Toute projection est reconstructible depuis des faits conservés et des
   politiques versionnées.
4. Toute exécution épingle les révisions ayant influencé contenu, aide,
   correction et verdict.
5. `NULL` ne remplace jamais un état métier disponible dans le document 25.
6. Une suppression privée ne cascade jamais vers le catalogue partagé.
7. Une relation ou traduction n'est jamais déduite d'une égalité de chaînes.
8. Une liste et une session historique référencent des sens et snapshots
   immuables.
9. Une dette n'est résolue que par une preuve admissible.
10. Un prompt mémoire et une projection de maîtrise restent deux mécanismes
    indépendants.
11. Une panne, ambiguïté ou absence de média ne produit ni réussite ni échec
    utilisateur implicite.
12. Une commande à effet est idempotente et une mutation concurrente contrôle
    la version attendue.
13. Toute opération destructive est auditée, bornée et rejouable après
    restauration via tombstone.
14. Les schémas OpenAPI, événements, outils et imports dérivés de ce dictionnaire
    utilisent les mêmes noms et enums ; aucun alias divergent n'est accepté sans
    période de compatibilité documentée.
15. Toute entité ajoutée ultérieurement déclare son owner, sa racine d'agrégat,
    sa classe de données, sa politique de rétention, ses contraintes d'unicité
    et sa nature fait/révision/état/projection avant implémentation.
