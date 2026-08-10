# W04 - Rapport de correction

## Perimetre

Correction exclusive du catalogue W04 apres le verdict `FAIL` de
`task-W04-review.md`. Aucun fichier frontend ou CI W17 n'a ete modifie ni
stage par cette correction.

## Corrections apportees

1. Les enfants d'une revision publiee sont desormais immuables en PostgreSQL :
   varietes d'appui de pack, moules grammaticaux, analyses de forme,
   realisations forme-sens et composants d'expressions. Les tests couvrent
   `UPDATE` et `DELETE` pour chaque famille.
2. Les mutations `required` du DAG prennent un verrou consultatif de
   transaction. Le controle de cycle utilise une exploration iterative bornee
   a 64 profondeurs et 4096 noeuds, avec refus explicite en cas de budget
   depasse. Le test concurrent prouve qu'une seconde insertion antagoniste
   attend la premiere transaction puis est rejetee.
3. PostgreSQL verifie la coherence des realisations : une analyse et sa
   realisation partagent l'unite, un sens appartient a cette unite et la meme
   revision de pack. Les composants MWE exigent une racine MWE et partagent
   pack et variete avec leur composant.
4. La recherche lexicale page les analyses dans une CTE SQL avec curseur et
   `LIMIT limit + 1`, puis agrege les sens de la page seulement.
5. Les fixtures referencent les composants MWE par `unit_revision_id` et
   lemme. Le validateur ferme les cibles de competences, les statuts publies
   imbriques, les identifiants et les references de composants. Des fixtures
   hostiles couvrent reference absente, sens non publie, composant absent et
   identifiant duplique.
6. La validation des stable codes est identique dans le domaine, la migration
   et les metadonnees SQLAlchemy.
7. La garde d'immuabilite des enfants controle desormais, lors d'un `UPDATE`,
   les proprietaires `OLD` avant le reparentage puis les proprietaires `NEW`.
   Un enfant d'une revision publiee ne peut donc plus etre deplace vers une
   revision brouillon. `DELETE` continue de verifier `OLD` et `INSERT` verifie
   `NEW`. Les cinq familles enfant sont couvertes.

## Preuves locales

- RED : commit `eb94b2c` avec les regressions W04, echec attendu avant les
  corrections.
- RED relecture : commit `02db7e5`; les cinq tests de reparentage publie vers
  brouillon echouaient avec `DID NOT RAISE DBAPIError` avant la correction.
- Test cible de reparentage : `5 passed in 0.60s`.
- `uv run pytest tests/unit/catalogue tests/property/catalogue
  tests/integration/catalogue tests/contract/catalogue -q` : `40 passed`,
  `1 warning` connu, en `2.67s`.
- `uv run ruff check src tests` : passe.
- `uv run mypy src` : passe, 43 fichiers source.
- Round-trip reel : `0003_catalogue -> 0002_identity -> 0003_catalogue`.
- `uv run alembic check` : aucune operation de migration nouvelle.
- `uv run alembic current` : `0003_catalogue (head)`.

## Limites

La revue linguistique humaine de la fixture italienne reste explicitement
`pending_human`. Cette correction ne revendique aucun statut `P-LING`.
