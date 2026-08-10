# W04F - Catalogue des fondations IT

## Statut apres revue round 1

Le correctif round 1 clot tous les constats P1/P2 de
`task-W04F-review.md`. Le detail et les preuves sont consignes dans
`task-W04F-fix1-report.md`.

## Portee livree

W04F ajoute au catalogue publie le pilote des fondations IT:

- aggregate immuable `PublishedFoundationCatalogue` avec definition, references
  versionnees typees, blocs, items et gate;
- cinq blocs ordonnes `F1` a `F5`, dix items `ITF-F1-01` a `ITF-F5-02`, correcteurs structurels et reponses brutes;
- gate `FOUNDATIONS_IT_V0` exacte: cinq facettes `reliable`, couverture `1.0`,
  confiance `0.6`, deux sessions, controle F1 a 24 h, 8/10 son, 8/10 lecture,
  4/5 survie sans revelation et oral `not_evaluable` non bloquant;
- lecture bornee et deterministe par `pack_revision_id`, qui retourne `None` lorsque la definition publiee est absente ou incoherente;
- tables et contraintes `0003_catalogue`, FKs `RESTRICT`, UUIDv7, checksums
  lies au contenu, statuts publies, references resolues, unicites, triggers
  d'immuabilite y compris INSERT tardif et garde de coherence du gate;
- fixture canonique `FX-CATALOGUE-IT` mise a jour avec manifeste SHA-256 et revue linguistique `pending_human` preservee.

Les routes, OpenAPI, contrats W00 et fichiers W03/W05 ne sont pas modifies par ce lot.

## TDD

- RED initial: `c78ae49 test(w04f): define published foundations contracts`.
- GREEN initial: `ee8e77f`.
- RED correctif observable avant le nouveau GREEN:
  `1ef604c test(w04f): expose foundation integrity gaps`.
- Le RED correctif a expose les gates non exactes, references non resolues,
  checksums non lies au contenu et INSERT tardif valide.

## Preuves

- `uv run pytest tests/unit/catalogue tests/property/catalogue tests/integration/catalogue tests/contract/catalogue -q`:
  `107 passed, 1 warning`.
- Domaine et fixture seuls: `60 passed`.
- Migration `0003` ciblee en PostgreSQL neuf: `34 passed`.
- Base PostgreSQL neuve et ephemere: `0003 -> 0002 -> 0003 -> head` vert.
- `uv run alembic check`: `No new upgrade operations detected.`
- Verification statique ciblee: Ruff et `git diff --check` verts;
  `mypy src`: `Success: no issues found in 56 source files`.
- Les tests de migration prouvent les droits runtime strictement SELECT, le
  refus d'INSERT tardif valide, UPDATE, DELETE et reparentage, la resolution
  des references, les checksums lies au contenu et chaque valeur exacte de gate.
- Les bases PostgreSQL de preuve ont ete supprimees automatiquement; aucune donnee partagee n'a ete detruite.

## Limites et revue

- La revue linguistique de `FX-CATALOGUE-IT` reste `pending_human` par contrat de fixture.
- Suite backend integree en base isolee, mode `--import-mode=importlib`:
  `327 passed, 2 skipped, 18 errors`.
- Onze erreurs viennent des seeds W05 qui recreent `it-IT__fr-FR` apres la
  matrice catalogue; sept viennent de l'URL de retention non fournie. Elles
  restent hors write set W04F. La matrice W04 isolee est verte.
