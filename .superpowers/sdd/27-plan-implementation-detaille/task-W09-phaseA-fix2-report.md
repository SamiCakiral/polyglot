# W09 Phase A - Fix round 2

## Statut

GREEN local sur les deux bloquants de la contre-revue. Aucun push n'a ete
effectue.

## Cycle TDD

- RED: `a3582da` (`test(w09): require seeded primitive oracles`).
- GREEN: commit contenant ce rapport (`fix(w09): seed primitive fixture oracles`).
- Le RED observait l'absence de `instance_seeds` et de `primitive_oracles` dans
  le rapport du chargeur: `2 failed, 2 passed`.

## Seed et rejeu

- `payload.seed` est transmis jusqu'a chaque `ExerciseInstance` creee pendant
  le rejeu.
- L'ordre de rejeu est derive par tri SHA-256 de `seed:primitive_id` et compare
  a l'oracle litteral `expected_replay_order` de la fixture.
- Deux executions avec la meme seed produisent le meme ordre.
- Le contre-exemple `123456` injecte cette valeur dans les 22 instances et
  produit un ordre different de la seed canonique `9009`.

## Oracles par primitive

- Chacune des 22 entrees porte un `oracle_id` unique, une strategie adaptee au
  type de reponse et une valeur negative valide pour ce meme type.
- Le cas positif execute directement `item.sample.raw_value`; il n'existe plus
  d'oracle texte global rejoue pour toutes les primitives.
- Quatre familles de strategie sont executees: `exact_value`, `accepted_set`,
  `exact_normalized` et `structural_constraints`.
- Chaque entree compare ses verdicts litteraux `correct`, `incorrect`,
  `ambiguous` et `not_evaluable` aux resultats effectivement produits.
- Une mutation du verdict positif d'une seule primitive est rejetee par le
  chargeur.

## Verification

- Suite W09 ciblee: `22 passed`.
- Ruff: aucun constat sur sources et tests exercises/core.
- Mypy: aucun constat sur les 3 fichiers source exercises/core.
- Le test de contrat interdit `socket.socket`; la fixture reste hors reseau.
- Le checksum SHA-256 de `primitives.json` est mis a jour dans les metadonnees.

## Limites

- Aucun test d'integration SQL n'est ajoute ou simule en Phase A.
- Aucune migration, route HTTP ou modification OpenAPI.
- La validation linguistique humaine reste hors de cette preuve synthetique.
