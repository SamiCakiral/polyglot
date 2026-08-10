# W09 Phase A - Rapport d'implementation

Date: 2026-08-10

## Statut

**COMPLETE pour W09 Phase A.** Le domaine pur des exercices est livre dans le
write set autorise. Aucun fichier de migration, route HTTP, contrat OpenAPI,
composition partagee ou fichier W15 n'est inclus.

## Livraison

- Registre ferme de 22 primitives `core`, avec les unions de reponse canoniques
  du document 12 et un adaptateur commun par primitive.
- `ExerciseDefinition` revisionnee et publiee, `ExerciseInstance` figee avec
  seed, revisions de stimulus et revision de pack epinglees.
- `Answer` ferme par `kind`, sans payload libre; la valeur brute est gelee dans
  chaque tentative.
- `Attempt` immuable: `draft -> submitted -> correcting -> corrected` ou
  `not_evaluable`, soumission idempotente, horloge et IDs injectes, journal des
  aides append-only, revelation H4 et soumission forcee explicites.
- Aides H0-H4 avec multiplicateurs normatifs. Une revelation H4 produit une
  activite mais aucun credit positif.
- `CorrectionResult` et `CorrectionCase` append-only, avec ambiguite et
  indisponibilite explicites, sans succes ni credit derives.
- Correcteurs locaux `exact_normalized`, `accepted_set`, `morphological`,
  `structural_constraints` et grille `rubric`.
- Cycle `ExerciseBlockRun` pour disponibilite, saut, abandon et indisponibilite.
- `FX-PRIMITIVES` offline, horloge/graine figees, empreinte SHA-256 et
  declaration par primitive des cas positif, negatif, ambigu, non evaluable et
  de l'alternative clavier/lecteur d'ecran/temps non contraint.

## TDD et commits

| Etape | Commit | Preuve |
| --- | --- | --- |
| RED | `7653f88` | Tests/fixtures W09 ajoutes avant le domaine; import direct du module absent echoue avec `ModuleNotFoundError`. |
| GREEN | commit de ce rapport | Domaine minimal, fixtures verrouillees et suite W09 verte. |

Le premier commit RED a ete amende avant GREEN pour retirer des fichiers W15
crees en parallele; ces fichiers ont ete conserves non suivis et ne font partie
d'aucun commit W09.

## Verification

Execute depuis `backend/` avec un environnement Python 3.13.11 isole, car
l'import de `pytest` dans `.venv` local restait bloque avant la collecte:

- `PYTHONPATH=src /tmp/polyglot-w09-venv/bin/python -m pytest tests/unit/exercises_core tests/property/exercises_core -q`: **12 passed**.
- `/tmp/polyglot-w09-venv/bin/ruff check src/polyglot/modules/exercises/core tests/unit/exercises_core tests/property/exercises_core`: **All checks passed**.
- `PYTHONPATH=src /tmp/polyglot-w09-venv/bin/python -m mypy --cache-dir=/tmp/polyglot-w09-mypy-cache-20260810b src/polyglot/modules/exercises/core`: **Success: no issues found in 2 source files**.
- `git diff --check`: **pass** avant le commit GREEN.

## Limites et suite

- Cette phase n'ajoute pas `0009_exercises`; W09 persistence/integration reste
  bloquee par la demande explicite Phase A et ne doit pas preceder W08.
- Aucune route, idempotence HTTP, concurrence SQL, evenement/outbox, projection
  d'observation ou lien vers Sprint/SessionPlan n'est livre ici.
- Les fixtures declarent les parcours de certification; leur execution complete
  via persistance, media et frontend appartient aux phases W09 suivantes.
- Aucun push n'a ete effectue.
