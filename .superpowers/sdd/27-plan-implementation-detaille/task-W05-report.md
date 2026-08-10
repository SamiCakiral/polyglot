# W05 - Rapport d'implémentation

Date: 2026-08-10

Statut global: **BLOQUÉ À W05-T03 PAR UN CONTRAT W00 MANQUANT**.

## Livré

W05-T01 et W05-T02 sont implémentés en TDD et committés. Le cycle éditorial
est protégé au domaine, dans le service transactionnel et directement dans
PostgreSQL. Les six commandes canoniques utilisent UoW,
`SqlCommandReceiptStore`, version attendue, verrou d'agrégat et écriture
atomique événement/outbox. Les preuves, décisions, manifestes, entrées de
manifeste et références historiques sont append-only. Les révisions gardent
leur contenu, provenance, droits, épingles et auteur immuables dès l'insertion.

La publication valide les références W04 publiées, fige leur checksum,
provenance, droits et statut, sérialise les premières publications concurrentes
et conserve une lecture historique complète après remplacement ou retrait.

## Preuves

- PostgreSQL isolé : `polyglot_w05_codex` ;
- Alembic : `0005 -> 0004 -> 0005` réussi, aucune base partagée rétrogradée ;
- contenu ciblé : `19 passed` ;
- Ruff ciblé : réussi ;
- mypy strict ciblé : réussi ;
- aucun helper `create_approved_revision` ou ancien repository de publication ;
- commits RED/GREEN : `24b2773`, `7707989`, `87f2836`, `3bec26c`.

## Blocage précis

W05 exige dix routes, dont
`GET /api/v1/authoring/drafts/{draft_id}`. Cette query est absente du registre
W00. Le RED `cec57b0` le démontre et échoue avec un seul élément manquant.

Le write set W05 interdit `contracts/registry/**`; son brief exige explicitement
un incrément W00 séparé dans ce cas. T03 ne peut donc pas devenir GREEN sans
autoriser d'abord l'ajout de `GetContentDraft` et de sa route au registre W00.
T04 reste en attente de ce contrat stabilisé.

## Reprise exacte

1. Ouvrir un incrément W00 et enregistrer `GetContentDraft` sur
   `GET /authoring/drafts/{draft_id}`.
2. Reprendre `cec57b0`, implémenter les dix routes et régénérer OpenAPI.
3. Exécuter T03 sécurité/permissions/pagination/Problem Details.
4. Exécuter FX-CONTENT positif/négatif et le parcours base vide T04.
