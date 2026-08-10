# W09 Phase A - Fix round 3

## Statut

GREEN local sur le dernier blocage de strategie. Aucun push n'a ete effectue.

## Cycle TDD

- RED: `1f21b05` (`test(w09): require normative primitive strategies`).
- GREEN: commit contenant ce rapport (`fix(w09): execute normative primitive strategies`).
- Le RED observait l'absence de `bounded_translation` dans le domaine et de la
  trace strategies declarees/executables dans FX: `2 failed, 7 passed`.

## Domaine

- Ajout minimal des strategies normatives absentes:
  `bounded_translation`, `self_assessment` et `before_after`.
- Les implementations existantes `morphological`, `rubric`,
  `structural_constraints`, `accepted_set` et `exact_normalized` sont reutilisees.
- La comparaison avant/apres exige une revision effective et une cible attendue.
- L'auto-evaluation utilise une grille numerique et retourne une preuve partielle
  sous le seuil, sans promouvoir artificiellement la reponse.

## FX-PRIMITIVES

- Chaque primitive declare une chaine ordonnee de strategies et leurs parametres;
  le chargeur execute cette chaine sans table de mapping des 22 IDs.
- Les cas morphologiques portent traits attendus et observes, y compris les
  cellules de grille.
- Les productions et comprehensions ouvertes portent leurs criteres, seuils et
  scores de grille propres.
- `EX-PROD-01` compose contraintes et grille; `EX-PROD-02` et `EX-PROD-03`
  executent leurs grilles; `EX-ORAL-01` execute l'auto-evaluation;
  `EX-REPAIR-01` compare avant/apres.
- Les raisons `ambiguous` et `not_evaluable` sont propres a chaque primitive.
- Le rapport certifie l'egalite entre strategies declarees et executees.

## Verification

- Suite W09 ciblee: `23 passed`.
- Ruff: aucun constat sur sources et tests exercises/core.
- Mypy: aucun constat sur les 3 fichiers source exercises/core.
- Le contrat FX reste hors reseau et le checksum SHA-256 est mis a jour.

## Limites

- Aucun test d'integration SQL n'est ajoute ou simule en Phase A.
- Aucune migration, route HTTP ou modification OpenAPI.
- Aucune revue humaine ou dependance reseau n'est simulee.
