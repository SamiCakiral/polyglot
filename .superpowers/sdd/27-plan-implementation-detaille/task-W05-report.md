# W05 - Rapport d'implémentation

Date : 2026-08-10

Statut : **IMPLEMENTATION TECHNIQUE W05 TERMINEE ; FIX ROUND 3 VERT**.

Les preuves detaillees sont dans `task-W05-fix2-report.md`,
`task-W05-rejection-report.md` et `task-W05-fix3-report.md`.

## Livré

- domaine éditorial, rôles et transitions contrôlées ;
- migration `0005_content`, provenance et historique ;
- six commandes transactionnelles avec receipts, version, verrou, événement et
  outbox atomiques ;
- défense PostgreSQL contre les mutations hors commande et ajouts tardifs ;
- dix routes auteur/lecture sécurisées et OpenAPI déterministe ;
- décision éditoriale fermée `approved|rejected`, événement
  `content_rejected`, rejeu et conflit d'idempotence ;
- commandes liees a une session humaine prouvee, a une reauth publication et a
  une affectation editoriale de pack jusque dans la frontiere SQL ;
- rapports de validation et manifestes scelles avec count/checksum coherents ;
- portee pack auteur/reviewer/admin sur les six commandes et quatre lectures ;
- `FX-CONTENT` positif/négatif, hors réseau, avec `P-LING pending_human` ;
- parcours base vide incluant rejet, nouvelle révision, remplacement, retrait
  et historique lisible.

## Commits TDD fix round 2

- P0 RED/GREEN : `8919150`, `d335b42` ;
- T03 RED/GREEN : `d333ed6`, `e17f059`, `ae0c8b7` ;
- T04 RED/GREEN : `736d417`, `7774869` ;
- cohérence Alembic GREEN : `3aca6c2`.
- rejet éditorial RED/GREEN : `66a8cf5`, `8970f09`.
- fix round 3 RED/GREEN : `cf2e502`, `e3dee18`.

## Résultats

Dans le clone exact `/tmp/polyglot-w05-fix3-proof-e3dee18`, revision
`e3dee18b7f0265f9578d7b28b6498e6feff6c6a9`, sur la base PostgreSQL 17 neuve
`polyglot_w05_fix3_proof` : W05 `53 passed` en cinq processus separes, cycle
migration `0005 -> 0004 -> 0005` vert, `alembic check` vert, Ruff complet vert,
mypy complet vert sur 56 fichiers, OpenAPI vert et registre W00 vert.

La matrice amont, rejouée par incrément sur bases isolées pour éviter les
collisions de fixtures, est verte pour plateforme (`114`), identité (`68`),
W04F catalogue (`88`) et profils linguistiques (`20`).

## Restes explicites

La matrice fix3 couvre explicitement les commits de rejet `ae0bfc7`, `66a8cf5`
et `8970f09` : decision, evenement/outbox unique, idempotence, publication
interdite et nouvelle revision obligatoire.

Reste uniquement la revue linguistique humaine, maintenue hors acceptation
technique avec `P-LING pending_human`.

Aucun commit n'a été poussé.
