# Polyglot V2 - Registre des incréments d'implémentation

## 1. Contrat d'exécution

Ce registre décompose W00-W19 sans modifier leurs write sets, dépendances ou
gates du document 27. Chaque ligne est un incrément reviewable : le test nommé
est créé d'abord et échoue pour le motif indiqué, puis le minimum de production
le fait passer. Une ligne ne mélange pas migration, domaine et transport. Les
artefacts générés suivent le bot d'intégration W00/W01/W17 du document 27.

Conventions : `B` = backend ; les commandes sont lancées depuis `backend` avec
`uv run pytest`; `F` = frontend avec `pnpm --dir frontend`; `C` = contrats avec
le validateur standard-library W00. « Pass » signifie code de sortie 0 et oracle
exact, pas seulement absence d'exception. Toute ligne cite dans sa PR les
`CapabilityId` résolus via le document 23 et les `REQ-*` indiquées par Wxx.

## 2. Incréments W00-W04

| ID | RED ciblé | GREEN borné | Résultat attendu |
|---|---|---|---|
| `W00-T01` | `C scripts/validate_contract_registry.py contracts/registry contracts/tests` rejette registre absent | ajouter enums, erreurs, commandes et queries du document 25 | zéro nom/route dupliqué, enums `lower_snake_case` |
| `W00-T02` | même commande rejette enveloppe événement sans version | ajouter enveloppe et catalogue d'événements | chaque commande a événement ou absence justifiée |
| `W00-T03` | même commande rejette outil sans limite/exemple | encoder les onze contrats du document 30 | entrée/sortie/erreurs/limites et fixtures présentes |
| `W00-T04` | contrôle de traçabilité trouve une famille incomplète | encoder manifestes de fixtures et mapping doc 23 | chaque famille a owner, lot, fixture, preuve, approbateur |
| `W00-T05` | revue ADR signale une décision implicite | écrire ADR 0001-0008 depuis docs 06/15/17 | approbations enregistrées, W01 autorisé |
| `W01-T01` | `B tests/unit/platform/test_primitives.py -q` échoue | horloge, UUIDv7, empreinte, Problem Details purs | valeurs reproductibles et erreurs typées |
| `W01-T02` | `B tests/integration/platform/test_migration_0001.py -q` échoue sur table absente | migration plateforme complète du document 27 | upgrade base vide, contraintes et indexes présents |
| `W01-T03` | `B tests/integration/platform/test_idempotency_outbox.py -q` double l'effet | transaction, receipt, event et outbox atomiques | rejeu x100 = un effet/un événement |
| `W01-T04` | `B tests/contract/platform/test_http_shell.py -q` retourne format divergent | bootstrap FastAPI, auth dependency vide, erreurs RFC 9457 | health et erreur corrélée conformes |
| `W01-T05` | export OpenAPI temporaire diffère du registre | générateur/check bot et CI socle | diff nul, Q0-Q3 exécutables |
| `W02-T01` | `B tests/unit/identity/test_account_session.py -q` transitions invalides acceptées | agrégats compte, identité, rôle, session, consentement | transitions du doc 09 exactes |
| `W02-T02` | `B tests/integration/identity/test_migration_0002.py -q` échoue | migration identity, Argon2id, sessions opaques, RLS | isolation des deux comptes FX-USERS |
| `W02-T03` | `B tests/contract/identity/test_commands.py -q` routes absentes | handlers/routes identité du registre 25 | positif, erreur, authz et idempotence par commande |
| `W02-T04` | `B tests/contract/identity/test_csrf_cookies.py -q` accepte requête hostile | cookie, CSRF, rotation/révocation | cas FX-AUTH tous conformes |
| `W03-T01` | `B tests/unit/language_profiles/test_diagnostic_v0.py -q` diverge des golden cases | politique pure de diagnostic/arrêt | P-ABS/P-FAUX/P-INT déterministes |
| `W03-T02` | `B tests/unit/language_profiles/test_foundation_gate.py -q` crédite dispense/audio absent | runs F1-F5 et gate différée | aucune maîtrise implicite |
| `W03-T03` | `B tests/integration/language_profiles/test_migration_0004.py -q` échoue | migration profils/diagnostics/fondations | unicité compte-variété et reprise 24 h |
| `W03-T04` | `B tests/contract/language_profiles/test_commands.py -q` routes absentes | commandes, queries, RLS et erreurs | parcours onboarding hors réseau complet |
| `W04-T01` | `B tests/unit/catalogue/test_revisions_dag.py -q` accepte cycle/mutation | valeurs, révisions et DAG catalogue | cycle rejeté, publié immuable |
| `W04-T02` | `B tests/integration/catalogue/test_migration_0003.py -q` échoue | migration packs, compétences, grammaire, lexique partagé | toutes références pilote résolues |
| `W04-T03` | `B tests/contract/catalogue/test_queries.py -q` lectures absentes | routes packs/cibles/recherche | pagination stable et bornée |
| `W04-T04` | `B tests/contract/catalogue/test_it_pack_validation.py -q` accepte fixtures négatives | validateurs et FX-CATALOGUE-IT | manifeste pilote valide hors réseau |

## 3. Incréments W05-W09

| ID | RED ciblé | GREEN borné | Résultat attendu |
|---|---|---|---|
| `W05-T01` | `B tests/unit/content/test_lifecycle.py -q` accepte transition interdite | agrégats/revisions et machine éditoriale | cycle exact, auto-approbation refusée |
| `W05-T02` | `B tests/integration/content/test_migration_0005.py -q` échoue | migration contenu/validation/approbation/provenance | ancienne révision reste lisible |
| `W05-T03` | `B tests/integration/content/test_atomic_publish.py -q` publie sans event | handlers publication et outbox atomique | contenu+event dans une transaction |
| `W05-T04` | `B tests/contract/content/test_authoring_reads.py -q` routes absentes | commands/lectures auteur du doc 25 | FX-CONTENT couvre tous statuts |
| `W06-T01` | `B tests/unit/lexicon_core/test_identity_resolution.py -q` fusionne homonymes | sens, formes, mentions, résolutions, relations | piano/MWE/syncrétisme restent distincts |
| `W06-T02` | `B tests/integration/lexicon_core/test_migration_0006.py -q` échoue | rencontres, annotations, préférences et RLS | faits append-only, aucun objet progress |
| `W06-T03` | `B tests/property/lexicon_core/test_ingestion_idempotency.py -q` duplique | ingestion/capture lacune et déduplication | même clé = une rencontre/mention |
| `W06-T04` | `B tests/contract/lexicon_core/test_word_bank.py -q` fuite un contexte | queries WB, voisinage, pagination, suppression privée | 0/10/100k et cross-user conformes |
| `W07-T01` | `B tests/unit/memory/test_fsrs_adapter.py -q` diverge oracle | port FSRS et conversion des notes | parité fixture `SPK-FSRS` acceptée |
| `W07-T02` | `B tests/unit/memory/test_prompt_lifecycle.py -q` perd l'historique | create/suspend/resume/reset/archive/restore/merge/delete | statut produit séparé de memory_state |
| `W07-T03` | `B tests/integration/memory/test_migration_0007.py -q` échoue | prompts, reviews, reset, schedule projection | reviews append-only et rebuild identique |
| `W07-T04` | `B tests/property/memory/test_replay.py -q` varie à ordre égal | scheduler horloge/version épinglées | replay x100 même état/due |
| `W08-T01` | `B tests/unit/exchange/test_conflicts.py -q` choisit implicitement | aperçu, classifications et stratégies | conflit interactif exige décision |
| `W08-T02` | `B tests/integration/exchange/test_migration_0008.py -q` échoue | listes/snapshots/import/export/manifeste | commit/revert auditables |
| `W08-T03` | `B tests/contract/exchange/test_import_pipeline.py -q` accepte archive hostile | quarantaine, parse borné, resolve/commit | FX-IMPORTS sans traversal/zip bomb |
| `W08-T04` | `B tests/integration/exchange/test_revert.py -q` supprime ressource réutilisée | compensation depuis manifeste | seules créations exclusives sont annulées |
| `W09-T01` | `B tests/unit/exercises_core/test_contracts.py -q` accepte payload libre | définition/instance/réponse union fermée | chaque primitive core valide son schéma |
| `W09-T02` | `B tests/unit/exercises_core/test_corrections.py -q` crédite ambiguïté/aide | stratégies, aides H0-H4 et observations | panne/ambiguïté = aucune réussite |
| `W09-T03` | `B tests/integration/exercises_core/test_migration_0009.py -q` échoue | définitions, instances, attempts, corrections/cases | réponse brute immuable, révisions conservées |
| `W09-T04` | `B tests/contract/exercises_core/test_commands.py -q` double soumission | handlers/routes/idempotence/concurrence | double submit même résultat |
| `W09-T05` | certification FX-PRIMITIVES échoue sur a11y/panne | fixtures par primitive et chemin local de correction | toutes primitives `core` certifiées |

## 4. Incréments W10-W14

| ID | RED ciblé | GREEN borné | Résultat attendu |
|---|---|---|---|
| `W10-T01` | `B tests/unit/gym/test_operations.py -q` accepte calque/prérequis absent | GYM-01..15, préconditions/invariants | transformations pures conformes |
| `W10-T02` | `B tests/property/gym/test_seed.py -q` varie avec même graine | sélection déterministe des étapes | même entrée = même chaîne |
| `W10-T03` | `B tests/integration/gym/test_migration_0010.py -q` échoue | `gym_plan`, `gym_step`, ordre/revisions | reprise et audit possibles |
| `W10-T04` | `B tests/contract/gym/test_g0_g4.py -q` crédite support lexical | correction et cycle G0-G4 | J+1/transfert sans faux crédit |
| `W11-T01` | `B tests/unit/curriculum/test_module_contract.py -q` accepte DAG/charge invalides | module/revision/day/enrollment purs | 3-30 jours et sorties mesurables |
| `W11-T02` | `B tests/integration/curriculum/test_migration_0011.py -q` échoue | migration et unicité enrôlement actif | révisions épinglées |
| `W11-T03` | validateur pilote rejette manifeste incomplet | encoder J1-J3, listes et dialogues doc 13 | FX-MODULE-IT charge hors réseau |
| `W11-T04` | `B tests/integration/curriculum/test_partial_regeneration.py -q` mute le passé | nouvelle révision + mapping objectifs | journées exécutées inchangées |
| `W12-T01` | `B tests/property/sprints/test_budget_composer.py -q` dépasse budget | contraintes dures et optimisation doc 11 | tous budgets 10..60, marge respectée |
| `W12-T02` | `B tests/property/sprints/test_snapshot_seed.py -q` varie | snapshot/cutoff/graine et équilibre modal | plan identique et raison par bloc |
| `W12-T03` | `B tests/integration/sprints/test_migration_0012.py -q` échoue | plans/blocs/liaison instances/runs | aucun FK aval et un run actif |
| `W12-T04` | `B tests/contract/sprints/test_resume_j1.py -q` perd J+1 | recodage différé, interruption/reprise | source figée, jour manqué sans duplication |
| `W12-T05` | `B tests/contract/sprints/test_free_practice.py -q` contourne prérequis | contexte/défi/mode libre bornés | n'altère ni module ni journée |
| `W13-T01` | `B tests/unit/progress/test_mastery_v0.py -q` diverge golden | observation vers evidence/projection | valeurs doc 10 exactes |
| `W13-T02` | `B tests/property/progress/test_replay_properties.py -q` dépend ordre/doublon | consommateurs inbox et remplacement | reconstruction même empreinte |
| `W13-T03` | `B tests/integration/progress/test_migration_0013.py -q` échoue | evidence, facettes, dettes, projections | ownership progress unique |
| `W13-T04` | `B tests/contract/progress/test_http.py -q` moyenne axes | projection modale et explication | vecteur 4D, inconnus non moyennés |
| `W14-T01` | `B tests/unit/assessments/test_form_selection.py -q` ressert forme | sélection 60/20/20, quotas, graine | forme compatible non exposée |
| `W14-T02` | `B tests/unit/assessments/test_scores.py -q` diverge grilles | score/couverture/confiance/bandes | quatre protocoles exacts |
| `W14-T03` | `B tests/integration/assessments/test_migration_0014.py -q` échoue | runs/sections/réponses/résultats | timer serveur et snapshot figés |
| `W14-T04` | `B tests/contract/assessments/test_resume_review.py -q` double/perd réponse | pause/reprise/submit/revue humaine | expiration et idempotence exactes |

## 5. Incréments W15-W19

| ID | RED ciblé | GREEN borné | Résultat attendu |
|---|---|---|---|
| `W15-T01` | `B tests/unit/media/test_state_machine.py -q` saute vérification | upload/quarantaine/process/ready/delete | transitions internes du doc 25 |
| `W15-T02` | `B tests/integration/media/test_migration_0015.py -q` échoue | assets/revisions/variants/segments/rights | aucun bucket ou objet public |
| `W15-T03` | `B tests/contract/media/test_hostile_upload.py -q` accepte MIME/checksum faux | scan, limites, stockage objet local | FX-MEDIA hostile rejeté |
| `W15-T04` | `B tests/contract/media/test_tts_degradation.py -q` choisit autre voix | catalogue et faux ports explicites | disparition voix visible, zéro fallback |
| `W16-T01` | `B tests/unit/generation/test_jobs_tools.py -q` permet publication | spécialisations job et façade doc 30 | aucun outil ne publie/attribue maîtrise |
| `W16-T02` | `B tests/integration/generation/test_migration_0016.py -q` recrée Job | migration spécialisations/outils/prompts | références W01, aucune table dupliquée |
| `W16-T03` | `B tests/contract/generation/test_tool_schemas.py -q` accepte sortie hostile | onze handlers + validation entrée/sortie | succès/erreur/permission/limite par outil |
| `W16-T04` | `B tests/contract/generation/test_offline_runner.py -q` varie transcript | runner horloge/graine figées | JSONL et drafts identiques hors réseau |
| `W17-T01` | `F test --run src/shell` échoue sur navigation | shell, routing, providers, mocks générés | routes structurantes accessibles |
| `W17-T02` | `F test --run src/features/exercise-player` échoue par primitive | lecteur universel et état réponse | pas de logique de score frontend |
| `W17-T03` | `F exec playwright test learner-flows` échoue | onboarding, sprint, WB, progression, évaluations | parcours P-ABS/P-RETOUR desktop/mobile |
| `W17-T04` | axe/zoom/visual snapshots échouent | clavier, focus, responsive et états limites | G4 sans défaut bloquant après revue humaine |
| `W18-T01` | `F test --run src/authoring` autorise auto-approbation | atelier catalogue/contenu/module/outils | rôles auteur/reviewer séparés |
| `W18-T02` | `F exec playwright test authoring-lifecycle` échoue | draft/validate/diff/approve/publish/retire | historique et erreurs visibles |
| `W18-T03` | runner outils produit draft introuvable dans Atelier | intégrer jobs/transcript/preview | sortie IA reste brouillon révisable |
| `W18-T04` | authz E2E croisé permet lecture interdite | scopes, réauth et audit UI/API | aucune fuite inter-owner |
| `W19-T01` | validation IaC/CI échoue sur environnement vide | local/test/preview/staging/prod, IAM, secrets, images | déploiement par digest reproductible |
| `W19-T02` | panne synthétique sans alerte/runbook | métriques, logs, alertes et kill switches | chaque alerte possède owner/action |
| `W19-T03` | charge FX-WB/SPRINTS dépasse NFR | indexes/cache borné/quotas après profil | rapport p95 et plans d'action |
| `W19-T04` | restore rehearsal ressuscite tombstone | backup/PITR/restore/purge replay | RPO/RTO mesurés, zéro résurrection |
| `W19-T05` | migration N-1/base vide diverge | expand/migrate/switch/contract | upgrade et rollback applicatif prouvés |
| `W19-T06` | E2E référence échoue réseau coupé | assembler release evidence G0-G6 | dossier `PARTIAL` si preuve humaine manque |
| `W19-T07` | canary sans rollback est refusé | canary après approbation explicite | G7 seulement avec SLO et rollback signés |

## 6. Règle de clôture

Un incrément passe de `planned` à `implemented` après GREEN local, à `verified`
après preuves requises du document 23, et à `accepted` après approbateur. Les
cases de ce fichier restent volontairement sans statut : l'outil de suivi V2 les
instanciera avec commit, owner et preuve. Cocher une ligne dans un document
d'architecture ne constituerait pas une preuve d'implémentation.
