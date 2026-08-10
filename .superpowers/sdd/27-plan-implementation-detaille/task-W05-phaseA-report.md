# W05 - Rapport intermédiaire Phase A

Date: 2026-08-10

## Périmètre livré

Cette phase livre exclusivement W05-T01 et W05-T02, conformément à
`task-W05-brief.md` :

- domaine éditorial révisionné et cycle `draft -> validating -> validated ->
  approved -> published`, avec sorties explicites `rejected`, `abandoned`,
  `retired` et `superseded` ;
- séparation auteur/reviewer dans le domaine et au niveau du schéma : une
  approbation par son propre auteur est refusée ;
- migration `0005_content`, chaînée après `0004_language_profiles`, avec
  schéma `content`, contraintes d'intégrité, droits runtime et migration,
  provenance obligatoire et garde d'immuabilité des révisions publiées ;
- persistance des révisions, rapports et constats de validation, décisions
  d'approbation, manifestes et références historiques ;
- publication transactionnelle qui produit dans la même transaction la
  révision publiée, le manifeste, l'événement `content_published` et son
  message outbox ;
- lecture d'une révision retirée ou remplacée par son identifiant figé.

La couche HTTP, les routes auteur/lecture et `FX-CONTENT` restent pour
W05-T03/T04 après intégration de W03. Aucune route partagée, aucun contrat
OpenAPI, `app.py`, frontend, fichier W03 ou configuration GitHub n'a été
modifié.

## TDD et commits

| Étape | Commit | Résultat |
| --- | --- | --- |
| W05-T01 RED | `f9d7977` | invariants du cycle et séparation auteur/reviewer écrits avant l'implémentation |
| W05-T01 GREEN | `dac6544` | domaine éditorial révisionné implémenté |
| W05-T02 RED | `5436180` | contrats d'intégration de migration, publication/outbox et historique écrits avant la persistance |
| W05-T02 GREEN | commit de cette phase | migration et dépôt SQL implémentés |

## Preuves exécutées

- `pytest tests/unit/content tests/property/content tests/integration/content -q`
  : **11 passed**. Les tests d'intégration se connectent au rôle runtime pour
  les écritures W05; seul le jeu de provenance/catégorie existant est préparé
  par le rôle de migration.
- `ruff check src/polyglot/modules/content tests/unit/content
  tests/property/content tests/integration/content` : **pass**.
- `mypy src/polyglot/modules/content` : **Success: no issues found in 3 source
  files**.
- Alembic réel : downgrade de `0005_content` et `0004_language_profiles` vers
  `0003_catalogue`, puis upgrade jusqu'à `0005_content (head)` : **pass**.
- Test transactionnel : après une publication suivie d'un rollback, il ne
  reste ni révision, ni manifeste, ni `content_published`, ni outbox.

## État de la revue de migration

`alembic check` s'exécute mais signale une dérive des tables
`language_profiles` de W03. Les fichiers W03 sont simultanément en cours de
travail et leurs métadonnées ne sont pas encore stabilisées dans le registre
Alembic. Le résultat ne contient aucune dérive `content` après alignement de
la contrainte `ck_content_revision_payload` dans le modèle SQLAlchemy.

Cette phase est donc **verte pour W05-T01/T02**, avec un contrôle global
Alembic **PARTIAL** jusqu'à l'intégration complète de W03. La reprise devra
rejouer `alembic check` après W03, avant W05-T03/T04.

## Exclusions et suite

- Aucun endpoint, autorisation HTTP, idempotence HTTP ou contrôle de version
  API n'est ajouté : ils relèvent de W05-T03.
- Aucun validateur éditorial concret ni brouillon `FX-CONTENT` n'est ajouté :
  ils relèvent de W05-T04.
- Le dépôt n'est pas poussé dans cette phase.
