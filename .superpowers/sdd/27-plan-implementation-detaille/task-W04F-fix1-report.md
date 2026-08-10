# W04F - Correctif revue round 1

## Statut

Tous les constats P1/P2 de `task-W04F-review.md` sont clos dans le write set
W04F. Les routes, OpenAPI, contrats W00 et sources W03/W05 restent inchanges.

## TDD RED/GREEN

- RED committe avant correction: `1ef604c test(w04f): expose foundation integrity gaps`.
- Domaine/fixture RED: `21 failed, 6 passed`; les gates non exactes, references
  absentes et checksums falsifies etaient acceptes.
- PostgreSQL RED sur bases ephemeres: `11 failed`; un INSERT tardif distinct,
  structurellement valide et muni d'un checksum valide etait accepte.
- GREEN: implementation, fixture et preuves PostgreSQL ci-dessous sont vertes.

## Cloture des constats

### Gate exacte

`PublishedFoundationGate`, la fixture et `0003_catalogue` expriment chaque
regle separement: les cinq facettes exactes au statut `reliable`, couverture
`1.0`, confiance `0.6`, exactement deux sessions, controle F1 a 24 h, 8/10
grapheme-son, 8/10 lecture ciblee, 4/5 survie sans revelation et oral sans
correcteur `not_evaluable_non_blocking`. Les valeurs valides de forme mais non
contractuelles sont exercees au domaine, par fixture et en PostgreSQL.

### References resolues

Le catalogue publie 19 references versionnees et typees `target`, `facet` ou
`waiver_policy`. L'agregat exige l'ensemble exact des references utilisees,
leur type, leur pack et leur statut publie. La migration impose unicite,
UUIDv7, FK `RESTRICT`, statut, checksum et triggers de resolution pour les
blocs, items et gate. La fixture couvre les absences reelles de chaque type.

### Checksums lies au contenu

Les revisions definition, reference, bloc, item et gate utilisent une
serialisation canonique partagee Python/PostgreSQL et un SHA-256 recalcule a
la construction ou a l'ecriture SQL. Une mutation de contenu et un checksum
forge mais bien forme sont refuses.

### Immuabilite et runtime

Les INSERT tardifs de definition, reference, bloc ou item sont refuses des
qu'une gate publiee scelle l'agregat. Le test PostgreSQL exerce un nouvel item
entierement valide. UPDATE, DELETE et reparentage d'un item publie sont refuses.
Toutes les tables de fondations accordent uniquement SELECT a
`polyglot_runtime`; INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES et TRIGGER sont
explicitement testes absents.

## Preuves finales

- Domaine et fixture: `60 passed`.
- Migration `0003` ciblee: `34 passed` sur PostgreSQL neuf.
- Round-trip isole: `0003 -> 0002 -> 0003 -> head` vert.
- `alembic check`: `No new upgrade operations detected.`
- Matrice W04: `107 passed, 1 warning`.
- Ruff cible: vert; `mypy src`: `Success: no issues found in 56 source files`;
  `git diff --check`: vert.
- Chaque base de preuve a ete creee sous un nom W04F unique puis supprimee avec
  connexions forcees; la base partagee `polyglot` n'a pas ete tronquee.

## Limites

- La revue linguistique reste `pending_human`, conformement au contrat.
- La suite backend integree en mode importlib donne `327 passed, 2 skipped,
  18 errors`: 11 collisions de seed W05 sur `language_packs.pack_code` apres
  les tests catalogue et 7 erreurs plateforme faute d'URL de retention. Ces
  erreurs sont hors write set W04F; la matrice W04 isolee est verte.
