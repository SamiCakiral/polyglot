# W06 - ultime revue independante

Date : 2026-08-10  
Revision revue : `c4394c4e6566f20d5b472916b0edf40ab2bc8c64`  
Perimetre : fermeture du finding OpenAPI de
`task-W06-acceptance-review.md`.  
Verdict : **PASS technique**. `P-LING` reste `pending_human` et ne bloque pas
l'acceptation technique de W06.

## Finding precedent

Le finding unique etait l'absence des routes W06 dans l'ensemble exact attendu
par le test contractuel global OpenAPI. Le snapshot OpenAPI etait deja courant.

Le commit `c4394c4` ferme ce finding :

- il ne modifie que
  `backend/tests/contract/platform/test_openapi.py` ;
- il renomme le test pour annoncer explicitement la surface W01 a W06 ;
- il ajoute les 16 routes W06 absentes de l'attente precedente ;
- il ne retire aucune route et ne modifie ni le snapshot ni le runtime.

## Verification fraiche

La revision exacte a ete reconstruite depuis les objets Git dans
`/tmp/polyglot-w06-final-review`, car les fichiers du worktree Documents sont
decharges par macOS. Les tests ont utilise Python 3.13.11 depuis
`/tmp/polyglot-global-matrix-src/backend/.venv`, avec un `PYTHONPATH` absolu
vers la copie revue.

Commande executee :

```text
PYTHONPATH=/tmp/polyglot-w06-final-review/backend/src \
  /tmp/polyglot-global-matrix-src/backend/.venv/bin/python -m pytest \
  tests/contract/platform/test_openapi.py -vv --tb=short
```

Resultat :

```text
4 passed in 1.51s
```

Les quatre controles passent, y compris :

- l'ensemble exact des routes W01 a W06 ;
- les modeles, en-tetes de securite et erreurs RFC 9457 ;
- le rejet des contrats incomplets par le registre ;
- le caractere deterministe et courant du snapshot versionne.

## Concordance exacte des routes

Une extraction structurelle independante a compare l'ensemble litteral du
test, `contracts/openapi/v1.json` et le document produit par
`create_app(test_mode=True).openapi()` :

```text
expected=48 snapshot=48 runtime=48
expected==snapshot: True
expected==runtime: True
snapshot==runtime: True
```

Les quatre differences directionnelles sont vides. Entre le parent de
`c4394c4` et sa revision, le test passe de 32 a 48 routes : 16 ajouts W06 et
zero suppression. Le correctif couvre donc exactement toute la surface du
snapshot sans elargissement parasite.

## Decision

Le seul blocage technique identifie par la revue precedente est ferme. Les
preuves W06 deja acceptees pour les 58 tests PostgreSQL non privilegies, les
roles, RLS, IDOR, les projections WB-01 a WB-12 et les performances restent
applicables ; aucune recharge du corpus 100k n'etait requise.

W06 est **accepte techniquement**. La revue linguistique `P-LING` demeure une
validation humaine ulterieure et distincte.

Aucun code produit n'a ete modifie. Aucun commit ni push n'a ete effectue.
