# W10 - Verification technique

Statut : `technical_pass`, avec `P-LING` encore `pending_human`.

## Portee verifiee

- registre ferme `GYM-01..15`, preconditions et invariants semantiques ;
- blocage des calques italiens publies et des prerequis absents ;
- composition deterministe de un a trois pas avec graines PostgreSQL `bigint` ;
- correction bornee sans credit du lexique support ;
- cycle `G0-G4`, `J+1`, variation de contexte et transfert sans indice ;
- migration `0010_gym`, aller-retour Alembic, RLS proprietaire et faits immuables ;
- references versionnees vers W04, W08 et W09 ;
- ports catalogue, lexique et exercices resolus avant toute ecriture Gym ;
- fixture canonique `FX-GYM-IT` executable hors reseau.

## Commandes de preuve

```text
pytest tests/unit/gym tests/property/gym tests/contract/gym tests/integration/gym -q
95 passed

pytest tests -q
866 passed, 2 skipped

ruff check backend/src/polyglot/modules/exercises/gym backend/tests/**/gym
All checks passed

mypy backend/src/polyglot/modules/exercises/gym
Success: no issues found

alembic downgrade 0009_exercises
alembic upgrade 0010_gym
success
```

## Validation restante

La fixture declare explicitement `linguistic_review: pending_human`. Aucun test
automatique ne remplace la signature d'un linguiste italien ; W10 ne revendique
donc pas encore la preuve `P-LING`.
