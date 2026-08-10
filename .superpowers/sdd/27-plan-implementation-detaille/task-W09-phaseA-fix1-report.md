# W09 Phase A - Fix round 1

## Statut

GREEN local. Les constats de la revue Phase A sont corriges dans le perimetre domaine,
tests et fixture canonique. Aucun push n'a ete effectue.

## Cycle TDD

- RED: `bf8858b` (`test(w09): expose phase A review regressions`).
- GREEN: commit contenant ce rapport (`fix(w09): harden immutable exercise replay`).
- Les echecs RED observes couvraient la mutation des listes appelantes, l'absence de cle
  d'idempotence sur la correction et l'absence du chargeur executable FX-PRIMITIVES.

## Corrections

- Deep immutability: copie defensive en tuples pour les collections de definition,
  instance, tentative, resultat de correction, strategie et dossier de correction.
- Idempotence stable: recus immuables conserves dans les agregats pour hint/reveal,
  submit, forced submit, correction, skip, abandon et unavailable.
- Un rejeu avec la meme cle et le meme corps est sans effet, y compris apres une
  transition terminale; la reutilisation d'une cle avec un autre corps produit
  `IDEMPOTENCY_CONFLICT`.
- Une correction rejouee ne cree jamais une seconde correction.
- FX-PRIMITIVES: chargeur/validateur strict, checksum ferme et execution hors reseau de
  22 primitives avec oracles positif, negatif, ambigu, not_evaluable, unavailable,
  H0-H4, accessibilite, rejeu, saut et abandon.
- Le chargeur rejette une fixture a laquelle manque un oracle par primitive.

## Verification

- `20 passed` sur `tests/unit/exercises_core`, `tests/property/exercises_core` et
  `tests/contract/exercises_core`.
- Ruff: aucun constat sur le domaine et les tests W09.
- Mypy: aucun constat sur les 3 fichiers source du module exercises/core.
- Fixture executee avec `socket.socket` interdit par le test de contrat.

## Limites assumees

- Aucun test d'integration SQL n'est ajoute ou simule en Phase A.
- La persistance et les contraintes transactionnelles restent a prouver dans une phase
  d'integration SQL ulterieure.
- Aucune migration, route HTTP ou modification OpenAPI.
- Aucune dependance reseau et aucune validation linguistique humaine revendiquee.
