# W05 - Fix round 1 et clôture T03/T04

Date: 2026-08-10

## Décision préalable SPK-PUBLISH

Verdict: **ADOPTER**.

La publication verrouille d'abord la ligne stable `content.content_items` avec
`SELECT ... FOR UPDATE`, vérifie sa version attendue, puis lit et remplace le
manifeste actif dans la même transaction. Ce verrou existe même lorsqu'aucun
manifeste n'est encore publié; deux premières publications concurrentes sont
donc sérialisées sur l'agrégat au lieu de dépendre d'une erreur tardive de
l'index unique partiel. L'index reste un filet d'intégrité.

La transaction canonique contient receipt d'idempotence, mutation éditoriale,
événement et outbox. Un conflit de version ou un échec injecté annule tout.
La suite PostgreSQL W05 doit démontrer qu'un seul concurrent gagne avec la
version attendue et que le perdant reçoit `version_conflict`, sans publication
ni événement partiels.

## Environnement isolé

Les preuves W05 utilisent exclusivement la base locale dédiée
`polyglot_w05_codex`. La base partagée `polyglot` et la migration W04 `0003`
ne sont ni rétrogradées ni modifiées pendant le travail W04F parallèle.

## Résultats

### W05-T01/T02 - terminé

Commits TDD :

- `24b2773` RED : attaques SQL directes, cycle et append-only ;
- `7707989` GREEN : triggers, contraintes et immutabilité PostgreSQL ;
- `87f2836` RED : six commandes, idempotence, concurrence et atomicité ;
- `3bec26c` GREEN : service transactionnel/UoW, receipts, versions, verrou
  agrégat, événements/outbox, références W04 et historique complet.

Preuves exécutées sur `polyglot_w05_codex` :

- cycle Alembic isolé `0005 -> 0004 -> 0005` : réussi ;
- tests unitaires, propriétés et intégration contenu : `19 passed` ;
- test de concurrence SPK-PUBLISH inclus : un gagnant, un
  `version_conflict`, un manifeste et un événement ;
- échec injecté après événement : mutation, manifeste, événement et outbox
  annulés, receipt terminal `failed` conservé ;
- Ruff ciblé : réussi ;
- mypy strict ciblé : réussi.

### W05-T03 - RED committé, bloqué par W00

Le commit `cec57b0` ajoute la preuve RED des dix routes exigées. Le registre
W00 `contracts/registry/queries.yaml` ne contient pas
`GET /api/v1/authoring/drafts/{draft_id}`. Le test échoue uniquement sur cette
route manquante.

Le brief W05 interdit de modifier `contracts/registry/**` et ordonne d'arrêter
W05 si une incohérence requiert un incrément W00. Implémenter la dixième route
ferait échouer `validate_registry_compatibility`; la supprimer violerait le
brief W05. Aucun GREEN T03 conforme n'est donc possible avant ajout de cette
query par un incrément W00 distinct.

### W05-T04 - non démarré

T04 dépend du contrat HTTP T03 stabilisé pour son parcours base vide. Il reste
intentionnellement non démarré afin de ne pas construire FX-CONTENT sur un
contrat incomplet.
