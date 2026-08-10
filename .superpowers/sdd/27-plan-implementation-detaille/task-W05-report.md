# W05 - Rapport d'implémentation

Date : 2026-08-10

Statut : **FIX ROUND 2, T03 ET T04 TERMINÉS ; ACCEPTATION GLOBALE PARTIAL**.

Le détail exécutable et les preuves fraîches sont dans
`task-W05-fix2-report.md`.

## Livré

- domaine éditorial, rôles et transitions contrôlées ;
- migration `0005_content`, provenance et historique ;
- six commandes transactionnelles avec receipts, version, verrou, événement et
  outbox atomiques ;
- défense PostgreSQL contre les mutations hors commande et ajouts tardifs ;
- dix routes auteur/lecture sécurisées et OpenAPI déterministe ;
- `FX-CONTENT` positif/négatif, hors réseau, avec `P-LING pending_human` ;
- parcours base vide jusqu'au remplacement, retrait et historique lisible.

## Commits TDD fix round 2

- P0 RED/GREEN : `8919150`, `d335b42` ;
- T03 RED/GREEN : `d333ed6`, `e17f059`, `ae0c8b7` ;
- T04 RED/GREEN : `736d417`, `7774869` ;
- cohérence Alembic GREEN : `3aca6c2`.

## Résultats

Sur la base PostgreSQL isolée neuve `polyglot_w05_acceptance` : W05
`36 passed`, cycle migration `0005 -> 0004 -> 0005` vert, `alembic check` vert,
Ruff complet vert, mypy complet vert, OpenAPI vert et registre W00 vert.

La matrice amont, rejouée par incrément sur bases isolées pour éviter les
collisions de fixtures, est verte pour plateforme (`114`), identité (`68`),
W04F catalogue (`88`) et profils linguistiques (`20`).

## Restes explicites

1. Ajouter au registre W00 un événement canonique de rejet avant d'exposer la
   décision humaine `validated -> rejected` par le service et l'API.
2. Obtenir la revue indépendante finale et la revue linguistique humaine.

Aucun commit n'a été poussé.
