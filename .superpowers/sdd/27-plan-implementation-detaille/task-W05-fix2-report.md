# W05 - Fix round 2 et clôture T03/T04

Date : 2026-08-10
Révision vérifiée : `3aca6c26442666e041cb5f8b98144da5a3e12bbc`

## Verdict

**PASS pour le périmètre fix round 2 demandé : deux P0, T03 et T04.**

L'acceptation globale du brief W05 reste **PARTIAL** pour deux dépendances hors
write set : le rejet éditorial exécutable n'a toujours aucun événement canonique
W00, et la matrice W04F est rouge pendant une modification parallèle de
`catalogue/0003`. Aucun de ces fichiers n'a été modifié ou indexé par W05.

`P-LING` reste explicitement `pending_human`.

## P0 fermés

1. Toute mutation SQL W05 doit être ouverte par `content.begin_command` depuis
   un receipt canonique `started`. Un trigger différé exige avant commit le
   receipt `succeeded`, l'événement exact de la commande et exactement une
   outbox. Chaque transition est limitée au type de commande autorisé.
2. `validation_findings` et `publication_manifest_entries` ne peuvent être
   insérés que dans le contexte transactionnel de leur commande. Une insertion
   après clôture, terminalité ou dans une transaction ultérieure est refusée.
3. Les invariants déjà verts restent couverts : révisions immuables après
   insertion, preuves/décisions/manifestes/références append-only, séparation
   auteur/reviewer, version attendue, idempotence, concurrence de publication,
   rollback injecté, droits, provenance et historique lisible.

Commits RED/GREEN :

- `8919150` RED : chaîne SQL et insertions tardives ;
- `d335b42` GREEN : contexte de commande et vérification différée atomique ;
- `e17f059` RED / `ae0c8b7` GREEN : conservation de `content_type` et API T03 ;
- `3aca6c2` GREEN complémentaire : métadonnées SQLAlchemy de
  `content.command_contexts`, après RED `alembic check`.

## T03

Les dix routes canoniques sont montées sous `/api/v1` : six commandes, liste,
lecture de brouillon, historique et rapport. Les handlers délèguent au service
transactionnel W05.

Les preuves couvrent session propriétaire, rôles, auteur hors portée, reviewer,
auto-approbation, reauth récente, Origin, CSRF, `If-Match`,
`Idempotency-Key`, pagination par curseur opaque stable et Problem Details
RFC 9457. OpenAPI est régénéré et le registre W00 incluant `GetContentDraft`
est valide. Aucune route service, outil ou job ne publie du contenu.

Commits RED/GREEN : `d333ed6`, `ae0c8b7`.

## T04

`FX-CONTENT` est synthétique, déterministe, hors réseau et protégé par SHA-256.
Il couvre les statuts éditoriaux, deux auteurs, un reviewer, un acteur multi-rôle,
les rapports `passed|failed|human_required`, les références W04, l'historique
épinglé et quatre fixtures négatives checksum/provenance/droits/manifeste.

Les six contre-exemples V1 du document 22 sont enregistrés comme oracles
`human_required`; aucun booléen automatique ne prétend valider leur naturalité.
Le parcours PostgreSQL exécute validation échouée, correction par nouvelle
révision, validation verte, approbation distincte, publication, remplacement,
retrait et lecture de la première révision supersédée.

Commits RED/GREEN : `736d417`, `7774869`.

## Preuves exécutées

Base isolée neuve : `polyglot_w05_acceptance`, PostgreSQL 17 local, sans DSN ni
secret versionné.

- base vide `alembic upgrade head` : PASS jusqu'à `0005_content` ;
- cycle isolé `0005 -> 0004_language_profiles -> 0005` : PASS ;
- `alembic check` : PASS, aucune opération nouvelle ;
- W01 plateforme : `114 passed` ;
- W02 identité : `68 passed` ;
- profils linguistiques : `20 passed` ;
- W05 complet : `36 passed` ;
- Ruff `src tests` : PASS ;
- mypy `src` : PASS, 56 fichiers ;
- export OpenAPI `--check` : PASS ;
- validateur du registre : `contract registry valid` ;
- `git diff --check` : PASS.

Versions : Python 3.13.11, pytest 9.1.1, Alembic 1.19.1, Ruff 0.16.2,
mypy 2.3.0.

## Limites et blocages externes

- W04F : `14 failed, 74 passed` pendant que ses fichiers non committés modifient
  la table `foundation_reference_revisions` et un trigger qui attend encore
  `blocking_facet_refs`. W05 n'a ni modifié ni indexé ces fichiers.
- Le lancement de toute la matrice en un seul processus Pytest provoque trois
  collisions de noms de modules. Les incréments ont été relancés séparément.
- Le rejet humain `validated -> rejected` existe au domaine et dans la fixture,
  mais n'est pas exposé par le service : W00 n'autorise pour
  `ApproveContentRevision` que `content_approved` et ne définit aucun événement
  de rejet. Inventer silencieusement cet événement violerait le registre.
- La revue finale indépendante et l'approbation éditoriale humaine restent à
  demander après stabilisation de ces deux dépendances.
