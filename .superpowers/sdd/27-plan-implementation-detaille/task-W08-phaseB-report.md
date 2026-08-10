# W08 phase B - Pipeline SQL et HTTP

## Statut

GREEN local intermediaire. W08 n'est pas accepte : les gates T01-T04 completes
restent ouvertes.

## Portee livree

- listes revisionnees, snapshots immuables, partage publie puis retire ;
- parseurs JSON/CSV bornes et inspection ZIP sans extraction ;
- sept classes de conflit et quatre strategies de preview deterministes ;
- import preview, decision interactive, commit, manifeste et revert compensatoire ;
- distinction auditee entre references creees et reutilisees ;
- export demande uniquement apres reauthentification recente ;
- receipts, evenements canoniques et outbox atomiques ;
- routes FastAPI W08, OpenAPI et client TypeScript regeneres ;
- fixture canonique `FX-IMPORTS`, hors reseau, checksum verrouille et cas 10 000 lignes.

## Cycles RED/GREEN ajoutes

- une reutilisation exacte creait un doublon et ne renseignait pas `reused_refs` ;
- une resolution interactive ne propageait pas son action vers le commit ;
- les routes dynamiques exposaient `_resource_type` dans OpenAPI ;
- les commandes W08 ne produisaient ni evenement ni outbox ;
- clone et merge produisaient a tort `vocabulary_list_created` ;
- la publication partagee, son retrait et la reauthentification export n'etaient
  pas prouves par PostgreSQL ;
- `FX-IMPORTS` et la suite property W08 etaient absents.

## Preuves locales

- W08 unit/property/integration/contract/spike : `41 passed` ;
- Ruff cible W08 : PASS ;
- mypy strict sur le module et les routes : PASS ;
- migration `0008 -> 0007 -> 0008`, puis `alembic check` : PASS ;
- OpenAPI W01-W08 et compatibilite registre : PASS ;
- generation Orval, lint, typecheck et Vitest frontend : PASS ;
- registre W00 : `contract registry valid`.

## Gates encore ouvertes

- domaine pur complet des listes dynamiques, archivage et associations ;
- ports W06/W07 : le commit ne doit pas ecrire directement leurs tables ;
- machine d'etat complete upload/quarantaine/parsing et politiques hostiles V1 ;
- selection partielle explicite et rapport d'erreur borne ;
- `PrivateArtifactPort`, manifeste d'export et attestation de chiffrement ;
- concurrence/adversarial, volume 100 000, profil SQL et p50/p95/p99 ;
- non-regression W06/W07, revue securite et approbation produit humaines.

Aucun push et aucune acceptation W08 ne sont revendiques par ce rapport.
