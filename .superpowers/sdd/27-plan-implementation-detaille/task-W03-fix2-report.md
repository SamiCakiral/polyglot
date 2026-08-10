# W03 - Fix round 2

## Verdict

**PASS W03.** Les trois constats bloquants de `task-W03-rereview.md` sont
fermes par des tests RED/GREEN, des contrats HTTP verifies et une execution sur
une instance PostgreSQL 17.10 locale, neuve et dediee.

## Correctifs

### Seuils absolus de fondations

- `ITF-F1-01` materialise exactement 10 discriminations distinctes par
  session; la gate exige au moins 8 succes.
- `ITF-F1-02` materialise exactement 10 lectures ciblees distinctes par
  session; la gate exige au moins 8 succes.
- `ITF-F5-02` materialise exactement 5 echanges de survie distincts; la gate
  exige au moins 4 succes sans revelation.
- Chaque mesure persiste `trial_ordinal` et le critere derive par le backend.
  L'unicite PostgreSQL porte sur run, session, item et essai.
- Les deux controles F1 doivent chacun satisfaire leur seuil dans deux
  sessions distinctes separees d'au moins 24 heures. Un ratio `2/2` ne peut
  plus satisfaire un seuil `8/10`.
- Une session complete contient 32 reponses brutes : 10 + 10 + 5 essais et
  les sept autres items publies executes une fois. Score, critere,
  evaluabilite et credit restent entierement derives cote serveur.

### Reprise et expiration P-RETOUR

- Avant 24 heures, une nouvelle commande de depart renvoie le run actif
  existant, avec le meme ID, le meme snapshot et la meme version. Aucune ligne
  de run supplementaire n'est inseree.
- A partir de 24 heures, l'ancien run est persiste `expired` et un nouveau run
  peut etre cree.
- Une soumission tardive verrouille le run, persiste `expired` et incremente sa
  version dans une transaction validee avant de retourner `run_expired`.

### ETag, If-Match et OpenAPI

- Toutes les transitions pause, reprise, archivage et suppression posent
  l'ETag correspondant a la nouvelle version de la ressource.
- Toutes les commandes W03 sur ressource existante declarent `If-Match`
  obligatoire et non nullable dans OpenAPI.
- L'absence runtime de `If-Match` retourne 428; la reponse RFC 9457 est
  documentee sur chaque commande concernee.
- `contracts/openapi/v1.json` a ete regenere et son controle deterministe passe.

## Commits RED/GREEN

- `de98733` RED essais et seuils absolus; `884c31d` GREEN persistance et gate.
- `1dc76a1` RED reprise/expiration P-RETOUR; `fc7846a` GREEN transaction durable.
- `6b8abf5` RED contrat concurrence HTTP; `ff81064` GREEN runtime et OpenAPI.
- `b3b8c70` publie l'artefact OpenAPI regenere et verifie.

## Preuves finales

Instance dediee : PostgreSQL `17.10`, cluster
`/tmp/polyglot-w03-r2-pgdata`, port `55439`, base `polyglot`, roles migration,
runtime et retention sans `BYPASSRLS`.

```text
W03 unit/property/contract/integration       37 passed in 4.73s
OpenAPI plateforme                           4 passed in 1.09s
Ruff W03                                     All checks passed
mypy strict                                  Success: 64 source files
Alembic base -> head                         passed
Alembic head -> base -> head                 passed avec garde destructive explicite
Alembic check                                No new upgrade operations detected
OpenAPI export --check                       passed
```

La matrice backend monolithique reste inexecutable telle quelle pour deux
causes hors W03 : collisions de noms de modules en mode normal et imports
absolus `test_contracts` incompatibles avec `--import-mode=importlib` dans
`exercises_core`. La matrice separee par domaine confirme W03 (`16` contrats,
`6` integrations) et les domaines stables. Elle expose aussi des travaux
concurrents hors W03 encore rouges : `exercises_core` incomplet, detection de
secrets dans l'historique Git et integration `content` contaminee par l'ordre
des suites. Aucun de ces echecs n'est presente comme une preuve W03.

## Livraison

- Aucun fichier W05 ou frontend modifie par ce round.
- Aucun fichier duplique ` 2.py` present.
- Commits locaux uniquement; aucun push.
