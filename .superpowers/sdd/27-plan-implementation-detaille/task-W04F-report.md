# W04F - Catalogue des fondations IT

## Portee livree

W04F ajoute au catalogue publie le pilote des fondations IT:

- aggregate immuable `PublishedFoundationCatalogue` avec definition, blocs, items et gate;
- cinq blocs ordonnes `F1` a `F5`, dix items `ITF-F1-01` a `ITF-F5-02`, correcteurs structurels et reponses brutes;
- gate `FOUNDATIONS_IT_V0` avec deux sessions, delai de 24 h, seuils 8/10 son, 8/10 lecture, 4/5 survie sans reveal et oral `not_evaluable` non bloquant;
- lecture bornee et deterministe par `pack_revision_id`, qui retourne `None` lorsque la definition publiee est absente ou incoherente;
- tables et contraintes `0003_catalogue`, FKs `RESTRICT`, UUIDv7, checksums, statuts publies, unicites, triggers d'immuabilite et garde de coherence du gate;
- fixture canonique `FX-CATALOGUE-IT` mise a jour avec manifeste SHA-256 et revue linguistique `pending_human` preservee.

Les routes, OpenAPI, contrats W00 et fichiers W03/W05 ne sont pas modifies par ce lot.

## TDD

- RED observable committe avant le code: `c78ae49 test(w04f): define published foundations contracts`.
- RED confirme par l'absence des types fondations et du contrat fixture avant implementation.
- GREEN: schemas domaine, persistence, migration, fixture et tests verts apres implementation.

## Preuves

- `uv run pytest tests/unit/catalogue tests/property/catalogue tests/integration/catalogue tests/contract/catalogue -q`: `48 passed, 1 warning`.
- Base PostgreSQL neuve et ephemere: `0003 -> 0002 -> 0003 -> head` vert.
- `uv run alembic check`: `No new upgrade operations detected.`
- Verification statique ciblee: Ruff vert, neuf fichiers formates, `mypy src`: `Success: no issues found in 54 source files`.
- Les tests de migration prouvent les droits runtime en lecture seule, le refus de mutation et de reparentage d'un item publie, et le refus d'un correcteur structurel incomplet.
- Les bases PostgreSQL de preuve ont ete supprimees automatiquement; aucune donnee partagee n'a ete detruite.

## Limites et revue

- La revue linguistique de `FX-CATALOGUE-IT` reste `pending_human` par contrat de fixture.
- Une revue independante reste a demander: aucun canal de delegation/revue independante n'etait disponible dans cette execution.
- Suite complete en base isolee, mode `--import-mode=importlib`: `268 passed, 1 skipped, 2 failed, 5 errors`.
  - cinq erreurs sont dans les fixtures d'integration W05 (`tests/integration/content/test_application.py`): collision sur `catalogue.language_packs.pack_code`;
  - un echec est le contrat OpenAPI courant (`tests/contract/platform/test_openapi.py`), hors perimetre W04F;
  - un echec Hypothesis de lenteur est dans `tests/property/catalogue/test_graph_properties.py` sous charge concurrente. La meme matrice W04 ciblee est verte.
