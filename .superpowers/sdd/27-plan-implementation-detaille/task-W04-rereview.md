# Rerevue independante W04

## Verdict

**FAIL**

Le correctif `5362a0f` ferme la quasi-totalite des constats du rapport initial et
la suite W04 passe. Il reste cependant un contournement direct de l'immutabilite
des enfants d'une revision publiee. Cette condition faisait partie des conditions
minimales de PASS ; W04 ne peut donc pas encore etre accepte.

## Perimetre

Rerevue read-only de l'etat commite `5362a0f`, apres le commit RED `eb94b2c`.
Les changements W17 interleaves ont ete ignores. La grille de controle est celle
de `task-W04-review.md` : immutabilite des enfants, DAG concurrent et borne,
coherences lexicales, pagination SQL, fixture, stable codes et migration 0003.

## Constat bloquant

### Critical - un enfant publie peut etre deplace vers une revision brouillon

`catalogue.guard_published_child()` construit `related_revisions` avec les
valeurs `NEW` pour toute operation autre que `DELETE`
(`backend/migrations/versions/0003_catalogue.py:481-519`). Lors d'un `UPDATE`,
la garde ne controle donc pas le proprietaire `OLD`.

Un auteur SQL peut ainsi :

1. creer une revision brouillon compatible ;
2. changer la cle de rattachement d'un enfant appartenant a une revision
   publiee pour le rattacher a cette revision brouillon ;
3. modifier ou supprimer ensuite cet enfant.

Le contournement concerne les cinq familles protegees :

- `language_pack_support_varieties.pack_revision_id` ;
- `grammar_patterns.structure_revision_id` ;
- `form_analyses.unit_revision_id` ;
- les rattachements de `form_realizations` ;
- les rattachements de `expression_components`.

Les tests parametrises ajoutes dans
`backend/tests/integration/catalogue/test_migration_0003.py:171-218` executent
des `UPDATE` sans changement de proprietaire (`SET template = template`, etc.)
et des `DELETE`. Ils prouvent la mutation en place et la suppression, mais pas
le reparentage. Ils passent donc malgre ce contournement.

La correction minimale est de verifier l'ensemble des revisions possedees par
`OLD` **et** `NEW` pour `UPDATE`, avec un test PostgreSQL de reparentage pour
chaque famille. Toute revision publiee presente d'un cote ou de l'autre doit
faire rejeter l'operation.

## Conditions du FAIL initial maintenant satisfaites

- **DAG concurrent : conforme.** Les insertions/mutations `required` prennent
  un verrou consultatif transactionnel commun. Le test concurrent attend la
  premiere transaction puis rejette l'arete antagoniste.
- **DAG borne : conforme.** Le controle PostgreSQL refuse au-dela de 64 niveaux
  ou 4096 noeuds avec `prerequisite_graph_limit`, au lieu d'une CTE recursive
  sans budget.
- **Coherence forme/unite/sens : conforme.** Les triggers imposent l'unite de
  l'analyse, l'appartenance du sens et la revision de pack.
- **Coherence MWE : conforme.** La racine doit etre une
  `multiword_expression`; racine et composants partagent pack et variete.
- **Pagination lexicale : conforme.** La selection des analyses applique le
  curseur et `LIMIT limit + 1` dans la CTE SQL, puis agrege tous les sens des
  seules analyses selectionnees.
- **Fixture : conforme sur la grille demandee.** Les references de cibles, les
  statuts imbriques, les identifiants globaux, les codes et les composants par
  `unit_revision_id` sont valides. Les cas hostiles ajoutes couvrent reference
  absente, sens non publie, composant absent et identifiant duplique. Le cycle
  negatif canonique reste rejete hors reseau.
- **Stable codes : conforme.** Le domaine et PostgreSQL appliquent le meme
  contrat ASCII aux codes concernes.
- **Migration 0003 : conforme d'apres les preuves disponibles.** Le rapport de
  correction documente `0003 -> 0002 -> 0003`, `alembic check` sans derive et
  `0003_catalogue (head)`. La tentative de repetition pendant cette rerevue a
  ete interrompue avant restitution complete ; aucun echec de migration n'a ete
  observe.

## Preuves d'execution

- Suite cible W04 executee pendant la rerevue : **35 passed**, 1 avertissement
  de deprecation Starlette/httpx, en 2,16 s.
- Preuve independante fournie apres clone exact de `5362a0f` : suite backend
  complete **212 passed**, 1 avertissement, en 19,90 s.
- Le rapport RED/GREEN et les tests ont ete inspectes ; aucun changement de code
  n'a ete effectue par la revue.

## Condition unique de PASS restante

Pour toute table enfant, un `UPDATE` doit verifier les proprietaires `OLD` et
`NEW`. Ajouter les regressions de reparentage correspondantes, puis relancer la
suite W04, la suite backend complete et le round-trip Alembic. Aucun autre
blocage du rapport initial ne subsiste dans le perimetre examine.
