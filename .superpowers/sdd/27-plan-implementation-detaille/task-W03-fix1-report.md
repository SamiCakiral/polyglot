# W03 - Fix round 1

## Verdict

**PASS W03.** Tous les constats de la revue independante ont un correctif et
une preuve automatisee dans le perimetre W03.

## Constats fermes

| Revue | Correctif | Preuve |
|---|---|---|
| Gate fondations absente | Parcours F1-F5, deux sessions, controle differe, decisions append-only, transition active et event/outbox atomiques | Contrat PostgreSQL complet et 20 mesures persistantes |
| Placement forgeable | Corps client limite a la reponse brute; item, cible, score, confiance et evaluabilite derives du contenu W04F | Requete forgee 422 et correcteurs deterministes |
| Expiration non persistante | Expiration transactionnelle avant redemarrage diagnostic/fondations | P-RETOUR, ancien run `expired`, nouvel ID |
| Concurrence HTTP incomplete | ETag sur ressources, If-Match, 428, version attendue et 409 stale | Tests HTTP et OpenAPI |
| References W04 absentes | Injection stricte du `CatalogueReader` publie; pack/fondation/item verifies | `foundation_pack_missing` et `diagnostic_unavailable` |
| Fixtures/couverture absentes | FX-PERSONAS, FX-IT-FOUND, integration, contrat et propriete | Hashes offline et 30 tests W03 verts |

## Commits RED/GREEN du round

- `74efd1a` RED placement client; `8f0a30c` GREEN evaluation serveur.
- `db2b370`, `8ac878a` RED parcours/gate; `c7b9f4b` GREEN fondations W04F.
- `07f4a60` RED expiration; `943168a` GREEN reprise persistante.
- `82323d1` RED fixtures; `782929c` GREEN bundles offline.
- `5509720` RED OpenAPI; `64a6001` GREEN ETag/concurrence.
- `33842c8` RED pack diagnostic; `9a47828` GREEN verification W04F.
- `69623ce` ajoute la preuve de propriete de la borne 24 h.

## Verification

```text
W03 targeted                         30 passed in 4.26s
Ruff W03                            All checks passed
mypy strict W03                     Success: 9 source files
Alembic 0005 -> 0003 -> head        passed
Alembic check                       No new upgrade operations detected
OpenAPI --check                     passed
```

La base utilisee etait une instance PostgreSQL 17 dediee. Les clones `/tmp`
crees pour ce round ont ete nettoyes; l'arret Compose a ete demande, mais le
daemon Docker ne repondait plus apres saturation du disque. Les deux
duplicatas `language_profiles 2.py` ont ete compares, declares obsoletes puis
supprimes; aucun fichier ` 2.py` ne subsiste.

## Ecart global hors W03

La matrice backend monolithique n'est pas verte pour des causes de harness
inter-domaines et d'environnement : collisions de noms de tests, contamination
catalogue/content, variables retention absentes et disque plein. Elle a atteint
331 tests passes avant ces echecs. Aucune de ces causes n'est masquee comme une
preuve W03; la matrice W03 isolee et la migration fraiche sont vertes.

## Livraison Git

Commits locaux uniquement sur `codex/v2-rebuild`. Aucun push.
