# W04F - Correctif checksum round 2

## Statut

Le constat checksum bloquant de `task-W04F-rereview.md` est ferme dans le
write set W04F. Aucun fichier W03, W05, W00, route ou contrat OpenAPI n'est
modifie par ce correctif.

## TDD RED/GREEN

- RED: `29c5697 test(w04f): expose checksum list collision`.
- Python RED: `("alpha\x1ebeta",)` et `("alpha", "beta")` produisaient le
  meme SHA-256 `5385cf019017c7a124dfcf64b9fc09c651dc8daed228a81a90588d19504dd4df`.
- PostgreSQL RED: un item contenant une seule valeur avec `0x1e` et le
  checksum de deux valeurs distinctes etait accepte (`DID NOT RAISE`).
- GREEN: les deux tests passent avec la serialisation canonique V2.

## Protocole canonique

Le payload SHA-256 est un JSON canonique UTF-8 sans espaces, compose de
tableaux ordonnes. Chaque valeur normative porte un type explicite:

- `uuid` et `string` conservent leur valeur textuelle echappee JSON;
- `integer` et `decimal` utilisent une forme textuelle normalisee;
- `boolean` conserve sa valeur JSON native;
- `array` conserve sa structure, sa cardinalite implicite et l'ordre exact de
  ses elements, chacun encode recursivement.

L'enveloppe `foundation-checksum-v2` lie aussi le type de revision et l'ordre
des champs. La structure JSON rend non ambigus les separateurs embarques,
listes vides, cardinalites, types scalaires et permutations.

## Alignement des trois frontieres

- Domaine: `foundation_content_checksum` construit le JSON type et calcule le
  SHA-256.
- Fixture: les 36 checksums de definition, references, blocs, items et gate
  sont recalcules depuis tous leurs champs normatifs; le chargeur domaine les
  revalide.
- PostgreSQL: des encodeurs SQL types construisent les memes fragments JSON;
  chaque branche du trigger fournit explicitement tous les champs normatifs
  dans le meme ordre que le domaine.

La matrice d'insertion PostgreSQL seme avec les checksums calcules en Python les
cinq familles de revisions. Elle prouve ainsi l'identite Python/SQL pour UUID,
chaines, entiers, decimaux, booleens, listes vides et listes ordonnees. Le cas
collisionnel avec caractere de controle est refuse.

## Fixture et manifeste

- `36/36` checksums de revisions recalcules et verifies.
- SHA-256 de `catalogue.json`:
  `9c178b39c5d2c0966fbb7f301a2bd469d231972d424df98775a27d8f80132aad`.
- `fixture-metadata.json` mis a jour; revue linguistique conservee a
  `pending_human`.

## Preuves finales

- Domaine et fixture: `61 passed`.
- Base PostgreSQL isolee: `0003 -> 0002 -> 0003 -> head` vert.
- `alembic check`: `No new upgrade operations detected.`
- Matrice W04F: `109 passed, 1 warning`.
- Ruff cible, `mypy src` et `git diff --check`: verts.
- Toutes les bases `w04f_fix2_*` ont ete supprimees automatiquement; aucune
  donnee de la base partagee `polyglot` n'a ete tronquee.

## Limites

- La revue linguistique reste `pending_human` par contrat.
- Le protocole V2 est un changement de hash volontaire: toute fixture ou
  publication externe utilisant l'ancien protocole doit recalculer ses
  checksums avant import. Dans ce repository, seule `FX-CATALOGUE-IT` porte ces
  revisions W04F.
