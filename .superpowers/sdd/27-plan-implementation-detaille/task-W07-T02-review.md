# W07-T02 - Revue indépendante initiale

## Révision relue

- RED : `8cc2a6a`.
- GREEN : `f43d32d`.
- Revue read-only exécutée depuis `/tmp/polyglot-w07-t02-review`.
- Vérification ciblée : `21 passed`, Ruff et mypy strict passés.

## Verdict

`FAIL` technique.

## Findings W07 retenus

1. `P0` : la certification était déclarative et non reliée à l'opération, au
   protocole et à la révision de cible épinglés par le prompt.
2. `P0` : le rebuild utilisait un unique scheduler et une unique politique
   fournis par l'appelant au lieu de résoudre les versions persistées par fait.
3. `P1` : resume et restore recalculaient la due sans fait append-only rejouable.
4. `P1` : la fusion rejouait uniquement les reviews puis attachait les resets,
   ce qui pouvait produire une projection différente du rebuild.
5. `P1` : l'ordre à instant égal dépendait des UUID et ignorait le checkpoint.
6. `P1` : une review backdatée pouvait être acceptée dans l'ordre de soumission
   puis rejouée dans un autre ordre.
7. `P1` : les invariants d'appartenance, de chronologie, d'identité moteur et de
   compteurs des faits étaient incomplets.
8. `P2` : les propriétés suspension, reprise, fusion avec reset/déduplication,
   transitions interdites, ordre à instant égal, versions de politique et
   directions après fusion manquaient.

## Finding exclu

Le finding W11 hors périmètre est un faux positif produit par les commits W11
intercalés dans le worktree partagé. Aucun fichier W11 n'est attribuable aux
commits W07-T02 et aucun fichier W11 ne sera modifié par la correction.

## Suite exigée

Correction TDD RED/GREEN complète, matrice élargie et nouvelle revue
indépendante avant W07-T03.
