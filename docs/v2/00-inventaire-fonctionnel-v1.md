# Polyglot V1 - Inventaire fonctionnel factuel

## 1. Objet et périmètre

Ce document inventorie la V1 telle qu'elle existe au commit courant. Il décrit
ce qui est présent, relié et observable ; il ne prescrit pas l'architecture de
la V2 et ne déduit pas une qualité pédagogique d'une simple présence dans le
code.

Baseline auditée :

| Élément | Valeur |
|---|---|
| Commit | `1eaaf086b6c88e77281625837c043aa4c5abe165` |
| Commit court | `1eaaf08` |
| Date | `2026-06-09T11:30:39+02:00` |
| Message | `fix: harden auth and learning flows` |
| Application | Flask 3, Flask-SQLAlchemy 3, Flask-Login 0.6 |
| Stockage par défaut | SQLite, `sqlite:///anki.db` |
| Frontend | Jinja, CSS et JavaScript sans framework frontend |
| Règles HTTP applicatives | 119 hors route statique Flask |
| Blueprints | 14 |
| Templates HTML | 55 |
| Classes SQLAlchemy | 18, soit `User` plus 17 modèles fonctionnels |

### 1.1 Niveaux de preuve

- **HEAD** : fichier suivi par Git et identique au commit ci-dessus. Les routes,
  modèles, templates, moteurs et tests appartiennent à ce niveau.
- **Local ignoré** : présent dans le dossier de travail mais exclu par
  `.gitignore`. Cela concerne `pillar_content/`, `card_sets/`, `scripts/`,
  `instance/` et `docker/`. Ces éléments expliquent la V1 locale, mais ne sont
  pas reproductibles depuis le commit seul.
- **Capture locale** : image dans `docs/v2/assets/v1/`, dossier non suivi au
  moment de l'audit. Une capture prouve un rendu ponctuel, pas le parcours qui
  l'a produit.

### 1.2 Définition des statuts

- **Actif** : une route utilisateur normale lit ou écrit le modèle ou rend le
  template ; le comportement n'est pas seulement un script de maintenance.
- **Partiel** : le chemin existe, mais dépend d'un service externe, d'un corpus
  incomplet, d'une donnée facultative ou ne couvre pas le cycle complet.
- **Dormant** : présent dans le code ou le disque, mais sans chemin utilisateur
  normal depuis les routes actuelles.
- **Mort** : template sans rendu direct ni inclusion depuis un template rendu.

## 2. Synthèse des surfaces fonctionnelles

| Surface V1 | Capacités observées | Fichiers principaux | Modèles | Statut |
|---|---|---|---|---|
| Identité | Inscription, connexion persistante, déconnexion, changement d'identifiant et de mot de passe | `app/routes/auth.py`, `app/templates/auth/*` | `User` | Actif |
| Profil apprenant | Langue maternelle, langues connues, niveau déclaré, années, style, correction, objectifs, temps quotidien, accent TTS, couleur d'avatar, autosauvegarde JSON | `app/routes/auth.py`, `auth/profile_settings.html` | `User.learner_profile` | Actif |
| Dashboard | Résumé des langues, cartes nouvelles/dues/en cours/maîtrisées, programmes actifs, paquets et activité récente | `app/routes/main.py`, `dashboard.html` | `Deck`, `Card`, `Review`, `TrainingProgram`, `UserLanguage` | Actif |
| Paquets | Liste, création, consultation, édition, suppression, réinitialisation, import d'un paquet public | `app/routes/decks.py`, `app/templates/decks/*` | `Deck`, `Card`, `Review` | Actif |
| Cartes | Création unitaire, édition, suppression, création en masse, import JSON par fichier ou texte, détection de doublons, catégories automatiques, mise à jour d'existants | `app/routes/cards.py`, `app/templates/cards/*`, `app/utils.py` | `Card`, `Category`, `Deck` | Actif |
| Catégories | Liste par paquet, création, renommage, couleur, suppression et statistiques ; association plusieurs-à-plusieurs aux cartes | `app/routes/categories.py`, `app/templates/categories/*` | `Category`, `Card`, `card_categories` | Actif |
| Révision autonome | Deux directions, retournement ou réponse écrite, filtres de catégories OR/AND et obligatoires, filtre de note, nouvelles cartes, limite, mélange, navigation arrière/avant, reprise, redémarrage, arrêt et bilan | `app/routes/training.py`, `app/templates/training/*` | `TrainingSession`, `Card`, `Review` | Actif |
| Planification mémoire | Persistance FSRS par direction, champs historiques SM-2, note A-F, retrievability, échéance, boost croisé des directions | `app/fsrs.py`, `app/sm2.py`, `app/models.py`, `app/grades.py` | `Card`, `Review` | Actif, hybride |
| Statistiques | Totaux globaux, activité hebdomadaire, états des cartes, historique et vues par paquet/catégorie | `app/routes/stats.py`, `app/templates/stats/*` | `Deck`, `Card`, `Category`, `Review` | Actif |
| Catalogue de langues | Sélecteur de sept langues et graphe de piliers par niveau A0-C2 | `app/pillar_config.py`, `app/routes/pillars.py`, `app/templates/pillars/*` | `UserLanguage` | Partiel : corpus inégal |
| Onboarding langue | Choix d'un niveau déclaré, création de la langue utilisateur, auto-validation des niveaux antérieurs et initialisation des statuts | `app/routes/pillars.py`, `pillars/onboarding.html` | `UserLanguage` | Actif, sans diagnostic réel |
| Pilier/cours | Carte du parcours, prérequis visuels, détail, leçon, exemples, erreurs, astuces, création d'un paquet de cartes, démarrage, progression, complétion et suppression d'une langue | `app/routes/pillars.py`, `pillar_content/*` | `UserLanguage`, `Deck`, `Card`, `PillarExercise` | Partiel : contenu local non versionné |
| Exercices libres | Conjugaison, phrase à trous, transformation, ordre des mots, particules et genre ; difficulté 1-5, génération, correction, exercice suivant, historique, profil de faiblesse, conseil de saut et readiness | `app/routes/pillar_exercises.py`, `app/exercise_generator.py`, `app/exercise_config.py` | `PillarExercise`, `PillarExerciseResult`, `UserLanguage` | Actif pour les types autorisés par langue |
| Professeur de pilier | Chat contextuel avec contenu du pilier et profil utilisateur | `app/routes/pillar_chat.py`, `app/llm_service.py`, `base.html` | `User`, `UserLanguage` | Partiel : LLM externe obligatoire |
| Évaluations CECR | Hub, dashboard, création, reprise, minuterie, sections grammaire/vocabulaire/lecture/écoute/écriture/dialogue, soumission, correction, résultat et validation automatique de piliers | `app/routes/assessments.py`, `app/assessment_generator.py`, `app/cecr_config.py`, `app/templates/assessments/*` | `Assessment`, `AssessmentSection`, `UserLanguage` | Partiel : génération/correction LLM et pas d'oral parlé |
| Programmes | Assistant en cinq étapes, paire de langues, profil, thèmes, ordre et activation des exercices, durée, mutations FSI, ressources de shadowing, création, édition, activation et suppression | `app/routes/programs.py`, `app/templates/programs/*` | `TrainingProgram`, `Deck`, `WeeklyTheme`, `LegoStructure`, `ShadowingVideo` | Actif, génération externe partielle |
| Sprint quotidien | Reprise d'une session du jour, thème hebdomadaire/journalier, vocabulaire et dette, six modules ordonnables, passage au module suivant, arrêt et bilan | `app/routes/session.py`, `app/templates/session/*` | `ProgramSession` et modèles associés | Actif |
| Module vocabulaire | Sélection de cartes dues/nouvelles et de dettes, génération de mots, création de vraies cartes, réemploi du lecteur de révision | `app/routes/session.py`, `app/routes/training.py` | `Card`, `TrainingSession`, `DebtWord`, `ProgramSession` | Actif |
| Git Input | Génération d'un texte cible, traduction cible vers langue maternelle, correction itérative, détection de mots inconnus, sauvegarde pour J+1 | `app/routes/session.py`, `session/git_input.html` | `DailyText`, `DebtWord`, `ProgramSession` | Partiel : LLM pour génération/correction |
| Gym | Découverte d'une structure, construction Lego, mutations FSI, traduction ciblée, rotation espacée des structures, révélation de vocabulaire | `app/routes/session.py`, `app/gym_engine.py`, `app/lego_generator.py`, `session/gym.html` | `LegoStructure`, `ProgramSession`, `DebtWord`, `Card` | Actif, qualité dépendante des données |
| Shadowing | Vidéo/segment, incrément d'usage, génération de texte et TTS de secours, passage ou complétion | `app/routes/session.py`, `session/shadowing.html`, `app/tts_service.py` | `ShadowingVideo`, `DailyText`, `ProgramSession` | Partiel : aucune vidéo dans la base locale et TTS externe |
| Git Output J+1 | Récupération d'un texte antérieur, reconstruction maternelle vers cible, comparaison triple, saut si aucune source | `app/routes/session.py`, `session/git_output.html` | `DailyText`, `ProgramSession` | Actif |
| Smart Writing | Mission thématique, mots imposés, production, correction et feedback | `app/routes/session.py`, `session/writing.html` | `ProgramSession`, `DebtWord` | Partiel : LLM pour mission/correction |
| Word Bank et SOS | Barre latérale, consultation du vocabulaire du jour, révélation, ajout contextuel, quota de jetons, création d'une dette et ajout au paquet | `app/routes/session.py`, `components/_vocab_sidebar.html` | `DebtWord`, `Card`, `ProgramSession` | Actif |
| TTS | Santé, langues, voix et génération WAV via Qwen3-TTS | `app/routes/tts.py`, `app/tts_service.py` | Préférences dans `User.learner_profile` | Partiel : service HTTP séparé |
| Génération LLM | LM Studio, puis vLLM, puis Ollama ; génération de cours, thèmes, vocabulaire, structures, exercices, évaluations et corrections | `app/llm_service.py`, générateurs spécialisés | Plusieurs | Partiel : services non inclus dans HEAD |
| Outils opérateur | Génération/post-traitement des cours, imports, migrations SQLite, enrichissement et débogage de données | `scripts/*` | Base locale et JSON | Dormant côté UI, local ignoré |

## 3. Registre exhaustif des 119 routes

Le décompte vient de `app.url_map` après création de l'application, en excluant
uniquement la route `static`. Une règle acceptant plusieurs méthodes compte pour
une route.

### `app/routes/main.py` - 1 route

| Méthode(s) | Route | Handler |
|---|---|---|
| `GET` | `/` | `index` |

### `app/routes/auth.py` - 7 routes

| Méthode(s) | Route | Handler |
|---|---|---|
| `POST` | `/api/profile/password` | `api_change_password` |
| `POST` | `/api/profile/save` | `api_profile_save` |
| `POST` | `/api/profile/username` | `api_change_username` |
| `GET,POST` | `/login` | `login` |
| `GET` | `/logout` | `logout` |
| `GET,POST` | `/profile/settings` | `profile_settings` |
| `GET,POST` | `/register` | `register` |

### `app/routes/decks.py` - 7 routes

| Méthode(s) | Route | Handler |
|---|---|---|
| `GET` | `/decks/` | `list_decks` |
| `GET` | `/decks/<int:deck_id>` | `view_deck` |
| `POST` | `/decks/<int:deck_id>/delete` | `delete_deck` |
| `GET,POST` | `/decks/<int:deck_id>/edit` | `edit_deck` |
| `GET,POST` | `/decks/<int:deck_id>/reset` | `reset_deck` |
| `GET,POST` | `/decks/import-public` | `import_public_deck` |
| `GET,POST` | `/decks/new` | `new_deck` |

### `app/routes/cards.py` - 5 routes

| Méthode(s) | Route | Handler |
|---|---|---|
| `POST` | `/cards/<int:card_id>/delete` | `delete_card` |
| `GET,POST` | `/cards/<int:card_id>/edit` | `edit_card` |
| `GET,POST` | `/cards/bulk-create/<int:deck_id>` | `bulk_create` |
| `GET,POST` | `/cards/deck/<int:deck_id>/new` | `new_card` |
| `GET,POST` | `/cards/json-import/<int:deck_id>` | `json_import` |

### `app/routes/categories.py` - 5 routes

| Méthode(s) | Route | Handler |
|---|---|---|
| `POST` | `/categories/<int:category_id>/delete` | `delete_category` |
| `GET,POST` | `/categories/<int:category_id>/edit` | `edit_category` |
| `GET` | `/categories/<int:category_id>/stats` | `category_stats` |
| `GET` | `/categories/deck/<int:deck_id>` | `list_categories` |
| `GET,POST` | `/categories/deck/<int:deck_id>/new` | `new_category` |

### `app/routes/training.py` - 11 routes

| Méthode(s) | Route | Handler |
|---|---|---|
| `GET` | `/train/back` | `go_back` |
| `GET` | `/train/card` | `show_card` |
| `POST` | `/train/check-answer` | `check_answer` |
| `GET` | `/train/complete` | `session_complete` |
| `GET` | `/train/deck/<int:deck_id>` | `start_training` |
| `GET` | `/train/deck/<int:deck_id>/count` | `count_cards` |
| `POST` | `/train/deck/<int:deck_id>/session` | `create_session` |
| `GET` | `/train/forward` | `go_forward` |
| `GET` | `/train/restart` | `restart_session` |
| `POST` | `/train/review` | `submit_review` |
| `POST` | `/train/stop` | `stop_training` |

### `app/routes/stats.py` - 2 routes

| Méthode(s) | Route | Handler |
|---|---|---|
| `GET` | `/stats/` | `global_stats` |
| `GET` | `/stats/deck/<int:deck_id>` | `deck_stats` |

### `app/routes/programs.py` - 9 routes

| Méthode(s) | Route | Handler |
|---|---|---|
| `GET` | `/programs/` | `list_programs` |
| `GET` | `/programs/<int:program_id>` | `view_program` |
| `POST` | `/programs/<int:program_id>/delete` | `delete_program` |
| `GET` | `/programs/<int:program_id>/edit` | `edit_program` |
| `POST` | `/programs/<int:program_id>/toggle` | `toggle_program` |
| `POST` | `/programs/api/generate-templates` | `api_generate_templates` |
| `POST` | `/programs/api/generate-themes` | `api_generate_themes` |
| `GET` | `/programs/new` | `new_program` |
| `GET,POST` | `/programs/new/step/<int:step>` | `wizard_step` |

### `app/routes/session.py` - 34 routes

| Méthode(s) | Route | Handler |
|---|---|---|
| `POST` | `/session/chat_helper` | `chat_helper` |
| `GET` | `/session/complete` | `complete` |
| `GET` | `/session/flashcards` | `module_flashcards` |
| `POST` | `/session/flashcards/complete` | `flashcards_complete` |
| `POST` | `/session/flashcards/generate-words` | `generate_daily_words` |
| `GET` | `/session/flashcards/sidebar-data` | `get_sidebar_data` |
| `GET` | `/session/git-input` | `module_git_input` |
| `POST` | `/session/git-input/generate` | `generate_git_input_text` |
| `POST` | `/session/git-input/submit` | `submit_git_input` |
| `GET` | `/session/git-output` | `module_git_output` |
| `POST` | `/session/git-output/skip` | `skip_git_output` |
| `POST` | `/session/git-output/submit` | `submit_git_output` |
| `GET` | `/session/gym` | `module_gym` |
| `POST` | `/session/gym/check` | `check_gym_answer` |
| `POST` | `/session/gym/complete` | `gym_complete` |
| `POST` | `/session/gym/generate-translations` | `generate_gym_translations` |
| `POST` | `/session/gym/get-exercise` | `get_gym_exercise` |
| `POST` | `/session/gym/reveal-vocab` | `reveal_vocab_word` |
| `GET` | `/session/module` | `current_module` |
| `GET` | `/session/next` | `next_module` |
| `GET` | `/session/shadowing` | `module_shadowing` |
| `POST` | `/session/shadowing/complete` | `shadowing_complete` |
| `POST` | `/session/shadowing/generate-text` | `generate_shadowing_text` |
| `POST` | `/session/shadowing/get-next-video` | `get_next_shadowing_video` |
| `GET` | `/session/sidebar-data` | `get_sidebar_data` |
| `POST` | `/session/sos` | `use_sos` |
| `GET` | `/session/start/<int:program_id>` | `start_session` |
| `POST` | `/session/stop` | `stop_session` |
| `POST` | `/session/vocab/add` | `add_vocab_word` |
| `GET` | `/session/wordbank` | `get_wordbank` |
| `POST` | `/session/wordbank/reveal` | `reveal_word` |
| `GET` | `/session/writing` | `module_writing` |
| `POST` | `/session/writing/generate-quest` | `generate_writing_quest` |
| `POST` | `/session/writing/submit` | `submit_writing` |

### `app/routes/pillars.py` - 14 routes

| Méthode(s) | Route | Handler |
|---|---|---|
| `GET` | `/pillars/` | `index` |
| `GET` | `/pillars/<lang>` | `language_view` |
| `GET` | `/pillars/<lang>/<pillar_id>` | `pillar_detail` |
| `GET` | `/pillars/<lang>/<pillar_id>/cards` | `api_cards` |
| `POST` | `/pillars/<lang>/<pillar_id>/complete` | `complete_pillar` |
| `GET` | `/pillars/<lang>/<pillar_id>/lesson` | `api_lesson` |
| `POST` | `/pillars/<lang>/<pillar_id>/progress` | `update_pillar_progress` |
| `POST` | `/pillars/<lang>/<pillar_id>/start` | `start_pillar` |
| `POST` | `/pillars/<lang>/delete` | `delete_language` |
| `GET` | `/pillars/<lang>/onboarding` | `onboarding` |
| `POST` | `/pillars/<lang>/start` | `start_language` |
| `GET` | `/pillars/api/<lang>/pillars` | `api_pillars` |
| `GET` | `/pillars/api/<lang>/progress` | `api_progress` |
| `GET` | `/pillars/api/languages` | `api_languages` |

### `app/routes/pillar_exercises.py` - 10 routes

| Méthode(s) | Route | Handler |
|---|---|---|
| `POST` | `/api/pillars/<lang>/exercises/check` | `api_check` |
| `POST` | `/api/pillars/<lang>/exercises/difficulty` | `api_difficulty` |
| `POST` | `/api/pillars/<lang>/exercises/generate` | `api_generate` |
| `GET` | `/api/pillars/<lang>/exercises/next` | `api_next` |
| `POST` | `/api/pillars/<lang>/exercises/skip-advice` | `api_skip_advice` |
| `GET` | `/api/pillars/<lang>/exercises/stats` | `api_stats` |
| `GET` | `/api/pillars/<lang>/exercises/weakness-profile` | `api_weakness_profile` |
| `GET` | `/api/pillars/<lang>/level-readiness` | `api_level_readiness` |
| `GET` | `/pillars/<lang>/exercises` | `exercises_list` |
| `GET` | `/pillars/<lang>/exercises/<exercise_type>` | `exercise_session` |

### `app/routes/pillar_chat.py` - 1 route

| Méthode(s) | Route | Handler |
|---|---|---|
| `POST` | `/pillars/<lang>/<pillar_id>/chat` | `pillar_chat` |

### `app/routes/assessments.py` - 9 routes

| Méthode(s) | Route | Handler |
|---|---|---|
| `GET` | `/api/pillars/<lang>/assessments/<int:assessment_id>` | `api_get_assessment` |
| `POST` | `/api/pillars/<lang>/assessments/<int:assessment_id>/complete` | `api_complete_assessment` |
| `POST` | `/api/pillars/<lang>/assessments/<int:assessment_id>/dialogue/<int:section_id>/chat` | `api_dialogue_chat` |
| `POST` | `/api/pillars/<lang>/assessments/<int:assessment_id>/section/<int:section_id>/submit` | `api_submit_section` |
| `POST` | `/api/pillars/<lang>/assessments/start` | `api_start_assessment` |
| `GET` | `/pillars/<lang>/assessments` | `assessment_hub` |
| `GET` | `/pillars/<lang>/assessments/<int:assessment_id>` | `assessment_exam` |
| `GET` | `/pillars/<lang>/assessments/<int:assessment_id>/results` | `assessment_results` |
| `GET` | `/pillars/<lang>/dashboard` | `cecr_dashboard` |

### `app/routes/tts.py` - 4 routes

| Méthode(s) | Route | Handler |
|---|---|---|
| `POST` | `/api/tts` | `api_generate_tts` |
| `GET` | `/api/tts/languages` | `api_tts_languages` |
| `GET` | `/api/tts/speakers` | `api_tts_speakers` |
| `GET` | `/api/tts/status` | `api_tts_status` |

Vérification arithmétique :
`1 + 7 + 7 + 5 + 5 + 11 + 2 + 9 + 34 + 14 + 10 + 1 + 9 + 4 = 119`.

## 4. Modèle de données

### 4.1 Écart de décompte

Le code ne contient pas 17 classes SQLAlchemy au total. Le registre SQLAlchemy
mappe **18 classes** et la metadata contient **19 tables**, la table
`card_categories` étant une table d'association sans classe. Le décompte de
17 est exact seulement si `User`, modèle d'identité transverse, est séparé des
17 modèles fonctionnels demandés ci-dessous.

### 4.2 Modèle d'identité transverse

| Modèle | Rôle | Usage normal | Statut |
|---|---|---|---|
| `User` | Identité, mot de passe, avatar, abonnement `is_pro`, profil apprenant JSON, relations vers paquets et langues | Authentification, profil, dashboard et contexte LLM | Actif ; `is_pro` n'a pas de politique fonctionnelle observée |

### 4.3 Les 17 modèles fonctionnels

| # | Modèle/table | Responsabilité et relations | Preuve de chemin actif | Statut |
|---:|---|---|---|---|
| 1 | `UserLanguage` / `user_language` | Langue cible d'un utilisateur, niveau estimé, progression des piliers et statistiques agrégées | Parcours, onboarding, exercices et évaluations | Actif |
| 2 | `PillarExercise` / `pillar_exercise` | Instance d'exercice générée ou pré-générée, type, pilier, difficulté et contenu JSON | Création au démarrage d'un pilier et API d'exercices | Actif |
| 3 | `PillarExerciseResult` / `pillar_exercise_result` | Tentative utilisateur, réponse, exactitude, temps et difficulté | Correction, historique, faiblesse et dashboard CECR | Actif |
| 4 | `Assessment` / `assessment` | Contrôle CECR, niveau cible, état, score, seuil, temps et feedback | Hub, reprise, complétion et résultats | Partiel : création et certaines corrections dépendent du LLM |
| 5 | `AssessmentSection` / `assessment_section` | Section typée, contenu, score, réponses, dates et feedback | Soumission section par section et dialogue | Partiel : même dépendance et aucune section d'oral parlé |
| 6 | `Deck` / `deck` | Paquet personnel ou dédié à un programme/pilier | CRUD, imports, révision, programme, pilier et stats | Actif |
| 7 | `Card` / `card` | Recto/verso, état mémoire bidirectionnel SM-2/FSRS, slot Lego et catégories | CRUD, import, révision, sprint, gym et stats | Actif, avec double modèle de planification |
| 8 | `Category` / `category` | Étiquette colorée d'un paquet, plusieurs-à-plusieurs avec cartes | CRUD, imports, filtres, Lego et stats | Actif |
| 9 | `Review` / `review` | Fait de révision, qualité, direction et date | Soumission d'une carte, dashboard et statistiques | Actif |
| 10 | `TrainingSession` / `training_session` | Snapshot JSON d'une session autonome de cartes | Création, reprise, navigation et arrêt | Actif |
| 11 | `TrainingProgram` / `training_program` | Configuration d'un programme, paire de langues, profil, ordre, thèmes, prompts, mutations, médias et jetons | Assistant de création, liste, détail, activation et sprint | Actif ; plusieurs champs sont des blobs JSON |
| 12 | `ProgramSession` / `program_session` | État quotidien, module courant, mots du jour, dette, gym, écriture et résultats JSON | Orchestrateur des six modules et reprise du jour | Actif |
| 13 | `DailyText` / `daily_text` | Texte cible, traduction, correction et reconstruction différée J+1 | Git Input, shadowing et Git Output | Actif |
| 14 | `LegoStructure` / `lego_structure` | Moule grammatical, exemples, difficulté, stabilité, échéance, tags et activation | Sélection/révision dans le moteur de gym | Actif |
| 15 | `ShadowingVideo` / `shadowing_video` | Ressource vidéo, segments, durée, usage et activation | Assistant de programme et module shadowing | Partiel : chemin actif, zéro ligne dans la base locale auditée |
| 16 | `DebtWord` / `debt_word` | Dette lexicale par utilisateur/programme, source, contexte et traitement | Démarrage du sprint, révélations, Word Bank et SOS | Actif |
| 17 | `WeeklyTheme` / `weekly_theme` | Thème d'une semaine, ventilation journalière, bases de génération et progression | Création de programme et contexte de sprint | Actif, génération LLM avec fallback local |

### 4.4 Contraintes et persistance observées

- La propriété est portée par `user_id` sur `Deck`, `UserLanguage`,
  `TrainingProgram`, `ProgramSession`, `DailyText`, `DebtWord`, `WeeklyTheme`,
  `PillarExerciseResult` et `Assessment`. Les aides de `app/authz.py` protègent
  explicitement paquets, cartes, catégories et sessions autonomes.
- La progression, le profil de faiblesse et la difficulté d'exercice sont
  regroupés dans `UserLanguage.pillar_progress`, un JSON modifié par plusieurs
  routes.
- Les configurations et résultats des programmes/sprints sont également des
  JSON mutables. Il n'existe pas de schéma versionné pour ces blobs.
- Aucune contrainte unique SQL n'est déclarée pour le couple utilisateur/langue,
  la semaine d'un programme ou l'unicité d'une dette. Les déduplications
  observées sont applicatives.
- Il n'existe pas d'outil de migration versionné dans les dépendances. Les
  migrations présentes sont des scripts locaux ignorés par Git.
- La base locale ignorée contient une table `generated_vocabulary` absente de
  la metadata SQLAlchemy courante : c'est une trace de schéma historique.

### 4.5 Instantané de la base locale, non reproductible depuis HEAD

Cet instantané n'est pas une source normative. Il sert seulement à distinguer
un modèle relié d'un modèle effectivement peuplé dans l'environnement audité.

| Table | Lignes locales |
|---|---:|
| `user` | 8 |
| `user_language` | 7 |
| `deck` | 18 |
| `card` | 2 731 |
| `category` | 189 |
| `card_categories` | 6 456 |
| `review` | 2 487 |
| `training_session` | 59 |
| `training_program` | 7 |
| `program_session` | 12 |
| `daily_text` | 6 |
| `lego_structure` | 32 |
| `shadowing_video` | 0 |
| `debt_word` | 7 |
| `weekly_theme` | 5 |
| `pillar_exercise` | 154 |
| `pillar_exercise_result` | 35 |
| `assessment` | 4 |
| `assessment_section` | 13 |
| `generated_vocabulary` | 0 |

## 5. Contenus et langues

### 5.1 Catalogue de piliers

`app/pillar_config.py`, suivi dans HEAD, annonce 195 piliers sur sept langues.
Les fichiers pédagogiques sont locaux et ignorés par Git.

| Code | Langue affichée | Piliers configurés | JSON locaux valides | Couverture | Cartes locales | Exercices locaux | TTS déclaré |
|---|---|---:|---:|---:|---:|---:|---|
| `it` | Italien | 44 | 44 | 100 % | 1 102 | 91 | Oui |
| `ja` | Japonais | 40 | 37 | 92,5 % | 884 | 61 | Oui |
| `tr` | Turc | 38 | 38 | 100 % | 828 | 64 | Non |
| `zh` | Chinois Mandarin | 19 | 0 | 0 % | 0 | 0 | Oui |
| `ko` | Coréen | 19 | 0 | 0 % | 0 | 0 | Oui |
| `ru` | Russe | 18 | 0 | 0 % | 0 | 0 | Oui |
| `es` | Espagnol | 17 | 0 | 0 % | 0 | 0 | Oui |
| **Total** |  | **195** | **119** | **61,0 %** | **2 814** | **216** |  |

Les 119 JSON présents sont syntaxiquement valides et possèdent tous les clés
de premier niveau suivantes : `pillar_id`, `language`, `cefr`, `name`,
`native_name`, `category`, `lesson`, `cards`, `exercises`,
`curriculum_context`, `metadata`.

Fichiers japonais manquants par rapport à la configuration :

- `kanji_n2_ja.json` ;
- `kanji_n3_ja.json` ;
- `vocab_thematic_ja.json`.

Pour `zh`, `ko`, `ru` et `es`, les parcours sont affichables depuis la
configuration mais aucun fichier `pillar_content/<lang>/...` n'est présent.
Le démarrage d'un pilier sans contenu crée néanmoins un paquet vide, marque le
pilier `in_progress` et renvoie zéro carte/zéro exercice.

### 5.2 Jeux de cartes locaux

| Fichier local ignoré | Contenu observé |
|---|---:|
| `card_sets/deck_italien.json` | 1 986 cartes |
| `card_sets/deck_italien_enriched.json` | 1 986 cartes |
| `card_sets/deck_italien_mot_courant.json` | 27 cartes |
| `card_sets/deck_italien_vocab.json` | 130 cartes |
| `card_sets/hiragana.json` | 46 cartes |
| `card_sets/katakana.json` | 46 cartes |
| `card_sets/kanas_complet.json` | 92 cartes |
| `card_sets/card_creating_example.json` | 3 cartes |
| `card_sets/gym_structures.json` | 3 structures |
| `card_sets/gym_vocabulary.json` | 15 entrées |

Les deux paquets italiens de 1 986 cartes sont deux variantes locales de même
volume ; l'inventaire ne prouve ni leur équivalence sémantique ni leur niveau de
qualité.

### 5.3 Espaces de langues divergents

- Les piliers utilisent sept codes ISO courts : `it`, `ja`, `tr`, `zh`, `ko`,
  `ru`, `es`.
- Le créateur de programme utilise onze identifiants anglais : `french`,
  `italian`, `spanish`, `german`, `english`, `portuguese`, `japanese`,
  `chinese`, `korean`, `arabic`, `russian`.
- Le TTS attend dix codes courts : `zh`, `en`, `ja`, `ko`, `de`, `fr`, `ru`,
  `pt`, `es`, `it`. Le turc est explicitement non supporté et l'arabe n'est pas
  listé.
- `training.show_card` transmet directement
  `TrainingProgram.target_language` au TTS. Une valeur telle que `italian` ne
  correspond donc pas au contrat `it` du service TTS.

## 6. Templates actifs, partiels et morts

### 6.1 Décompte

| Catégorie | Nombre | Définition |
|---|---:|---|
| Rendus directement | 44 | Chaîne littérale passée à `render_template` |
| Dépendances indirectes | 3 | `base.html`, sidebar vocabulaire et progression du wizard |
| Actifs/rejoignables | 47 | Union des deux catégories précédentes |
| Morts | 8 | Aucun rendu et aucune inclusion depuis le graphe actif |
| Total | 55 | Tous les fichiers sous `app/templates/` |

### 6.2 Templates actifs par surface

- **Socle** : `base.html`, `dashboard.html`.
- **Auth** : `auth/login.html`, `auth/register.html`,
  `auth/profile_settings.html`.
- **Paquets/cartes/catégories** : cinq templates `decks/*`, trois `cards/*`,
  trois `categories/*`.
- **Révision/statistiques** : trois `training/*`, deux `stats/*`.
- **Piliers** : `pillars/index.html`, `language.html`, `onboarding.html`,
  `pillar_detail.html`, `exercises.html`, `exercise_session.html`.
- **Évaluations** : les quatre templates `assessments/*`.
- **Programmes** : `programs/list.html`, `programs/view.html`, les cinq étapes
  suffixées `_themes`, `_exercises`, `_resources`, `_finalize`, plus
  `wizard/_progress.html`.
- **Sprint** : `session/complete.html`, `flashcards_loading.html`,
  `git_input.html`, `gym.html`, `shadowing.html`, `git_output.html`,
  `writing.html`.
- **Composant transversal** : `components/_vocab_sidebar.html`.

### 6.3 Templates morts

| Template | Observation |
|---|---|
| `auth/profiles.html` | Ancien écran de profils, aucune route ni inclusion |
| `components/modal.html` | Exemple/composant isolé, non inclus par le graphe actif |
| `components/toast.html` | Exemple/composant isolé, non inclus par le graphe actif |
| `programs/edit.html` | L'édition réutilise le wizard, ce fichier n'est jamais rendu |
| `programs/wizard/step2.html` | Remplacé par `step2_themes.html` |
| `programs/wizard/step3.html` | Remplacé par `step3_exercises.html` |
| `programs/wizard/step4.html` | Remplacé par `step4_resources.html` |
| `session/flashcards.html` | Le module actif réutilise le lecteur `training/card.html` et rend seulement l'écran de chargement |

## 7. Moteurs et dépendances fonctionnelles

| Module | Rôle observé | Statut de preuve |
|---|---|---|
| `app/fsrs.py` | Calcul FSRS 4.5, stabilité, difficulté, retrievability, intervalle et notes | Suivi dans HEAD, utilisé par les révisions |
| `app/sm2.py` | Calcul des intervalles affichés sur les boutons et compatibilité historique | Suivi dans HEAD, encore actif dans l'UI |
| `app/gym_engine.py` | Sélection espacée des structures, génération des étapes Lego/FSI/traduction et mise à jour | Suivi dans HEAD, données locales requises |
| `app/lego_generator.py` | Remplissage des slots d'une structure avec les cartes/catégories | Suivi dans HEAD |
| `app/theme_generator.py` | Création et lecture d'un thème hebdomadaire et du contexte journalier | Suivi dans HEAD, génération LLM |
| `app/exercise_generator.py` | Génération et persistance d'exercices par langue/type/difficulté | Suivi dans HEAD, génération LLM ou corpus existant |
| `app/assessment_generator.py` | Création, correction et agrégation des évaluations | Suivi dans HEAD, génération/correction LLM |
| `app/llm_service.py` | Adaptateurs LM Studio, vLLM et Ollama | Suivi dans HEAD, serveurs externes |
| `app/tts_service.py` | Adaptateur Qwen3-TTS | Suivi dans HEAD, conteneur/serveur externe |
| `app/prompt_templates.py` | Prompts de thèmes, traduction, correction, gym et écriture | Suivi dans HEAD |
| `app/pillar_config.py` | Catalogue des sept langues et 195 piliers | Suivi dans HEAD |
| `app/exercise_config.py` | Six primitives et paramètres de langue | Suivi dans HEAD |
| `app/cecr_config.py` | Niveaux, seuils, sections et paramètres des examens | Suivi dans HEAD |

Le comportement LLM par défaut n'est pas un échec fermé : LM Studio bascule
automatiquement vers vLLM puis Ollama. Les appels ne possèdent pas d'identifiant
de génération, de version de prompt persistée, de journal fournisseur structuré
ni de garantie d'idempotence observée.

## 8. Tests et vérifications

### 8.1 Inventaire

| Fichier | Tests déclarés | Nature |
|---|---:|---|
| `tests/test_security_regressions.py` | 10 | `unittest`, assertions sur propriété, redirection, mot de passe, échappement et configuration |
| `tests/test_assessment_generation.py` | 1 | `unittest`, rollback si une section générée est vide |
| `tests/test_gym_engine.py` | 1 | Fonction pytest dépendante de la base locale ; impressions, pas d'assertion |
| `tests/test_lego_generation.py` | 1 | Fonction pytest dépendante de la base locale ; impressions, pas d'assertion |
| `scripts/test_lego.py` | 0 test collectable | Script manuel local, sortie console |

Total déclaré sous `tests/` : 13 fonctions/méthodes dont 11 réellement
collectables par `unittest` et 2 nécessitant pytest.

### 8.2 Exécution pendant l'audit

- `python -m unittest discover -s tests -v` avec le Python du venv : **11 tests
  exécutés, 11 réussis**.
- Avertissements observés : `datetime.utcnow()` déprécié, `Query.get()` legacy
  SQLAlchemy 2 et connexions SQLite non fermées signalées par `ResourceWarning`.
- `pytest` n'est installé ni dans le venv ni dans le Python système et n'est pas
  déclaré dans `requirements.txt`. Les deux fonctions pytest n'ont donc pas été
  exécutées.
- La création de l'application et l'introspection de `app.url_map` réussissent ;
  elles confirment 119 règles applicatives.

### 8.3 Couverture absente ou insuffisante

Il n'existe pas de preuve automatisée complète pour :

- le parcours navigateur d'un nouvel utilisateur jusqu'à un sprint achevé ;
- les 119 routes et leurs états 200/400/401/404/500 ;
- le wizard de programme, sa réédition et ses cinq étapes ;
- les six modules du sprint et leur reprise après interruption ;
- FSRS, l'échéance réelle et la cohérence avec les intervalles affichés ;
- les imports JSON complets et leurs variantes de conflit ;
- les sept langues, les fichiers manquants et la cohérence du contenu ;
- les appels réels LM Studio/vLLM/Ollama et Qwen3-TTS ;
- l'évaluation complète, son minuteur, sa reprise et toutes ses sections ;
- le responsive mobile et l'accessibilité.

## 9. Défauts et incohérences observés

Les éléments ci-dessous sont des constats du code, des données locales ou des
captures. Ils ne supposent pas que tous se produisent à chaque exécution.

### Critiques pour la reproductibilité

1. **La V1 fonctionnelle n'est pas reconstructible depuis HEAD.** Les 119
   fichiers de cours, les jeux de cartes, les scripts de génération/migration,
   Docker et la base sont ignorés par Git.
2. **Le catalogue promet plus de contenu qu'il n'en existe.** Quatre langues ont
   zéro fichier de cours ; le japonais en manque trois.
3. **Un pilier sans contenu peut être démarré.** La route crée un paquet vide et
   passe le pilier à `in_progress` sans erreur bloquante.
4. **Le schéma n'a pas de migration canonique.** Plusieurs scripts SQLite locaux
   se chevauchent et la base observée conserve une table orpheline.

### Intégrité pédagogique et progression

5. **La maîtrise est directement pilotable par le client.** L'API de progression
   accepte un nombre envoyé par le navigateur et complète automatiquement le
   pilier à partir de 80 ; l'API `complete` le place directement à 100.
6. **Les prérequis ne bloquent pas le démarrage.** Le code indique explicitement
   qu'aucun contrôle de verrou n'est appliqué à `start_pillar`.
7. **Un contrôle CECR réussi valide en bloc tous les piliers requis.** Ils passent
   à `completed` avec au moins 80, sans preuve distincte par compétence.
8. **Une évaluation peut être complétée sans garde explicite exigeant toutes les
   sections.** Les sections non soumises valent zéro dans l'agrégation ; l'état
   final est uniquement `passed` ou `failed`.
9. **Le niveau global et la carte de piliers agrègent des signaux hétérogènes.**
   `pillar_progress` contient à la fois états de cours, maîtrise, difficulté et
   profil de faiblesse.

### Mémoire, langues et services

10. **L'interface d'intervalle est SM-2 alors que la mutation est FSRS.** Les
    boutons affichent les intervalles calculés par SM-2 ; la soumission persiste
    un intervalle FSRS. L'intervalle annoncé peut donc différer de l'échéance.
11. **Les identifiants de langue ne sont pas unifiés.** Codes ISO, noms anglais
    et contrats TTS coexistent ; `italian` peut être transmis à un service qui
    attend `it`.
12. **Le fallback LLM change automatiquement de fournisseur.** Une même action
    peut être exécutée par LM Studio, vLLM ou Ollama sans trace métier persistée
    du choix.
13. **Le shadowing vidéo est configuré mais non alimenté dans la base locale.**
    La voie TTS de secours reste dépendante d'un service HTTP séparé.
14. **La clé de session change à chaque démarrage sans `SECRET_KEY`.** La valeur
    de secours est générée par processus ; les sessions existantes deviennent
    invalides après redémarrage.

### HTTP, sécurité et maintenabilité

15. **Aucune protection CSRF n'est présente dans les dépendances ou
    l'initialisation Flask.** Les nombreuses mutations par formulaire ou JSON
    reposent sur la session sans jeton CSRF observé.
16. **Certaines mutations utilisent GET.** C'est notamment le cas de la
    déconnexion, du redémarrage/navigation de révision, du démarrage et du
    passage de modules, et de la complétion de session.
17. **Les APIs et pages partagent les mêmes blueprints sans contrat versionné.**
    Les erreurs alternent redirections HTML et JSON ; aucun schéma OpenAPI ou
    version d'API n'est présent.
18. **Le modèle métier est fortement concentré dans des JSON mutables.** Les
    profils, états de session, résultats, progression et configurations n'ont
    ni version ni validation de schéma persistée.
19. **Le support de test est incomplet.** `pytest` manque, deux tests sont
    non assertifs, et les services externes ne sont pas simulés de bout en bout.

### Défauts visuels ou défauts de capture

20. **Sept captures sont blanches ou quasi blanches et non exploitables comme
    preuve visuelle.** Il s'agit de trois captures desktop et quatre captures
    mobiles pleine page listées ci-dessous. Les variantes mobiles de viewport
    correspondantes sont visibles ; l'audit ne peut donc pas distinguer avec
    certitude un défaut de page d'un défaut du mécanisme de capture pleine page.
21. **La navigation mobile de la carte italienne est tronquée horizontalement**
    dans la capture viewport, et le panneau flottant TTS/professeur recouvre les
    dernières cartes visibles.
22. **La page de leçon observée est très longue et entièrement éditoriale.** Le
    démarrage du pilier, l'ouverture d'un exercice à trous et une correction
    exacte ont fonctionné dans l'interface ; cela ne prouve ni l'acquisition, ni
    la validité linguistique de toutes les règles, ni la série complète de sept.

## 10. Index des captures `docs/v2/assets/v1`

Les dimensions viennent des fichiers PNG. Le statut `visible` signifie que la
capture contient une interface lisible ; `non exploitable` signifie qu'elle est
blanche ou presque blanche.

| Capture | Dimensions | Surface représentée | Statut/observation |
|---|---:|---|---|
| `desktop-new-user-dashboard.png` | 1280x1543 | Dashboard, état vide langues/programmes/paquets | Visible |
| `desktop-language-picker.png` | 1280x746 | Liste de langues, état vide | Visible |
| `desktop-language-modal.png` | 1280x755 | Modal des sept langues | Visible |
| `desktop-italian-onboarding.png` | 1280x1119 | Onboarding italien et niveaux A0-C2 | Visible |
| `desktop-italian-learning-map.png` | 1280x2628 | Carte des 44 piliers italiens | Visible |
| `desktop-greetings-pillar.png` | 1280x1961 | Leçon Salutations et Politesse | Visible |
| `desktop-greetings-exercise.png` | 1280x934 | Exercice à trous 1/7 après démarrage du pilier | Visible |
| `desktop-greetings-exercise-corrected.png` | 1280x720 | Réponse `Ciao`, correction exacte et action suivante | Visible |
| `desktop-italian-exercises.png` | 1280x1160 | Cinq exercices libres disponibles en italien | Visible |
| `desktop-italian-assessments.png` | 1280x928 | Hub de contrôle A0 vers A1 | Visible |
| `desktop-italian-progress.png` | 1280x1015 | Dashboard CECR et états vides | Visible |
| `desktop-profile-settings.png` | 1280x2754 | Profil apprenant et préférences | Visible |
| `desktop-stats.png` | 1280x953 | Statistiques globales vides | Visible |
| `desktop-decks.png` | 1280x720 | Paquets | Non exploitable : blanc |
| `desktop-programs.png` | 1280x720 | Programmes | Non exploitable : blanc |
| `desktop-italian-pillar-dashboard.png` | 1280x2628 | Vue dashboard/pilier italien | Non exploitable : blanc |
| `mobile-viewport-dashboard.png` | 390x844 | Dashboard italien, premier viewport | Visible |
| `mobile-viewport-italian-learning-map.png` | 390x844 | Carte italienne, premier viewport | Visible ; tabs tronqués et panneau flottant superposé |
| `mobile-viewport-italian-exercises.png` | 390x844 | Exercices italiens, premier viewport | Visible |
| `mobile-viewport-italian-progress.png` | 390x844 | Progression CECR, premier viewport | Visible |
| `mobile-dashboard.png` | 390x1958 | Dashboard, pleine page | Non exploitable : quasi blanc |
| `mobile-italian-learning-map.png` | 390x3527 | Carte italienne, pleine page | Non exploitable : quasi blanc |
| `mobile-italian-exercises.png` | 390x1132 | Exercices italiens, pleine page | Non exploitable : quasi blanc |
| `mobile-italian-progress.png` | 390x1282 | Progression, pleine page | Non exploitable : quasi blanc |

Bilan des captures : 24 fichiers, 17 visibles et 7 non exploitables. Tous les
fichiers portent désormais un contenu PNG cohérent avec leur extension.

## 11. Limites de preuve

1. Cet audit prouve la présence et les connexions du code au commit indiqué ; il
   ne prouve pas que chaque route fonctionne avec toutes les données possibles.
2. Les contenus, scripts, bases, services Docker et captures ne sont pas dans le
   commit. Leur inventaire décrit l'environnement local du jour de l'audit et
   peut dériver sans historique Git.
3. Les 11 tests exécutés couvrent surtout des régressions de sécurité ciblées.
   Ils ne constituent pas un test de recette de la V1.
4. Les deux tests gym/Lego n'ont pas été exécutés faute de pytest et ne
   contiennent pas d'assertions capables de faire échouer proprement une CI.
5. Aucun appel réel aux fournisseurs LLM ou TTS n'a été requis pour cet audit ;
   leur disponibilité, leur latence et la qualité de leurs sorties ne sont donc
   pas prouvées.
6. Les JSON de cours ont été validés syntaxiquement et comptés, pas relus
   exhaustivement sur le plan linguistique ou pédagogique. Un JSON valide ne
   prouve ni exactitude, ni naturalité, ni progression adaptée.
7. Les captures visibles prouvent des écrans ponctuels. Elles ne prouvent ni les
   clics intermédiaires, ni les écritures en base, ni la reprise, ni les erreurs.
   Les sept captures blanches ne permettent pas de conclure si la cause est le
   rendu applicatif ou l'outil de capture.
8. La base locale contient des données historiques de plusieurs utilisateurs.
   Ses volumes étayent l'existence de chemins utilisés, mais pas leur correction
   actuelle ni leur reproductibilité.
9. Le statut `actif` signifie relié à un chemin normal dans le code ; il ne vaut
   pas certification fonctionnelle, sécurité, accessibilité ou qualité UX.
10. Une architecture V2 ne doit donc pas prendre les agrégats V1, les niveaux
    CECR, les validations automatiques ou les contenus générés comme vérités
    pédagogiques sans contrats et tests supplémentaires.
