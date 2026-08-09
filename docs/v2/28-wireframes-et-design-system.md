# Polyglot V2 - Wireframes et design system UX

## 1. Autorité et portée

Ce document fixe l'architecture UX de référence pour les surfaces apprenant et
Atelier. Il complète le document 20 et utilise les noms techniques, enums,
commandes et routes API du document 25. En cas d'écart technique, le document
25 prévaut. Les labels visibles définis ici sont français et ne deviennent
jamais des valeurs persistées.

Ce document décrit :

- l'architecture de navigation et les shells responsive ;
- les wireframes low-fi desktop et mobile ;
- les états vide, erreur, interruption et reprise ;
- les tokens sémantiques, dimensions et règles de densité ;
- les composants frontend et leur ownership ;
- les critères WCAG 2.2 AA, clavier et zoom.

Il ne fixe ni direction artistique finale, ni illustration, ni animation de
marque, ni code de composant. Le frontend ne calcule jamais la maîtrise, la
dette, le prochain exercice ou un verdict : il affiche les projections et
raisons servies par l'API.

## 2. Vocabulaire UI et termes techniques

| Concept technique | Label UI principal | Règle |
|---|---|---|
| `language_profile` | Profil de langue | La paire langue d'appui/langue cible est toujours explicite. |
| `session_plan` | Séance du jour | « Plan » n'est affiché que dans les détails. |
| `sprint_run` | Séance en cours | « Sprint » reste un terme technique interne. |
| `exercise_block` | Étape | Le type pédagogique peut être indiqué en sous-label. |
| `attempt` | Réponse | Une tentative corrigée n'est pas appelée « compétence acquise ». |
| `word-bank` | Banque de mots | La destination de navigation reste **Vocabulaire**. |
| `memory_prompt` | Révision programmée | Les états FSRS restent techniques. |
| `mastery_status` | État de maîtrise | Labels normatifs du document 25. |
| `assessment_run` | Évaluation | Toujours qualifiée par compétence. |
| `content_revision` | Révision de contenu | Réservé à l'Atelier. |
| `generation_job` | Tâche de génération | Son état est visible, sans promesse de résultat. |

Mapping obligatoire de `mastery_status` :

| Valeur technique | Label UI |
|---|---|
| `non_observed` | Non observé |
| `discovered` | Découvert |
| `in_progress` | En cours |
| `reliable` | Fiable |
| `mastered` | Maîtrisé |
| `review_due` | À revoir |
| `not_evaluable` | Non évaluable |

## 3. Architecture de navigation et routes

### 3.1 Navigation principale

Ordre desktop : **Aujourd'hui**, **Apprendre**, **S'entraîner**,
**Vocabulaire**, **Progression**, **Évaluer**. Le profil de langue, les
préférences, l'aide et **Atelier** selon rôle sont secondaires.

Sur mobile, la barre basse contient **Aujourd'hui**, **Apprendre**,
**S'entraîner**, **Vocabulaire** et **Progression**. **Évaluer**, **Atelier** et
les réglages sont dans **Menu**. Une évaluation ou une séance en cours remplace
la barre basse par les commandes propres au parcours.

### 3.2 Routes UI et ressources canoniques

Les routes UI viennent du document 20. Les ressources et commandes associées
reprennent exactement le registre du document 25.

| Surface | Route UI | Lectures API dominantes | Commandes dominantes |
|---|---|---|---|
| Onboarding | `/language-profile` | `/session`, `/catalogue/targets`, `/language-packs`, `/diagnostics/{id}`, `/foundation-runs/{id}` | `RegisterAccount`, `CreateLanguageProfile`, `UpdateLearningGoals`, `StartDiagnostic`, `SubmitDiagnosticResponse`, `CompleteDiagnostic`, `StartFoundationRun`, `CompleteFoundationGate` |
| Accueil | `/today` | `/language-profiles/{id}`, `/language-profiles/{id}/recommendations`, `/session-plans/{id}`, `/module-enrollments/{id}` | `ComposeDailySession`, `PrepareSessionPlan`, `StartSprintRun` |
| Sprint | `/sprints/:runId` | `/sprint-runs/{id}`, `/exercise-instances/{id}`, `/attempts/{id}` | `OpenExerciseAttempt`, `SaveAttemptDraft`, `UseExerciseHint`, `SubmitExerciseAttempt`, `ContestCorrection`, `SkipExerciseBlock`, `AbandonExerciseBlock`, `InterruptSprintRun`, `ResumeSprintRun`, `StopSprintRun`, `CompleteSprintRun` |
| Word Bank | `/vocabulary` | `/language-profiles/{id}/word-bank`, `/lexicon/search`, `/lexical-senses/{id}`, `/vocabulary-lists`, `/memory-prompts/due` | `RecordLexicalEncounter`, `ResolveMention`, `AddPrivateLexicalUnit`, `CreateVocabularyList`, `ReviseVocabularyList`, `ChangeListMembers`, `FreezeVocabularyList`, `CreateMemoryPrompt`, `SubmitMemoryReview` |
| Progression | `/progress` | `/language-profiles/{id}/progress`, `/language-profiles/{id}/recommendations` | Aucune mutation de maîtrise côté frontend |
| Évaluations | `/assess`, `/assess/:modality`, `/assess/runs/:runId` | `/assessments/{id}`, `/language-profiles/{id}/progress`, `/language-profiles/{id}/recommendations` | `PrepareAssessment`, `StartAssessment`, `SaveAssessmentResponse`, `PauseAssessment`, `ResumeAssessment`, `SubmitAssessment` |
| Entraînement libre | `/practice`, `/practice/configure` | `/language-profiles/{id}/progress`, `/language-profiles/{id}/recommendations`, `/language-profiles/{id}/word-bank`, `/catalogue/targets` | `ComposeFreePractice`, `PrepareSessionPlan`, `StartSprintRun` |
| Atelier | `/authoring/*` | `/authoring/drafts`, `/validation-reports/{id}`, `/jobs/{id}`, `/jobs/{id}/events` | `CreateContentDraft`, `ReviseContentDraft`, `ValidateContentRevision`, `ApproveContentRevision`, `PublishContentRevision`, `RetireContentRevision`, `CreateLearningModule`, `PublishLearningModule`, `RequestGenerationJob`, `CancelGenerationJob` |

Les routes `/learn`, `/learn/modules/:moduleId`, `/vocabulary/lists/:listId`,
`/vocabulary/senses/:senseId` et `/progress/skills/:skillId` conservent le shell
défini ici. Un changement de profil invalide les queries liées au profil et
retourne vers la destination équivalente sans fusionner les données.

## 4. Shells responsive

### 4.1 Desktop, 1024 px et plus

```text
+----------------------+------------------------------------------------------+
| POLYGLOT             | Profil : Italien v         Aide   Compte v          |
|----------------------|------------------------------------------------------|
| Aujourd'hui          |                                                      |
| Apprendre            |  Titre de page                  Action principale    |
| S'entraîner          |  Contexte / état / raison                            |
| Vocabulaire          |------------------------------------------------------|
| Progression          |                                                      |
| Évaluer              |  Contenu de la route                                 |
|                      |                                                      |
|----------------------|                                                      |
| Atelier (si rôle)    |                                                      |
| Préférences          |                                                      |
+----------------------+------------------------------------------------------+
```

- rail de navigation : `240px`, réductible à `72px` entre 1024 et 1199 px ;
- barre haute : `64px` ;
- contenu : largeur fluide, maximum `1280px`, marge interne `24-32px` ;
- une route de travail dense peut utiliser toute la largeur après le rail ;
- aucun panneau latéral métier ne dépasse `360px` sans action explicite.

### 4.2 Mobile, 320 à 767 px

```text
+--------------------------------------+
| Italien v       Titre          Menu  |  56
|--------------------------------------|
|                                      |
| Contenu vertical de la route         |
|                                      |
|                                      |
|--------------------------------------|
| Auj.  Appr.  Exo.  Mots  Progr.      |  64 + zone sûre
+--------------------------------------+
```

- aucune barre latérale permanente ;
- largeur utile minimale `320px`, sans défilement horizontal de page ;
- les panneaux secondaires deviennent une route, un accordéon ou un panneau
  plein écran ;
- la barre basse disparaît dans le lecteur de séance, l'évaluation et l'éditeur
  Atelier afin de réserver l'espace aux actions du parcours ;
- les actions persistantes respectent la zone sûre et ne recouvrent jamais le
  dernier champ.

## 5. Convention des wireframes

- `[Action]` : action principale ou secondaire ;
- `( )` / `(x)` : choix unique ;
- `[ ]` / `[x]` : choix multiple ;
- `v` : menu ou sélecteur ;
- `...` : contenu variable, jamais un élément manquant du contrat ;
- les encadrés représentent des régions, pas des cartes décoratives ;
- un seul appel à l'action principal est visuellement dominant par région.

## 6. Onboarding et diagnostic

Route UI : `/language-profile`. Le `language_profile_status` pilote l'étape :
`onboarding`, puis éventuellement `foundations`, puis `active`.

### 6.1 Desktop

```text
+----------------------------------------------------------------------------+
| POLYGLOT                                            Étape 3 sur 6           |
|----------------------------------------------------------------------------|
| Profil de langue                                                           |
| Français -> Italien                                                        |
|                                                                            |
|  Étapes                     |  Votre expérience                            |
|  [x] Langues                |                                              |
|  [x] Objectifs              |  Depuis combien de temps apprenez-vous ?     |
|  [>] Expérience             |  ( ) Je débute                               |
|  [ ] Diagnostic             |  ( ) J'ai déjà quelques bases                |
|  [ ] Résultat               |  ( ) Je pratique régulièrement               |
|  [ ] Orientation            |                                              |
|                             |  Temps quotidien [ 30 min v ]                |
|                             |                                              |
|                             |  [Retour]                    [Continuer]      |
+----------------------------------------------------------------------------+
```

Le diagnostic remplace la colonne de formulaire par une micro-épreuve. Le
stimulus, la réponse et la progression d'étape restent dans des régions stables.
Le résultat montre les quatre compétences séparément et une confiance, jamais
une moyenne globale.

### 6.2 Mobile

```text
+--------------------------------------+
| Retour       Profil de langue   3/6  |
|--------------------------------------|
| Français -> Italien                  |
|                                      |
| Votre expérience                     |
|                                      |
| Depuis combien de temps              |
| apprenez-vous ?                      |
|                                      |
| ( ) Je débute                        |
| ( ) J'ai déjà quelques bases         |
| ( ) Je pratique régulièrement        |
|                                      |
| Temps quotidien                      |
| [ 30 min v                         ] |
|                                      |
| [Continuer                         ] |
+--------------------------------------+
```

L'étape courante est textuelle (`3/6`) et non transmise par couleur seule. Le
bouton Retour conserve les réponses locales ; Continuer persiste lorsque la
commande correspondante existe.

## 7. Accueil Aujourd'hui

Route UI : `/today`. La surface répond dans cet ordre : que faire, pourquoi ce
choix, combien de temps, et que se passe-t-il ensuite.

### 7.1 Desktop

```text
+----------------------+------------------------------------------------------+
| Navigation           | Aujourd'hui                         Italien v        |
|----------------------|------------------------------------------------------|
|                      | Séance du jour                                      |
|                      | 30 min v   Prête                                     |
|                      | Arriver en Italie - jour 2                           |
|                      | 6 étapes : rappels 2, nouveau 2, production 2        |
|                      | Priorité : revoir les mots hésitants d'hier          |
|                      | [Commencer la séance]                                |
|                      |------------------------------------------------------|
|                      | Ensuite                                              |
|                      | Module : Arriver en Italie       Jour 2 sur 7        |
|                      | Prochaine mission : demander son chemin              |
|                      |------------------------------------------------------|
|                      | Recommandé                                           |
|                      | Réviser 8 mots à échéance       [Réviser]            |
|                      | Travailler les questions        [S'entraîner]        |
+----------------------+------------------------------------------------------+
```

### 7.2 Mobile

```text
+--------------------------------------+
| Italien v       Aujourd'hui     Menu |
|--------------------------------------|
| Séance du jour                      |
| 30 min v                 Prête      |
|                                      |
| Arriver en Italie - jour 2           |
| 6 étapes                             |
| Rappels 2 . Nouveau 2 . Production 2 |
|                                      |
| Pourquoi maintenant ?                |
| Revoir les mots hésitants d'hier     |
|                                      |
| [Commencer la séance               ] |
|--------------------------------------|
| Ensuite                              |
| Demander son chemin                  |
|--------------------------------------|
| 8 mots à revoir            [Réviser] |
|--------------------------------------|
| Auj.  Appr.  Exo.  Mots  Progr.      |
+--------------------------------------+
```

Un plan `preparing` affiche « Préparation de la séance » et une estimation
prudente, sans faux progrès. `ready` affiche « Prête ». `failed` affiche une
erreur récupérable. `expired` propose de recomposer, pas de démarrer l'ancien
snapshot.

## 8. Lecteur de sprint

Route UI : `/sprints/:runId`. Le shell possède la progression, la reprise, la
soumission, l'idempotence, le minuteur, les erreurs et la télémétrie. Le renderer
de primitive ne reçoit qu'une instance immuable et émet des intentions.

### 8.1 Desktop

```text
+----------------------------------------------------------------------------+
| Quitter  Séance du jour    Étape 3 sur 6       env. 18 min     Enregistré  |
|----------------------------------------------------------------------------|
| Objectif : demander poliment une information                               |
|----------------------------------------------------------------------------|
|                                                                            |
|                         STIMULUS STABLE                                    |
|                 Transformez la phrase au vouvoiement                       |
|                         "Dove vai?"                                       |
|                                                                            |
|----------------------------------------------------------------------------|
| Votre réponse                                                              |
| [ Dove va?______________________________________________________________ ] |
|                                                                            |
| [Aide] [Écouter] [Signaler une ambiguïté]                   [Valider]      |
|----------------------------------------------------------------------------|
| Progression des étapes     1 [x]  2 [x]  3 [>]  4 [ ]  5 [ ]  6 [ ]       |
+----------------------------------------------------------------------------+
```

Après soumission, la région de réponse garde sa taille minimale. La correction
apparaît sous la réponse, puis l'action devient **Continuer**. Le tiroir Banque
de mots occupe au maximum `360px` à droite et ne réduit jamais le stimulus sous
`560px` ; sinon il passe en panneau superposé non modal.

### 8.2 Mobile

```text
+--------------------------------------+
| Quitter     Étape 3/6      Enregistré|
| env. 18 min                          |
|--------------------------------------|
| Demander poliment une information    |
|--------------------------------------|
| Transformez au vouvoiement            |
|                                      |
| "Dove vai?"                         |
|                                      |
| Votre réponse                         |
| [ Dove va?_________________________ ] |
|                                      |
| [Aide] [Écouter] [Mots]              |
|                                      |
| [Valider                           ] |
+--------------------------------------+
```

La Banque de mots est un panneau plein écran mobile. La fermeture restaure le
focus sur **Mots**. En `submitting`, **Valider** reste occupé et désactivé sans
disparaître. En `corrected`, le focus se place sur le titre de correction, puis
**Continuer** reste la prochaine action logique.

## 9. Word Bank

Routes UI : `/vocabulary`, `/vocabulary/lists/:listId` et
`/vocabulary/senses/:senseId`. Label de navigation : **Vocabulaire**. Titre de
surface : **Banque de mots**.

### 9.1 Desktop

```text
+----------------------+------------------------------------------------------+
| Navigation           | Banque de mots                      [Ajouter un mot] |
|----------------------|------------------------------------------------------|
|                      | [Rechercher un mot________________] [Filtres]        |
|                      | Rencontrés 248  Reconnus 173  Utilisables 91         |
|                      |------------------------------------------------------|
|                      | Filtres          | Résultats              | Détail   |
|                      | État v           | piano                  | piano    |
|                      | Modalité v       | avere bisogno di       | Sens 2   |
|                      | Domaine v        | binario                | À revoir |
|                      | Liste v          | ...                    |          |
|                      | Échéance v       |                        | Preuves  |
|                      |                  |                        | Contextes|
|                      |                  |                        | Listes   |
|                      |                  |                        |          |
|                      |                  |                        |[Entraîner]|
+----------------------+------------------------------------------------------+
```

La liste centrale est virtualisée pour la fixture `100 000` sens. Le détail
n'est pas une carte imbriquée : c'est une troisième région redimensionnable. Le
compteur de couverture n'est affiché qu'avec un référentiel borné nommé.

### 9.2 Mobile

```text
+--------------------------------------+
| Retour       Banque de mots     +    |
|--------------------------------------|
| [Rechercher_____________________]     |
| [Filtres (2)]                         |
|                                      |
| Rencontrés 248                        |
| Reconnus 173     Utilisables 91       |
|--------------------------------------|
| piano                         À revoir|
| sens 2 . trajet lent                  |
|--------------------------------------|
| avere bisogno di              Fiable |
| expression . besoin                   |
|--------------------------------------|
| binario                       En cours|
| quai / voie                           |
|--------------------------------------|
| Auj.  Appr.  Exo.  Mots  Progr.      |
+--------------------------------------+
```

Un résultat ouvre `/vocabulary/senses/:senseId` en page entière. Les filtres
s'ouvrent dans un panneau plein écran avec **Appliquer** et **Réinitialiser**.
Le bouton `+` a le nom accessible « Ajouter un mot ».

## 10. Progression par quatre compétences

Routes UI : `/progress` et `/progress/skills/:skillId`. La lecture canonique est
`GET /language-profiles/{id}/progress`. Aucune moyenne globale n'est créée dans
le frontend.

### 10.1 Desktop

```text
+----------------------+------------------------------------------------------+
| Navigation           | Progression                          Italien v        |
|----------------------|------------------------------------------------------|
|                      | Vos quatre compétences                               |
|                      | État, confiance et fraîcheur restent séparés         |
|                      |                                                      |
|                      | Compréhension écrite   | Compréhension orale         |
|                      | Fiable                 | En cours                    |
|                      | Confiance : élevée     | Confiance : moyenne         |
|                      | Vérifié il y a 4 j     | Vérifié il y a 12 j         |
|                      | [Voir les preuves]     | [Voir les preuves]          |
|                      |------------------------|-----------------------------|
|                      | Expression écrite      | Expression orale            |
|                      | En cours               | Non évaluable               |
|                      | Confiance : moyenne    | Données insuffisantes       |
|                      | Vérifié il y a 8 j     | Oral simulé disponible      |
|                      | [Voir les preuves]     | [Évaluer]                   |
|                      |------------------------------------------------------|
|                      | Prochaine vérification : questions indirectes        |
|                      | [S'entraîner]                         [Évaluer]       |
+----------------------+------------------------------------------------------+
```

### 10.2 Mobile

```text
+--------------------------------------+
| Italien v       Progression     Menu |
|--------------------------------------|
| Vos quatre compétences               |
| Pas de niveau global calculé          |
|--------------------------------------|
| Compréhension écrite                  |
| Fiable . confiance élevée             |
| Vérifié il y a 4 jours                |
| [Voir les preuves]                    |
|--------------------------------------|
| Compréhension orale                   |
| En cours . confiance moyenne          |
| Vérifié il y a 12 jours               |
| [Voir les preuves]                    |
|--------------------------------------|
| Expression écrite                    |
| En cours . confiance moyenne          |
| [Voir les preuves]                    |
|--------------------------------------|
| Expression orale                     |
| Non évaluable                         |
| [Évaluer]                             |
|--------------------------------------|
| Auj.  Appr.  Exo.  Mots  Progr.      |
+--------------------------------------+
```

L'ordre des quatre compétences est constant. L'état utilise toujours libellé,
icône et couleur. Confiance, fraîcheur et date de dernière évaluation restent
des champs distincts, sans barre agrégée.

## 11. Évaluations

Routes UI : `/assess`, `/assess/:modality` et `/assess/runs/:runId`.

### 11.1 Desktop

```text
+----------------------+------------------------------------------------------+
| Navigation           | Évaluer                                              |
|----------------------|------------------------------------------------------|
|                      | Choisissez une compétence                            |
|                      |                                                      |
|                      | Compréhension écrite   | Compréhension orale         |
|                      | 20 min . disponible    | 15 min . casque conseillé  |
|                      | Dernière : Fiable      | Dernière : En cours         |
|                      | [Voir le protocole]    | [Voir le protocole]         |
|                      |------------------------|-----------------------------|
|                      | Expression écrite      | Expression orale            |
|                      | 25 min . disponible    | Oral simulé . 15 min        |
|                      | Dernière : En cours    | Non évaluée                 |
|                      | [Voir le protocole]    | [Voir le protocole]         |
|                      |------------------------------------------------------|
|                      | Historique des évaluations                           |
|                      | Date       Compétence              Résultat           |
+----------------------+------------------------------------------------------+
```

Le protocole précise durée, matériel, pause autorisée ou non, nombre de
réécoutes et règle de finalisation avant `StartAssessment`.

### 11.2 Mobile

```text
+--------------------------------------+
| Retour          Évaluer         Menu |
|--------------------------------------|
| Compréhension écrite                  |
| 20 min . disponible                   |
| Dernière : Fiable                     |
| [Voir le protocole                  ] |
|--------------------------------------|
| Compréhension orale                   |
| 15 min . casque conseillé             |
| Dernière : En cours                   |
| [Voir le protocole                  ] |
|--------------------------------------|
| Expression écrite                    |
| 25 min . disponible                   |
| [Voir le protocole                  ] |
|--------------------------------------|
| Expression orale                     |
| Oral simulé . non évaluée             |
| [Voir le protocole                  ] |
+--------------------------------------+
```

Pendant une évaluation, la barre haute contient compétence, item, minuteur et
**Quitter**. La réponse n'est jamais révélée avant `SubmitAssessment`. En
`scoring`, le résultat affiche « Analyse en cours ». En `review_required`, il
affiche « Revue nécessaire », sans score provisoire présenté comme définitif.

## 12. Entraînement libre

Routes UI : `/practice` et `/practice/configure`. La composition passe par
`ComposeFreePractice`, puis utilise le même `session_plan` et le même lecteur
que la séance du jour.

### 12.1 Desktop

```text
+----------------------+------------------------------------------------------+
| Navigation           | S'entraîner                                          |
|----------------------|------------------------------------------------------|
|                      | Configuration rapide                                 |
|                      |                                                      |
|                      | Objectif       [Recommandé : questions v]            |
|                      | Compétence     [Expression écrite v]                 |
|                      | Durée          [ 20 min v ]                          |
|                      |                                                      |
|                      | [Afficher les réglages avancés]                      |
|                      |------------------------------------------------------|
|                      | Aperçu                                               |
|                      | 4 étapes . 2 rappels . aucune nouveauté              |
|                      | Travaille : questions et politesse                   |
|                      | Prérequis : disponibles                              |
|                      |                                     [Créer la séance]|
+----------------------+------------------------------------------------------+
```

Les réglages avancés ajoutent modalité, cible, requête Banque de mots,
primitive, nouveauté autorisée et mode entraînement/test. Les valeurs
recommandées sont présélectionnées et leur raison est consultable.

### 12.2 Mobile

```text
+--------------------------------------+
| Retour        S'entraîner       Menu |
|--------------------------------------|
| Configuration rapide                 |
|                                      |
| Objectif                             |
| [Questions v                       ] |
|                                      |
| Compétence                           |
| [Expression écrite v               ] |
|                                      |
| Durée                                |
| [ 20 min v                         ] |
|                                      |
| [Réglages avancés]                   |
|--------------------------------------|
| Aperçu : 4 étapes                    |
| 2 rappels . aucune nouveauté          |
|                                      |
| [Créer la séance                   ] |
+--------------------------------------+
```

Un prérequis manquant est placé près du champ concerné et dans le résumé. Le
bouton de création reste désactivé avec une explication textuelle ; il n'est
pas seulement grisé.

## 13. Atelier pédagogique

Route UI : `/authoring/*`, visible uniquement pour les rôles autorisés. La
surface est un outil de travail dense : tableaux, formulaires, diff, rapports et
prévisualisation. Aucune génération ne publie directement.

### 13.1 Desktop

```text
+----------------------+------------------------------------------------------+
| Atelier              | Contenus / Révision 42           Brouillon          |
|----------------------|------------------------------------------------------|
| Compétences          | Liste / recherche   | Éditeur                      |
| Structures           |---------------------|------------------------------|
| Lexique              | Salutations v3      | Titre [___________________]  |
| Contenus             | Questions v2        | Type  [Structure v]          |
| Exercices            | Voyage v5           | Langue [it-IT v]             |
| Modules              | ...                 |                              |
| Packs                |                     | Contenu structuré             |
| Validations          |                     | [__________________________] |
| Tâches               |                     | [__________________________] |
|                      |                     |                              |
|                      |                     | [Enregistrer] [Valider]      |
|----------------------|---------------------|------------------------------|
| Historique / versions| Rapport : 2 erreurs, 1 avertissement  [Ouvrir]      |
+----------------------------------------------------------------------------+
```

Les actions **Approuver**, **Publier** et **Retirer** n'apparaissent que si le
rôle et `content_revision_status` les autorisent. Une auto-approbation interdite
n'est jamais contournée par l'interface.

### 13.2 Mobile

```text
+--------------------------------------+
| Retour          Atelier         Menu |
|--------------------------------------|
| Contenus > Révision 42                |
| Brouillon                             |
|                                      |
| [Éditer] [Aperçu] [Rapport] [Comparer]|
|--------------------------------------|
| Titre                                |
| [__________________________________] |
| Type                                 |
| [Structure v                        ] |
| Langue                               |
| [it-IT v                            ] |
|                                      |
| Contenu structuré                    |
| [__________________________________] |
| [__________________________________] |
|                                      |
| [Enregistrer                       ] |
| [Lancer la validation              ] |
+--------------------------------------+
```

Une seule région est visible à la fois sur mobile. Le diff et la prévisualisation
sont des vues plein écran. Une action de publication utilise une confirmation
nommant la révision, le pack et la portée ; elle n'est jamais placée à côté de
**Enregistrer** sans séparation.

## 14. États vides, erreurs et reprise

### 14.1 Patrons transversaux

```text
ÉTAT VIDE
+--------------------------------------+
| Titre de l'état                       |
| Ce qui manque et pourquoi.            |
| [Action utile]                        |
+--------------------------------------+

ERREUR RÉCUPÉRABLE
+--------------------------------------+
| Impossible de charger cette section  |
| Vos données saisies sont conservées.  |
| [Réessayer]  [Revenir]                |
+--------------------------------------+

REPRISE
+--------------------------------------+
| Une activité interrompue est disponible|
| Dernier enregistrement : 14:32        |
| Étape 3 sur 6                         |
| [Reprendre]  [Arrêter]                |
+--------------------------------------+
```

Le patron ne remplace pas le contexte métier. Le titre, l'explication, la
conséquence et l'action sont spécifiques à la surface. Une erreur ne promet
jamais que des données sont conservées si aucun accusé serveur ne le prouve.

### 14.2 Matrice par surface

| Surface | Vide utile | Erreur récupérable | Reprise |
|---|---|---|---|
| Onboarding | « Aucun profil de langue » ; **Créer mon profil** | « Diagnostic indisponible » ; conserver les réponses et proposer **Réessayer** | « Reprendre le diagnostic » avec étape et date de sauvegarde |
| Accueil | « Aucune séance prévue » ; **Préparer ma séance** | « Séance impossible à préparer » ; raison autorisée et **Réessayer** | Bannière « Séance interrompue » ; **Reprendre** prioritaire |
| Sprint | Aucun bloc valide devient `fatal_error`, jamais un succès vide | Brouillon conservé seulement si confirmé ; même `Idempotency-Key` au nouvel essai | Restaurer le snapshot serveur, l'étape, la correction et le focus |
| Word Bank | « Aucun mot rencontré » ; **Ajouter un mot** ou **Commencer une séance** | Garder recherche et filtres ; **Réessayer** la lecture | Restaurer recherche, filtres, sélection et position virtualisée |
| Progression | « Pas encore assez de preuves » ; **Faire une séance** | Conserver la dernière projection en la datant, ou afficher l'erreur sans inventer | Restaurer le filtre et la compétence détaillée |
| Évaluations | « Aucune évaluation disponible » avec cause | Matériel indisponible avant départ ; aucune tentative ouverte | **Reprendre l'évaluation** avec compétence, section et fenêtre restante |
| Entraînement libre | « Aucun objectif compatible » ; expliquer le prérequis | Conserver la configuration locale et recomposer manuellement | Reprendre la séance créée, pas relancer la composition |
| Atelier | « Aucun brouillon » ; **Créer un brouillon** | Brouillon local nommé, conflit de version et diff avant écrasement | Restaurer onglet, curseur et dernière version serveur confirmée |

### 14.3 États techniques traduits

| Enum | Valeur | Présentation UI |
|---|---|---|
| `session_plan_status` | `draft` / `preparing` | Préparation de la séance |
| `session_plan_status` | `ready` | Séance prête |
| `session_plan_status` | `failed` | Préparation impossible |
| `session_plan_status` | `expired` | Séance expirée |
| `sprint_run_status` | `in_progress` | Séance en cours |
| `sprint_run_status` | `interrupted` | Séance interrompue |
| `sprint_run_status` | `completed` | Séance terminée |
| `sprint_run_status` | `stopped` | Séance arrêtée |
| `assessment_run_status` | `paused` | Évaluation en pause |
| `assessment_run_status` | `scoring` | Analyse en cours |
| `assessment_run_status` | `review_required` | Revue nécessaire |
| `content_revision_status` | `draft` | Brouillon |
| `content_revision_status` | `validated` | Validée |
| `content_revision_status` | `approved` | Approuvée |
| `content_revision_status` | `published` | Publiée |
| `job_status` | `running` | Tâche en cours |
| `job_status` | `retry_wait` | Nouvelle tentative planifiée |
| `job_status` | `failed` | Tâche échouée |

Les valeurs absentes de cette table utilisent une traduction centralisée dans
le catalogue de labels, jamais une transformation automatique du code technique.

### 14.4 Erreurs API et réponse UX

| Code canonique du document 25 | Réponse UX |
|---|---|
| `validation_failed` | Conserver les saisies, placer un résumé focalisable avant le formulaire et relier chaque erreur à son champ. |
| `unauthenticated` | Afficher « Votre session a expiré » et **Se reconnecter** ; ne pas annoncer un brouillon serveur non confirmé. |
| `forbidden` | Afficher « Vous n'avez pas accès à cette page » et une destination sûre ; aucun bouton Réessayer. |
| `not_found` | Distinguer ressource inexistante, retirée ou supprimée lorsque l'API l'autorise ; proposer le parent de route. |
| `version_conflict` | Conserver le brouillon local, charger la version serveur et proposer **Comparer les versions** avant toute nouvelle mutation. |
| `idempotency_conflict` | Bloquer la répétition, conserver la réponse et proposer de recharger l'état serveur ; ne jamais changer la clé silencieusement. |
| `invalid_transition` | Actualiser l'état, expliquer que l'action n'est plus disponible et retirer la commande devenue invalide. |
| `rate_limited` | Afficher l'attente autorisée par le serveur et un nouvel essai manuel ; aucun appel fournisseur de remplacement. |
| `dependency_unavailable` | Afficher le service indisponible et l'alternative explicitement prévue par le protocole ; aucun fallback implicite. |
| `internal_error` | Afficher une erreur bornée, un identifiant de suivi non sensible et **Réessayer** seulement si l'opération est rejouable. |

Le mode hors ligne initial est consultatif. Les ressources déjà chargées restent
lisibles et marquées « Hors connexion », mais aucune mutation n'est mise en file
localement. La reconnexion recharge l'état serveur avant de réactiver les actions.

## 15. Design system sémantique

### 15.1 Principe non monotone

La progression n'utilise pas une teinte unique de plus en plus saturée. Les
états sont catégoriels : neutre, bleu, ambre, vert, violet et corail. Cette
palette non monotone empêche de lire la couleur comme une note continue. L'ordre
et le sens restent portés par le libellé, l'icône, la position et une description
accessible. La couleur n'est jamais la seule preuve d'état.

### 15.2 Tokens de couleur

Les valeurs sont une baseline claire à valider par mesure de contraste. Les
composants consomment les tokens sémantiques, jamais les hexadécimaux directement.

| Token | Valeur de référence | Usage |
|---|---:|---|
| `color.canvas` | `#F6F7F9` | fond d'application |
| `color.surface` | `#FFFFFF` | surface de travail |
| `color.surface.subtle` | `#EEF1F4` | groupe ou ligne secondaire |
| `color.text` | `#181B20` | texte principal |
| `color.text.muted` | `#56606C` | métadonnée, jamais seule pour une information critique |
| `color.border` | `#C7CED6` | séparation standard |
| `color.border.strong` | `#7B8794` | séparation active ou tableau dense |
| `color.action` | `#075E54` | action principale |
| `color.action.hover` | `#044D45` | survol action principale |
| `color.focus` | `#005FCC` | focus visible, indépendant de l'accent |
| `color.info` | `#0B63CE` | information et état découvert |
| `color.warning` | `#8A4B00` | attention, en cours, prérequis |
| `color.success` | `#137333` | confirmation et état fiable |
| `color.danger` | `#B42318` | erreur, suppression, à revoir |
| `color.mastered` | `#5B3F99` | état maîtrisé uniquement |

Aliases de maîtrise :

| Token | Couleur | Icône/forme obligatoire |
|---|---|---|
| `mastery.non_observed` | neutre | cercle vide + « Non observé » |
| `mastery.discovered` | `color.info` | étincelle simple + « Découvert » |
| `mastery.in_progress` | `color.warning` | demi-cercle + « En cours » |
| `mastery.reliable` | `color.success` | coche + « Fiable » |
| `mastery.mastered` | `color.mastered` | double coche + « Maîtrisé » |
| `mastery.review_due` | `color.danger` | horloge + « À revoir » |
| `mastery.not_evaluable` | neutre fort | tiret + « Non évaluable » |

Les fonds d'état utilisent une teinte claire dédiée et du texte foncé mesuré.
Du texte blanc sur une couleur sémantique n'est permis qu'après validation
WCAG. Les graphiques ajoutent motif, forme ou annotation aux couleurs.

### 15.3 Typographie

| Token | Taille/ligne | Usage |
|---|---|---|
| `type.caption` | `12/16px` | métadonnée non critique |
| `type.body-sm` | `14/20px` | tableau dense, aide |
| `type.body` | `16/24px` | lecture et formulaires |
| `type.heading-sm` | `18/24px` | panneau ou section compacte |
| `type.heading-md` | `22/28px` | titre de page mobile/panneau |
| `type.heading-lg` | `28/36px` | titre de page desktop |

- pile système lisible et stable ;
- aucune taille calculée depuis la largeur du viewport ;
- `letter-spacing: 0` pour tous les tokens ;
- graisse 400 pour le corps, 600 pour titres et commandes ;
- italique jamais utilisé seul pour un état ou une instruction.

### 15.4 Espacement, rayon et élévation

| Famille | Valeurs |
|---|---|
| Espacement | `4, 8, 12, 16, 24, 32, 48px` |
| Rayons | `0, 4, 6, 8px` ; maximum `8px` |
| Bordures | `1px` standard, `2px` sélection/focus interne |
| Ombres | une ombre faible pour menu/panneau superposé uniquement |

Les sections de page sont des bandes ou régions non encadrées. Les cartes sont
réservées aux items répétés et aux modales. Aucune carte dans une carte.

## 16. Densité et dimensions stables

### 16.1 Modes de densité

| Mode | Usage | Ligne | Espacement vertical |
|---|---|---:|---:|
| `comfortable` | apprenant, onboarding, sprint | `48-56px` | `12-16px` |
| `compact` | Word Bank, historique, Atelier | `40-44px` | `8-12px` |

Le mode est choisi par surface, pas par préférence globale initiale. Les actions
tactiles gardent une cible minimale `44x44px`, même en mode compact.

### 16.2 Dimensions contractuelles

| Élément | Dimension stable |
|---|---|
| Barre haute desktop/mobile | `64px` / `56px` |
| Navigation desktop | `240px`, compacte `72px` |
| Barre basse mobile | `64px` + zone sûre |
| Contrôle standard | hauteur `40px`, cible tactile `44px` |
| Bouton principal mobile | hauteur minimale `48px`, largeur disponible |
| Ligne tableau compact | minimum `44px` |
| Tiroir desktop | `320-360px` |
| Modale | max `640px`, marge mobile `16px` |
| Stimulus sprint | min `200px`, max lisible `72ch` |
| Zone de réponse sprint | min `120px` avant correction |
| Lecteur principal | max `880px`, centré hors tiroir |
| Colonne texte courant | `60-72ch` |

Les états chargement, aide, correction, audio et erreur réservent leur espace ou
s'insèrent dans le flux sans déplacer les commandes essentielles. Les skeletons
reprennent les dimensions du contenu attendu. Les labels longs passent sur deux
lignes ; aucun bouton ne tronque son action principale.

## 17. Catalogue de composants

### 17.1 Primitives partagées

`frontend/src/components` possède seulement des composants sans règle métier :

| Composant | Contrat |
|---|---|
| `Button`, `IconButton` | variantes sémantiques, état occupé stable, tooltip pour icône inconnue |
| `TextField`, `TextArea`, `SelectField` | label persistant, aide, erreur liée par ID |
| `Checkbox`, `RadioGroup`, `Switch` | contrôle natif ou sémantique ARIA complète |
| `SegmentedControl`, `Tabs` | modes et vues ; navigation clavier conforme |
| `Slider`, `Stepper` | valeur numérique annoncée et saisie alternative |
| `StatusBadge` | icône + label + couleur, aucun enum métier calculé |
| `ProgressSteps` | position discrète dans un parcours, jamais score de maîtrise |
| `DataTable`, `VirtualList` | tri annoncé, focus stable, alternative mobile |
| `Dialog`, `Drawer`, `Popover`, `Tooltip` | focus piégé/restauré et fermeture explicite |
| `InlineNotice`, `EmptyState`, `ErrorState` | titre, conséquence, action et annonce appropriée |
| `AudioPlayer` | lecture clavier, vitesse, transcription, état sans audio |
| `SaveStatus` | en cours, enregistré, échec ; annonce non intrusive |
| `Skeleton` | taille identique au contenu attendu |

### 17.2 Composants de domaine

| Owner frontend | Composants possédés | Interdictions |
|---|---|---|
| `app/` | `AppShell`, router, providers, `RouteBoundary`, `ActiveLanguageGuard`, sélecteur de profil | aucune règle pédagogique, aucun calcul de projection |
| `features/language-profile/` | étapes onboarding, diagnostic, fondations, résultat par compétence | ne décide pas du placement ni de la dispense |
| `features/today/` | `TodayPage`, résumé de `session_plan`, recommandations, bannière de reprise | ne compose pas la séance |
| `features/learn/` | modules, journées, mission et prérequis | ne crédite pas une maîtrise à la fin d'une journée |
| `features/practice/` | configuration libre, `SprintShell`, bilan, adaptateurs de primitive | ne calcule ni difficulté, ni verdict, ni prochaine étape |
| `features/vocabulary/` | recherche, filtres, liste virtualisée, détail de sens, listes | ne fusionne pas les sens localement |
| `features/progress/` | grille quatre compétences, preuves, historique, recommandations | aucune moyenne globale locale |
| `features/assessments/` | catalogue des quatre évaluations, protocole, runner, résultat | aucun score provisoire inventé |
| `features/authoring/` | tables, éditeur, diff, validation, jobs, publication autorisée | ne publie jamais une sortie de génération directement |
| `generated/` | client OpenAPI généré | aucune modification manuelle |
| `lib/` | transport, formatage, i18n, télémétrie autorisée | aucun état serveur métier dupliqué |

Une feature ne lit jamais l'état interne d'une autre. Elle utilise une route, le
cache TanStack Query typé ou un contrat public de composant. Les adaptateurs de
primitive implémentent `renderStimulus`, `renderResponse`, `serializeDraft`,
`validateLocalShape`, `renderCorrection` et `focusFirstAction`. Le `SprintShell`
reste propriétaire de la soumission et de la reprise.

### 17.3 Ownership de l'état

| État | Owner |
|---|---|
| Ressource et version serveur | TanStack Query, clé incluant profil et ID |
| Paramètres, filtres partageables, onglet | route et recherche validées |
| Formulaire en cours | React Hook Form ; brouillon local explicitement nommé |
| Lecteur sprint/évaluation | reducer ou machine déterministe sérialisable |
| Ouverture de menu/panneau | composant local |
| Maîtrise, dette, recommandation | backend uniquement |

Les mutations optimistes restent limitées aux préférences et gestes réellement
réversibles. Elles sont interdites pour tentative, correction, évaluation,
publication, import, suppression et toute projection de progression.

## 18. Accessibilité, clavier et zoom

### 18.1 WCAG 2.2 AA

- contraste texte normal au moins `4.5:1`, grand texte au moins `3:1` ;
- contraste des composants et états graphiques au moins `3:1` ;
- focus visible non masqué, contour `3px` avec contraste mesuré ;
- aucune information transmise par couleur, position ou son seuls ;
- ordre des titres logique, un `h1` par route ;
- régions `nav`, `main`, `aside` et `status` nommées ;
- erreurs associées aux champs et résumé d'erreurs focalisable ;
- contenus temporels pausables ; minuteur annoncé à intervalles raisonnables ;
- transcription pour tout contenu audio ; absence d'audio non bloquante lorsque
  le protocole le permet ;
- mouvement réduit respecté ; aucune animation nécessaire à la compréhension.

### 18.2 Clavier

- ordre de tabulation identique à l'ordre visuel et documentaire ;
- lien d'évitement vers le contenu principal ;
- Entrée/Espace activent le contrôle focalisé selon son rôle natif ;
- Échap ferme menu, popover ou panneau non destructif et restaure le focus ;
- aucune soumission globale avec Entrée dans une réponse multiligne ;
- toute interaction glisser-déposer possède boutons Monter/Descendre ;
- tabs, radio, listes et menus suivent leurs patterns ARIA ;
- après correction, erreur ou changement d'étape, le focus rejoint le premier
  élément utile annoncé par le shell ;
- aucun raccourci à touche unique n'est actif dans un champ de saisie.

### 18.3 Zoom et reflow

- validation à `200%` sur viewport desktop et largeur CSS résultante ;
- fonctionnement complet à `320px` sans défilement horizontal de page ;
- les tableaux peuvent défiler dans une région nommée et proposent une vue en
  liste lorsque la comparaison de colonnes n'est pas indispensable ;
- les barres persistantes ne recouvrent ni champ, ni message, ni action ;
- les tooltips ne portent aucune information indispensable ;
- texte agrandi jusqu'à `200%` sans troncature des labels ou perte d'action ;
- les panneaux à trois colonnes deviennent une pile de routes/vues, pas trois
  colonnes comprimées.

## 19. Critères d'acceptation UX

| ID | Critère bloquant |
|---|---|
| `REQ-UX-028-001` | Les huit surfaces disposent d'un rendu desktop et mobile conforme aux routes de ce document. |
| `REQ-UX-028-002` | Tous les labels d'état proviennent d'un mapping explicite des enums du document 25. |
| `REQ-UX-028-003` | Une activité terminée n'est jamais affichée comme maîtrise sans projection backend. |
| `REQ-UX-028-004` | Les quatre compétences restent séparées ; aucune moyenne globale n'est calculée ou suggérée. |
| `REQ-UX-028-005` | Chargement, vide, erreur, conflit, hors ligne, contenu extrême et reprise sont testés par route. |
| `REQ-UX-028-006` | Reprendre un sprint ou une évaluation restaure le dernier état serveur confirmé sans double soumission. |
| `REQ-UX-028-007` | Les couleurs de maîtrise sont non monotones et toujours doublées par label et icône. |
| `REQ-UX-028-008` | Aucun état dynamique ne redimensionne brutalement le shell ou ne masque une commande essentielle. |
| `REQ-UX-028-009` | Les parcours critiques sont complets au clavier, à 320 px et à 200 % de zoom. |
| `REQ-UX-028-010` | Les composants et l'état respectent les ownerships ; aucune feature ne lit l'interne d'une autre. |
| `REQ-UX-028-011` | L'Atelier respecte rôles, séparation auteur/reviewer et absence de publication automatique. |
| `REQ-UX-028-012` | Les fixtures `FX-UI`, `FX-WB` et `FX-AUTHORING` couvrent vide, 10/100 000 sens, texte long, lenteur, panne et conflit. |

La gate de sortie est `G4 UX-ready` : captures approuvées à 320, 768 et 1440 px,
zoom 200 %, axe-core sans violation sérieuse ou critique, parcours clavier
manuel, reprise E2E et revue visuelle humaine desktop/mobile. Cette architecture
est spécifiée ; elle ne constitue pas encore cette preuve.
