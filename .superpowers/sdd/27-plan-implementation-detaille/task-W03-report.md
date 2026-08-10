# W03 - Rapport d'implementation consolide

## Statut

**COMPLETE apres fix round 2.** Les constats de `task-W03-review.md` et
`task-W03-rereview.md` sont corriges dans le write set W03. Aucun code W05 ou
frontend n'a ete modifie.

## Livraison

- Le diagnostic refuse les signaux normatifs client, verifie le pack publie
  via `CatalogueReader`, verifie l'item et l'ordinal, puis derive score,
  confiance, facette et evaluabilite depuis le correcteur W04F.
- Les modalites sans correcteur sont persistees `not_evaluable`; elles ne
  produisent ni succes, ni echec, ni credit implicite.
- P-RETOUR reprend exactement le meme run avant 24 heures sans insertion. A
  l'echeance, une soumission tardive persiste `expired`; un nouveau depart
  expire aussi l'ancien run avant de creer un nouveau snapshot.
- Un run fondations epingle la definition publiee et materialise F1-F5. Les
  mesures par item et session sont append-only et derivees par le backend.
- Chaque evaluation de gate est append-only. Le passage exige deux sessions,
  deux controles F1 separes d'au moins 24 heures, exactement 8/10
  discriminations, 8/10 lectures ciblees et 4/5 echanges sans revelation.
- La decision finale, la transition `foundations -> active`, l'evenement
  `foundation_gate_completed` et son message outbox partagent une transaction.
- Toutes les ressources et transitions exposent leur `ETag`; `If-Match` est
  obligatoire et non nullable dans OpenAPI, son absence retourne 428 et une
  version obsolete retourne le conflit canonique.
- `FX-PERSONAS` couvre P-ABS, P-FAUX, P-INT et P-RETOUR. `FX-IT-FOUND` couvre
  F1-F5, la borne 24 h, l'audio absent et la revelation. Les deux bundles sont
  hashes, offline et sans credit implicite.

## Verification finale

Executee le 10 aout 2026 depuis `/tmp/polyglot-w03-final-20260810-2` contre
une instance PostgreSQL 17 dediee et une base reconstruite.

- Tests W03 unitaires, proprietes, integration et contrat : **37 passed**.
- Ruff W03 : **passed**.
- mypy strict : **Success, 64 source files**.
- Alembic `head -> base -> head` sur PostgreSQL 17.10 frais : **passed**.
- `alembic check` : **No new upgrade operations detected**.
- Export OpenAPI `--check` : **passed**.
- Test de propriete : aucune combinaison de scores ne contourne 24 heures.
- PostgreSQL reel : RLS, append-only, transaction, outbox et reprise exerces.

## Matrice backend

La commande agregee `pytest tests` n'est pas un gate vert fiable dans l'etat
du depot : sans `--import-mode=importlib`, elle collisionne sur plusieurs noms
de modules de test. Avec ce mode, elle atteint **331 passed**, puis les suites
catalogue/content se contaminent via deux IDs differents pour le meme
`pack_code`; les tests retention manquent leurs variables de connexion et les
tests de restauration ont rencontre un disque systeme plein. Ces echecs sont
hors W03 et reproductibles sans changement W03. La matrice cible W03 reste
entierement verte sur base fraiche.

## Limites

- Aucun niveau CECR, aucune maitrise W13 et aucune preuve pedagogique implicite.
- Aucun STT, professeur permanent, exercice W09 ou frontend.
- La revue linguistique des fixtures reste `pending_human`.
- Aucun push n'a ete effectue.
